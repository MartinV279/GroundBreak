import sys
from html import escape
from pathlib import Path
import shutil

from PySide6.QtWidgets import QApplication, QDialog
from PySide6.QtCore import QThread
from PySide6.QtGui import QIcon

from core.config import load_config, save_config
from core.sessions import (
    create_session,
    delete_session,
    list_sessions,
    load_session,
    save_session,
)
from core.roles import list_roles, get_role, create_role, update_role, delete_role, Role
from core.locations import (
    list_locations,
    get_location,
    delete_location,
)
from core.chat_backend import ChatBackend
from ui.main_window import MainWindow
from ui.settings_dialog import SettingsDialog
from ui.role_dialog import RoleDialog
from ui.location_dialog import LocationDialog
from ui.tray import TrayController
from tools.registry import ToolRegistry


def main() -> int:
    app = QApplication(sys.argv)

    config = load_config()
    tool_registry = ToolRegistry()

    backend_thread = QThread()
    chat_backend = ChatBackend(config=config, tool_registry=tool_registry)
    chat_backend.moveToThread(backend_thread)

    window = MainWindow(config=config)
    # Set application/window icon from logo.jpg if available.
    logo_path = Path(__file__).resolve().parent / "logo.jpg"
    if logo_path.exists():
        app_icon = QIcon(str(logo_path))
        app.setWindowIcon(app_icon)
        window.setWindowIcon(app_icon)

    # Core wiring: UI <-> backend
    window.send_message.connect(chat_backend.handle_user_message)
    chat_backend.assistant_reply.connect(window.add_assistant_message)
    chat_backend.tool_call_started.connect(window.on_tool_started)
    chat_backend.tool_call_finished.connect(window.on_tool_finished)
    chat_backend.error.connect(window.on_error)
    chat_backend.rag_sources.connect(window.set_rag_sources)

    # --- Roles and sessions (simple persistence) ---
    sessions = list_sessions()
    current_session = sessions[0] if sessions else create_session("New chat")

    def apply_scope_from_session() -> None:
        if not current_session:
            chat_backend.set_system_prompt("")
            chat_backend.set_rag_index(None)
            window.set_offline_mode(False)
            window.set_role_prompt("")
            window.set_chat_title("Chat", None)
            return
        if current_session.scope_type == "role" and current_session.scope_id:
            role = get_role(current_session.scope_id)
            if role:
                chat_backend.set_system_prompt(role.system_prompt)
                if role.model:
                    chat_backend.update_model(role.model)
                else:
                    chat_backend.update_model(config.model)
                if role.temperature is not None:
                    chat_backend.update_temperature(role.temperature)
                else:
                    chat_backend.update_temperature(config.temperature)
                window.set_role_prompt(role.system_prompt)

                # Hybrid role: attach a Location index while keeping tools enabled.
                from core.locations import get_location as _get_loc  # local import to avoid cycles

                if role.hybrid_enabled and role.attached_location_id:
                    loc = _get_loc(role.attached_location_id)
                    if loc and loc.ready:
                        chat_backend.set_rag_index(
                            loc.index_dir,
                            mode="hybrid",
                            location_name=loc.name,
                        )
                    else:
                        chat_backend.set_rag_index(None)
                else:
                    chat_backend.set_rag_index(None)

                window.set_offline_mode(False)
                window.set_chat_title(current_session.name, f"Role: {role.name}")
                return
        if current_session.scope_type == "location" and current_session.scope_id:
            loc = get_location(current_session.scope_id)
            if loc and loc.ready:
                chat_backend.set_system_prompt("")
                chat_backend.update_model(config.model)
                chat_backend.update_temperature(config.temperature)
                chat_backend.set_rag_index(
                    loc.index_dir,
                    mode="offline",
                    location_name=loc.name,
                )
                window.set_role_prompt("")
                window.set_offline_mode(True, loc.name)
                window.set_chat_title(current_session.name, f"Location: {loc.name}")
                return
        # General chat or unknown scope: online mode, no role prompt, no offline index.
        chat_backend.set_system_prompt("")
        chat_backend.update_model(config.model)
        chat_backend.update_temperature(config.temperature)
        chat_backend.set_rag_index(None)
        window.set_role_prompt("")
        window.set_offline_mode(False)
        window.set_chat_title(current_session.name, "General")

    def refresh_sidebar() -> None:
        all_sessions = list_sessions()
        all_roles = list_roles()
        locations = list_locations()

        general_sessions = []
        role_sessions: dict[str, list] = {}
        location_sessions: dict[str, list] = {}
        for s in all_sessions:
            if s.scope_type == "role" and s.scope_id:
                role_sessions.setdefault(s.scope_id, []).append(s)
            elif s.scope_type == "location" and s.scope_id:
                location_sessions.setdefault(s.scope_id, []).append(s)
            else:
                general_sessions.append(s)
        window.set_structure(
            general_sessions,
            all_roles,
            role_sessions,
            locations,
            location_sessions,
            current_session.id if current_session else None,
        )

    def load_into_ui(sess_id: str) -> None:
        nonlocal current_session
        sess = load_session(sess_id)
        if sess is None:
            return
        current_session = sess
        window.clear_chat_view()
        # Re-render saved messages in the chat view (user + assistant only).
        for m in sess.messages:
            role = m.get("role")
            content = m.get("content", "")
            if role == "user":
                window.append_user_history(str(content))
            elif role == "assistant":
                window.append_assistant_history(str(content))
        apply_scope_from_session()
        chat_backend.reset_conversation()
        refresh_sidebar()
        window.focus_input()

    def append_and_persist(role: str, content: str) -> None:
        if current_session is None:
            return
        current_session.messages.append({"role": role, "content": content})

        save_session(current_session)
        refresh_sidebar()

    def maybe_generate_title_with_ai() -> None:
        nonlocal current_session
        if current_session is None:
            return
        if not current_session.name.startswith("New chat"):
            return
        # Need at least two full user/assistant exchanges -> 4 messages.
        if len(current_session.messages) < 4:
            return
        # Build a compact transcript from the first two exchanges.
        transcript_lines = []
        for m in current_session.messages[:4]:
            role = m.get("role")
            content = str(m.get("content", "")).strip()
            if not content:
                continue
            if role == "user":
                transcript_lines.append(f"User: {content}")
            elif role == "assistant":
                transcript_lines.append(f"Assistant: {content}")
        if not transcript_lines:
            return

        # Import here so that .env has already been loaded (via core.config).
        from ollama import chat as ollama_chat  # type: ignore

        system_msg = {
            "role": "system",
            "content": (
                "You are a helpful assistant that generates short, descriptive chat titles.\n"
                "Given the conversation so far, respond with a concise 3–7 word title only.\n"
                "Do not add quotes, punctuation at the end, or extra explanation."
            ),
        }
        user_msg = {
            "role": "user",
            "content": "Conversation so far:\n" + "\n".join(transcript_lines),
        }
        try:
            resp = ollama_chat(
                model=config.model,
                messages=[system_msg, user_msg],
                options={"temperature": 0.3},
                think=False,
            )
            title = (getattr(resp, "message", resp).content or "").strip().splitlines()[0]
        except Exception:
            return

        if not title:
            return
        if len(title) > 60:
            title = title[:57].rstrip() + "..."
        current_session.name = title
        save_session(current_session)
        refresh_sidebar()

    # Persist messages alongside the existing wiring.
    def on_user_sent_persist(text: str) -> None:
        append_and_persist("user", text)

    window.send_message.connect(on_user_sent_persist)

    def on_assistant_reply_persist(text: str) -> None:
        append_and_persist("assistant", text)
        # This is invoked on the backend thread, so it is safe to make another
        # blocking Ollama call here without freezing the UI.
        maybe_generate_title_with_ai()

    chat_backend.assistant_reply.connect(on_assistant_reply_persist)

    def _new_general_chat() -> None:
        nonlocal current_session
        current_session = create_session("New chat", scope_type="general", scope_id=None)
        window.clear_chat_view()
        apply_scope_from_session()
        chat_backend.reset_conversation()
        refresh_sidebar()
        window.focus_input()

    def _new_chat_for_role(role_id: str) -> None:
        nonlocal current_session
        current_session = create_session("New chat", scope_type="role", scope_id=role_id)
        window.clear_chat_view()
        apply_scope_from_session()
        chat_backend.reset_conversation()
        refresh_sidebar()
        window.focus_input()

    window.new_general_chat.connect(_new_general_chat)
    window.new_role_chat.connect(_new_chat_for_role)
    window.load_chat.connect(load_into_ui)

    def _rename_chat(sess_id: str, new_name: str) -> None:
        sess = load_session(sess_id)
        if sess is None:
            return
        sess.name = new_name
        save_session(sess)
        refresh_sidebar()

    def _delete_chat(sess_id: str) -> None:
        nonlocal current_session
        delete_session(sess_id)
        sessions = list_sessions()
        if current_session and current_session.id == sess_id:
            current_session = sessions[0] if sessions else create_session("New chat")
            window.clear_chat_view()
            apply_scope_from_session()
            chat_backend.reset_conversation()
            if current_session:
                load_into_ui(current_session.id)
        refresh_sidebar()

    window.rename_chat.connect(_rename_chat)
    window.delete_chat.connect(_delete_chat)

    # --- Role management ---

    def _create_role() -> None:
        nonlocal current_session
        dlg = RoleDialog(window)
        if dlg.exec() != QDialog.Accepted:
            return
        name, description, system_prompt, attached_loc_id, hybrid_enabled = dlg.get_values()
        if not system_prompt.strip():
            return
        role = create_role(
            name,
            description,
            system_prompt,
            attached_location_id=attached_loc_id,
            hybrid_enabled=hybrid_enabled,
        )
        # Immediately create and switch to a first chat for this role so
        # the user can start chatting without extra steps.
        current_session = create_session("New chat", scope_type="role", scope_id=role.id)
        window.clear_chat_view()
        apply_scope_from_session()
        chat_backend.reset_conversation()
        refresh_sidebar()
        window.focus_input()

    def _edit_role(role_id: str) -> None:
        role = get_role(role_id)
        if role is None:
            return
        dlg = RoleDialog(window, role=role)
        if dlg.exec() != QDialog.Accepted:
            return
        name, description, system_prompt, attached_loc_id, hybrid_enabled = dlg.get_values()
        updated = Role(
            id=role.id,
            name=name or role.name,
            description=description or role.description,
            system_prompt=system_prompt or role.system_prompt,
            model=role.model,
            temperature=role.temperature,
            created_at=role.created_at,
            updated_at=role.updated_at,
            attached_location_id=attached_loc_id or role.attached_location_id,
            hybrid_enabled=hybrid_enabled,
        )
        update_role(updated)
        refresh_sidebar()

    def _delete_role_and_chats(role_id: str) -> None:
        nonlocal current_session
        # Delete chats belonging to this role
        for s in list_sessions():
            if s.scope_type == "role" and s.scope_id == role_id:
                delete_session(s.id)
        delete_role(role_id)
        sessions_after = list_sessions()
        if sessions_after:
            current_session = sessions_after[0]
        else:
            current_session = create_session("New chat")
        window.clear_chat_view()
        apply_scope_from_session()
        chat_backend.reset_conversation()
        if current_session:
            load_into_ui(current_session.id)
        refresh_sidebar()

    window.new_role.connect(_create_role)
    window.edit_role.connect(_edit_role)
    window.delete_role.connect(_delete_role_and_chats)

    # --- Location management ---

    def _create_location() -> None:
        dlg = LocationDialog(window)
        if dlg.exec() != QDialog.Accepted:
            return
        loc = dlg.get_location()
        if loc is None:
            return
        # Refresh the tree and immediately create/select a first chat for this location
        # so the user lands in Offline (LocationName) mode right away.
        refresh_sidebar()
        _new_chat_for_location(loc.id)

    def _edit_location(location_id: str) -> None:
        loc = get_location(location_id)
        if loc is None:
            return
        dlg = LocationDialog(window, location=loc)
        if dlg.exec() != QDialog.Accepted:
            return
        refresh_sidebar()

    def _delete_location_and_chats(location_id: str) -> None:
        nonlocal current_session
        loc = get_location(location_id)
        # Delete chats belonging to this location
        for s in list_sessions():
            if s.scope_type == "location" and s.scope_id == location_id:
                delete_session(s.id)
        delete_location(location_id)
        if loc and loc.index_dir:
            try:
                shutil.rmtree(Path(loc.index_dir), ignore_errors=True)
            except Exception:
                pass
        sessions_after = list_sessions()
        if sessions_after:
            current_session = sessions_after[0]
        else:
            current_session = create_session("New chat")
        window.clear_chat_view()
        apply_scope_from_session()
        chat_backend.reset_conversation()
        if current_session:
            load_into_ui(current_session.id)
        refresh_sidebar()

    def _new_chat_for_location(location_id: str) -> None:
        nonlocal current_session
        current_session = create_session(
            "New chat",
            scope_type="location",
            scope_id=location_id,
        )
        window.clear_chat_view()
        apply_scope_from_session()
        chat_backend.reset_conversation()
        refresh_sidebar()
        window.focus_input()

    window.new_location.connect(_create_location)
    window.edit_location.connect(_edit_location)
    window.delete_location.connect(_delete_location_and_chats)
    window.new_location_chat.connect(_new_chat_for_location)

    apply_scope_from_session()
    refresh_sidebar()

    # --- Settings dialog ---
    def open_settings() -> None:
        model_options = ["qwen3.5:4b", config.model]
        dlg = SettingsDialog(
            config=config,
            model_options=list(dict.fromkeys(model_options)),
            mcp_status=tool_registry._mcp.status(),
        )
        if dlg.exec() == QDialog.Accepted:
            dlg.apply_to(config)
            window.setWindowTitle(config.window_title)
            chat_backend.update_model(config.model)
            save_config(config)

    window.open_settings.connect(open_settings)

    # --- System tray integration ---
    app.setQuitOnLastWindowClosed(False)
    # Prefer custom logo icon if loaded, otherwise fallback to theme icon.
    tray_icon = app.windowIcon() if not app.windowIcon().isNull() else QIcon.fromTheme("chat")
    tray = TrayController(icon=tray_icon, tooltip=config.window_title)

    def toggle_window() -> None:
        if window.isVisible():
            window.hide()
        else:
            window.show()
            window.raise_()
            window.activateWindow()

    tray.show_hide_requested.connect(toggle_window)
    tray.settings_requested.connect(open_settings)

    quitting = {"value": False}

    def quit_app() -> None:
        quitting["value"] = True
        tray.tray.hide()
        app.quit()

    tray.quit_requested.connect(quit_app)
    tray.show()

    # Close to tray
    original_close_event = window.closeEvent

    def close_event_to_tray(event):
        if quitting["value"]:
            return original_close_event(event)
        event.ignore()
        window.hide()

    window.closeEvent = close_event_to_tray  # type: ignore[assignment]

    backend_thread.start()
    window.show()

    exit_code = app.exec()

    backend_thread.quit()
    backend_thread.wait()

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
