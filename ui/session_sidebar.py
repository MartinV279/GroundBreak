from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Any

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QHBoxLayout,
    QInputDialog,
    QMenu,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.sessions import ChatSession
from core.roles import Role
from core.locations import Location


@dataclass
class SessionListItem:
    session_id: str
    name: str


class SessionSidebar(QWidget):
    new_general_chat_requested = Signal()
    new_role_chat_requested = Signal(str)
    new_role_requested = Signal()
    new_location_requested = Signal()
    session_load_requested = Signal(str)
    session_rename_requested = Signal(str, str)
    session_delete_requested = Signal(str)
    role_edit_requested = Signal(str)
    role_delete_requested = Signal(str)
    edit_location_requested = Signal(str)
    delete_location_requested = Signal(str)
    new_location_chat_requested = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        toolbar = QHBoxLayout()
        self.new_button = QPushButton("New chat", self)
        self.new_button.clicked.connect(self._on_new_chat_clicked)
        self.new_role_button = QPushButton("New role", self)
        self.new_role_button.clicked.connect(self.new_role_requested.emit)
        self.new_location_button = QPushButton("New location", self)
        self.new_location_button.clicked.connect(self.new_location_requested.emit)
        toolbar.addWidget(self.new_button)
        toolbar.addWidget(self.new_role_button)
        toolbar.addWidget(self.new_location_button)
        toolbar.addStretch(1)

        self.tree = QTreeWidget(self)
        self.tree.setHeaderHidden(True)
        self.tree.itemActivated.connect(self._on_item_activated)
        self.tree.currentItemChanged.connect(self._on_current_item_changed)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._on_context_menu)

        layout.addLayout(toolbar)
        layout.addWidget(self.tree, 1)

    def set_structure(
        self,
        general_sessions: List[ChatSession],
        roles: List[Role],
        role_sessions: Dict[str, List[ChatSession]],
        locations: List[Location],
        location_sessions: Dict[str, List[ChatSession]],
        selected_session_id: Optional[str],
    ) -> None:
        self.tree.clear()

        general_root = QTreeWidgetItem(self.tree, ["General"])
        general_root.setData(0, Qt.UserRole, {"kind": "section", "section": "general"})
        for s in general_sessions:
            item = QTreeWidgetItem(general_root, [s.name])
            item.setData(0, Qt.UserRole, {"kind": "session", "id": s.id, "scope_type": "general"})
            if selected_session_id and s.id == selected_session_id:
                self.tree.setCurrentItem(item)

        roles_root = QTreeWidgetItem(self.tree, ["Roles"])
        roles_root.setData(0, Qt.UserRole, {"kind": "section", "section": "roles"})
        for r in roles:
            role_item = QTreeWidgetItem(roles_root, [r.name])
            role_item.setData(0, Qt.UserRole, {"kind": "role", "id": r.id})
            for s in role_sessions.get(r.id, []):
                child = QTreeWidgetItem(role_item, [s.name])
                child.setData(
                    0,
                    Qt.UserRole,
                    {"kind": "session", "id": s.id, "scope_type": "role", "scope_id": r.id},
                )
                if selected_session_id and s.id == selected_session_id:
                    self.tree.setCurrentItem(child)

        offline_root = QTreeWidgetItem(self.tree, ["Offline"])
        offline_root.setData(0, Qt.UserRole, {"kind": "section", "section": "offline"})
        for loc in locations:
            label = loc.name
            if not loc.ready:
                label = f"{loc.name} (needs index)"
            loc_item = QTreeWidgetItem(offline_root, [label])
            loc_item.setData(0, Qt.UserRole, {"kind": "location", "id": loc.id})
            for s in location_sessions.get(loc.id, []):
                child = QTreeWidgetItem(loc_item, [s.name])
                child.setData(
                    0,
                    Qt.UserRole,
                    {
                        "kind": "session",
                        "id": s.id,
                        "scope_type": "location",
                        "scope_id": loc.id,
                    },
                )
                if selected_session_id and s.id == selected_session_id:
                    self.tree.setCurrentItem(child)

        self.tree.expandItem(general_root)
        self.tree.expandItem(roles_root)
        self.tree.expandItem(offline_root)

        # Refresh button label based on current selection/scope.
        self._update_new_button_label()

    def _current_scope_for_new_chat(self) -> Tuple[str, Optional[str]]:
        item = self.tree.currentItem()
        if not item:
            return "general", None
        data: Any = item.data(0, Qt.UserRole)
        if not isinstance(data, dict):
            return "general", None
        kind = data.get("kind")
        if kind == "session":
            scope_type = data.get("scope_type")
            if scope_type == "role":
                return "role", data.get("scope_id")
            if scope_type == "location":
                return "location", data.get("scope_id")
            return "general", None
        if kind == "role":
            return "role", data.get("id")
        if kind == "location":
            return "location", data.get("id")
        return "general", None

    def _on_new_chat_clicked(self) -> None:
        scope_type, scope_id = self._current_scope_for_new_chat()
        if scope_type == "role" and scope_id:
            self.new_role_chat_requested.emit(str(scope_id))
        elif scope_type == "location" and scope_id:
            self.new_location_chat_requested.emit(str(scope_id))
        else:
            self.new_general_chat_requested.emit()

    def _update_new_button_label(self) -> None:
        scope_type, scope_id = self._current_scope_for_new_chat()
        if scope_type == "role" and scope_id:
            item = self.tree.currentItem()
            role_name = "role"
            if item is not None:
                data: Any = item.data(0, Qt.UserRole)
                kind = data.get("kind") if isinstance(data, dict) else None
                if kind == "role":
                    role_name = item.text(0)
                else:
                    parent = item.parent()
                    while parent is not None:
                        pdata: Any = parent.data(0, Qt.UserRole)
                        if isinstance(pdata, dict) and pdata.get("kind") == "role":
                            role_name = parent.text(0)
                            break
                        parent = parent.parent()
            self.new_button.setText(f"New chat ({role_name})")
        elif scope_type == "location" and scope_id:
            item = self.tree.currentItem()
            loc_name = "location"
            if item is not None:
                data: Any = item.data(0, Qt.UserRole)
                kind = data.get("kind") if isinstance(data, dict) else None
                if kind == "location":
                    loc_name = item.text(0)
                else:
                    parent = item.parent()
                    while parent is not None:
                        pdata: Any = parent.data(0, Qt.UserRole)
                        if isinstance(pdata, dict) and pdata.get("kind") == "location":
                            loc_name = parent.text(0)
                            break
                        parent = parent.parent()
            self.new_button.setText(f"New chat ({loc_name})")
        else:
            self.new_button.setText("New chat (General)")

    @Slot(QTreeWidgetItem, QTreeWidgetItem)
    def _on_current_item_changed(self, current: QTreeWidgetItem, previous: QTreeWidgetItem) -> None:
        self._update_new_button_label()

    def selected_session_id(self) -> Optional[str]:
        item = self.tree.currentItem()
        if not item:
            return None
        data: Any = item.data(0, Qt.UserRole)
        if not isinstance(data, dict):
            return None
        if data.get("kind") == "session":
            return str(data.get("id"))
        return None

    @Slot(QTreeWidgetItem)
    def _on_item_activated(self, item: QTreeWidgetItem) -> None:
        data: Any = item.data(0, Qt.UserRole)
        if not isinstance(data, dict):
            return
        kind = data.get("kind")
        if kind == "session":
            sid = data.get("id")
            if sid:
                self.session_load_requested.emit(str(sid))

    def _on_context_menu(self, pos) -> None:
        item = self.tree.itemAt(pos)
        if item is None:
            return
        data: Any = item.data(0, Qt.UserRole)
        if not isinstance(data, dict):
            return
        kind = data.get("kind")

        menu = QMenu(self)
        if kind == "session":
            sid = str(data.get("id"))
            rename_action = menu.addAction("Rename chat…")
            delete_action = menu.addAction("Delete chat")
            chosen = menu.exec(self.tree.mapToGlobal(pos))
            if chosen == rename_action:
                new_name, ok = QInputDialog.getText(self, "Rename chat", "New name:", text=item.text(0))
                if ok and new_name.strip():
                    self.session_rename_requested.emit(sid, new_name.strip())
            elif chosen == delete_action:
                self.session_delete_requested.emit(sid)
        elif kind == "role":
            rid = str(data.get("id"))
            edit_action = menu.addAction("Edit role…")
            delete_action = menu.addAction("Delete role")
            new_chat_action = menu.addAction("New chat in role")
            chosen = menu.exec(self.tree.mapToGlobal(pos))
            if chosen == edit_action:
                self.role_edit_requested.emit(rid)
            elif chosen == delete_action:
                self.role_delete_requested.emit(rid)
            elif chosen == new_chat_action:
                self.new_role_chat_requested.emit(rid)
        elif kind == "location":
            lid = str(data.get("id"))
            edit_action = menu.addAction("Edit Location…")
            new_chat_action = menu.addAction("New chat in Location")
            delete_action = menu.addAction("Delete Location")
            chosen = menu.exec(self.tree.mapToGlobal(pos))
            if chosen == edit_action:
                self.edit_location_requested.emit(lid)
            elif chosen == delete_action:
                self.delete_location_requested.emit(lid)
            elif chosen == new_chat_action:
                self.new_location_chat_requested.emit(lid)

