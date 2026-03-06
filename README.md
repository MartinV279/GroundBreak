## Ollama Desktop Chat (PySide6)

A small Ubuntu-friendly desktop chatbot built with PySide6 and a local Ollama backend.

** Key Note ** 100% vibe coded in a slow morning

### Features
- **Compact popup-style chat window** that stays on top.
- **Local Ollama backend** using the `ollama` Python client.
- **Default model** `qwen3.5:4b` (configurable).
- **Multi-turn history** with tool usage rendered in the chat.
- **Tool registry** (`web_search`, `web_fetch`, and MCP-style tools).
- **Config via `.env` and `data/config.json`**.
- **MCP integration scaffold** with an example `mcp_echo` tool.

### Project layout
- `app.py` — GUI entry point.
- `core/` — configuration, chat backend, MCP scaffold.
- `ui/` — PySide6 windows and widgets.
- `tools/` — tool registry and built-in tools.
- `data/` — JSON configuration and other data files.

### Requirements
- Ubuntu (or any recent Linux) with Python 3.10+
- A running Ollama instance with the `qwen3.5:4b` model available (see below).
- Internet access if you want to use `web_search` / `web_fetch`.

### Install and run Ollama (`qwen3.5:4b`)

These steps are for Ubuntu/Linux with an NVIDIA GPU such as a **GeForce RTX 4060 Laptop GPU**. Ollama will automatically use your GPU when the NVIDIA drivers are installed correctly.

1. **Install Ollama (Linux)**  
   In a terminal:
   ```bash
   curl -fsSL https://ollama.com/install.sh | sh
   ```

2. **Start the Ollama server** (if it is not already running):  
   ```bash
   ollama serve
   ```
   You can leave this running in a terminal while you use the desktop app.

3. **Download the `qwen3.5:4b` model**  
   In another terminal:
   ```bash
   ollama pull qwen3.5:4b
   ```

4. **Quick test of the model and GPU usage (optional but recommended)**  
   - In one terminal, watch GPU usage:
     ```bash
     nvidia-smi
     ```
   - In another terminal, run:
     ```bash
     ollama run qwen3.5:4b
     ```
   If your NVIDIA drivers are installed, Ollama should offload inference to the GPU automatically (including on an RTX 4060 Laptop GPU).

### Enable Ollama web search API

To use the built-in `web_search` and `web_fetch` tools, you need an **Ollama Web Search API key**. This is separate from the local Ollama server and is used by the `ollama` Python client.

1. **Create an Ollama account (if you don't have one yet)**  
   - Go to the Ollama website and sign up for an account.

2. **Generate an API key**  
   - Visit the keys page (for example: [`ollama.com/settings/keys`](https://ollama.com/settings/keys)).  
   - Create a new API key and copy it.

3. **Store the API key in `.env`**  
   Edit your `.env` file in the project root and add:
   ```bash
   OLLAMA_API_KEY=your_api_key_here
   ```
   Replace `your_api_key_here` with the key from the Ollama settings page.

4. **Restart the app**  
   Close and re-run the desktop app (or the terminal client) so it picks up the updated environment.  
   Once set, the `web_search` and `web_fetch` tools will use this key to call Ollama's web search API.

### Increase model context (beyond 4k)

By default, Ollama may use a **4k context window** on GPUs with less than 24 GB VRAM. This app already asks Ollama for up to **32k tokens** of context, but Ollama itself must be configured to allow more than 4k.

You have two simple options:

1. **Quick global override via environment variable**  
   Start the Ollama server with a higher context limit (for example 32k):
   ```bash
   OLLAMA_CONTEXT_LENGTH=32000 ollama serve
   ```
   You can adjust `32000` to another value supported by your hardware.

2. **Create a custom model with a larger context (recommended)**  
   This makes the setting explicit and reproducible:
   ```bash
   ollama pull qwen3.5:4b

   ollama create qwen3.5-32k -f - << 'EOF'
   FROM qwen3.5:4b
   PARAMETER num_ctx 32000
   EOF
   ```
   Then tell this app to use the new model:
   - **Option A (JSON config)**: Edit `data/config.json` and set:
     ```json
     { "model": "qwen3.5-32k", "...": "..." }
     ```
   - **Option B (environment)**: In `.env`, set:
     ```bash
     MODEL=qwen3.5-32k
     ```

With either approach, the desktop app will be able to use a larger context window than the default 4k.

### Setup (Ubuntu)
1. Clone or open this project directory.
2. (Recommended) Create and activate a virtual environment:
```bash
python3 -m venv .venv
source .venv/bin/activate
```
3. Install dependencies:
```bash
pip install -r requirements.txt
```
4. Create a `.env` file based on `.env.example`:
```bash
cp .env.example .env
```
   Edit `.env` and set `OLLAMA_API_KEY` if your Ollama setup requires one.
5. (Optional) Adjust `data/config.json` to change the model, window title, or tool output truncation length.

### Running the desktop app
```bash
python app.py
```

- Type in the input field and press **Enter** or click **Send**.
- Tool calls (e.g. `web_search`, `web_fetch`, `mcp_echo`) are shown inline in the chat.
- The window is designed as a compact popup that stays on top of other windows.

### Adding new tools
- Register new Python callables in `tools/registry.py` by creating additional `ToolSpec` entries.
- Any registered tool will automatically be:
  - Exposed to the model via `ollama.chat(..., tools=...)`.
  - Logged in the UI when it is called.

### MCP integration path
- The `core/mcp.py` module provides a small `McpIntegration` class and an example `mcp_echo` tool.
- To hook up a real MCP server, extend `McpIntegration` to:
  - Discover tools from your MCP server.
  - Expose them as `McpToolDescriptor` instances.
  - Register them with `ToolRegistry._register_mcp_tools`.

### Next steps
- Improve error reporting in the UI (e.g. non-blocking banners).
- Add streaming responses from Ollama for more responsive UX.
- Add per-conversation settings (temperature, model, etc.) and persistence.
- Package the app as a desktop launcher (`.desktop` file) for easier startup.
