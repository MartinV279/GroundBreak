from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QThread, QObject, Signal, Slot
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from core.locations import Location, create_location, update_location
from core.offline_indexer import build_index, OfflineIndexMeta


class _IndexWorker(QObject):
    finished = Signal(object, object)  # meta or error

    def __init__(self, source_dir: str, index_dir: str) -> None:
        super().__init__()
        self._source_dir = source_dir
        self._index_dir = index_dir

    @Slot()
    def run(self) -> None:
        try:
            meta = build_index(Path(self._source_dir), Path(self._index_dir))
            self.finished.emit(meta, None)
        except Exception as exc:
            self.finished.emit(None, exc)


class LocationDialog(QDialog):
    def __init__(self, parent=None, location: Location | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Location")
        self.setModal(True)
        self.setWindowFlag(Qt.Tool)

        self._location: Location | None = location
        self._thread: Optional[QThread] = None
        self._worker: Optional[_IndexWorker] = None
        self._directory: str = location.directory if location is not None else ""

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.name_edit = QLineEdit(self)
        if location is not None:
            self.name_edit.setText(location.name)

        self.dir_label = QLabel(self._directory or "(no folder selected)", self)
        choose_btn = QPushButton("Choose folder…", self)
        choose_btn.clicked.connect(self._choose_folder)

        self.status_label = QLabel("Status: not configured", self)
        self.details_label = QLabel("", self)

        form.addRow("Name", self.name_edit)
        form.addRow("Folder", self.dir_label)
        form.addRow("", choose_btn)
        form.addRow("Status", self.status_label)
        form.addRow("Details", self.details_label)

        layout.addLayout(form)

        self.index_button = QPushButton("Build / Rebuild index", self)
        self.index_button.clicked.connect(self._start_index)
        layout.addWidget(self.index_button)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._refresh_status_initial()

    def _refresh_status_initial(self) -> None:
        loc = self._location
        if loc is None or not loc.directory:
            self.status_label.setText("Status: not configured")
            self.details_label.setText("")
            self.index_button.setEnabled(bool(self._directory))
            return

        self.dir_label.setText(loc.directory)
        meta_path = Path(loc.index_dir) / "meta.json"
        if not meta_path.exists():
            self.status_label.setText("Status: ready to process")
            self.details_label.setText("")
            self.index_button.setEnabled(True)
            return

        try:
            import json

            data = json.loads(meta_path.read_text(encoding="utf-8"))
            files = int(data.get("file_count", 0))
            chunks = int(data.get("chunk_count", 0))
            self.status_label.setText("Status: ready" if data.get("ready") else "Status: index present")
            self.details_label.setText(f"Files: {files}, chunks: {chunks}")
        except Exception:
            self.status_label.setText("Status: ready")
            self.details_label.setText("")
        self.index_button.setEnabled(True)

    def _choose_folder(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Choose location folder")
        if directory:
            self._directory = directory
            self.dir_label.setText(directory)
            self.status_label.setText("Status: ready to process")
            self.details_label.setText("")
            self.index_button.setEnabled(True)

    def _ensure_location_for_index(self) -> Location | None:
        directory = (self._directory or "").strip()
        name = self.name_edit.text().strip()
        if not directory:
            return None
        if self._location is None:
            self._location = create_location(name, directory)
        else:
            self._location.name = name or self._location.name
            self._location.directory = directory
            self._location.ready = False
            update_location(self._location)
        return self._location

    def _start_index(self) -> None:
        if self._thread is not None:
            return
        loc = self._ensure_location_for_index()
        if loc is None or not loc.directory:
            self.status_label.setText("Status: please choose a folder first")
            return

        self.status_label.setText("Status: processing…")
        self.details_label.setText("Building local index, this may take a while.")
        self.index_button.setEnabled(False)

        self._thread = QThread(self)
        self._worker = _IndexWorker(loc.directory, loc.index_dir)
        self._worker.moveToThread(self._thread)
        self._worker.finished.connect(self._on_index_finished)
        self._thread.started.connect(self._worker.run)
        self._thread.start()

    @Slot(object, object)
    def _on_index_finished(self, meta, error) -> None:
        if self._thread:
            self._thread.quit()
            self._thread.wait()
            self._thread.deleteLater()
        if self._worker:
            self._worker.deleteLater()
        self._thread = None
        self._worker = None

        if error is not None or meta is None:
            self.status_label.setText("Status: error")
            self.details_label.setText(str(error))
            self.index_button.setEnabled(bool(self._directory))
            return

        assert isinstance(meta, OfflineIndexMeta)
        self.status_label.setText("Status: ready")
        self.details_label.setText(f"Files: {meta.file_count}, chunks: {meta.chunk_count}")
        self.index_button.setEnabled(True)

        if self._location is not None:
            self._location.ready = True
            update_location(self._location)

    def get_location(self) -> Location | None:
        """Return the persisted Location for this dialog (if any)."""
        directory = (self._directory or "").strip()
        name = self.name_edit.text().strip()
        if not directory and self._location is None:
            return None
        if self._location is None:
            self._location = create_location(name, directory)
        else:
            if name:
                self._location.name = name
            if directory:
                self._location.directory = directory
        update_location(self._location)
        return self._location

