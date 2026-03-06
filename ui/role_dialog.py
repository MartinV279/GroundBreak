from __future__ import annotations

from PySide6.QtCore import Qt, QThread, Signal, QObject, Slot
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QComboBox,
    QCheckBox,
)

from core.role_prompts import generate_role_system_prompt
from core.roles import Role
from core.locations import list_locations, Location


class RoleDialog(QDialog):
    def __init__(self, parent=None, role: Role | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Role")
        self.setModal(True)
        self.setWindowFlag(Qt.Tool)

        self._role = role
        self._locations: list[Location] = list_locations()

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.name_edit = QLineEdit(self)
        self.description_edit = QTextEdit(self)
        self.system_prompt_edit = QTextEdit(self)

        # Hybrid / location selection
        self.hybrid_checkbox = QCheckBox("Enable hybrid (local + web)", self)
        self.location_combo = QComboBox(self)
        self.location_combo.addItem("(None)", userData=None)
        for loc in self._locations:
            self.location_combo.addItem(loc.name, userData=loc.id)

        if role is not None:
            self.name_edit.setText(role.name)
            self.description_edit.setPlainText(role.description)
            self.system_prompt_edit.setPlainText(role.system_prompt)
            if role.hybrid_enabled and role.attached_location_id:
                self.hybrid_checkbox.setChecked(True)
                # Pre-select attached location if present.
                for idx in range(self.location_combo.count()):
                    if self.location_combo.itemData(idx) == role.attached_location_id:
                        self.location_combo.setCurrentIndex(idx)
                        break

        generate_row = QHBoxLayout()
        generate_button = QPushButton("Generate prompt", self)
        self._generate_status = QLabel("", self)
        self._generate_status.setStyleSheet("color: #888; font-size: 11px;")
        self._gen_thread: QThread | None = None
        self._gen_worker: QObject | None = None

        generate_button.clicked.connect(self._on_generate_clicked)
        generate_row.addWidget(generate_button)
        generate_row.addWidget(self._generate_status)

        form.addRow("Name", self.name_edit)
        form.addRow("Description", self.description_edit)
        form.addRow("", generate_row)
        form.addRow("System prompt", self.system_prompt_edit)
        form.addRow("Hybrid search", self.hybrid_checkbox)
        form.addRow("Attached Location", self.location_combo)

        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_generate_clicked(self) -> None:
        if self._gen_thread is not None:
            # Generation already in progress; ignore extra clicks.
            return
        desc = self.description_edit.toPlainText().strip()
        if not desc:
            self._generate_status.setText("Enter a description first.")
            return
        self._generate_status.setText("Generating prompt...")

        class _Worker(QObject):
            finished = Signal(str)

            def __init__(self, text: str) -> None:
                super().__init__()
                self._text = text

            def run(self) -> None:
                prompt = generate_role_system_prompt(self._text) or ""
                self.finished.emit(prompt)

        thread = QThread(self)
        worker = _Worker(desc)
        worker.moveToThread(thread)

        self._gen_thread = thread
        self._gen_worker = worker

        worker.finished.connect(self._on_prompt_generated)
        thread.started.connect(worker.run)
        thread.finished.connect(self._on_thread_finished)
        thread.start()

    @Slot(str)
    def _on_prompt_generated(self, prompt: str) -> None:
        desc = self.description_edit.toPlainText().strip()
        if not prompt.strip():
            self._generate_status.setText("Failed to generate prompt.")
            return
        self.system_prompt_edit.setPlainText(prompt)
        if not self.name_edit.text().strip() and desc:
            title = desc.splitlines()[0]
            if len(title) > 60:
                title = title[:57].rstrip() + "..."
            self.name_edit.setText(title)
        self._generate_status.setText("Prompt generated.")
        if self._gen_thread is not None:
            self._gen_thread.quit()

    @Slot()
    def _on_thread_finished(self) -> None:
        if self._gen_worker is not None:
            self._gen_worker.deleteLater()
        if self._gen_thread is not None:
            self._gen_thread.deleteLater()
        self._gen_worker = None
        self._gen_thread = None

    def get_values(self) -> tuple[str, str, str, str | None, bool]:
        name = self.name_edit.text().strip()
        description = self.description_edit.toPlainText().strip()
        system_prompt = self.system_prompt_edit.toPlainText().strip()
        hybrid_enabled = self.hybrid_checkbox.isChecked()
        attached_location_id = self.location_combo.currentData()
        if hybrid_enabled and not attached_location_id:
            # Require a location when hybrid is enabled.
            hybrid_enabled = False
        return name, description, system_prompt, attached_location_id, hybrid_enabled

