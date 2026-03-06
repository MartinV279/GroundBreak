## Ollama Desktop Chat HTTP API

This document describes the HTTP API exposed by `api_server.py`, suitable for use by a web or mobile frontend.

Base URL examples (development):

- `http://localhost:8000` (if started via `uvicorn api_server:app --reload`)

The API is built with FastAPI, so an OpenAPI schema and interactive docs are also available at:

- `GET /docs` (Swagger UI)
- `GET /openapi.json`

---

### Health

#### `GET /health`

**Description**: Simple health check.

**Response**:

```json
{ "status": "ok" }
```

---

### Roles

Roles correspond to reusable system prompts and (optionally) attached Locations for hybrid search.

#### `GET /roles`

**Description**: List all roles.

**Response**: Array of Role objects:

```json
[
  {
    "id": "uuid",
    "name": "Docs assistant",
    "description": "Helps with project docs",
    "system_prompt": "...",
    "created_at": 1730838000.0,
    "updated_at": 1730838000.0,
    "model": null,
    "temperature": null,
    "attached_location_id": "location-uuid-or-null",
    "hybrid_enabled": true
  }
]
```

#### `GET /roles/{role_id}`

**Description**: Fetch a single role by id.

**404** if not found.

#### `POST /roles`

**Description**: Create a new role.

**Body**:

```json
{
  "name": "Docs assistant",
  "description": "Helps with my documentation",
  "system_prompt": "You are an expert documentation assistant...",
  "attached_location_id": "optional-location-id",
  "hybrid_enabled": true
}
```

- `attached_location_id` and `hybrid_enabled` are optional; when both are set and the Location is indexed, hybrid local+web behaviour is enabled for chats scoped to this role.

**Response**: Created Role object.

#### `PUT /roles/{role_id}`

**Description**: Update a role.

**Body** (all fields optional):

```json
{
  "name": "New name",
  "description": "New description",
  "system_prompt": "Updated system prompt",
  "attached_location_id": "location-id-or-null",
  "hybrid_enabled": true
}
```

**Response**: Updated Role object.

#### `DELETE /roles/{role_id}`

**Description**: Delete a role and all its chats.

**Response**:

```json
{ "status": "deleted" }
```

---

### Locations (Offline knowledge bases)

Locations represent local folders whose documents have been indexed into a per-location RAG index.

#### `GET /locations`

**Description**: List all Locations.

**Response**: Array of Location objects:

```json
[
  {
    "id": "uuid",
    "name": "My CV",
    "directory": "/abs/path/to/folder",
    "index_dir": "/abs/path/to/data/offline_index/<id>",
    "ready": true,
    "created_at": 1730838000.0,
    "updated_at": 1730838000.0
  }
]
```

#### `GET /locations/{location_id}`

**Description**: Fetch a single Location by id.

**404** if not found.

#### `POST /locations`

**Description**: Create a new Location, optionally building the index immediately.

**Body**:

```json
{
  "name": "My CV",
  "directory": "/abs/path/to/folder",
  "build_index": true
}
```

- `build_index: true` triggers `build_index(directory, index_dir)` and marks the Location as `ready`.

**Response**:

- If `build_index` is false:

```json
{ "location": { ...Location... } }
```

- If `build_index` is true:

```json
{
  "location": { ...Location... },
  "meta": {
    "source_dir": "/abs/path/to/folder",
    "chunk_count": 123,
    "file_count": 5,
    "ready": true
  }
}
```

#### `PUT /locations/{location_id}`

**Description**: Update a Location’s name and/or directory.

**Body**:

```json
{
  "name": "New name",
  "directory": "/new/path"
}
```

- Changing `directory` automatically sets `ready=false`; you must reindex.

**Response**: Updated Location object.

#### `POST /locations/{location_id}/reindex`

**Description**: Rebuild the RAG index for a Location.

**Response**:

```json
{
  "location": { ...updated Location with ready=true... },
  "meta": { "source_dir": "...", "chunk_count": 123, "file_count": 5, "ready": true }
}
```

#### `DELETE /locations/{location_id}`

**Description**: Delete a Location, all its chats, and (best-effort) its index directory on disk.

**Response**:

```json
{ "status": "deleted" }
```

---

### Sessions (Chats)

Sessions represent saved chat histories, scoped to General, Role, or Location.

#### `GET /sessions`

**Description**: List all sessions.

**Response**: Array of `ChatSession` objects:

```json
[
  {
    "id": "uuid",
    "name": "New chat",
    "created_at": 1730838000.0,
    "updated_at": 1730838010.0,
    "messages": [ { "role": "user", "content": "..." }, ... ],
    "scope_type": "role",
    "scope_id": "role-uuid"
  }
]
```

#### `GET /sessions/{session_id}`

**Description**: Fetch a single session including message history.

**404** if not found.

#### `POST /sessions`

**Description**: Create a new session.

**Body**:

```json
{
  "name": "optional title",
  "scope_type": "general" | "role" | "location",
  "scope_id": "optional-role-or-location-id"
}
```

**Response**: Created `ChatSession`.

#### `PATCH /sessions/{session_id}`

**Description**: Rename a session.

**Body**:

```json
{ "name": "New title" }
```

**Response**: Updated `ChatSession`.

#### `DELETE /sessions/{session_id}`

**Description**: Delete a session.

**Response**:

```json
{ "status": "deleted" }
```

---

### Chat

#### `POST /chat`

**Description**: Send a message and receive a reply, with behaviour depending on scope:

- **General / non-hybrid role**:
  - Online chat with full tool support (web_search, web_fetch, MCP, plugin tools).
- **Location scope**:
  - Strict **offline** RAG over that Location’s index:
    - Local context injected.
    - Tools disabled.
- **Hybrid Role**:
  - Local context from attached Location **plus** tools enabled:
    - Model is instructed to prefer local docs for user-specific facts and use tools for general web info.

**Request body**:

```json
{
  "session_id": "optional-existing-session-id",
  "scope_type": "general" | "role" | "location",
  "scope_id": "optional-role-or-location-id",
  "message": "your question"
}
```

- If `session_id` is omitted, a new session is created using `scope_type`/`scope_id`.
- If `session_id` is provided, the existing session is loaded and appended to.

**Response**:

```json
{
  "session_id": "uuid",
  "reply": "assistant reply text",
  "sources": [
    {
      "chunk_id": "123",
      "source_file_path": "/abs/path/file.pdf",
      "source_file_name": "file.pdf",
      "chunk_index": 0,
      "score": 0.92
    }
  ]
}
```

- `sources` is non-empty only when RAG is used (Location or hybrid Role).

