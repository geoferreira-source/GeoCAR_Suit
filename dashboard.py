# -*- coding: utf-8 -*-
"""
dashboard.py — GeoCAR Suite
Aba de Dashboard com gráficos gerados a partir dos resultados do lote.

Gráficos:
  1. Área por município (barras horizontais)
  2. Percentual de imóveis com sobreposição por base (barras verticais)
  3. Evolução do desmatamento PRODES por ano (linha)
  4. Distribuição de área dos imóveis (histograma)
"""

import logging
from collections import defaultdict

log = logging.getLogger("GeoCAR_Suite")


def criar_widget_dashboard(parent=None):
    """
    Cria e retorna o QWidget da aba Dashboard.
    Inclui botão de atualização e os 4 gráficos.
    """
    try:
        import matplotlib
        matplotlib.use("Agg")  # backend sem janela
        from matplotlib.figure import Figure
        from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas

        from qgis.PyQt.QtWidgets import (
            QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
            QLabel, QScrollArea, QFrame, QSizePolicy
        )
        from qgis.PyQt.QtCore import Qt

    except ImportError as e:
        from qgis.PyQt.QtWidgets import QWidget, QVBoxLayout, QLabel
        w = QWidget(parent)
        v = QVBoxLayout(w)
        v.addWidget(QLabel(f"matplotlib não instalado.\nExecute: pip install matplotlib\n\nErro: {e}"))
        return w

    class DashboardWidget(QWidget):
        def __init__(self, parent=None):
            super().__init__(parent)
            self._dados = []
            self._build_ui()

        def _build_ui(self):
            layout = QVBoxLayout(self)
            layout.setContentsMargins(8, 8, 8, 8)
            layout.setSpacing(6)

            # Cabeçalho
            h = QHBoxLayout()
            titulo = QLabel("Dashboard de Resultados")
            titulo.setStyleSheet(
                "font-size: 15px; font-weight: bold; color: #1B5E20;"
            )
            self._label_total = QLabel("Nenhum lote processado ainda.")
            self._label_total.setStyleSheet("color: #607D8B; font-size: 11px;")

            btn_atualizar = QPushButton("↻  Atualizar Gráficos")
            btn_atualizar.setStyleSheet(
                "background: #2E7D32; color: white; border: none; "
                "border-radius: 4px; padding: 6px 14px; font-weight: bold;"
            )
            btn_atualizar.clicked.connect(self.atualizar)

            h.addWidget(titulo)
            h.addWidget(self._label_total)
            h.addStretch()
            h.addWidget(btn_atualizar)
            layout.addLayout(h)

            # Área de rolagem para os gráficos
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setStyleSheet("QScrollArea { border: none; background: #FAFAFA; }")

            inner = QWidget()
            inner.setStyleSheet("background: #FAFAFA;")
            self._grid = QVBoxLayout(inner)
            self._grid.setSpacing(12)

            # Linha 1: dois gráficos lado a lado
            self._row1 = QHBoxLayout()
            self._row1.setSpacing(10)

            # Linha 2: dois gráficos lado a lado
            self._row2 = QHBoxLayout()
            self._row2.setSpacing(10)

            self._grid.addLayout(self._row1)
            self._grid.addLayout(self._row2)
            self._grid.addStretch()

            scroll.setWidget(inner)
            layout.addWidget(scroll, stretch=1)

            # Placeholder inicial
            self._mostrar_placeholder()

        def _mostrar_placeholder(self):
            lbl = QLabel(
                "📊  Processe um lote de CARs na aba 'Proc. em Lote'\n"
                "e clique em '↻ Atualizar Gráficos' para ver os resultados."
            )
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet("color: #90A4AE; font-size: 13px; padding: 40px;")
            self._row1.addWidget(lbl)

        def carregar_dados(self, resultados: list):
            """
            Recebe a lista de dicionários de resultado do WorkerCAR
            e armazena para exibição.
            """
            self._dados = [r for r in resultados if r.get("status") == "ok"]
            self._label_total.setText(
                f"{len(self._dados)} imóvel(is) com dados  |  "
                f"{len(resultados) - len(self._dados)} com erro"
            )

        def atualizar(self):
            """Redesenha todos os gráficos com os dados atuais."""
            if not self._dados:
                return

            self._limpar_graficos()

            try:
                self._grafico_area_municipio()
                self._grafico_sobreposicoes()
                self._grafico_prodes_anos()
                self._grafico_histograma_area()
            except Exception as e:
                log.error(f"Erro ao gerar dashboard: {e}")

        def _limpar_graficos(self):
            """Remove todos os widgets dos layouts de linha."""
            for layout in [self._row1, self._row2]:
                while layout.count():
                    item = layout.takeAt(0)
                    if item.widget():
                        item.widget().deleteLater()

        # ─────────────────────────────────────────────
        # GRÁFICO 1 — Área total por município
        # ─────────────────────────────────────────────

        def _grafico_area_municipio(self):
            from matplotlib.figure import Figure
            from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas

            municipios = defaultdict(float)
            for r in self._dados:
                mun  = r.get("municipio") or "S/D"
                area = r.get("area_ha") or 0
                if isinstance(area, (int, float)):
                    municipios[mun] += area

            if not municipios:
                return

            # Ordenar pelo maior e limitar a 15
            itens = sorted(municipios.items(), key=lambda x: x[1], reverse=True)[:15]
            labels = [i[0] for i in itens]
            valores = [i[1] for i in itens]

            fig = Figure(figsize=(5.5, 4), facecolor="#FAFAFA")
            ax  = fig.add_subplot(111)
            ax.set_facecolor("#F5F7FA")

            barras = ax.barh(labels, valores, color="#2E7D32", edgecolor="white", linewidth=0.5)
            ax.set_xlabel("Área Total (ha)", fontsize=9)
            ax.set_title("Área por Município (ha)", fontsize=11, fontweight="bold",
                         color="#1B5E20", pad=8)
            ax.tick_params(labelsize=8)

            for barra, val in zip(barras, valores):
                ax.text(barra.get_width() + max(valores) * 0.01, barra.get_y() + barra.get_height() / 2,
                        f"{val:,.1f}", va="center", fontsize=7, color="#37474F")

            ax.invert_yaxis()
            fig.tight_layout()

            canvas = FigureCanvas(fig)
            canvas.setMinimumHeight(280)
            self._row1.addWidget(canvas)

        # ─────────────────────────────────────────────
        # GRÁFICO 2 — % de imóveis com sobreposição
        # ─────────────────────────────────────────────

        def _grafico_sobreposicoes(self):
            from matplotlib.figure import Figure
            from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas

            BASES = {
                "sobr_uc_federal_sim_nao":     "UC Federal",
                "sobr_uc_estadual_sim_nao":    "UC Estadual",
                "sobr_terra_indigena_sim_nao": "Terra Indígena",
                "sobr_prodes_sim_nao":         "PRODES",
                "sobr_assentamento_sim_nao":   "Assentamento",
                "sobr_quilombo_sim_nao":       "Quilombo",
                "sobr_embargo_ibama_sim_nao":  "Embargo IBAMA",
                "sobr_sigef_sim_nao":          "SIGEF",
            }

            total = len(self._dados)
            labels, valores, cores = [], [], []

            CORES_BASE = [
                "#1565C0", "#0277BD", "#00838F", "#2E7D32",
                "#558B2F", "#F57F17", "#E65100", "#6A1B9A"
            ]

            for i, (campo, nome) in enumerate(BASES.items()):
                count = sum(1 for r in self._dados if r.get(campo) == "SIM")
                if count > 0 or True:  # mostrar todas, mesmo as zeradas
                    labels.append(nome)
                    valores.append(round((count / total) * 100, 1) if total > 0 else 0)
                    cores.append(CORES_BASE[i % len(CORES_BASE)])

            fig = Figure(figsize=(5.5, 4), facecolor="#FAFAFA")
            ax  = fig.add_subplot(111)
            ax.set_facecolor("#F5F7FA")

            barras = ax.bar(labels, valores, color=cores, edgecolor="white", linewidth=0.5)
            ax.set_ylabel("% de Imóveis", fontsize=9)
            ax.set_ylim(0, 110)
            ax.set_title("Sobreposição por Base (%)", fontsize=11, fontweight="bold",
                         color="#1B5E20", pad=8)
            ax.tick_params(axis="x", labelsize=7, rotation=30)
            ax.tick_params(axis="y", labelsize=8)

            for barra, val in zip(barras, valores):
                if val > 0:
                    ax.text(barra.get_x() + barra.get_width() / 2, barra.get_height() + 1.5,
                            f"{val:.0f}%", ha="center", fontsize=8, color="#37474F", fontweight="bold")

            fig.tight_layout()
            canvas = FigureCanvas(fig)
            canvas.setMinimumHeight(280)
            self._row1.addWidget(canvas)

        # ─────────────────────────────────────────────
        # GRÁFICO 3 — Evolução PRODES por ano
        # ─────────────────────────────────────────────

        def _grafico_prodes_anos(self):
            from matplotlib.figure import Figure
            from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas

            anos = defaultdict(float)

            for r in self._dados:
                detalhe = r.get("prodes_anos_detalhe") or ""
                if not detalhe:
                    continue
                # Formato: "2019: 5.20 ha | 2021: 8.30 ha"
                for parte in detalhe.split("|"):
                    parte = parte.strip()
                    if ":" in parte:
                        ano_str, ha_str = parte.split(":", 1)
                        try:
                            ano = ano_str.strip()
                            ha  = float(ha_str.replace("ha", "").strip())
                            if ano.isdigit():
                                anos[ano] += ha
                        except ValueError:
                            continue

            fig = Figure(figsize=(5.5, 4), facecolor="#FAFAFA")
            ax  = fig.add_subplot(111)
            ax.set_facecolor("#F5F7FA")

            if anos:
                anos_ord = dict(sorted(anos.items()))
                x = list(anos_ord.keys())
                y = list(anos_ord.values())

                ax.plot(x, y, color="#C62828", marker="o", linewidth=2,
                        markersize=7, markerfacecolor="white",
                        markeredgewidth=2, markeredgecolor="#C62828")
                ax.fill_between(x, y, alpha=0.12, color="#C62828")

                for xi, yi in zip(x, y):
                    ax.text(xi, yi + max(y) * 0.03, f"{yi:.1f}",
                            ha="center", fontsize=8, color="#C62828", fontweight="bold")

                ax.set_ylabel("Área Desmatada (ha)", fontsize=9)
                ax.tick_params(labelsize=8)
            else:
                ax.text(0.5, 0.5, "Sem dados de PRODES\nneste lote",
                        ha="center", va="center", transform=ax.transAxes,
                        fontsize=11, color="#90A4AE")

            ax.set_title("Desmatamento PRODES por Ano (ha)", fontsize=11,
                         fontweight="bold", color="#1B5E20", pad=8)
            fig.tight_layout()

            canvas = FigureCanvas(fig)
            canvas.setMinimumHeight(280)
            self._row2.addWidget(canvas)

        # ─────────────────────────────────────────────
        # GRÁFICO 4 — Histograma de área dos imóveis
        # ─────────────────────────────────────────────

        def _grafico_histograma_area(self):
            from matplotlib.figure import Figure
            from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas

            areas = [
                r["area_ha"] for r in self._dados
                if isinstance(r.get("area_ha"), (int, float)) and r["area_ha"] > 0
            ]

            fig = Figure(figsize=(5.5, 4), facecolor="#FAFAFA")
            ax  = fig.add_subplot(111)
            ax.set_facecolor("#F5F7FA")

            if areas:
                n_bins = min(15, max(5, len(areas) // 3))
                ax.hist(areas, bins=n_bins, color="#1565C0", edgecolor="white",
                        linewidth=0.5, alpha=0.85)
                ax.set_xlabel("Área (ha)", fontsize=9)
                ax.set_ylabel("Nº de Imóveis", fontsize=9)
                ax.tick_params(labelsize=8)

                media = sum(areas) / len(areas)
                ax.axvline(media, color="#C62828", linestyle="--", linewidth=1.5,
                           label=f"Média: {media:.1f} ha")
                ax.legend(fontsize=8)
            else:
                ax.text(0.5, 0.5, "Sem dados de área", ha="center", va="center",
                        transform=ax.transAxes, fontsize=11, color="#90A4AE")

            ax.set_title("Distribuição de Área dos Imóveis", fontsize=11,
                         fontweight="bold", color="#1B5E20", pad=8)
            fig.tight_layout()

            canvas = FigureCanvas(fig)
            canvas.setMinimumHeight(280)
            self._row2.addWidget(canvas)

    return DashboardWidget(parent)
