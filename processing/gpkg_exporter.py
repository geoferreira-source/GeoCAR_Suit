# -*- coding: utf-8 -*-
"""gpkg_exporter.py — Exporta GeoDataFrames para GeoPackage consolidado."""

import logging
from pathlib import Path
log = logging.getLogger("GeoCAR_Suite")

def exportar_gpkg(lista_gdfs: list, caminho_saida: str, nome_camada="imoveis_car") -> tuple:
    if not lista_gdfs:
        return False, "Nenhum GeoDataFrame para exportar"
    try:
        import geopandas as gpd
        import pandas as pd

        gdf = gpd.GeoDataFrame(pd.concat(lista_gdfs, ignore_index=True), crs=lista_gdfs[0].crs)
        if gdf.crs and gdf.crs.to_epsg() != 4326:
            gdf = gdf.to_crs("EPSG:4326")

        manter = [
            "codigo_car","uf","cod_ibge","municipio","area_ha","id_tema","status",
            "sobr_uc_federal_sim_nao","sobr_uc_federal_ha",
            "sobr_uc_estadual_sim_nao","sobr_uc_estadual_ha",
            "sobr_terra_indigena_sim_nao","sobr_terra_indigena_ha",
            "sobr_prodes_sim_nao","sobr_prodes_ha","prodes_anos_detalhe",
            "sobr_assentamento_sim_nao","sobr_assentamento_ha",
            "sobr_quilombo_sim_nao","sobr_quilombo_ha",
            "sobr_embargo_ibama_sim_nao","sobr_embargo_ibama_ha",
            "sobr_sigef_sim_nao","sobr_sigef_ha",
            "geometry",
        ]
        cols = [c for c in manter if c in gdf.columns]
        Path(caminho_saida).parent.mkdir(parents=True, exist_ok=True)
        gdf[cols].to_file(caminho_saida, layer=nome_camada, driver="GPKG")
        log.info(f"GeoPackage: {caminho_saida} ({len(gdf)} feição/feições)")
        return True, caminho_saida
    except ImportError:
        return False, "geopandas não instalado"
    except Exception as e:
        return False, f"Erro ao exportar GPKG: {e}"
