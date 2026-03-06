## Integration Guide: Desktop App + HTTP API

This document explains how the core concepts (General, Roles, Locations, Offline/Hybrid behaviour) map between the desktop PySide6 app and the HTTP API defined in `api_server.py`. Use it as a reference when wiring a web or mobile frontend.

---

### Core Concepts

- **Sessions (`ChatSession`)**
  - Represent individual chats (tab/conversation) with:
    - `id`, `name`, timestamps, full `messages` history.
    - `scope_type`: `"general"`, `"role"`, or `"location"`.
    - `scope_id`: `null` for General, a role id for Role chats, or a location id for Location chats.
  - On desktop:
    - Listed in the sidebar under General, Roles, or Offline.
  - In API:
    - Managed via `/sessions` endpoints.
    - `POST /chat` creates a session implicitly if you don’t provide `session_id`.

- **Roles**
  - Reusable system prompts and optional model/temperature overrides.
  - Extended with:
    - `attached_location_id`: id of a Location to use for hybrid search.
    - `hybrid_enabled`: whether local RAG should be combined with tools when chatting under this Role.
  - On desktop:
    - Created/edited via `RoleDialog`.
    - Chats under a Role appear as children in the “Roles” section.
  - In API:
    - Managed via `/roles` endpoints.
    - Hybrid behaviour is honoured by `POST /chat` when `scope_type="role"` and the Role is configured accordingly.

- **Locations (Offline knowledge bases)**
  - Represent local folders of documents with their own per-location RAG index.
  - Fields:
    - `directory`: source folder.
    - `index_dir`: where the index is stored (`data/offline_index/<id>`).
    - `ready`: whether indexing has been completed.
  - On desktop:
    - Created/edited via `LocationDialog`.
    - Chats under a Location appear in the “Offline” section.
    - Index built in a background `QThread`.
  - In API:
    - Managed via `/locations` endpoints.
    - Index building triggered via `POST /locations` with `build_index=true` or `POST /locations/{id}/reindex`.

- **RAG Modes**
  - **Online (General / regular Role)**:
    - No local RAG index used.
    - Tools (web_search, web_fetch, MCP, plugins) are available.
  - **Offline (Location chats)**:
    - RAG over the Location’s index only.
    - Tools disabled.
    - Model is instructed to admit when local docs are insufficient.
  - **Hybrid (Role + attached Location)**:
    - RAG over the attached Location’s index + tools enabled.
    - System prompt tells the model:
      - Prefer local docs for user-specific data.
      - Use web/MCP for general information.

---

### How the Desktop App Uses These Concepts

#### Scope application (`app.py`)

- When a session is loaded or created, the desktop app calls `apply_scope_from_session()`:
  - **General**:
    - Clears role prompt and RAG.
    - Uses global model/temperature.
    - Shows `Mode: Online`.
  - **Role**:
    - Applies the Role’s system prompt.
    - Uses Role’s model/temperature if provided, otherwise global.
    - If `hybrid_enabled` and `attached_location_id` refers to a ready Location:
      - Configures the backend in **hybrid** mode for that Location.
      - Mode label remains `Mode: Online` (hybrid is transparent to the user).
  - **Location**:
    - Clears role prompt.
    - Uses global model/temperature.
    - Configures the backend in **offline** mode with that Location’s index.
    - Shows `Mode: Offline (LocationName)`.

#### Backend behaviour (`core/chat_backend.py`)

- Maintains `_messages` as the internal conversation history passed to Ollama.
- When RAG is configured (`_rag` not `None` and `_rag_mode` set):
  - Builds a compact `convo` from recent user+assistant messages.
  - Uses the latest user message as `question`.
  - Calls `RagService.build_context(question)` to get:
    - `context_text` (concatenated local snippets).
    - `sources` (metadata for UI/API).

- **Offline mode**:
  - Tools list is set to `[]` (no tools).
  - If context is non-empty:
    - Emits sources.
    - Prepends a system instruction describing OFFLINE behaviour and embeds `context_text`.
  - If context is empty:
    - Emits empty sources.
    - Instructs the model to honestly say that local docs don’t contain enough information.

- **Hybrid mode**:
  - Tools list remains populated from `ToolRegistry`.
  - If context is non-empty:
    - Emits sources.
    - Prepends a system instruction saying:
      - Local docs are user-specific.
      - Tools are for general background.
      - Local context is provided inline.
  - If context is empty:
    - Emits empty sources and a system instruction explaining that local docs aren’t relevant for this question, but tools are still available.

---

### How the HTTP API Mirrors Desktop Behaviour

- The API reuses the same building blocks:
  - `core.sessions` for persistence.
  - `core.roles` and `core.locations` for metadata and hybrid configuration.
  - `core.rag_service.RagService` for per-location RAG.
  - `tools.registry.ToolRegistry` for tools wiring.

- `POST /chat` in `api_server.py` essentially replicates the desktop logic:
  - Determines scope from `session_id` or (`scope_type`, `scope_id`).
  - Calls `_build_rag_context_for_scope` to choose:
    - `mode` = `"offline"`, `"hybrid"`, or `""` (none).
  - Builds a compact `convo` from recent user+assistant messages.
  - Constructs `messages` and `tools` exactly like `ChatBackend._chat_turn`:
    - Offline: tools disabled, local-only context with explicit OFFLINE instructions.
    - Hybrid: local context injected + tools enabled, with instructions to prefer local docs.
    - Online: no local context; tools fully enabled.
  - Runs `_run_tool_loop`, which:
    - Calls `ollama.chat` with `messages` and `tools`.
    - Handles tool calls inline, appending tool results as `{"role": "tool"}` messages.
  - Stores user + assistant messages back into the `ChatSession` and returns:
    - `session_id` for future calls.
    - `reply` (assistant text).
    - `sources` (RAG sources, if any).

---

### How to Replicate Desktop Usage from a Frontend

1. **Discover configuration**
   - Call:
     - `GET /roles` to list existing Roles and their hybrid/Location attachment.
     - `GET /locations` to list Locations and check which are `ready`.
     - `GET /sessions` to list existing chats if you want to show history.

2. **Create or attach a Location**
   - To create a new Location and index it:

```http
POST /locations
Content-Type: application/json

{
  "name": "My Docs",
  "directory": "/abs/path/to/folder",
  "build_index": true
}
```

   - Alternatively:
     - `POST /locations` with `build_index=false`.
     - Then `POST /locations/{id}/reindex` when ready to build the index.

3. **Create a Role (optional hybrid)**

```http
POST /roles
Content-Type: application/json

{
  "name": "Docs assistant",
  "description": "Helps answer questions about my docs",
  "system_prompt": "You are a helpful documentation assistant...",
  "attached_location_id": "<location-id>",
  "hybrid_enabled": true
}
```

   - This Role will behave online but with local RAG support from the attached Location.

4. **Create or reuse a chat session**

   - To create a **General** chat:

```http
POST /sessions
Content-Type: application/json

{ "name": "General chat", "scope_type": "general" }
```

   - To create a **Role** chat:

```http
POST /sessions
Content-Type: application/json

{ "name": "Role chat", "scope_type": "role", "scope_id": "<role-id>" }
```

   - To create an **Offline Location** chat:

```http
POST /sessions
Content-Type: application/json

{ "name": "Offline chat", "scope_type": "location", "scope_id": "<location-id>" }
```

   - Alternatively, skip explicit session creation and let `POST /chat` create a session by passing `scope_type` and `scope_id` directly.

5. **Send chat messages**

   - Use `POST /chat` with an existing `session_id`:

```http
POST /chat
Content-Type: application/json

{
  "session_id": "<session-id>",
  "message": "Who is Satoshi?"
}
```

   - The backend:
     - Applies RAG + tool behaviour based on the session’s scope:
       - General: online with tools.
       - Role (non-hybrid): online with tools and Role’s system prompt.
       - Role (hybrid): RAG from attached Location + tools.
       - Location: strict offline RAG, tools disabled.
     - Returns:

```json
{
  "session_id": "<session-id>",
  "reply": "Assistant answer...",
  "sources": [
    {
      "source_file_path": "/path/to/file",
      "chunk_index": 0,
      "score": 0.92,
      "chunk_id": "123",
      "source_file_name": "file.pdf"
    }
  ]
}
```

   - On the frontend, display:
     - The `reply` as the assistant message.
     - `sources` as a list of referenced documents (e.g. file paths with clickable links).

6. **Rename or delete chats**
   - To rename:

```http
PATCH /sessions/{session_id}
Content-Type: application/json

{ "name": "Better title" }
```

   - To delete:

```http
DELETE /sessions/{session_id}
```

---

### Recommended Frontend State Shape

For a frontend that mimics the desktop behaviour, maintain:

- **Global lists**:
  - `roles` (from `GET /roles`).
  - `locations` (from `GET /locations`).
  - `sessions` (from `GET /sessions`), grouped by `scope_type`/`scope_id`.

- **Current session**:
  - `currentSessionId`.
  - When it changes, re-render:
    - Chat history (`GET /sessions/{id}`) or cached messages.
    - Mode label:
      - `"Online"` for General/Role.
      - `"Offline (LocationName)"` for Location.
    - Attached Role/Location labels.

- **Per-message interactions**:
  - Always send `session_id` back on `POST /chat`.
  - Append user and assistant messages locally for a responsive UI; reconcile with server history if needed.

---

### Summary

- The **desktop app** and **HTTP API** share the same underlying data model and RAG logic.
- Scopes (`general`, `role`, `location`) and hybrid Role configuration determine how RAG and tools are used.
- By using `/roles`, `/locations`, `/sessions`, and `/chat`, a frontend can:
  - Manage Roles and attach Locations for hybrid search.
  - Manage offline Locations and their indices.
  - Create, rename, and delete chats.
  - Run conversations in General, Role, or Offline modes with behaviour matching the desktop app.

