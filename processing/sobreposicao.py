# -*- coding: utf-8 -*-
"""sobreposicao.py — Sobreposição espacial com bases locais (SHP + GPKG)."""

import logging
from pathlib import Path
from collections import defaultdict

log = logging.getLogger("GeoCAR_Suite")
EPSG_UTM_PADRAO = "EPSG:31982"

NOMES_EXIBICAO = {
    "uc_federal":    "UC Federal",
    "uc_estadual":   "UC Estadual",
    "terra_indigena":"Terra Indígena",
    "prodes":        "Desmatamento PRODES",
    "assentamento":  "Assentamento Federal",
    "quilombo":      "Quilombo Federal",
    "embargo_ibama": "Embargo IBAMA",
    "sigef":         "SIGEF",
}

CAMPO_ALT = {
    "uc_federal":    ["nome","nome_uc","name","nm_uc","nomobjetouc"],
    "uc_estadual":   ["nome","nome_uc","name","nm_uc","denominacao"],
    "terra_indigena":["terrai_nom","nome","name","ti_nome","nome_ti"],
    "prodes":        ["ano","year","class_name","classe","nome","id"],
    "assentamento":  ["nome_proje","nome","ds_nome","name","nm_projeto"],
    "quilombo":      ["nm_comunid","nome","name","nm_quilomb","comunidade"],
    "embargo_ibama": ["num_auto","nr_auto","numero_auto","nome","id_embargo"],
    "sigef":         ["denominacao","nome_imovel","nome","cod_imovel","situacao"],
}


def _carregar_bases():
    try:
        from .config_manager import obter_bases
    except Exception:
        from config_manager import obter_bases
    bases = {}
    for bid, info in obter_bases().items():
        bases[bid] = {
            "nome_exibicao": NOMES_EXIBICAO.get(bid, bid),
            "tipo":   info.get("tipo","shp"),
            "caminho":info.get("caminho"),
            "camada": info.get("camada"),
            "campo_nome": info.get("campo_nome","nome"),
            "campo_alt":  CAMPO_ALT.get(bid, ["nome"]),
        }
    return bases


def _ler_gdf(base_info):
    import geopandas as gpd
    tipo    = base_info.get("tipo","shp")
    caminho = base_info["caminho"]
    camada  = base_info.get("camada")
    if tipo == "gpkg":
        if not camada: raise ValueError("GPKG sem camada definida")
        return gpd.read_file(caminho, layer=camada)
    return gpd.read_file(caminho)


def _utm(gdf):
    try:
        lon = gdf.geometry.centroid.x.mean()
        if lon < -54: return "EPSG:31981"
        elif lon < -48: return "EPSG:31982"
        else: return "EPSG:31983"
    except Exception: return EPSG_UTM_PADRAO


def _overlay_seguro(gdf1, gdf2):
    import geopandas as gpd
    try:
        return gpd.overlay(gdf1[["geometry"]], gdf2, how="intersection", keep_geom_type=False)
    except Exception:
        g1 = gdf1.copy(); g1["geometry"] = g1.geometry.buffer(0)
        g2 = gdf2.copy(); g2["geometry"] = g2.geometry.buffer(0)
        try: return gpd.overlay(g1[["geometry"]], g2, how="intersection", keep_geom_type=False)
        except Exception: return None


def _encontrar_campo(colunas, campo_principal, alternativas):
    cl = [c.lower() for c in colunas]
    for c in [campo_principal] + alternativas:
        if c and c.lower() in cl:
            return colunas[cl.index(c.lower())]
    return None


def _extrair_nomes(gdf, campo):
    try:
        ns = gdf[campo].dropna().astype(str).str.strip().unique().tolist()
        return [n for n in ns if n and n.lower() not in ("none","nan","")]
    except Exception: return []


def _vazio(motivo=""):
    return {"sobrepoe":False,"area_ha":0.0,"nomes":[],"status":motivo}

def _vazio_prodes(motivo=""):
    return {"sobrepoe":False,"area_ha":0.0,"anos":{},"anos_lista":"","nomes":[],"status":motivo}


def _calcular(gdf_imovel, base_info):
    try:
        import geopandas as gpd
        gdf_base = _ler_gdf(base_info)
        if gdf_base.empty: return _vazio("base vazia")
        if gdf_base.crs != gdf_imovel.crs:
            gdf_base = gdf_base.to_crs(gdf_imovel.crs)
        bbox = gdf_imovel.total_bounds
        gdf_f = gdf_base.cx[bbox[0]:bbox[2], bbox[1]:bbox[3]]
        if gdf_f.empty: return {"sobrepoe":False,"area_ha":0.0,"nomes":[],"status":"ok"}
        inter = _overlay_seguro(gdf_imovel, gdf_f)
        if inter is None or inter.empty: return {"sobrepoe":False,"area_ha":0.0,"nomes":[],"status":"ok"}
        area_ha = round(inter.to_crs(_utm(gdf_imovel)).geometry.area.sum() / 10_000, 4)
        if area_ha <= 0: return {"sobrepoe":False,"area_ha":0.0,"nomes":[],"status":"ok"}
        campo = _encontrar_campo(inter.columns.tolist(), base_info["campo_nome"], base_info["campo_alt"])
        nomes = _extrair_nomes(inter, campo) if campo else []
        log.info(f"  ✓ {base_info['nome_exibicao']}: {area_ha:.2f} ha")
        return {"sobrepoe":True,"area_ha":area_ha,"nomes":nomes,"status":"ok"}
    except ImportError: return _vazio("geopandas não instalado")
    except Exception as e: log.error(f"  Erro [{base_info['nome_exibicao']}]: {e}"); return _vazio(str(e))


def _calcular_prodes(gdf_imovel, base_info):
    try:
        import geopandas as gpd
        gdf_base = _ler_gdf(base_info)
        if gdf_base.empty: return _vazio_prodes("base vazia")
        if gdf_base.crs != gdf_imovel.crs:
            gdf_base = gdf_base.to_crs(gdf_imovel.crs)
        bbox = gdf_imovel.total_bounds
        gdf_f = gdf_base.cx[bbox[0]:bbox[2], bbox[1]:bbox[3]]
        if gdf_f.empty: return _vazio_prodes()
        inter = _overlay_seguro(gdf_imovel, gdf_f)
        if inter is None or inter.empty: return _vazio_prodes()
        inter_utm = inter.to_crs(_utm(gdf_imovel))
        inter_utm["_area_ha"] = inter_utm.geometry.area / 10_000
        area_total = round(inter_utm["_area_ha"].sum(), 4)
        if area_total <= 0: return _vazio_prodes()
        campo = _encontrar_campo(inter_utm.columns.tolist(), base_info["campo_nome"], base_info["campo_alt"])
        anos = defaultdict(float)
        if campo:
            for _, row in inter_utm.iterrows():
                ano = str(row.get(campo,"S/D")).strip()
                if not ano or ano.lower() in ("none","nan",""): ano = "S/D"
                anos[ano] = round(anos[ano] + row.get("_area_ha",0.0), 4)
        anos_ord = dict(sorted(anos.items()))
        anos_lista = " | ".join(f"{a}: {h:.2f} ha" for a, h in anos_ord.items())
        log.info(f"  ✓ PRODES: {area_total:.2f} ha | {list(anos_ord.keys())}")
        return {"sobrepoe":True,"area_ha":area_total,"anos":anos_ord,
                "anos_lista":anos_lista,"nomes":list(anos_ord.keys()),"status":"ok"}
    except ImportError: return _vazio_prodes("geopandas não instalado")
    except Exception as e: log.error(f"  Erro [PRODES]: {e}"); return _vazio_prodes(str(e))


def calcular_sobreposicoes(gdf_imovel) -> dict:
    BASES = _carregar_bases()
    resultados = {}
    for bid, info in BASES.items():
        caminho = info.get("caminho")
        if not caminho:
            resultados[bid] = _vazio("não configurada"); continue
        if not Path(caminho).exists():
            log.warning(f"  [{info['nome_exibicao']}] não encontrado: {caminho}")
            resultados[bid] = _vazio("arquivo não encontrado"); continue
        log.info(f"  Verificando: {info['nome_exibicao']}")
        resultados[bid] = _calcular_prodes(gdf_imovel, info) if bid == "prodes" else _calcular(gdf_imovel, info)
    return resultados


def formatar_para_relatorio(resultados: dict) -> dict:
    campos = {}
    for bid, res in resultados.items():
        p = f"sobr_{bid}"
        campos[f"{p}_sim_nao"] = "SIM" if res["sobrepoe"] else "NÃO"
        campos[f"{p}_ha"]      = res["area_ha"]
        campos[f"{p}_nomes"]   = " | ".join(res.get("nomes",[])) if res.get("nomes") else ""
        if bid == "prodes":
            campos["prodes_anos_detalhe"] = res.get("anos_lista","")
            for ano, area in res.get("anos",{}).items():
                campos[f"prodes_{ano}_ha"] = area
    return campos
