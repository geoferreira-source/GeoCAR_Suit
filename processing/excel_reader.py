# -*- coding: utf-8 -*-
"""excel_reader.py — Lê planilha de entrada com códigos CAR."""

import logging
from pathlib import Path

log = logging.getLogger("GeoCAR_Suite")

COLUNAS_ACEITAS = [
    "codigo_car","codigocar","cod_car","car","numero_car",
    "numerocar","num_car","numero","code","cod_imovel",
]

def ler_planilha(caminho: str) -> tuple:
    arquivo = Path(caminho)
    if not arquivo.exists():
        return False, f"Arquivo não encontrado: {caminho}"
    try:
        import pandas as pd
        df = pd.read_csv(arquivo, dtype=str, encoding="utf-8-sig") \
            if arquivo.suffix.lower() == ".csv" \
            else pd.read_excel(arquivo, dtype=str)
        if df.empty:
            return False, "Planilha vazia"
        col_car = _encontrar_coluna(df.columns.tolist())
        if not col_car:
            col_car = df.columns[0]
            log.warning(f"Coluna CAR não identificada. Usando: '{col_car}'")
        lista = []
        for i, valor in enumerate(df[col_car].dropna(), start=2):
            codigo = str(valor).strip().upper()
            if codigo and len(codigo) > 10:
                lista.append({"codigo_car": codigo, "linha": i})
        if not lista:
            return False, "Nenhum código CAR válido encontrado"
        log.info(f"{len(lista)} CAR(s) carregados de '{col_car}'")
        return True, lista
    except ImportError:
        return False, "pandas não instalado. Execute: pip install pandas openpyxl"
    except Exception as e:
        return False, f"Erro ao ler planilha: {e}"

def _encontrar_coluna(colunas):
    for col in colunas:
        cl = col.strip().lower().replace(" ","_").replace("-","_")
        if cl in COLUNAS_ACEITAS:
            return col
        if any(kw in cl for kw in ["car","imovel","imóvel","codigo"]):
            return col
    return None
