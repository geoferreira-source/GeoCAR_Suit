# -*- coding: utf-8 -*-
"""config_manager.py — Gerencia config.json (SHP + GPKG)."""

import json, logging
from pathlib import Path

log = logging.getLogger("GeoCAR_Suite")
CONFIG_PATH = Path(__file__).parent.parent / "config.json"

DEFAULTS = {
    "bases": {
        "uc_federal":     {"tipo":"shp","caminho":None,"camada":None,"campo_nome":"nome"},
        "uc_estadual":    {"tipo":"shp","caminho":None,"camada":None,"campo_nome":"nome"},
        "terra_indigena": {"tipo":"shp","caminho":None,"camada":None,"campo_nome":"terrai_nom"},
        "prodes":         {"tipo":"shp","caminho":None,"camada":None,"campo_nome":"ano"},
        "assentamento":   {"tipo":"shp","caminho":None,"camada":None,"campo_nome":"nome_proje"},
        "quilombo":       {"tipo":"shp","caminho":None,"camada":None,"campo_nome":"nm_comunid"},
        "embargo_ibama":  {"tipo":"shp","caminho":None,"camada":None,"campo_nome":"num_auto"},
        "sigef":          {"tipo":"shp","caminho":None,"camada":None,"campo_nome":"denominacao"},
    },
    "opcoes": {
        "timeout_api":30,"zoom_automatico":True,
        "calcular_sobreposicoes":True,"carregar_qgis":True,
    }
}

def carregar() -> dict:
    if not CONFIG_PATH.exists():
        _criar_template(); return DEFAULTS.copy()
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            return _mesclar(DEFAULTS, json.load(f))
    except Exception as e:
        log.error(f"config.json: {e}"); return DEFAULTS.copy()

def obter_bases() -> dict: return carregar().get("bases", DEFAULTS["bases"])
def obter_opcoes() -> dict: return carregar().get("opcoes", DEFAULTS["opcoes"])
def obter_opcao(chave, padrao=None): return obter_opcoes().get(chave, padrao)

def salvar(config: dict) -> bool:
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        log.error(f"Salvar config: {e}"); return False

def listar_camadas_gpkg(caminho: str) -> list:
    try:
        import sqlite3
        conn = sqlite3.connect(caminho)
        cur = conn.cursor()
        cur.execute("SELECT table_name FROM gpkg_contents WHERE data_type='features'")
        camadas = [r[0] for r in cur.fetchall()]
        conn.close(); return camadas
    except Exception as e:
        log.warning(f"GPKG camadas: {e}"); return []

def validar() -> list:
    status = []
    for base_id, info in obter_bases().items():
        caminho = info.get("caminho"); ok = False
        if not caminho: situacao = "⚠ Não configurada"
        elif not Path(caminho).exists(): situacao = "✗ Não encontrado"
        else:
            try:
                mb = Path(caminho).stat().st_size / 1_048_576
                situacao = f"✓ OK ({mb:.1f} MB)"; ok = True
            except Exception as e: situacao = f"✗ {e}"
        status.append({"base_id":base_id,"caminho":caminho or "—","ok":ok,"situacao":situacao})
    return status

def _criar_template():
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump({"_instrucoes":"Preencha os caminhos.", "bases":{
                k:{"tipo":"shp","caminho":None,"camada":None,"campo_nome":v["campo_nome"]}
                for k,v in DEFAULTS["bases"].items()},
                "opcoes":DEFAULTS["opcoes"]}, f, indent=2, ensure_ascii=False)
    except Exception as e: log.error(f"Template: {e}")

def _mesclar(base, sobrepor):
    r = base.copy()
    for k,v in sobrepor.items():
        if k in r and isinstance(r[k],dict) and isinstance(v,dict):
            r[k] = _mesclar(r[k], v)
        else: r[k] = v
    return r
