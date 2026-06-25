# -*- coding: utf-8 -*-
"""
geojson_processor.py — GeoCAR Suite
Converte GeoJSON → GeoDataFrame com área e município.

Ordem de prioridade para o município:
  1. Properties do GeoJSON retornado pela API (mais preciso)
  2. Lookup pelo código IBGE no número do CAR (fallback)
"""

import logging
log = logging.getLogger("GeoCAR_Suite")

# Todos os 144 municípios do Pará com código IBGE
MUNICIPIOS_PA = {
    "1500107":"Abaetetuba","1500206":"Abel Figueiredo","1500305":"Acará",
    "1500404":"Afuá","1500503":"Água Azul do Norte","1500602":"Alenquer",
    "1500701":"Almeirim","1500800":"Altamira","1500859":"Anapu",
    "1500909":"Augusto Corrêa","1501006":"Aurora do Pará","1501105":"Aveiro",
    "1501204":"Bagre","1501303":"Baião","1501402":"Bannach",
    "1501501":"Barcarena","1501600":"Belém","1501709":"Belterra",
    "1501808":"Benevides","1501907":"Bom Jesus do Tocantins","1502004":"Bonito",
    "1502103":"Bragança","1502152":"Brasil Novo","1502202":"Brejo Grande do Araguaia",
    "1502301":"Breu Branco","1502400":"Breves","1502509":"Bujaru",
    "1502608":"Cachoeira do Arari","1502707":"Cametá","1502756":"Canaã dos Carajás",
    "1502806":"Capanema","1502905":"Capitão Poço","1503002":"Castanhal",
    "1503101":"Chaves","1503200":"Colares","1503309":"Conceição do Araguaia",
    "1503408":"Concórdia do Pará","1503457":"Cumaru do Norte","1503507":"Curionópolis",
    "1503606":"Curralinho","1503705":"Curuá","1503804":"Curuçá",
    "1503903":"Dom Eliseu","1504000":"Eldorado dos Carajás","1504109":"Faro",
    "1504208":"Floresta do Araguaia","1504307":"Garrafão do Norte",
    "1504406":"Goianésia do Pará","1504455":"Gran Pará","1504505":"Gurupá",
    "1504604":"Igarapé-Açu","1504703":"Igarapé-Miri","1504802":"Inhangapi",
    "1504901":"Ipixuna do Pará","1505007":"Irituia","1505106":"Itaituba",
    "1505205":"Itupiranga","1505304":"Jacareacanga","1505403":"Jacundá",
    "1505502":"Juruti","1505601":"Limoeiro do Ajuru","1505635":"Mãe do Rio",
    "1505700":"Marabá","1505809":"Maracanã","1505908":"Marapanim",
    "1506005":"Medicilândia","1506104":"Melgaço","1506203":"Mocajuba",
    "1506302":"Moju","1506351":"Mojuí dos Campos","1506401":"Monte Alegre",
    "1506500":"Muaná","1506559":"Nova Esperança do Piriá","1506609":"Nova Ipixuna",
    "1506708":"Nova Timboteua","1506807":"Novo Progresso","1506906":"Novo Repartimento",
    "1507003":"Óbidos","1507102":"Oeiras do Pará","1507201":"Oriximiná",
    "1507300":"Ourém","1507409":"Ourilândia do Norte","1507458":"Pacajá",
    "1507508":"Palestina do Pará","1507607":"Paragominas","1507706":"Parauapebas",
    "1507755":"Pau D'Arco","1507805":"Peixe-Boi","1507904":"Piçarra",
    "1508001":"Placas","1508100":"Ponta de Pedras","1508209":"Portel",
    "1508308":"Porto de Moz","1508407":"Prainha","1508506":"Primavera",
    "1508605":"Quatipuru","1508704":"Redenção","1508803":"Rio Maria",
    "1508902":"Rondon do Pará","1509007":"Rurópolis","1509108":"Salinópolis",
    "1509207":"Salvaterra","1509304":"Santa Bárbara do Pará",
    "1509403":"Santa Cruz do Arari","1509502":"Santa Isabel do Pará",
    "1509601":"Santa Luzia do Pará","1509700":"Santa Maria das Barreiras",
    "1509807":"Santa Maria do Pará","1509906":"Santana do Araguaia",
    "1510007":"Santarém","1510106":"Santarém Novo","1510205":"Santo Antônio do Tauá",
    "1510304":"São Caetano de Odivelas","1510403":"São Domingos do Araguaia",
    "1510502":"São Domingos do Capim","1510601":"São Félix do Xingu",
    "1510700":"São Francisco do Pará","1510809":"São João da Ponta",
    "1510908":"São João de Pirabas","1511005":"São João do Araguaia",
    "1511104":"São Miguel do Guamá","1511203":"São Sebastião da Boa Vista",
    "1511302":"Sapucaia","1511401":"Senador José Porfírio","1511500":"Soure",
    "1511599":"Tailândia","1511608":"Terra Alta","1511706":"Terra Santa",
    "1511805":"Tomé-Açu","1511904":"Tracuateua","1512001":"Trairão",
    "1512100":"Tucumã","1512209":"Tucuruí","1512308":"Ulianópolis",
    "1512407":"Uruará","1512506":"Vigia","1512605":"Viseu",
    "1512703":"Vitória do Xingu","1512802":"Xinguara",
}

# Campos possíveis de município nas properties do GeoJSON (ordem de prioridade)
_CAMPOS_MUNICIPIO = [
    "municipio","nm_municipio","nome_municipio","municipality",
    "nome_mun","ds_municipio","mun","cidade","nm_mun",
    "municipio_nome","ds_nome","nome",
]

# Campos possíveis de UF
_CAMPOS_UF = [
    "uf","estado","sg_uf","state","nm_uf","sigla_uf",
]


def processar_geojson(codigo_car: str, geojson: dict) -> tuple:
    """
    Converte GeoJSON da API SEMAS-PA em GeoDataFrame com área e município.

    Prioridade do município:
      1. Properties do GeoJSON (campo municipio, nm_municipio, etc.)
      2. Lookup pelo código IBGE do CAR (tabela completa 144 municípios)
      3. Fallback: UF/CódIBGE como referência
    """
    try:
        import geopandas as gpd
        from shapely.geometry import shape

        # Normalizar para Feature
        if geojson.get("type") == "Feature":
            feature = geojson
        else:
            feature = {
                "type":       "Feature",
                "geometry":   geojson.get("geometry", geojson),
                "properties": geojson.get("properties", {}),
            }

        geometria = shape(feature["geometry"])
        if geometria.is_empty:
            return False, "Geometria vazia"

        props = feature.get("properties") or {}

        # Log das properties recebidas (para diagnóstico)
        if props:
            log.debug(f"  Properties da API: {list(props.keys())}")

        gdf = gpd.GeoDataFrame([props], geometry=[geometria], crs="EPSG:4326")

        # Área em hectares
        epsg    = _utm(geometria)
        area_ha = round(gdf.to_crs(epsg).geometry.area.iloc[0] / 10_000, 4)

        # UF e código IBGE do número do CAR
        partes   = codigo_car.strip().upper().split("-")
        uf       = partes[0] if len(partes) > 0 else "N/D"
        cod_ibge = partes[1] if len(partes) > 1 else "N/D"

        # ── 1ª prioridade: properties do GeoJSON ──
        municipio = _extrair_municipio(props)

        # ── 2ª prioridade: tabela IBGE completa ──
        if not municipio:
            municipio = MUNICIPIOS_PA.get(cod_ibge, "")
            if municipio:
                log.debug(f"  Município via IBGE ({cod_ibge}): {municipio}")

        # ── 3ª prioridade: fallback legível ──
        if not municipio:
            municipio = f"{uf}/{cod_ibge}"
            log.warning(
                f"  Município não identificado para CAR {codigo_car}. "
                f"Código IBGE {cod_ibge} não está na tabela. "
                f"Usando '{municipio}' como referência. "
                f"Considere adicionar o município em geojson_processor.py."
            )

        # UF das properties (sobrescreve se disponível)
        uf_props = _extrair_uf(props)
        if uf_props:
            uf = uf_props

        gdf["codigo_car"] = codigo_car
        gdf["uf"]         = uf
        gdf["cod_ibge"]   = cod_ibge
        gdf["municipio"]  = municipio
        gdf["area_ha"]    = area_ha
        gdf["status"]     = "ok"

        log.info(f"  Geometria OK | {area_ha:.2f} ha | {municipio} ({uf})")
        return True, gdf

    except ImportError:
        return False, "geopandas não instalado. Execute: pip install geopandas"
    except Exception as e:
        return False, f"Erro ao processar GeoJSON: {e}"


def _extrair_municipio(props: dict) -> str:
    """Extrai município das properties do GeoJSON, testando campos comuns."""
    if not props:
        return ""
    pl = {k.lower(): v for k, v in props.items()}
    for campo in _CAMPOS_MUNICIPIO:
        v = pl.get(campo)
        if v and isinstance(v, str):
            v = v.strip()
            if v and v.lower() not in ("none", "null", "n/d", "", "nan"):
                log.debug(f"  Município via property '{campo}': {v}")
                return v
    return ""


def _extrair_uf(props: dict) -> str:
    """Extrai UF das properties do GeoJSON."""
    if not props:
        return ""
    pl = {k.lower(): v for k, v in props.items()}
    for campo in _CAMPOS_UF:
        v = pl.get(campo)
        if v and isinstance(v, str):
            v = v.strip().upper()
            if len(v) == 2 and v.isalpha():
                return v
    return ""


def _utm(geometria) -> str:
    """Escolhe EPSG UTM SIRGAS 2000 adequado para o Pará."""
    try:
        lon = geometria.centroid.x
        if lon < -54: return "EPSG:31981"
        elif lon < -48: return "EPSG:31982"
        else: return "EPSG:31983"
    except Exception:
        return "EPSG:31982"
