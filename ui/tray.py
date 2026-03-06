from __future__ import annotations

from PySide6.QtCore import QObject, Signal, Slot
from PySide6.QtGui import QIcon, QAction
from PySide6.QtWidgets import QMenu, QSystemTrayIcon


class TrayController(QObject):
    show_hide_requested = Signal()
    settings_requested = Signal()
    quit_requested = Signal()

    def __init__(self, icon: QIcon, tooltip: str) -> None:
        super().__init__()
        self.tray = QSystemTrayIcon(icon)
        self.tray.setToolTip(tooltip)

        menu = QMenu()
        self.toggle_action = QAction("Show/Hide")
        self.settings_action = QAction("Settings…")
        self.quit_action = QAction("Quit")

        self.toggle_action.triggered.connect(self.show_hide_requested.emit)
        self.settings_action.triggered.connect(self.settings_requested.emit)
        self.quit_action.triggered.connect(self.quit_requested.emit)

        menu.addAction(self.toggle_action)
        menu.addSeparator()
        menu.addAction(self.settings_action)
        menu.addSeparator()
        menu.addAction(self.quit_action)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_activated)

    def show(self) -> None:
        self.tray.show()

    @Slot(QSystemTrayIcon.ActivationReason)
    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.Trigger:
            self.show_hide_requested.emit()

