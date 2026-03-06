from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
    QPushButton,
)

from core.config import AppConfig


class SettingsDialog(QDialog):
    def __init__(self, config: AppConfig, model_options: list[str], mcp_status: str) -> None:
        super().__init__()
        self.setWindowTitle("Settings")
        self.setModal(True)
        self.setWindowFlag(Qt.Tool)

        self._config = config

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.title_field = QLineEdit(self)
        self.title_field.setText(config.window_title)

        self.model_combo = QComboBox(self)
        self.model_combo.setEditable(True)
        for m in model_options:
            self.model_combo.addItem(m)
        self.model_combo.setCurrentText(config.model)

        self.tool_output_spin = QSpinBox(self)
        self.tool_output_spin.setRange(500, 50000)
        self.tool_output_spin.setSingleStep(500)
        self.tool_output_spin.setValue(config.max_tool_output_chars)

        self.mcp_status_label = QLabel(mcp_status, self)

        form.addRow("Window title", self.title_field)
        form.addRow("Model", self.model_combo)
        form.addRow("Max tool output chars", self.tool_output_spin)
        form.addRow("MCP status", self.mcp_status_label)

        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def apply_to(self, config: AppConfig) -> None:
        config.window_title = self.title_field.text().strip() or config.window_title
        config.model = self.model_combo.currentText().strip() or config.model
        config.max_tool_output_chars = int(self.tool_output_spin.value())

