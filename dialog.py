# -*- coding: utf-8 -*-
"""
dialog.py — GeoCAR Suite
Interface principal com todas as abas.
Autor: Miguel A. L. Ferreira
"""

import os
import logging
from datetime import datetime
from pathlib import Path

from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QLineEdit, QProgressBar, QTextEdit, QFileDialog, QGroupBox,
    QTabWidget, QWidget, QTableWidget, QTableWidgetItem,
    QHeaderView, QFrame, QMessageBox, QScrollArea, QComboBox,
    QCheckBox, QSizePolicy
)
from qgis.PyQt.QtCore import Qt, QThread, pyqtSignal
from qgis.PyQt.QtGui import QColor, QTextCursor, QFont, QPixmap

log = logging.getLogger("GeoCAR_Suite")


# ═══════════════════════════════════════════════════════════════
# WORKERS
# ═══════════════════════════════════════════════════════════════

class WorkerCAR(QThread):
    sinal_log       = pyqtSignal(str, str)
    sinal_progresso = pyqtSignal(int, str)
    sinal_resultado = pyqtSignal(str, bool, dict)
    sinal_fim       = pyqtSignal(dict)

    def __init__(self, lista_cars, config, iface):
        super().__init__()
        self.lista_cars      = lista_cars
        self.config          = config
        self.iface           = iface
        self._cancelar       = False
        self._resultados_lote = []

    def cancelar(self): self._cancelar = True

    def run(self):
        from .processing.api_client        import buscar_imovel_completo, baixar_demonstrativo
        from .processing.geojson_processor import processar_geojson
        from .processing.gpkg_exporter     import exportar_gpkg
        from .processing.excel_exporter    import exportar_excel
        from .processing.sobreposicao      import (
            calcular_sobreposicoes, formatar_para_relatorio, NOMES_EXIBICAO
        )

        total = len(self.lista_cars)
        gdfs  = []
        resultados = []
        erros = []

        self.sinal_log.emit(f"Iniciando: {total} CAR(s)...", "info")

        for i, item in enumerate(self.lista_cars):
            if self._cancelar:
                self.sinal_log.emit("Cancelado.", "aviso"); break

            codigo_car = item["codigo_car"]
            pct = int((i / total) * 90)
            self.sinal_progresso.emit(pct, f"[{i+1}/{total}] {codigo_car[:34]}...")
            self.sinal_log.emit(f"[{i+1}/{total}] {codigo_car}", "info")

            linha = {
                "codigo_car": codigo_car, "uf":"", "cod_ibge":"",
                "municipio":"", "area_ha":"", "status":"erro", "erro":"",
                "demonstrativo_pdf":"",
                "sobr_uc_federal_sim_nao":"NÃO",    "sobr_uc_federal_ha":0.0,
                "sobr_uc_estadual_sim_nao":"NÃO",   "sobr_uc_estadual_ha":0.0,
                "sobr_terra_indigena_sim_nao":"NÃO","sobr_terra_indigena_ha":0.0,
                "sobr_prodes_sim_nao":"NÃO",        "sobr_prodes_ha":0.0,
                "sobr_assentamento_sim_nao":"NÃO",  "sobr_assentamento_ha":0.0,
                "sobr_quilombo_sim_nao":"NÃO",      "sobr_quilombo_ha":0.0,
                "sobr_embargo_ibama_sim_nao":"NÃO", "sobr_embargo_ibama_ha":0.0,
                "sobr_sigef_sim_nao":"NÃO",         "sobr_sigef_ha":0.0,
                "prodes_anos_detalhe":"",
            }

            # Passo 1: API
            ok, dados = buscar_imovel_completo(codigo_car, timeout=self.config.get("timeout",30))
            if not ok:
                self.sinal_log.emit(f"  ✗ {dados}", "erro")
                linha["erro"] = str(dados)
                resultados.append(linha)
                erros.append(codigo_car)
                self.sinal_resultado.emit(codigo_car, False, linha)
                continue

            self.sinal_log.emit(f"  _id: {dados['id']}", "info")

            # Passo 2: GeoJSON
            ok, gdf = processar_geojson(codigo_car, dados["geojson"])
            if not ok:
                self.sinal_log.emit(f"  ✗ {gdf}", "erro")
                linha["erro"] = str(gdf)
                resultados.append(linha)
                erros.append(codigo_car)
                self.sinal_resultado.emit(codigo_car, False, linha)
                continue

            area = gdf["area_ha"].iloc[0]
            mun  = gdf["municipio"].iloc[0]
            self.sinal_log.emit(f"  ✓ {mun} | {area:.2f} ha", "ok")

            # Passo 2.5: Demonstrativo PDF (opcional)
            if self.config.get("baixar_demonstrativo", False):
                ok_pdf, pdf_res = baixar_demonstrativo(dados["id"], timeout=self.config.get("timeout",30))
                if ok_pdf:
                    try:
                        demo_dir = Path(self.config["demonstrativos_dir"])
                        demo_dir.mkdir(parents=True, exist_ok=True)
                        nome_pdf = codigo_car.replace("/","_") + ".pdf"
                        cam_pdf  = demo_dir / nome_pdf
                        cam_pdf.write_bytes(pdf_res)
                        self.sinal_log.emit(f"  ✓ PDF: {nome_pdf}", "ok")
                        linha["demonstrativo_pdf"] = str(cam_pdf)
                    except Exception as e:
                        self.sinal_log.emit(f"  ⚠ PDF salvo: {e}", "aviso")
                else:
                    self.sinal_log.emit(f"  ⚠ PDF: {pdf_res}", "aviso")

            # Passo 3: Sobreposições
            if self.config.get("calcular_sobreposicoes", True):
                self.sinal_log.emit("  Calculando sobreposições...", "info")
                try:
                    sobr = calcular_sobreposicoes(gdf)
                    campos = formatar_para_relatorio(sobr)
                    linha.update(campos)
                    for k, v in campos.items(): gdf[k] = v
                    hits = [NOMES_EXIBICAO.get(b,b) for b,r in sobr.items() if r.get("sobrepoe")]
                    if hits:
                        self.sinal_log.emit(f"  ⚠ {', '.join(hits)}", "aviso")
                        if sobr.get("prodes",{}).get("anos_lista"):
                            self.sinal_log.emit(f"    PRODES: {sobr['prodes']['anos_lista']}", "aviso")
                    else:
                        self.sinal_log.emit("  ✓ Sem sobreposições", "ok")
                except Exception as e:
                    self.sinal_log.emit(f"  ⚠ Sobreposição: {e}", "aviso")

            linha.update({
                "uf":gdf["uf"].iloc[0], "cod_ibge":gdf["cod_ibge"].iloc[0],
                "municipio":mun, "area_ha":area, "status":"ok", "erro":"",
            })
            gdfs.append(gdf)
            resultados.append(linha)
            self.sinal_resultado.emit(codigo_car, True, linha)

        # Exportar GeoPackage
        self.sinal_progresso.emit(93, "Gerando GeoPackage...")
        gpkg_ok = False
        if gdfs:
            ok, msg = exportar_gpkg(gdfs, self.config["gpkg_path"])
            gpkg_ok = ok
            self.sinal_log.emit(f"GeoPackage: {'✓ ' if ok else '✗ '}{msg}", "ok" if ok else "erro")

        # Exportar Excel
        self.sinal_progresso.emit(96, "Gerando relatório Excel...")
        if resultados:
            ok, msg = exportar_excel(resultados, self.config["xlsx_path"])
            self.sinal_log.emit(f"Excel: {'✓ ' if ok else '✗ '}{msg}", "ok" if ok else "erro")

        self._resultados_lote = resultados

        self.sinal_progresso.emit(100, "Concluído!")
        self.sinal_fim.emit({
            "total":total, "sucesso":len(gdfs), "erro":len(erros),
            "erros":erros,
            "gpkg":self.config["gpkg_path"] if gpkg_ok else "",
            "xlsx":self.config["xlsx_path"],
            "carregar_qgis": gpkg_ok and self.config.get("carregar_qgis",True),
        })


class WorkerConsulta(QThread):
    sinal_log       = pyqtSignal(str, str)
    sinal_concluido = pyqtSignal(bool, dict)

    def __init__(self, codigo_car, timeout=30):
        super().__init__()
        self.codigo_car = codigo_car
        self.timeout    = timeout

    def run(self):
        from .processing.api_client        import buscar_imovel_completo
        from .processing.geojson_processor import processar_geojson
        from .processing.sobreposicao      import calcular_sobreposicoes, NOMES_EXIBICAO

        self.sinal_log.emit(f"Consultando {self.codigo_car}...", "info")
        ok, dados = buscar_imovel_completo(self.codigo_car, self.timeout)
        if not ok:
            self.sinal_log.emit(f"✗ {dados}", "erro")
            self.sinal_concluido.emit(False, {"erro": str(dados)})
            return

        self.sinal_log.emit(f"_id: {dados['id']}", "info")
        ok, gdf = processar_geojson(self.codigo_car, dados["geojson"])
        if not ok:
            self.sinal_log.emit(f"✗ {gdf}", "erro")
            self.sinal_concluido.emit(False, {"erro": str(gdf)})
            return

        res = {
            "codigo_car": self.codigo_car, "id_car": dados["id"],
            "uf": gdf["uf"].iloc[0], "cod_ibge": gdf["cod_ibge"].iloc[0],
            "municipio": gdf["municipio"].iloc[0], "area_ha": gdf["area_ha"].iloc[0],
            "sobreposicoes": {}, "erro": "",
        }
        self.sinal_log.emit(f"✓ {res['municipio']} | {res['area_ha']:.2f} ha", "ok")

        self.sinal_log.emit("Calculando sobreposições...", "info")
        try:
            sobr = calcular_sobreposicoes(gdf)
            for bid, r in sobr.items():
                nome = NOMES_EXIBICAO.get(bid, bid)
                res["sobreposicoes"][nome] = r
                if r.get("sobrepoe"):
                    extra = f" ({r['anos_lista']})" if bid == "prodes" and r.get("anos_lista") else ""
                    self.sinal_log.emit(f"  ⚠ {nome}: {r['area_ha']:.2f} ha{extra}", "aviso")
            if not any(r.get("sobrepoe") for r in sobr.values()):
                self.sinal_log.emit("  ✓ Sem sobreposições", "ok")
        except Exception as e:
            self.sinal_log.emit(f"  ⚠ {e}", "aviso")

        self.sinal_concluido.emit(True, res)


class WorkerDemonstrativo(QThread):
    sinal_log       = pyqtSignal(str, str)
    sinal_progresso = pyqtSignal(int, str)
    sinal_item      = pyqtSignal(str, bool, str)
    sinal_fim       = pyqtSignal(dict)

    def __init__(self, lista_cars, pasta_saida, timeout=30):
        super().__init__()
        self.lista_cars  = lista_cars
        self.pasta_saida = pasta_saida
        self.timeout     = timeout
        self._cancelar   = False

    def cancelar(self): self._cancelar = True

    def run(self):
        from .processing.api_client import buscar_id_car, baixar_demonstrativo
        total = len(self.lista_cars)
        sucesso = 0
        erros   = []
        Path(self.pasta_saida).mkdir(parents=True, exist_ok=True)

        for i, codigo_car in enumerate(self.lista_cars):
            if self._cancelar:
                self.sinal_log.emit("Cancelado.", "aviso"); break

            pct = int((i / total) * 100)
            self.sinal_progresso.emit(pct, f"[{i+1}/{total}] {codigo_car[:34]}...")
            self.sinal_log.emit(f"[{i+1}/{total}] {codigo_car}", "info")

            ok, id_car = buscar_id_car(codigo_car, self.timeout)
            if not ok:
                self.sinal_log.emit(f"  ✗ {id_car}", "erro")
                erros.append(codigo_car)
                self.sinal_item.emit(codigo_car, False, str(id_car)); continue

            ok, pdf = baixar_demonstrativo(id_car, self.timeout)
            if not ok:
                self.sinal_log.emit(f"  ✗ {pdf}", "erro")
                erros.append(codigo_car)
                self.sinal_item.emit(codigo_car, False, str(pdf)); continue

            try:
                nome    = codigo_car.replace("/","_") + ".pdf"
                caminho = Path(self.pasta_saida) / nome
                caminho.write_bytes(pdf)
                self.sinal_log.emit(f"  ✓ {nome}", "ok")
                sucesso += 1
                self.sinal_item.emit(codigo_car, True, str(caminho))
            except Exception as e:
                self.sinal_log.emit(f"  ✗ {e}", "erro")
                erros.append(codigo_car)
                self.sinal_item.emit(codigo_car, False, str(e))

        self.sinal_progresso.emit(100, "Concluído!")
        self.sinal_fim.emit({"total":total,"sucesso":sucesso,"erro":len(erros),"pasta":self.pasta_saida})


# ═══════════════════════════════════════════════════════════════
# DIÁLOGO PRINCIPAL
# ═══════════════════════════════════════════════════════════════

class GeoCARDialog(QDialog):

    def __init__(self, iface):
        super().__init__(iface.mainWindow())
        self.iface  = iface
        self.worker = None
        self._ultimo_car_consultado = ""
        self._dashboard_ref = None

        self.setWindowTitle("GeoCAR Suite")
        self.setMinimumSize(980, 720)
        self.resize(1040, 760)
        self.setModal(False)

        self._build_ui()
        self._apply_style()

        raiz = Path.home() / "GeoCAR_Suite"
        self._campo_planilha.setPlaceholderText(str(raiz / "entrada" / "cars.xlsx"))
        self._campo_saida.setText(str(raiz / "saida"))

    # ───────────────────────────────────────────────────────────
    # BUILD UI
    # ───────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(6)
        root.setContentsMargins(14, 12, 14, 10)

        root.addWidget(self._header())

        self._abas = QTabWidget()
        self._abas.addTab(self._aba_consultar(),     "🔍  Consultar CAR")
        self._abas.addTab(self._aba_demonstrativo(), "📄  Demonstrativo")
        self._abas.addTab(self._aba_lote(),          "📥  Proc. em Lote")
        self._abas.addTab(self._aba_configuracoes(), "⚙️  Configurações")
        self._abas.addTab(self._aba_dashboard(),     "📊  Dashboard")
        self._abas.addTab(self._aba_futura(
            "Análise Ambiental",
            "APP · Reserva Legal · Embargos IBAMA · MapBiomas"
        ), "🌿  Ambiental")
        root.addWidget(self._abas, stretch=1)

        root.addWidget(self._log_box())
        root.addWidget(self._progress_section())
        root.addLayout(self._action_buttons())
        root.addWidget(self._footer())

    # ── Cabeçalho ──────────────────────────────────────────────

    def _header(self):
        frame = QFrame()
        frame.setObjectName("header")
        h = QHBoxLayout(frame)
        h.setContentsMargins(16, 10, 16, 10)
        h.setSpacing(12)

        logo_path = Path(__file__).parent / "resources" / "logo.png"
        logo_lbl  = QLabel()
        if logo_path.exists():
            px = QPixmap(str(logo_path))
            logo_lbl.setPixmap(px.scaled(48, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        logo_lbl.setFixedSize(48, 48)
        logo_lbl.setAlignment(Qt.AlignCenter)
        h.addWidget(logo_lbl)

        col = QVBoxLayout()
        col.setSpacing(2)
        t = QLabel("GeoCAR Suite")
        t.setObjectName("titulo")
        s = QLabel("Plataforma de Gestão e Análise do Cadastro Ambiental Rural — Pará")
        s.setObjectName("subtitulo")
        col.addWidget(t)
        col.addWidget(s)
        h.addLayout(col)
        h.addStretch()

        autor = QLabel("Miguel A. L. Ferreira")
        autor.setObjectName("autor")
        h.addWidget(autor)
        return frame

    def _footer(self):
        f = QLabel("GeoCAR Suite  ·  Miguel A. L. Ferreira  ·  v1.0")
        f.setObjectName("footer")
        f.setAlignment(Qt.AlignCenter)
        return f

    # ── Aba Consultar CAR ───────────────────────────────────────

    def _aba_consultar(self):
        w = QWidget(); v = QVBoxLayout(w); v.setSpacing(8)

        g1 = QGroupBox("Consulta de Imóvel")
        h1 = QHBoxLayout(g1)
        self._campo_car_consulta = QLineEdit()
        self._campo_car_consulta.setPlaceholderText("PA-XXXXXXX-XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX")
        self._campo_car_consulta.returnPressed.connect(self._consultar_car)
        btn_c = self._btn_pri("🔍  Consultar", self._consultar_car)
        h1.addWidget(self._campo_car_consulta, stretch=1)
        h1.addWidget(btn_c)
        v.addWidget(g1)

        g2 = QGroupBox("Informações do Imóvel")
        v2 = QVBoxLayout(g2)
        self._label_consulta_resumo = QLabel("Nenhuma consulta realizada.")
        self._label_consulta_resumo.setObjectName("info")
        self._label_consulta_resumo.setWordWrap(True)
        v2.addWidget(self._label_consulta_resumo)
        v.addWidget(g2)

        g3 = QGroupBox("Sobreposições")
        v3 = QVBoxLayout(g3)
        self._tabela_consulta = QTableWidget(0, 3)
        self._tabela_consulta.setHorizontalHeaderLabels(["Base","Sobrepõe?","Área (ha) / Detalhe"])
        hh = self._tabela_consulta.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.Stretch)
        self._tabela_consulta.setEditTriggers(QTableWidget.NoEditTriggers)
        self._tabela_consulta.setAlternatingRowColors(True)
        v3.addWidget(self._tabela_consulta)
        v.addWidget(g3, stretch=1)

        g4 = QGroupBox("Log")
        v4 = QVBoxLayout(g4)
        self._log_consulta = QTextEdit()
        self._log_consulta.setReadOnly(True)
        self._log_consulta.setMaximumHeight(90)
        self._log_consulta.setObjectName("logArea")
        v4.addWidget(self._log_consulta)
        v.addWidget(g4)
        return w

    # ── Aba Demonstrativo ───────────────────────────────────────

    def _aba_demonstrativo(self):
        w = QWidget(); v = QVBoxLayout(w); v.setSpacing(8)

        g1 = QGroupBox("Imóvel(is)")
        v1 = QVBoxLayout(g1)
        h1 = QHBoxLayout()
        self._campo_car_demo = QLineEdit()
        self._campo_car_demo.setPlaceholderText("PA-XXXXXXX-XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX")
        btn_usar = self._btn_sec("↺ Usar CAR consultado", self._copiar_car_consultado)
        h1.addWidget(self._campo_car_demo, stretch=1)
        h1.addWidget(btn_usar)
        v1.addLayout(h1)
        lbl_ou = QLabel("— ou reutilize a fila da aba Proc. em Lote —")
        lbl_ou.setObjectName("info"); lbl_ou.setAlignment(Qt.AlignCenter)
        v1.addWidget(lbl_ou)
        v.addWidget(g1)

        g2 = QGroupBox("Pasta de Saída dos PDFs")
        h2 = QHBoxLayout(g2)
        self._campo_saida_demo = QLineEdit()
        btn_bd = self._btn_sec("📁", lambda: self._browse_saida_demo())
        btn_bd.setMaximumWidth(34)
        h2.addWidget(self._campo_saida_demo, stretch=1)
        h2.addWidget(btn_bd)
        v.addWidget(g2)

        g3 = QGroupBox("Status dos Downloads")
        v3 = QVBoxLayout(g3)
        self._tabela_demo = QTableWidget(0, 3)
        self._tabela_demo.setHorizontalHeaderLabels(["Código CAR","Status","Arquivo / Erro"])
        hh = self._tabela_demo.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        hh.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.Stretch)
        self._tabela_demo.setEditTriggers(QTableWidget.NoEditTriggers)
        self._tabela_demo.setAlternatingRowColors(True)
        v3.addWidget(self._tabela_demo)
        v.addWidget(g3, stretch=1)

        self._label_status_demo = QLabel("Aguardando...")
        self._label_status_demo.setObjectName("info")
        self._barra_demo = QProgressBar(); self._barra_demo.setValue(0)
        v.addWidget(self._label_status_demo)
        v.addWidget(self._barra_demo)

        g4 = QGroupBox("Log")
        v4 = QVBoxLayout(g4)
        self._log_demo = QTextEdit()
        self._log_demo.setReadOnly(True)
        self._log_demo.setMaximumHeight(90)
        self._log_demo.setObjectName("logArea")
        v4.addWidget(self._log_demo)
        v.addWidget(g4)

        h_btn = QHBoxLayout()
        self._btn_baixar_demo = self._btn_pri("⬇  Baixar Demonstrativo(s)", self._iniciar_demonstrativo)
        self._btn_baixar_demo.setMinimumHeight(36)
        self._btn_cancelar_demo = self._btn_per("⏹  Cancelar", self._cancelar_demonstrativo)
        self._btn_cancelar_demo.setEnabled(False)
        btn_pasta_demo = self._btn_sec("📂  Abrir Pasta", self._abrir_pasta_demo)
        h_btn.addWidget(self._btn_baixar_demo, stretch=2)
        h_btn.addWidget(self._btn_cancelar_demo)
        h_btn.addWidget(btn_pasta_demo)
        v.addLayout(h_btn)
        return w

    # ── Aba Processamento em Lote ───────────────────────────────

    def _aba_lote(self):
        w = QWidget(); v = QVBoxLayout(w); v.setSpacing(8)

        g1 = QGroupBox("Planilha de Entrada")
        h1 = QHBoxLayout(g1)
        self._campo_planilha = QLineEdit()
        h1.addWidget(self._campo_planilha, stretch=1)
        h1.addWidget(self._btn_sec("📁 Selecionar", self._browse_planilha))
        h1.addWidget(self._btn_sec("⬆ Importar",    self._importar_planilha))
        v.addWidget(g1)

        g2 = QGroupBox("Pasta de Saída")
        h2 = QHBoxLayout(g2)
        self._campo_saida = QLineEdit()
        btn_s = self._btn_sec("📁", self._browse_saida)
        btn_s.setMaximumWidth(34)
        h2.addWidget(self._campo_saida, stretch=1)
        h2.addWidget(btn_s)
        v.addWidget(g2)

        g_opt = QGroupBox("Opções")
        h_opt = QHBoxLayout(g_opt)
        self._chk_demonstrativo = QCheckBox("Também baixar Demonstrativo PDF de cada imóvel")
        self._chk_demonstrativo.setChecked(False)
        h_opt.addWidget(self._chk_demonstrativo)
        h_opt.addStretch()
        v.addWidget(g_opt)

        g3 = QGroupBox("Fila de Processamento")
        v3 = QVBoxLayout(g3)
        self._tabela = QTableWidget(0, 5)
        self._tabela.setHorizontalHeaderLabels(["Código CAR","Município","Área (ha)","Status","Observação"])
        hh = self._tabela.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        hh.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(4, QHeaderView.Stretch)
        self._tabela.setEditTriggers(QTableWidget.NoEditTriggers)
        self._tabela.setAlternatingRowColors(True)
        v3.addWidget(self._tabela)

        h3 = QHBoxLayout()
        self._label_contagem = QLabel("0 CARs na fila")
        self._label_contagem.setObjectName("info")
        h3.addWidget(self._label_contagem)
        h3.addStretch()
        h3.addWidget(self._btn_per("🗑 Limpar", self._limpar_tabela))
        v3.addLayout(h3)
        v.addWidget(g3, stretch=1)
        return w

    # ── Aba Configurações ───────────────────────────────────────

    def _aba_configuracoes(self):
        widget = QWidget()
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        inner  = QWidget()
        layout = QVBoxLayout(inner); layout.setSpacing(8)

        grupo = QGroupBox("Bases de Sobreposição")
        form  = QVBoxLayout(grupo); form.setSpacing(6)

        BASES_INFO = [
            ("uc_federal",    "UC Federal"),
            ("uc_estadual",   "UC Estadual"),
            ("terra_indigena","Terra Indígena"),
            ("prodes",        "PRODES"),
            ("assentamento",  "Assentamento Federal"),
            ("quilombo",      "Quilombo Federal"),
            ("embargo_ibama", "Embargo IBAMA"),
            ("sigef",         "SIGEF"),
        ]
        self._campos_bases = {}
        try:
            from .processing.config_manager import obter_bases
            bases_cfg = obter_bases()
        except Exception:
            bases_cfg = {}

        for base_id, nome_display in BASES_INFO:
            info   = bases_cfg.get(base_id) or {}
            tipo_a = info.get("tipo","shp")
            cam_a  = info.get("caminho") or ""
            cad_a  = info.get("camada") or ""
            fld_a  = info.get("campo_nome") or ""

            sub = QGroupBox(nome_display)
            sv  = QVBoxLayout(sub); sv.setSpacing(4)

            h0 = QHBoxLayout()
            lbl_t = QLabel("Formato:"); lbl_t.setFixedWidth(90); lbl_t.setObjectName("cfgLabel")
            combo_tipo = QComboBox()
            combo_tipo.addItems(["SHP — Shapefile individual","GPKG — GeoPackage"])
            combo_tipo.setCurrentIndex(1 if tipo_a=="gpkg" else 0)
            combo_tipo.setFixedWidth(240)
            h0.addWidget(lbl_t); h0.addWidget(combo_tipo); h0.addStretch()
            sv.addLayout(h0)

            h1 = QHBoxLayout()
            lbl_p = QLabel("Arquivo:"); lbl_p.setFixedWidth(90); lbl_p.setObjectName("cfgLabel")
            campo_path = QLineEdit(cam_a)
            campo_path.setPlaceholderText("Caminho do arquivo .shp ou .gpkg")
            btn_br = self._btn_sec("📁", lambda _, c=campo_path, cb=combo_tipo: self._browse_base(c, cb))
            btn_br.setMaximumWidth(34)
            h1.addWidget(lbl_p); h1.addWidget(campo_path, stretch=1); h1.addWidget(btn_br)
            sv.addLayout(h1)

            h2 = QHBoxLayout()
            lbl_c = QLabel("Camada:"); lbl_c.setFixedWidth(90); lbl_c.setObjectName("cfgLabel")
            combo_cam = QComboBox(); combo_cam.setEditable(True); combo_cam.setMinimumWidth(180)
            if cad_a: combo_cam.addItem(cad_a); combo_cam.setCurrentText(cad_a)
            combo_cam.setEnabled(tipo_a=="gpkg")
            btn_lst = self._btn_sec("↻ Listar", lambda _, cp=campo_path, cc=combo_cam: self._listar_camadas(cp, cc))
            h2.addWidget(lbl_c); h2.addWidget(combo_cam, stretch=1); h2.addWidget(btn_lst)
            sv.addLayout(h2)

            h3 = QHBoxLayout()
            lbl_f = QLabel("Campo nome:"); lbl_f.setFixedWidth(90); lbl_f.setObjectName("cfgLabel")
            campo_nome = QLineEdit(fld_a)
            campo_nome.setPlaceholderText("coluna com o nome da área")
            h3.addWidget(lbl_f); h3.addWidget(campo_nome, stretch=1)
            sv.addLayout(h3)

            combo_tipo.currentIndexChanged.connect(lambda idx, cc=combo_cam: cc.setEnabled(idx==1))
            form.addWidget(sub)
            self._campos_bases[base_id] = {"tipo":combo_tipo,"path":campo_path,"camada":combo_cam,"campo":campo_nome}

        layout.addWidget(grupo)

        h_btns = QHBoxLayout()
        btn_salvar  = self._btn_pri("💾  Salvar Configuração", self._salvar_config)
        btn_salvar.setMinimumHeight(34)
        btn_validar = self._btn_sec("✔ Verificar Bases", self._verificar_bases)
        h_btns.addWidget(btn_salvar, stretch=1); h_btns.addWidget(btn_validar)
        layout.addLayout(h_btns)

        self._label_status_bases = QLabel("")
        self._label_status_bases.setObjectName("info")
        self._label_status_bases.setWordWrap(True)
        layout.addWidget(self._label_status_bases)
        layout.addStretch()

        scroll.setWidget(inner)
        outer = QVBoxLayout(widget); outer.setContentsMargins(0,0,0,0); outer.addWidget(scroll)
        return widget

    # ── Aba Dashboard ───────────────────────────────────────────

    def _aba_dashboard(self):
        try:
            from .dashboard import criar_widget_dashboard
            self._dashboard_ref = criar_widget_dashboard()
            return self._dashboard_ref
        except Exception as e:
            w = QWidget(); v = QVBoxLayout(w)
            lbl = QLabel(
                f"⚠ Dashboard indisponível.\n\n"
                f"Instale o matplotlib:\n  pip install matplotlib\n\nErro: {e}"
            )
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet("color:#607D8B; font-size:12px;")
            v.addWidget(lbl)
            self._dashboard_ref = None
            return w

    # ── Aba Futura ──────────────────────────────────────────────

    def _aba_futura(self, titulo, descricao):
        w = QWidget(); v = QVBoxLayout(w); v.addStretch()
        for txt, obj in [("🔧","futIcn"),(titulo,"futTit"),(descricao,"futDesc"),
                         ("Em desenvolvimento — próxima versão","futSub")]:
            l = QLabel(txt); l.setObjectName(obj); l.setAlignment(Qt.AlignCenter); v.addWidget(l)
        v.addStretch(); return w

    # ── Log / Progress / Botões ─────────────────────────────────

    def _log_box(self):
        g = QGroupBox("Log de Execução"); v = QVBoxLayout(g)
        self._log_area = QTextEdit()
        self._log_area.setReadOnly(True); self._log_area.setMaximumHeight(115)
        self._log_area.setObjectName("logArea")
        v.addWidget(self._log_area); return g

    def _progress_section(self):
        frame = QFrame(); v = QVBoxLayout(frame); v.setSpacing(3); v.setContentsMargins(0,2,0,2)
        self._label_status = QLabel("Aguardando..."); self._label_status.setObjectName("info")
        self._barra = QProgressBar(); self._barra.setValue(0)
        v.addWidget(self._label_status); v.addWidget(self._barra); return frame

    def _action_buttons(self):
        h = QHBoxLayout()
        self._btn_processar = self._btn_pri("▶  PROCESSAR CARs", self._iniciar)
        self._btn_processar.setMinimumHeight(38)
        self._btn_cancelar = self._btn_per("⏹  Cancelar", self._cancelar)
        self._btn_cancelar.setEnabled(False)
        btn_pasta = self._btn_sec("📂  Pasta de Saída", self._abrir_pasta_saida)
        h.addWidget(self._btn_processar, stretch=2)
        h.addWidget(self._btn_cancelar)
        h.addWidget(btn_pasta)
        return h

    # ── Helpers de botão ─────────────────────────────────────────

    def _btn_pri(self, txt, fn):
        b = QPushButton(txt); b.setObjectName("btnPrimario"); b.clicked.connect(fn); return b
    def _btn_sec(self, txt, fn):
        b = QPushButton(txt); b.setObjectName("btnSec"); b.clicked.connect(fn); return b
    def _btn_per(self, txt, fn):
        b = QPushButton(txt); b.setObjectName("btnPerigo"); b.clicked.connect(fn); return b

    # ───────────────────────────────────────────────────────────
    # AÇÕES
    # ───────────────────────────────────────────────────────────

    def _browse_planilha(self):
        a, _ = QFileDialog.getOpenFileName(self,"Planilha","","Planilhas (*.xlsx *.xls *.csv)")
        if a: self._campo_planilha.setText(a)

    def _browse_saida(self):
        p = QFileDialog.getExistingDirectory(self,"Pasta de saída")
        if p: self._campo_saida.setText(p)

    def _browse_base(self, campo, combo_tipo):
        filtro = "GeoPackage (*.gpkg);;Todos (*)" if combo_tipo.currentIndex()==1 else "Shapefiles (*.shp);;Todos (*)"
        a, _ = QFileDialog.getOpenFileName(self,"Selecionar base","",filtro)
        if a: campo.setText(a)

    def _browse_saida_demo(self):
        p = QFileDialog.getExistingDirectory(self,"Pasta PDFs")
        if p: self._campo_saida_demo.setText(p)

    def _listar_camadas(self, campo_path, combo_camada):
        cam = campo_path.text().strip()
        if not cam or not Path(cam).exists():
            QMessageBox.warning(self,"Arquivo","Informe um caminho válido."); return
        try:
            from .processing.config_manager import listar_camadas_gpkg
            camadas = listar_camadas_gpkg(cam)
            combo_camada.clear(); combo_camada.addItems(camadas)
            self._log(f"✓ {len(camadas)} camada(s) no GPKG")
        except Exception as e:
            QMessageBox.critical(self,"Erro",str(e))

    def _importar_planilha(self):
        from .processing.excel_reader import ler_planilha
        arq = self._campo_planilha.text().strip()
        if not arq: QMessageBox.warning(self,"Planilha","Selecione um arquivo."); return
        ok, res = ler_planilha(arq)
        if not ok: QMessageBox.critical(self,"Erro",str(res)); self._log(f"✗ {res}","erro"); return
        self._tabela.setRowCount(0)
        for item in res: self._adicionar_linha(item["codigo_car"])
        self._atualizar_contagem()
        self._log(f"✓ {len(res)} CAR(s) importado(s) de {Path(arq).name}")

    def _adicionar_linha(self, codigo_car):
        r = self._tabela.rowCount(); self._tabela.insertRow(r)
        self._tabela.setItem(r,0,QTableWidgetItem(codigo_car))
        st = QTableWidgetItem("⏳ Aguardando"); st.setForeground(QColor("#9E9E9E"))
        for c in range(1,5): self._tabela.setItem(r,c,QTableWidgetItem(""))
        self._tabela.setItem(r,3,st)

    def _limpar_tabela(self):
        if not self._tabela.rowCount(): return
        if QMessageBox.question(self,"Limpar","Remover todos os CARs?",
                                QMessageBox.Yes|QMessageBox.No)==QMessageBox.Yes:
            self._tabela.setRowCount(0); self._atualizar_contagem()

    def _atualizar_contagem(self):
        n = self._tabela.rowCount()
        self._label_contagem.setText(f"{n} CAR{'s' if n!=1 else ''} na fila")

    def _abrir_pasta_saida(self):
        p = self._campo_saida.text().strip()
        if p and Path(p).exists():
            import subprocess, sys
            if sys.platform=="win32": os.startfile(p)
            else: subprocess.Popen(["xdg-open",p])

    def _salvar_config(self):
        try:
            from .processing.config_manager import carregar, salvar
            cfg = carregar()
            cfg.setdefault("bases",{})
            for bid, campos in self._campos_bases.items():
                tipo   = "gpkg" if campos["tipo"].currentIndex()==1 else "shp"
                caminho= campos["path"].text().strip() or None
                camada = campos["camada"].currentText().strip() or None
                campo  = campos["campo"].text().strip() or "nome"
                cfg["bases"][bid] = {"tipo":tipo,"caminho":caminho,"camada":camada,"campo_nome":campo}
            if salvar(cfg):
                self._log("✓ Configuração salva.","ok"); self._verificar_bases()
            else: self._log("✗ Erro ao salvar.","erro")
        except Exception as e: self._log(f"✗ {e}","erro")

    def _verificar_bases(self):
        try:
            from .processing.config_manager import validar
            sl = validar()
            self._label_status_bases.setText("\n".join(f"  {s['base_id']}: {s['situacao']}" for s in sl))
            ok_c = sum(1 for s in sl if s["ok"])
            self._log(f"Bases: {ok_c}/{len(sl)} configuradas.","info")
        except Exception as e: self._log(f"✗ {e}","erro")

    def _copiar_car_consultado(self):
        if self._ultimo_car_consultado:
            self._campo_car_demo.setText(self._ultimo_car_consultado)
        else:
            QMessageBox.information(self,"Demonstrativo","Nenhum CAR consultado ainda.")

    def _abrir_pasta_demo(self):
        p = self._campo_saida_demo.text().strip()
        if p and Path(p).exists():
            import subprocess, sys
            if sys.platform=="win32": os.startfile(p)
            else: subprocess.Popen(["xdg-open",p])

    # ── Consultar CAR ───────────────────────────────────────────

    def _consultar_car(self):
        codigo = self._campo_car_consulta.text().strip().upper()
        if not codigo: QMessageBox.warning(self,"CAR","Informe o número do CAR."); return
        self._log_consulta.clear()
        self._label_consulta_resumo.setText("Consultando...")
        self._tabela_consulta.setRowCount(0)
        self._worker_consulta = WorkerConsulta(codigo)
        self._worker_consulta.sinal_log.connect(lambda m,n: self._log_em(self._log_consulta,m,n))
        self._worker_consulta.sinal_concluido.connect(self._on_consulta_concluida)
        self._worker_consulta.start()

    def _on_consulta_concluida(self, sucesso, dados):
        if not sucesso:
            self._label_consulta_resumo.setText(f"❌ Erro: {dados.get('erro','')}"); return
        self._label_consulta_resumo.setText(
            f"<b>{dados['codigo_car']}</b><br>"
            f"Município: {dados['municipio']}  ({dados['uf']} — IBGE {dados['cod_ibge']})<br>"
            f"Área total: {dados['area_ha']:.2f} ha  |  ID: {dados['id_car']}"
        )
        self._tabela_consulta.setRowCount(0)
        for nome_base, res in dados["sobreposicoes"].items():
            r = self._tabela_consulta.rowCount()
            self._tabela_consulta.insertRow(r)
            self._tabela_consulta.setItem(r,0,QTableWidgetItem(nome_base))
            sn = QTableWidgetItem("SIM" if res.get("sobrepoe") else "NÃO")
            sn.setForeground(QColor("#C62828") if res.get("sobrepoe") else QColor("#2E7D32"))
            self._tabela_consulta.setItem(r,1,sn)
            det = f"{res.get('area_ha',0):.2f} ha"
            if res.get("anos_lista"): det += f"  —  {res['anos_lista']}"
            elif res.get("nomes"): det += "  —  " + ", ".join(res["nomes"][:3])
            self._tabela_consulta.setItem(r,2,QTableWidgetItem(det))
        self._ultimo_car_consultado = dados["codigo_car"]
        if hasattr(self,"_campo_car_demo"):
            self._campo_car_demo.setText(dados["codigo_car"])

    # ── Demonstrativo ───────────────────────────────────────────

    def _lista_cars_demo(self):
        ind = self._campo_car_demo.text().strip().upper()
        if ind: return [ind]
        return [self._tabela.item(r,0).text() for r in range(self._tabela.rowCount()) if self._tabela.item(r,0)]

    def _iniciar_demonstrativo(self):
        lista = self._lista_cars_demo()
        if not lista:
            QMessageBox.warning(self,"Demonstrativo","Informe um CAR ou importe uma planilha."); return
        pasta = self._campo_saida_demo.text().strip()
        if not pasta:
            pasta = str(Path.home()/"GeoCAR_Suite"/"saida"/"demonstrativos")
            self._campo_saida_demo.setText(pasta)
        self._tabela_demo.setRowCount(0)
        for c in lista:
            r = self._tabela_demo.rowCount(); self._tabela_demo.insertRow(r)
            self._tabela_demo.setItem(r,0,QTableWidgetItem(c))
            st = QTableWidgetItem("⏳ Aguardando"); st.setForeground(QColor("#9E9E9E"))
            self._tabela_demo.setItem(r,1,st); self._tabela_demo.setItem(r,2,QTableWidgetItem(""))
        self._btn_baixar_demo.setEnabled(False); self._btn_cancelar_demo.setEnabled(True)
        self._barra_demo.setValue(0); self._log_demo.clear()
        self._log_em(self._log_demo,f"▶ {len(lista)} demonstrativo(s)...")
        self._worker_demo = WorkerDemonstrativo(lista, pasta)
        self._worker_demo.sinal_log.connect(lambda m,n: self._log_em(self._log_demo,m,n))
        self._worker_demo.sinal_progresso.connect(lambda p,s: (self._barra_demo.setValue(p), self._label_status_demo.setText(s)))
        self._worker_demo.sinal_item.connect(self._on_item_demo)
        self._worker_demo.sinal_fim.connect(self._on_fim_demo)
        self._worker_demo.start()

    def _cancelar_demonstrativo(self):
        if hasattr(self,"_worker_demo"): self._worker_demo.cancelar()
        self._btn_cancelar_demo.setEnabled(False)

    def _on_item_demo(self, codigo_car, sucesso, info):
        for r in range(self._tabela_demo.rowCount()):
            it = self._tabela_demo.item(r,0)
            if it and it.text()==codigo_car:
                st = QTableWidgetItem("✅ OK" if sucesso else "❌ Erro")
                st.setForeground(QColor("#2E7D32") if sucesso else QColor("#C62828"))
                self._tabela_demo.setItem(r,1,st)
                self._tabela_demo.setItem(r,2,QTableWidgetItem(Path(info).name if sucesso else info)); break

    def _on_fim_demo(self, resumo):
        self._btn_baixar_demo.setEnabled(True); self._btn_cancelar_demo.setEnabled(False)
        self._barra_demo.setValue(100); self._label_status_demo.setText("Concluído!")
        self._log_em(self._log_demo,f"✅ {resumo['sucesso']}/{resumo['total']} PDF(s) em {resumo['pasta']}")
        QMessageBox.information(self,"Demonstrativo",
            f"✅ {resumo['sucesso']} de {resumo['total']} PDF(s) baixado(s).\n\n📁 {resumo['pasta']}"
            + (f"\n\n⚠ {resumo['erro']} com erro." if resumo['erro'] else ""))

    # ── Processamento em Lote ───────────────────────────────────

    def _lista_cars(self):
        return [{"codigo_car":self._tabela.item(r,0).text(),"linha":r}
                for r in range(self._tabela.rowCount()) if self._tabela.item(r,0)]

    def _iniciar(self):
        lista = self._lista_cars()
        if not lista: QMessageBox.warning(self,"Fila","Importe uma planilha."); return
        pasta = self._campo_saida.text().strip()
        if not pasta: QMessageBox.warning(self,"Saída","Informe a pasta de saída."); return
        config = {
            "gpkg_path":          str(Path(pasta)/"gpkg"/"car_consolidado.gpkg"),
            "xlsx_path":          str(Path(pasta)/"relatorios"/"relatorio_car.xlsx"),
            "demonstrativos_dir": str(Path(pasta)/"demonstrativos"),
            "timeout":            30,
            "carregar_qgis":      True,
            "calcular_sobreposicoes": True,
            "baixar_demonstrativo":   self._chk_demonstrativo.isChecked(),
        }
        self._btn_processar.setEnabled(False); self._btn_cancelar.setEnabled(True)
        self._barra.setValue(0)
        self._log(f"\n{'─'*52}")
        self._log(f"▶ Iniciando: {len(lista)} CAR(s)")
        self._log(f"{'─'*52}")
        self.worker = WorkerCAR(lista, config, self.iface)
        self.worker.sinal_log.connect(lambda m,n: self._log(m,n))
        self.worker.sinal_progresso.connect(self._on_progresso)
        self.worker.sinal_resultado.connect(self._on_resultado)
        self.worker.sinal_fim.connect(self._on_fim)
        self.worker.start()

    def _cancelar(self):
        if self.worker: self.worker.cancelar(); self._btn_cancelar.setEnabled(False)

    def _on_progresso(self, pct, status):
        self._barra.setValue(pct); self._label_status.setText(status)

    def _on_resultado(self, codigo_car, sucesso, dados):
        for r in range(self._tabela.rowCount()):
            it = self._tabela.item(r,0)
            if it and it.text()==codigo_car:
                if sucesso:
                    area = dados.get("area_ha","")
                    st   = QTableWidgetItem("✅ OK"); st.setForeground(QColor("#2E7D32"))
                    self._tabela.setItem(r,1,QTableWidgetItem(str(dados.get("municipio",""))))
                    self._tabela.setItem(r,2,QTableWidgetItem(f"{area:.2f}" if isinstance(area,float) else str(area)))
                    self._tabela.setItem(r,3,st)
                    hits = [k.replace("sobr_","").replace("_sim_nao","").upper()
                            for k,v in dados.items() if k.endswith("_sim_nao") and v=="SIM"]
                    self._tabela.setItem(r,4,QTableWidgetItem("⚠ "+", ".join(hits) if hits else ""))
                else:
                    st = QTableWidgetItem("❌ Erro"); st.setForeground(QColor("#C62828"))
                    self._tabela.setItem(r,3,st)
                    self._tabela.setItem(r,4,QTableWidgetItem(dados.get("erro","")))
                break

    def _on_fim(self, resumo):
        self._btn_processar.setEnabled(True); self._btn_cancelar.setEnabled(False)
        self._barra.setValue(98); self._label_status.setText("Finalizando...")

        # ── Carregar no QGIS (thread principal — sem crash) ──
        if resumo.get("carregar_qgis") and resumo.get("gpkg"):
            try:
                from .processing.qgis_loader import carregar_gpkg
                ok, msg = carregar_gpkg(self.iface, resumo["gpkg"])
                self._log(f"   QGIS: {'✓ '+msg if ok else '✗ '+msg}", "ok" if ok else "erro")
            except Exception as e:
                self._log(f"   ⚠ QGIS: {e}","aviso")

        # ── Atualizar Dashboard ──
        try:
            if self._dashboard_ref is not None:
                dados_dash = getattr(self.worker,"_resultados_lote",[])
                self._dashboard_ref.carregar_dados(dados_dash)
                self._dashboard_ref.atualizar()
                self._log("📊 Dashboard atualizado.","info")
        except Exception as e:
            log.warning(f"Dashboard: {e}")

        self._barra.setValue(100); self._label_status.setText("Concluído!")
        self._log(f"\n{'─'*52}")
        self._log(f"✅ {resumo['sucesso']}/{resumo['total']}  ✓ sucesso  ✗ {resumo['erro']} erro(s)")
        if resumo.get("gpkg"): self._log(f"   GeoPackage: {resumo['gpkg']}")
        self._log(f"   Relatório:  {resumo['xlsx']}")
        self._log(f"{'─'*52}\n")
        QMessageBox.information(self,"Concluído",
            f"✅ {resumo['sucesso']} de {resumo['total']} imóvel(is) processado(s).\n\n"
            f"📦 Arquivos em:\n{self._campo_saida.text()}"
            + (f"\n\n⚠ {resumo['erro']} CAR(s) com erro." if resumo['erro'] else ""))

    # ── Log helpers ─────────────────────────────────────────────

    def _log(self, mensagem, nivel="info"):
        self._log_em(self._log_area, mensagem, nivel)

    def _log_em(self, area, mensagem, nivel="info"):
        hora = datetime.now().strftime("%H:%M:%S")
        area.append(f"[{hora}] {mensagem}")
        cursor = area.textCursor()
        cursor.movePosition(QTextCursor.End)
        area.setTextCursor(cursor)

    # ───────────────────────────────────────────────────────────
    # ESTILO — TEMA CLARO PROFISSIONAL
    # ───────────────────────────────────────────────────────────

    def _apply_style(self):
        self.setStyleSheet("""
        QDialog {
            background-color: #F5F7FA; color: #263238;
            font-family: 'Segoe UI', Arial, sans-serif; font-size: 13px;
        }
        QFrame#header {
            background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #1B5E20,stop:1 #2E7D32);
            border-radius: 7px;
        }
        QLabel#titulo  { font-size:20px; font-weight:bold; color:#FFFFFF; }
        QLabel#subtitulo { font-size:11px; color:#C8E6C9; }
        QLabel#autor   { font-size:11px; color:#A5D6A7; font-style:italic; }
        QLabel#footer  { font-size:10px; color:#90A4AE; padding:3px; }
        QTabWidget::pane { border:1px solid #CFD8DC; background:#FFFFFF; border-radius:5px; }
        QTabBar::tab {
            background:#ECEFF1; color:#546E7A; padding:8px 14px;
            border-radius:4px 4px 0 0; margin-right:2px; font-size:12px; min-width:110px;
        }
        QTabBar::tab:selected { background:#2E7D32; color:#FFFFFF; font-weight:bold; }
        QTabBar::tab:hover:!selected { background:#DCEDC8; color:#33691E; }
        QGroupBox {
            border:1px solid #CFD8DC; border-radius:6px; margin-top:10px;
            padding-top:10px; background:#FFFFFF; color:#455A64;
            font-weight:bold; font-size:12px;
        }
        QGroupBox::title { subcontrol-origin:margin; left:10px; padding:0 6px; background:#FFFFFF; }
        QLineEdit, QComboBox {
            background:#FFFFFF; color:#263238; border:1px solid #B0BEC5;
            border-radius:4px; padding:5px 8px; font-size:12px;
        }
        QLineEdit:focus, QComboBox:focus { border-color:#2E7D32; }
        QComboBox::drop-down { border:none; width:20px; }
        QComboBox QAbstractItemView {
            background:#FFFFFF; border:1px solid #B0BEC5;
            selection-background-color:#C8E6C9; selection-color:#1B5E20;
        }
        QLabel#cfgLabel { color:#546E7A; font-size:11px; font-weight:normal; }
        QLabel#info     { color:#607D8B; font-size:11px; }
        QPushButton#btnPrimario {
            background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #388E3C,stop:1 #2E7D32);
            color:#FFFFFF; border:none; border-radius:5px;
            padding:8px 20px; font-weight:bold; font-size:13px;
        }
        QPushButton#btnPrimario:hover { background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #43A047,stop:1 #388E3C); }
        QPushButton#btnPrimario:disabled { background:#BDBDBD; color:#757575; }
        QPushButton#btnSec {
            background:#ECEFF1; color:#455A64; border:1px solid #B0BEC5;
            border-radius:4px; padding:6px 12px; font-size:12px;
        }
        QPushButton#btnSec:hover { background:#CFD8DC; color:#263238; }
        QPushButton#btnPerigo {
            background:#E53935; color:#FFFFFF; border:none;
            border-radius:4px; padding:6px 12px; font-size:12px;
        }
        QPushButton#btnPerigo:hover { background:#C62828; }
        QPushButton#btnPerigo:disabled { background:#BDBDBD; color:#757575; }
        QTableWidget {
            background:#FFFFFF; color:#263238; gridline-color:#ECEFF1;
            border:1px solid #CFD8DC; border-radius:4px; font-size:12px;
        }
        QTableWidget::item:alternate { background:#F5F7FA; }
        QTableWidget::item:selected  { background:#C8E6C9; color:#1B5E20; }
        QHeaderView::section {
            background:#ECEFF1; color:#455A64; padding:6px; border:none;
            border-bottom:2px solid #B0BEC5; font-weight:bold; font-size:12px;
        }
        QProgressBar {
            border:1px solid #B0BEC5; border-radius:5px; background:#ECEFF1;
            height:14px; color:#263238; text-align:center; font-size:11px;
        }
        QProgressBar::chunk {
            background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #2E7D32,stop:1 #66BB6A);
            border-radius:4px;
        }
        QTextEdit#logArea {
            font-family:'Consolas','Courier New',monospace; font-size:11px;
            background:#FAFAFA; color:#37474F;
            border:1px solid #CFD8DC; border-radius:4px;
        }
        QScrollArea { border:none; background:transparent; }
        QScrollBar:vertical { background:#F5F7FA; width:10px; border-radius:5px; }
        QScrollBar::handle:vertical { background:#B0BEC5; border-radius:5px; min-height:20px; }
        QScrollBar::handle:vertical:hover { background:#78909C; }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0px; }
        QLabel#futIcn  { font-size:36px; }
        QLabel#futTit  { font-size:15px; font-weight:bold; color:#546E7A; }
        QLabel#futDesc { font-size:11px; color:#78909C; }
        QLabel#futSub  { font-size:10px; color:#90A4AE; margin-top:6px; }
        """)
