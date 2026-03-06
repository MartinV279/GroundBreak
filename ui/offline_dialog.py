from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QThread, QObject, Signal, Slot
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from core.offline_config import load_offline_config, save_offline_config, OfflineConfig
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


class OfflineDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Offline Mode")
        self.setModal(True)
        self.setWindowFlag(Qt.Tool)

        self._cfg = load_offline_config()
        self._thread: Optional[QThread] = None
        self._worker: Optional[_IndexWorker] = None

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.enabled_checkbox = QCheckBox("Enable offline mode", self)
        self.enabled_checkbox.setChecked(self._cfg.enabled)

        self.dir_label = QLabel(self._cfg.source_dir or "(no folder selected)", self)
        choose_btn = QPushButton("Choose folder…", self)
        choose_btn.clicked.connect(self._choose_folder)

        self.status_label = QLabel("Status: not configured", self)
        self.progress_label = QLabel("", self)

        form.addRow("", self.enabled_checkbox)
        form.addRow("Folder", self.dir_label)
        form.addRow("", choose_btn)
        form.addRow("Status", self.status_label)
        form.addRow("Details", self.progress_label)

        layout.addLayout(form)

        self.index_button = QPushButton("Build / Rebuild index", self)
        self.index_button.clicked.connect(self._start_index)
        layout.addWidget(self.index_button)

        buttons = QDialogButtonBox(QDialogButtonBox.Close, self)
        buttons.rejected.connect(self._on_close_clicked)
        layout.addWidget(buttons)

        self._refresh_status_initial()

    def _refresh_status_initial(self) -> None:
        if not self._cfg.source_dir:
            self.status_label.setText("Status: not configured")
            self.progress_label.setText("")
        else:
            index_dir = Path(self._cfg.index_dir)
            meta_path = index_dir / "meta.json"
            if meta_path.exists():
                self.status_label.setText("Status: ready")
            else:
                # Index missing => offline mode cannot actually be active.
                self.status_label.setText("Status: ready to process")
                self._cfg.enabled = False
                self.enabled_checkbox.setChecked(False)

    def _choose_folder(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Choose offline knowledge folder")
        if directory:
            self._cfg.source_dir = directory
            self.dir_label.setText(directory)
            self.status_label.setText("Status: ready to process")
            self.progress_label.setText("")
            save_offline_config(self._cfg)

    def _start_index(self) -> None:
        if not self._cfg.source_dir:
            self.status_label.setText("Status: please choose a folder first")
            return
        if self._thread is not None:
            return
        self.status_label.setText("Status: processing…")
        self.progress_label.setText("Building local index, this may take a while.")

        self._thread = QThread(self)
        self._worker = _IndexWorker(self._cfg.source_dir, self._cfg.index_dir)
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
            self.progress_label.setText(str(error))
            return

        assert isinstance(meta, OfflineIndexMeta)
        self.status_label.setText("Status: ready")
        self.progress_label.setText(
            f"Files: {meta.file_count}, chunks: {meta.chunk_count}"
        )
        # When indexing succeeds, consider offline mode ready and keep the
        # checkbox state (user can still turn it off explicitly).

    def _on_close_clicked(self) -> None:
        # Save enable/disable state when closing dialog.
        self._cfg.enabled = self.enabled_checkbox.isChecked()
        save_offline_config(self._cfg)
        self.close()

