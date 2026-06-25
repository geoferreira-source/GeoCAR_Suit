# -*- coding: utf-8 -*-
"""GeoCAR Suite — Plugin QGIS | Miguel A. L. Ferreira"""

def classFactory(iface):
    from .car_analyzer import GeoCARSuitePlugin
    return GeoCARSuitePlugin(iface)
