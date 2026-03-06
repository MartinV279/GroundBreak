## Project Overview & Agent Behaviour

This project is a Python / PySide6 desktop chatbot app with a matching HTTP API layer, designed to talk to Ollama (with tools) and to local document indexes. It supports three main scopes: **General**, **Roles**, and **Offline Locations**, plus a hybrid mode that combines local RAG with web/MCP tools.

---

### High-Level Architecture

- **Core logic (`core/`)**
  - `config.py` – loads and saves global app configuration (model, temperature, MCP settings, window title, etc.).
  - `sessions.py` – defines `ChatSession` and handles persistence in `data/sessions/`:
    - Fields: `id`, `name`, `created_at`, `updated_at`, `messages`, `scope_type`, `scope_id`.
    - `scope_type` determines whether the session is General, Role, or Location-scoped.
  - `roles.py` – defines `Role` and manages `data/roles.json`:
    - Fields: id, name, description, system_prompt, model, temperature.
    - Hybrid-specific fields: `attached_location_id`, `hybrid_enabled`.
  - `locations.py` – defines `Location` and manages `data/locations.json`:
    - Fields: id, name, `directory`, `index_dir`, `ready`, timestamps.
    - One Location = one per-folder RAG index under `data/offline_index/<id>`.
  - `offline_indexer.py` / `offline_retriever.py` – per-Location RAG index:
    - Loads documents from `directory`, splits into sentence-based chunks.
    - Builds hybrid MiniLM + BM25 index (tokenization + shared `SentenceTransformer`).
    - Stores chunks, BM25 stats, embeddings, and `meta.json`.
  - `rag_service.py` – thin wrapper over `OfflineRetriever`:
    - Accepts an `index_dir`, builds expanded queries, merges RAG results, and returns:
      - `context_text` (annotated snippets).
      - `sources` (chunk metadata).
  - `chat_backend.py` – the background engine that talks to Ollama:
    - Maintains `_messages` history, system prompt, model, temperature.
    - Receives user messages from the UI, calls Ollama with tools, and emits replies.
    - Integrates RAG in two modes:
      - `offline`: strict local-only answers (Location chats).
      - `hybrid`: local context + tools (Roles with attached Locations).
  - `mcp.py` – minimal MCP integration for tool discovery and calls over stdio.
  - `embedding_model.py` – shared `SentenceTransformer` loader for efficient reuse.

- **Tools (`tools/`)**
  - `registry.py` – wires up built-in tools (`web_search`, `web_fetch`), MCP tools, and plugin tools into a single `ToolRegistry`:
    - Provides `get_ollama_tools_for_chat()` for both desktop and API chat flows.
    - Wraps shell-like tools with safety checks.

- **UI (`ui/`)**
  - `main_window.py` – main PySide6 window:
    - Left sidebar: `SessionSidebar` with General, Roles, Offline sections.
    - Right: chat view, “Offline sources” list, mode label, role prompt view, input row.
    - Renders assistant messages as markdown and styled chat bubbles.
  - `session_sidebar.py` – tree of:
    - General section with chats.
    - Roles section with roles and their chats.
    - Offline section with Locations and their chats (shows “(needs index)” when not ready).
    - Emits signals for creating/deleting/renaming chats, roles, and locations.
  - `role_dialog.py` – Role editor:
    - Name, description, system prompt.
    - “Generate prompt” helper.
    - Hybrid configuration: checkbox + attached Location dropdown.
  - `location_dialog.py` – Location editor:
    - Name, folder picker, status and index stats.
    - “Build / Rebuild index” button using a background `QThread`.
  - `settings_dialog.py` – global settings (window title, model, tool output limit, MCP status).
  - `tray.py` – system tray integration for showing/hiding the window and quitting.

- **Application entrypoint (`app.py`)**
  - Bootstraps Qt application, starts `ChatBackend` on a separate `QThread`.
  - Wires `MainWindow` signals to backend slots and persistence functions.
  - Central place where **scope is applied** (see below).

- **HTTP API (`api_server.py`)**
  - FastAPI app exposing:
    - `/roles`, `/locations`, `/sessions` CRUD endpoints.
    - `/chat` for sending messages and receiving replies (with RAG + tools behaviour mirroring the desktop app).
  - Designed so a web/mobile frontend can replicate everything the desktop does.

---

### Agent Behaviour & Modes

The “agent” is effectively the combination of:

- The Ollama model (`_config.model`).
- The tools exposed via `ToolRegistry`.
- The RAG integration supplied by `RagService` + per-Location offline indexes.
- The system prompts and role prompts chosen by scope.

The agent operates in three modes, determined by `scope_type` and Role configuration:

1. **General (Online)**
   - `scope_type="general"`, `scope_id=None`.
   - System prompt: generic, describes access to web search and tools.
   - Tools: all enabled (web_search, web_fetch, MCP, plugins).
   - No local RAG; answers are based on model + tools.

2. **Role (Online or Hybrid)**
   - `scope_type="role"`, `scope_id=<role-id>`.
   - System prompt: the Role’s `system_prompt` (overrides default).
   - Model/temperature: can be Role-specific or global.
   - Two sub-modes:
     - **Standard Role** (no hybrid or no attached Location/ready index):
       - Same as General, but with Role-specific instructions.
     - **Hybrid Role**:
       - Role has `hybrid_enabled=True` and a `attached_location_id` pointing to a ready Location.
       - RAG:
         - Local context from attached Location is built via `RagService`.
         - Injected into an additional system message:
           - Tells the model that local docs are user-specific data.
           - Encourages using tools for general web/background.
       - Tools remain enabled:
         - The agent can combine local and web/MCP sources in a single pass.

3. **Offline Location**
   - `scope_type="location"`, `scope_id=<location-id>`.
   - System prompt: generic (no Role-specific instructions).
   - Model/temperature: global config.
   - RAG:
     - Uses only the Location’s index for retrieval.
     - Tools are disabled (no web_search/MCP).
     - If local context is found:
       - Agent is instructed to answer strictly from that context.
     - If not:
       - Agent is instructed to explicitly admit that local docs don’t have enough info.

In all modes, short recent conversation history (last few user+assistant messages) is included to support follow-ups (e.g. “What is his number?” after an earlier answer).

---

### Scope Application Logic

The app interprets `ChatSession.scope_type` and `scope_id` to configure the agent, both in the desktop and via the HTTP API:

- In the **desktop app** (`app.apply_scope_from_session()`):
  - Reads the current session, finds associated Role/Location if any.
  - Sets:
    - System prompt (generic vs Role-specific).
    - Model/temperature (global vs per-Role).
    - `ChatBackend.set_rag_index(index_dir, mode, location_name)`:
      - `mode="offline"` for Location chats.
      - `mode="hybrid"` for Roles with attached Locations.
      - `None` to disable RAG.
  - Updates the UI:
    - Mode label (`Mode: Online` or `Mode: Offline (LocationName)`).
    - Role prompt view.
    - Chat title (e.g. `Title — Role: Docs assistant`).

- In the **HTTP API** (`api_server.py`):
  - `POST /chat`:
    - Uses `session_id` if provided, or (`scope_type`, `scope_id`) to create a new session.
    - Calls `_build_rag_context_for_scope` to choose:
      - `mode="offline"`, `"hybrid"`, or `""` (none).
    - Builds messages + tools config that mirror the desktop backend’s behaviour.

This means you can switch scopes either through the desktop UI or purely via API, and the agent’s behaviour will be consistent.

---

### How to Extend or Customize the Agent

- **Add new tools**
  - Implement a provider module under `tools/` with a `get_tools()` function that returns `ToolSpec` objects.
  - `ToolRegistry` auto-discovers these and exposes them to both desktop and API chat flows.

- **Change RAG strategy**
  - Modify `core/rag_service.py` to:
    - Adjust multi-query expansion.
    - Change score combination (alpha, thresholds).
    - Group or format context differently.
  - Both desktop and API will automatically pick up the new context-building logic.

- **Add new scopes or modes**
  - Extend `ChatSession.scope_type` semantics in `core/sessions.py`.
  - Update:
    - `app.apply_scope_from_session()` for desktop.
    - `_build_rag_context_for_scope()` in `api_server.py` for HTTP.
  - Decide what system prompts, tools, and RAG behaviour should apply for the new mode.

---

### Summary

- The project provides:
  - A desktop client (PySide6) with Roles, Offline Locations, and hybrid Role+Location support.
  - A reusable chat backend that handles model calls, tools, and RAG.
  - An HTTP API that mirrors the same behaviour for external frontends.
- The “agent” is configured purely by:
  - Scope (General / Role / Location).
  - Role system prompts and hybrid attachments.
  - Location indices and readiness.
- By respecting these configuration points, you can extend or re-skin the UI while keeping the same agent capabilities and behaviour.

