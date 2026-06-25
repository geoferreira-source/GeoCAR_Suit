# -*- coding: utf-8 -*-
"""GeoCAR Suite — Classe principal do plugin QGIS"""

import os
from qgis.PyQt.QtWidgets import QAction
from qgis.PyQt.QtGui import QIcon


class GeoCARSuitePlugin:
    def __init__(self, iface):
        self.iface   = iface
        self.dialog  = None
        self.actions = []
        self.menu    = "GeoCAR Suite"

    def initGui(self):
        icon_path = os.path.join(os.path.dirname(__file__), "icon.png")
        icon = QIcon(icon_path) if os.path.exists(icon_path) else QIcon()
        self.action = QAction(icon, "GeoCAR Suite", self.iface.mainWindow())
        self.action.setToolTip("GeoCAR Suite — Gestão e análise do CAR-PA")
        self.action.triggered.connect(self.abrir)
        self.iface.addPluginToMenu(self.menu, self.action)
        self.iface.addToolBarIcon(self.action)
        self.actions.append(self.action)

    def unload(self):
        for action in self.actions:
            self.iface.removePluginMenu(self.menu, action)
            self.iface.removeToolBarIcon(action)

    def abrir(self):
        from .dialog import GeoCARDialog
        if self.dialog is None or not self.dialog.isVisible():
            self.dialog = GeoCARDialog(self.iface)
            self.dialog.show()
        else:
            self.dialog.raise_()
            self.dialog.activateWindow()
