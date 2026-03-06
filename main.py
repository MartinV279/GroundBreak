#!/usr/bin/env python3
"""
Qwen terminal chat with web search.
Usage: python3 qwen_websearch.py
Requires: pip install 'ollama>=0.6.0' python-dotenv --break-system-packages
          Create a .env file in the same directory with: OLLAMA_API_KEY=your_key
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load .env BEFORE importing ollama so OLLAMA_API_KEY is in os.environ when ollama initializes
load_dotenv(Path(__file__).parent / ".env")

from ollama import chat, web_search, web_fetch

MODEL = os.environ.get("MODEL", "qwen3.5:4b")
AVAILABLE_TOOLS = {"web_search": web_search, "web_fetch": web_fetch}

DEBUG = os.environ.get("DEBUG", "0") == "1"

def dbg(label, value=""):
    if DEBUG:
        print(f"\033[35m[DBG] {label}\033[0m {value}", flush=True)

def run_tool(tool_call):
    fn = AVAILABLE_TOOLS.get(tool_call.function.name)
    if not fn:
        msg = f"Tool '{tool_call.function.name}' not found."
        print(f"\033[31m  [tool error] {msg}\033[0m")
        return msg
    try:
        print(f"\033[90m  [tool: {tool_call.function.name}({', '.join(f'{k}={repr(v)}' for k,v in tool_call.function.arguments.items())})] calling...\033[0m", flush=True)
        result = fn(**tool_call.function.arguments)
        result_str = str(result)[:8000]
        print(f"\033[90m  [tool result] {len(result_str)} chars returned\033[0m", flush=True)
        dbg("tool result preview:", result_str[:300] + "..." if len(result_str) > 300 else result_str)
        return result_str
    except Exception as e:
        msg = f"Tool error: {e}"
        print(f"\033[31m  [tool error] {msg}\033[0m", flush=True)
        return msg

def chat_turn(messages):
    """Send messages, handle tool calls in a loop, return final text."""
    iteration = 0
    while True:
        iteration += 1
        dbg(f"--- iteration {iteration}, messages in history: {len(messages)}")
        for i, m in enumerate(messages):
            role = m['role'] if isinstance(m, dict) else getattr(m, 'role', '?')
            dbg(f"  msg[{i}] role={role}")

        response = chat(
            model=MODEL,
            messages=messages,
            tools=[web_search, web_fetch],
            options={"num_ctx": 32000},
            think=False
        )

        dbg("response.message.role:", getattr(response.message, 'role', '?'))
        dbg("response.message.tool_calls:", str(response.message.tool_calls))
        dbg("response.message.content:", (response.message.content or "")[:200])

        messages.append(response.message)

        if response.message.tool_calls:
            for tc in response.message.tool_calls:
                result = run_tool(tc)
                tool_msg = {
                    "role": "tool",
                    "content": result,
                    "tool_name": tc.function.name,
                }
                dbg("appending tool result message:", str(tool_msg)[:200])
                messages.append(tool_msg)
        else:
            dbg("no tool calls — returning final response")
            return response.message.content or ""

def main():
    _api_key = os.environ.get("OLLAMA_API_KEY")
    if not _api_key:
        print("⚠️  Warning: OLLAMA_API_KEY not set. Web search may fail.")
        print("   Get a key at ollama.com/settings/keys, then add to .env:")
        print("   OLLAMA_API_KEY=your_key\n")
    else:
        dbg("OLLAMA_API_KEY loaded:", _api_key[:8] + "...")

    print(f"\033[1m🤖 Qwen Chat with Web Search\033[0m  (model: {MODEL})")
    print("Type your message and press Enter. Ctrl+C or type 'exit' to quit.\n")

    from datetime import datetime
    now = datetime.now()
    system_msg = {
        "role": "system",
        "content": (
            f"You are a helpful assistant with access to web search.\n"
            f"Current date: {now.strftime('%A, %B %d, %Y')}\n"
            f"Current time: {now.strftime('%H:%M')} (local time)\n"
            "Use web search for any questions about current events, news, or information that may have changed recently."
        )
    }
    messages = [system_msg]

    while True:
        try:
            user_input = input("\033[1;36mYou:\033[0m ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye!")
            sys.exit(0)

        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit", "bye"):
            print("Goodbye!")
            sys.exit(0)

        messages.append({"role": "user", "content": user_input})

        print("\033[1;32mQwen:\033[0m ", end="", flush=True)
        try:
            reply = chat_turn(messages)
            print(reply)
        except Exception as e:
            print(f"\n\033[31mError: {e}\033[0m")
            messages.pop()

        print()

if __name__ == "__main__":
    main()