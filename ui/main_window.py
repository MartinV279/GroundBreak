from __future__ import annotations

from html import escape

import markdown
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QMainWindow,
)

from core.config import AppConfig
from core.sessions import ChatSession
from core.roles import Role
from core.locations import Location
from ui.session_sidebar import SessionSidebar


class MainWindow(QMainWindow):
    """Compact popup-style chat window."""

    send_message = Signal(str)
    open_settings = Signal()
    new_general_chat = Signal()
    new_role_chat = Signal(str)
    new_role = Signal()
    edit_role = Signal(str)
    delete_role = Signal(str)
    new_location = Signal()
    edit_location = Signal(str)
    delete_location = Signal(str)
    new_location_chat = Signal(str)
    load_chat = Signal(str)
    rename_chat = Signal(str, str)
    delete_chat = Signal(str)

    def __init__(self, config: AppConfig) -> None:
        super().__init__()
        self._config = config
        self._build_ui()

    def _build_ui(self) -> None:
        self.setWindowTitle(self._config.window_title)
        self.resize(480, 640)
        self.setWindowFlag(Qt.Tool)
        self.setWindowFlag(Qt.WindowStaysOnTopHint)

        central = QWidget(self)
        layout = QVBoxLayout(central)

        self.sidebar = SessionSidebar()
        self.sidebar.new_general_chat_requested.connect(self.new_general_chat.emit)
        self.sidebar.new_role_chat_requested.connect(self.new_role_chat.emit)
        self.sidebar.new_role_requested.connect(self.new_role.emit)
        self.sidebar.new_location_requested.connect(self.new_location.emit)
        self.sidebar.session_load_requested.connect(self.load_chat.emit)
        self.sidebar.session_rename_requested.connect(self.rename_chat.emit)
        self.sidebar.session_delete_requested.connect(self.delete_chat.emit)
        self.sidebar.role_edit_requested.connect(self.edit_role.emit)
        self.sidebar.role_delete_requested.connect(self.delete_role.emit)
        self.sidebar.edit_location_requested.connect(self.edit_location.emit)
        self.sidebar.delete_location_requested.connect(self.delete_location.emit)
        self.sidebar.new_location_chat_requested.connect(self.new_location_chat.emit)

        self.chat_view = QTextEdit(self)
        self.chat_view.setReadOnly(True)
        self.chat_view.setPlaceholderText("Chat with the model...")
        self.chat_view.setStyleSheet(
            "QTextEdit { background-color: #fafafa; border: 1px solid #ddd; border-radius: 6px; }"
        )

        self.chat_title_label = QLabel("Chat", self)
        self.chat_title_label.setStyleSheet("font-weight: bold; font-size: 12px;")

        self.status_label = QLabel("", self)
        self.status_label.setStyleSheet("color: #888; font-size: 11px;")

        self.role_prompt_view = QTextEdit(self)
        self.role_prompt_view.setReadOnly(True)
        self.role_prompt_view.setPlaceholderText("Role system prompt...")
        self.role_prompt_view.setVisible(False)
        self.role_prompt_view.setStyleSheet("font-size: 11px; color: #555;")
        self.sources_label = QLabel("", self)
        self.sources_label.setStyleSheet("color: #666; font-size: 10px;")
        self.sources_label.setTextFormat(Qt.RichText)
        self.sources_label.setOpenExternalLinks(True)
        self.mode_label = QLabel("Mode: Online", self)
        self.mode_label.setStyleSheet("color: #666; font-size: 10px;")

        input_row = QHBoxLayout()
        self.input_field = QLineEdit(self)
        self.input_field.setPlaceholderText("Type a message and press Enter...")
        self.input_field.returnPressed.connect(self._on_send_clicked)

        self.send_button = QPushButton("Send", self)
        self.send_button.clicked.connect(self._on_send_clicked)

        self.settings_button = QPushButton("Settings", self)
        self.settings_button.clicked.connect(self.open_settings.emit)

        input_row.addWidget(self.input_field)
        input_row.addWidget(self.send_button)
        input_row.addWidget(self.settings_button)

        splitter = QSplitter(Qt.Horizontal, self)
        splitter.addWidget(self.sidebar)
        splitter.addWidget(self.chat_view)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([140, 340])

        layout.addWidget(splitter, 1)
        layout.addWidget(self.chat_title_label)
        layout.addWidget(self.status_label)
        layout.addWidget(self.mode_label)
        layout.addWidget(self.role_prompt_view)
        layout.addWidget(self.sources_label)
        layout.addLayout(input_row)

        central.setLayout(layout)
        self.setCentralWidget(central)

    def _append_html(self, html: str) -> None:
        self.chat_view.append(html)

    def _append_markdown_block(self, speaker: str, text: str) -> None:
        """Render markdown content from the model into the chat view."""
        html_body = markdown.markdown(
            text,
            extensions=["fenced_code", "tables"],
        )
        if speaker == "Assistant":
            block = (
                "<div style='margin-top:6px; margin-right:40px;'>"
                "<div style='display:inline-block; background-color:#f0f0f0; "
                "border-radius:8px; padding:6px 8px;'>"
                f"<b>{escape(speaker)}:</b><br/>{html_body}"
                "</div></div>"
            )
        else:
            block = f"<b>{escape(speaker)}:</b><br/>{html_body}"
        self._append_html(block)

    def _set_input_enabled(self, enabled: bool) -> None:
        self.input_field.setEnabled(enabled)
        self.send_button.setEnabled(enabled)

    def _on_send_clicked(self) -> None:
        text = self.input_field.text().strip()
        if not text:
            return
        self._set_input_enabled(False)
        user_html = (
            "<div style='margin-top:6px; margin-left:40px;'>"
            "<div style='display:inline-block; background-color:#e0f7ff; "
            "border-radius:8px; padding:6px 8px;'>"
            f"<b>You:</b> {escape(text)}"
            "</div></div>"
        )
        self._append_html(user_html)
        self.input_field.clear()
        self.send_message.emit(text)

    @Slot(str)
    def add_assistant_message(self, text: str) -> None:
        # Only render the assistant's final response as markdown in the chat view.
        self._append_markdown_block("Assistant", text)
        self._set_input_enabled(True)

    def append_user_history(self, text: str) -> None:
        """Render a past user message without affecting input state."""
        user_html = (
            "<div style='margin-top:6px; margin-left:40px;'>"
            "<div style='display:inline-block; background-color:#e0f7ff; "
            "border-radius:8px; padding:6px 8px;'>"
            f"<b>You:</b> {escape(text)}"
            "</div></div>"
        )
        self._append_html(user_html)

    def append_assistant_history(self, text: str) -> None:
        """Render a past assistant message without affecting input state."""
        self._append_markdown_block("Assistant", text)

    @Slot(str, dict)
    def on_tool_started(self, name: str, arguments: dict) -> None:
        # Show tool usage in a small status area, not in the chat stream.
        summary_parts = []
        for key, value in list(arguments.items())[:3]:
            summary_parts.append(f"{key}={escape(repr(value))}")
        summary = ", ".join(summary_parts)
        self.status_label.setText(f"Running tool: {escape(name)}({summary})")

    @Slot(str, str, bool)
    def on_tool_finished(self, name: str, preview: str, success: bool) -> None:
        status = "OK" if success else "FAILED"
        self.status_label.setText(f"Tool {escape(name)}: {status}")

    @Slot(str)
    def on_error(self, message: str) -> None:
        # Suppress tool errors from the main chat stream; they are reflected
        # via the status line and tool_finished signal instead.
        if message.lstrip().startswith("Tool error for "):
            return
        self._append_html(f"<span style='color: #c00;'>[error] {escape(message)}</span>")
        self.status_label.setText("")
        self._set_input_enabled(True)

    def clear_chat_view(self) -> None:
        self.chat_view.clear()
        self.status_label.setText("")
        self.sources_label.setText("")

    def set_structure(
        self,
        general_sessions: list[ChatSession],
        roles: list[Role],
        role_sessions: dict[str, list[ChatSession]],
        locations: list[Location],
        location_sessions: dict[str, list[ChatSession]],
        selected_id: str | None,
    ) -> None:
        self.sidebar.set_structure(
            general_sessions,
            roles,
            role_sessions,
            locations,
            location_sessions,
            selected_id,
        )

    @Slot(str)
    def set_role_prompt(self, prompt: str) -> None:
        text = prompt.strip()
        if not text:
            self.role_prompt_view.clear()
            self.role_prompt_view.setVisible(False)
            return
        self.role_prompt_view.setPlainText(text)
        self.role_prompt_view.setVisible(True)

    @Slot(list)
    def set_rag_sources(self, sources: list) -> None:
        if not sources:
            self.sources_label.setText("")
            return
        # Compact list of unique source file paths, rendered as clickable links.
        links = []
        seen = set()
        for s in sources:
            p = s.get("source_file_path")
            if p and p not in seen:
                seen.add(p)
                href = f"file://{p}"
                links.append(f'<a href="{href}">{escape(p)}</a>')
        html = "Offline sources:<br>" + "<br>".join(links)
        self.sources_label.setText(html)

    def set_offline_mode(self, enabled: bool, location_name: str | None = None) -> None:
        if enabled:
            if location_name:
                self.mode_label.setText(f"Mode: Offline ({location_name})")
            else:
                self.mode_label.setText("Mode: Offline")
        else:
            self.mode_label.setText("Mode: Online")

    def set_chat_title(self, title: str, scope: str | None = None) -> None:
        text = title.strip() or "Chat"
        if scope:
            self.chat_title_label.setText(f"{escape(text)}  —  {escape(scope)}")
        else:
            self.chat_title_label.setText(escape(text))

    def focus_input(self) -> None:
        self.input_field.setFocus()

