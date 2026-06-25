# -*- coding: utf-8 -*-
"""qgis_loader.py — Carrega GeoPackage no QGIS (deve ser chamado na thread principal)."""

import logging
log = logging.getLogger("GeoCAR_Suite")

def carregar_gpkg(iface, caminho_gpkg: str, nome_camada="GeoCAR Suite — Imóveis") -> tuple:
    try:
        from qgis.core import QgsVectorLayer, QgsProject
        from qgis.PyQt.QtGui import QColor

        _remover_camada(nome_camada)
        uri   = f"{caminho_gpkg}|layername=imoveis_car"
        layer = QgsVectorLayer(uri, nome_camada, "ogr")
        if not layer.isValid():
            return False, f"Camada inválida: {caminho_gpkg}"

        _simbologia(layer)
        QgsProject.instance().addMapLayer(layer)

        if layer.featureCount() > 0:
            _zoom(iface, layer)

        n = layer.featureCount()
        log.info(f"QGIS: {n} feição(ões) carregada(s)")
        return True, f"{n} imóvel(is) carregados"
    except Exception as e:
        return False, str(e)

def _remover_camada(nome):
    try:
        from qgis.core import QgsProject
        for lid, lyr in list(QgsProject.instance().mapLayers().items()):
            if lyr.name() == nome:
                QgsProject.instance().removeMapLayer(lid)
    except Exception: pass

def _simbologia(layer):
    try:
        from qgis.PyQt.QtGui import QColor
        r = layer.renderer()
        if not r: return
        s = r.symbol()
        if not s: return
        if layer.geometryType() == 2:
            sl = s.symbolLayer(0)
            if sl:
                sl.setFillColor(QColor("#FFEB3B"))
                sl.setStrokeColor(QColor("#1B5E20"))
                sl.setStrokeWidth(1.2)
            s.setOpacity(0.20)
        layer.triggerRepaint()
    except Exception as e:
        log.warning(f"Simbologia: {e}")

def _zoom(iface, layer):
    try:
        from qgis.core import QgsRectangle
        ext = layer.extent()
        mx, my = ext.width()*0.10, ext.height()*0.10
        ext_m = QgsRectangle(
            ext.xMinimum()-mx, ext.yMinimum()-my,
            ext.xMaximum()+mx, ext.yMaximum()+my
        )
        iface.mapCanvas().setExtent(ext_m)
        iface.mapCanvas().refresh()
    except Exception as e:
        log.warning(f"Zoom: {e}")
