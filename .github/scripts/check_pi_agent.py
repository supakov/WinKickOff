"""Checks of the image of pi-agent/ (the WinKickOff assistant) for the CI job pi-agent-container.

Run on the Linux runner from the root of a checkout, with Python 3.14 and Podman, after the image was built:

    podman build -t winkickoff-pi:ci ./pi-agent/
    python .github/scripts/check_pi_agent.py winkickoff-pi:ci

pi runs with its defaults (the customer removed the wrapper that restricted it on 02.10.2026): its own tools, the
built-in MCP support with exposure codemode, pi's default system prompt with /work/AGENTS.md as the context file. The
checks:
1. the image: /work holds only AGENTS.md, byte for byte pi-agent/AGENTS.md; python3, git, file and pip are absent;
   node, bash, rg and fdfind are present; "pi" is npm's own command, there is no wrapper in /usr/local/bin; no prompt,
   context, skill or extension file is baked in where pi looks; no file of the image is named after WinKickOff; CMD is
   pi and the working folder /work;
2. a headless WinKickOff HTTP server started from this checkout on 127.0.0.1 with a random token; its tools/list and
   resources/list are the reference (18 tools, the skill resource winkickoff://skill/SKILL.md);
3. "pi mcp list --json" in the container (host network, a temporary agent folder mounted as /home/pi/.pi/agent with the
   settings of pi-agent/README.md and the MCP entry as the window copies it, the token in an environment variable):
   winkickoff connected, exposure codemode, exactly the tools of the server, resources and templates offered. Only
   HTTP: the image has no WinKickOff program to start over stdio;
4. without a model: pi answers one prompt in print mode from a stub OpenAI-compatible server on 127.0.0.1. The first
   request offers pi's default tools and codemode, declares no mcp__ tool, and its system prompt holds AGENTS.md. The
   stub answers with a codemode script that calls WinKickOff tools (get_status, and get_rule with an unknown id, which
   the server refuses) and reads a resource; the next request must carry the script's result. pi 0.99.2 documents
   (docs/mcp.md) that a call in a script resolves to the whole CallToolResult, a refusal included (isError true), and
   that a resource read gives {server, uri, contents}; pi-agent/AGENTS.md teaches the model exactly that, so the check
   asserts it. Where pi names the server for the model is printed.

Nothing outside a temporary folder and WinKickOff/logs/ is written. Exit code 0: every check passed.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import subprocess
import sys
import tempfile
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
WINKICKOFF = REPO / "WinKickOff"
AGENTS = REPO / "pi-agent" / "AGENTS.md"
URL_RE = re.compile(r"http://127\.0\.0\.1:\d+/mcp")
SERVER = "winkickoff"
RESOURCE_TOOLS = {"list_mcp_resources", "list_mcp_resource_templates", "read_mcp_resource"}
REMOVED_WRAPPER = "/usr/local/bin/pi"
PI_DEFAULTS = {"read", "bash", "edit", "write"}
CODEMODE = "codemode"
SETTINGS = {"enableInstallTelemetry": False, "defaultTools": ["+codemode"]}  # as in pi-agent/README.md, step 1
ABSENT = ("python3", "python", "git", "file", "pip", "pip3")
PRESENT = ("node", "bash", "rg", "fdfind")
# files pi would load as prompt, context, skills or extensions, if the image held them where pi looks
BAKED = ("find /home/pi/.pi /home/pi/.agents \\( -name 'AGENTS.md' -o -name 'AGENTS.MD' -o -name 'AGENTS.override.md' "
         "-o -name 'CLAUDE.md' -o -name 'CLAUDE.MD' -o -name 'SYSTEM.md' -o -name 'APPEND_SYSTEM.md' -o -name skills "
         "-o -name extensions -o -name prompts \\) 2>/dev/null; "
         "for p in /AGENTS.md /AGENTS.MD /AGENTS.override.md /CLAUDE.md /CLAUDE.MD /.pi /.agents /work/.pi "
         "/work/.agents; do test -e \"$p\" && echo \"$p\"; done; true")
# the script the stub model runs through codemode: the WinKickOff tools as the instructions of the assistant call them
PROBE = """const out = {};
const s = await tools.mcp__winkickoff__get_status({});
out.statusKeys = (s && typeof s === "object") ? Object.keys(s).sort() : typeof s;
out.status = s?.structuredContent ?? null;
try {
  const r = await tools.mcp__winkickoff__get_rule({id: "no-such.rule"});
  out.refusal = {resolved: true, isError: r?.isError ?? null, text: r?.content?.[0]?.text ?? null,
                 kind: r?.structuredContent?.error ?? null};
} catch (e) { out.refusal = {resolved: false, text: String(e?.message ?? e)}; }
try {
  const d = await tools.read_mcp_resource({server: "winkickoff", uri: "winkickoff://skill/SKILL.md"});
  out.resource = {keys: Object.keys(d ?? {}), text: typeof d?.contents?.[0]?.text, size: JSON.stringify(d ?? null).length};
} catch (e) { out.resource = {error: String(e?.message ?? e)}; }
try { out.namespace = Object.keys((await describeNamespace("mcp__winkickoff")) ?? {}); }
catch (e) { out.namespace = String(e?.message ?? e); }
out.own = ["read", "bash", "edit", "write"].filter(n => typeof tools[n] === "function");
return out;
"""
NEEDLES = ("has_window", "unknown_id")  # in the result of get_status, in the refusal of get_rule; never in PROBE


def step(title: str) -> None:
    print(f"\n== {title}", flush=True)


def fail(message: str) -> None:
    raise SystemExit(f"FAILED: {message}")


def run(command: list[str], *, timeout: int = 300, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[bytes]:
    print("$ " + " ".join(command), flush=True)
    try:
        return subprocess.run(command, capture_output=True, timeout=timeout, env=env, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired as exc:
        raise SystemExit(f"FAILED: {' '.join(command[:3])} did not finish within {timeout} s") from exc


def text(result: subprocess.CompletedProcess[bytes]) -> str:
    return (result.stdout + result.stderr).decode("utf-8", "replace")


# --------------------------------------------------------------------------- 1. the image


def check_image(image: str) -> None:
    step("the image")
    config = json.loads(run(["podman", "image", "inspect", image, "--format", "{{json .Config}}"]).stdout)
    if config.get("Cmd") != ["pi"] or config.get("WorkingDir") != "/work":
        fail(f"CMD must be [\"pi\"] and the working folder /work: {config.get('Cmd')}, {config.get('WorkingDir')}")
    listing = run(["podman", "run", "--rm", image, "ls", "-A", "/work"])
    if listing.returncode != 0 or listing.stdout.decode().split() != ["AGENTS.md"]:
        fail(f"/work must hold only AGENTS.md: {text(listing)}")
    copied = run(["podman", "run", "--rm", image, "cat", "/work/AGENTS.md"]).stdout
    if copied != AGENTS.read_bytes():
        fail("/work/AGENTS.md differs from pi-agent/AGENTS.md")
    for name in ABSENT:
        if run(["podman", "run", "--rm", image, "sh", "-c", f"command -v {name}"]).returncode == 0:
            fail(f"{name} must not be in the image")
    for name in PRESENT:
        if run(["podman", "run", "--rm", image, "sh", "-c", f"command -v {name}"]).returncode != 0:
            fail(f"{name} is missing in the image")
    plain = run(["podman", "run", "--rm", image, "sh", "-c",
                 f'test ! -e {REMOVED_WRAPPER} && test "$(command -v pi)" = "$(npm prefix -g)/bin/pi"'])
    if plain.returncode != 0:
        fail(f"pi must be npm's own command, without a wrapper in {REMOVED_WRAPPER}: {text(plain)}")
    baked = run(["podman", "run", "--rm", image, "sh", "-c", BAKED]).stdout.decode().split()
    if baked:
        fail(f"the image holds files pi would load as prompt, context, skills or extensions: {baked}")
    named = run(["podman", "run", "--rm", image, "find", "/", "-xdev", "-iname", "*winkickoff*"]).stdout.decode().split()
    if named:
        fail(f"the image holds files named after WinKickOff: {named}")
    version = run(["podman", "run", "--rm", image, "pi", "--version"])
    if version.returncode != 0:
        fail(f"pi --version: {text(version)}")
    print("pi " + text(version).strip(), flush=True)


# --------------------------------------------------------------------------- 2. the WinKickOff server


def start_server(token: str) -> tuple[subprocess.Popen[str], str]:
    server = subprocess.Popen([sys.executable, "-m", "winkickoff", "--mcp", "http", "--port", "0", "--token", token,
                               "--profile", "office"], cwd=WINKICKOFF, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, text=True)
    first: list[str] = []
    reader = threading.Thread(target=lambda: first.append(server.stdout.readline() if server.stdout else ""), daemon=True)
    reader.start()
    reader.join(60)  # the server prints its URL right after the bind, or the error
    found = URL_RE.search(first[0]) if first else None
    if not found:
        try:
            code = server.wait(10)
        except subprocess.TimeoutExpired:
            server.kill()
            code = server.wait(10)
        print(f"the server exited with code {code}", flush=True)
        show_server_log(server.pid)
        fail(f"the headless WinKickOff server did not start: {first[0].strip() if first and first[0] else 'no URL printed'}")
    return server, found.group(0)


def show_server_log(pid: int) -> None:
    """A failed start-up is written only to the log of the headless process (logs/mcp-http-<pid>.log): print it."""
    logs = WINKICKOFF / "logs"
    own = logs / f"mcp-http-{pid}.log"
    candidates = [own] if own.is_file() else sorted(logs.glob("mcp-http-*.log"), key=lambda p: p.stat().st_mtime)[-1:]
    for path in candidates:
        print(f"--- {path}", flush=True)
        print(path.read_text(encoding="utf-8", errors="replace")[-8000:], flush=True)
    if not candidates:
        print(f"no log in {logs}", flush=True)


def rpc(url: str, token: str, message: dict[str, Any], session: str = "") -> tuple[dict[str, Any] | None, str]:
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json", "Accept": "application/json"}
    if session:
        headers["Mcp-Session-Id"] = session
    request = urllib.request.Request(url, json.dumps(message).encode(), headers, method="POST")
    with urllib.request.urlopen(request, timeout=30) as response:
        body = response.read()
        return (json.loads(body) if body else None), response.headers.get("Mcp-Session-Id") or session


def server_reference(url: str, token: str) -> tuple[set[str], set[str]]:
    """The tool names and resource URIs of the running server, asked over MCP as pi asks."""
    hello = {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "ci", "version": "1"}}
    _, session = rpc(url, token, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": hello})
    rpc(url, token, {"jsonrpc": "2.0", "method": "notifications/initialized"}, session)
    tools, _ = rpc(url, token, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, session)
    resources, _ = rpc(url, token, {"jsonrpc": "2.0", "id": 3, "method": "resources/list"}, session)
    names = {tool["name"] for tool in (tools or {})["result"]["tools"]}
    uris = {item["uri"] for item in (resources or {})["result"]["resources"]}
    if len(names) != 18:
        fail(f"the server lists {len(names)} tools, not 18: {sorted(names)}")
    if "winkickoff://skill/SKILL.md" not in uris:
        fail("the server does not offer winkickoff://skill/SKILL.md")
    return names, uris


# --------------------------------------------------------------------------- 3. pi mcp list


def write_agent_dir(folder: Path, url: str, stub_port: int) -> None:
    """The agent folder as pi-agent/README.md sets it up: the entry the window copies (no exposure), codemode added."""
    entry = {"type": "http", "url": url, "headers": {"Authorization": "Bearer ${WINKICKOFF_MCP_TOKEN}"}}
    (folder / "mcp.json").write_text(json.dumps({"mcpServers": {SERVER: entry}}, indent=2), encoding="utf-8")
    model = {"id": "stub", "name": "stub", "contextWindow": 32768, "maxTokens": 1024}
    provider = {"baseUrl": f"http://127.0.0.1:{stub_port}/v1", "api": "openai-completions", "apiKey": "none",
                "models": [model]}
    (folder / "models.json").write_text(json.dumps({"providers": {"stub": provider}}, indent=2), encoding="utf-8")
    (folder / "settings.json").write_text(json.dumps(SETTINGS), encoding="utf-8")
    folder.chmod(0o777)  # the container may run as another user than the runner


def container(image: str, agent_dir: Path, *command: str) -> list[str]:
    return ["podman", "run", "--rm", "--network=host", "-e", "WINKICKOFF_MCP_TOKEN", "-e", "PI_OFFLINE=1",
            "-v", f"{agent_dir}:/home/pi/.pi/agent", image, *command]


def bare(name: str) -> str:
    return name.split("__")[-1] if name.startswith("mcp__") else name


def check_mcp_list(image: str, agent_dir: Path, env: dict[str, str], tools: set[str]) -> None:
    step("pi mcp list in the container")
    result = run(container(image, agent_dir, "pi", "mcp", "list", "--json"), env=env, timeout=180)
    output = text(result)
    print(output, flush=True)
    if result.returncode != 0:
        fail(f"pi mcp list exited with {result.returncode}: the server did not connect")
    try:
        servers = {item["name"]: item for item in json.loads(result.stdout)["servers"]}
    except (ValueError, KeyError, TypeError) as exc:
        fail(f"pi mcp list --json printed no server list: {exc}")
    if SERVER not in servers:
        fail(f"the server {SERVER} must be listed: {sorted(servers)}")
    entry = servers[SERVER]
    if entry.get("state") != "connected" or entry.get("exposure") not in (None, CODEMODE):
        fail(f"{SERVER}: state {entry.get('state')}, exposure {entry.get('exposure')}; connected and codemode required")
    listed = {bare(item["name"] if isinstance(item, dict) else str(item)) for item in entry.get("tools", [])}
    if listed != tools:
        fail(f"pi lists other tools than the server: missing {sorted(tools - listed)}, extra {sorted(listed - tools)}")
    for key in ("resources", "resourceTemplates"):
        count = entry.get(key)
        count = len(count) if isinstance(count, list) else count
        if not isinstance(count, int) or count <= 0:
            fail(f"{SERVER}: {key} is {entry.get(key)!r}; the server offers resources and templates")
    print(f"{SERVER}: connected, exposure codemode, {len(listed)} tools", flush=True)


# --------------------------------------------------------------------------- 4. the requests pi sends to a model


class StubModel(BaseHTTPRequestHandler):
    """An OpenAI-compatible endpoint that records every request body. It answers the first request that offers
    codemode with a codemode call running PROBE, every other one with "ok"."""

    requests: list[dict[str, Any]] = []

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - the name of the base class
        print("stub model: " + format % args, flush=True)

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - the naming of the base class
        self._send(200, json.dumps({"object": "list", "data": [{"id": "stub", "object": "model"}]}).encode(),
                   "application/json")

    def do_POST(self) -> None:  # noqa: N802
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        StubModel.requests.append(body)
        offered = {item.get("function", {}).get("name"): item.get("function", {}) for item in body.get("tools", [])}
        answered = any(message.get("role") == "tool" for message in body.get("messages", []))
        call = None
        if CODEMODE in offered and not answered:
            required = (offered[CODEMODE].get("parameters") or {}).get("required") or ["code"]
            call = {"id": "call_probe", "type": "function",
                    "function": {"name": CODEMODE, "arguments": json.dumps({required[0]: PROBE})}}
        base = {"id": "stub-1", "created": 0, "model": "stub"}
        usage = {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}
        finish = "tool_calls" if call else "stop"
        if not body.get("stream"):
            message = {"role": "assistant", "content": None, "tool_calls": [call]} if call else \
                {"role": "assistant", "content": "ok"}
            answer = {**base, "object": "chat.completion", "usage": usage,
                      "choices": [{"index": 0, "message": message, "finish_reason": finish}]}
            self._send(200, json.dumps(answer).encode(), "application/json")
            return
        chunk = {**base, "object": "chat.completion.chunk"}
        delta = {"role": "assistant", "tool_calls": [{"index": 0, **call}]} if call else \
            {"role": "assistant", "content": "ok"}
        events = [
            {**chunk, "choices": [{"index": 0, "delta": delta, "finish_reason": None}]},
            {**chunk, "choices": [{"index": 0, "delta": {}, "finish_reason": finish}], "usage": usage},
        ]
        stream = "".join(f"data: {json.dumps(event)}\n\n" for event in events) + "data: [DONE]\n\n"
        self._send(200, stream.encode(), "text/event-stream")


def message_text(message: dict[str, Any]) -> str:
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(str(item.get("text", "")) for item in content if isinstance(item, dict))
    return ""


def system_text(body: dict[str, Any]) -> str:
    return "\n".join(message_text(m) for m in body.get("messages", []) if m.get("role") in ("system", "developer"))


def check_model_request(image: str, agent_dir: Path, env: dict[str, str]) -> None:
    step("what pi gives the model and how a codemode script reaches WinKickOff (stub model, no real model)")
    result = run(container(image, agent_dir, "pi", "-p", "ping", "--no-session", "--provider", "stub", "--model", "stub"),
                 env=env, timeout=300)
    print(f"exit code {result.returncode}\n{text(result)}", flush=True)
    chats = [body for body in StubModel.requests if "messages" in body]
    if not chats:
        fail("pi sent no chat request to the stub model")
    first = chats[0]
    sent = {item.get("function", {}).get("name") for item in first.get("tools", [])}
    print(f"request 1 offers {len(sent)} tools: {sorted(str(name) for name in sent)}", flush=True)
    missing = sorted((PI_DEFAULTS | {CODEMODE}) - sent)
    if missing:
        fail(f"pi does not offer the model {missing}: its default tools and codemode are expected")
    declared = sorted(str(name) for name in sent if str(name).startswith("mcp__"))
    if declared:
        fail(f"with exposure codemode no MCP tool is declared to the model: {declared}")
    print(f"resource tools declared: {sorted(RESOURCE_TOOLS & sent)}; tool_search declared: {'tool_search' in sent}",
          flush=True)
    prompt = system_text(first).replace("\r\n", "\n")
    agents = AGENTS.read_text(encoding="utf-8").replace("\r\n", "\n")
    for line in (agents.splitlines()[0], "You are the WinKickOff assistant."):
        if line not in prompt:
            fail(f"the system prompt lacks {line!r} of pi-agent/AGENTS.md")
    print(f"the system prompt: {len(prompt)} characters; the whole AGENTS.md in it: {agents.strip() in prompt}; "
          f"pi's default preamble: {'coding assistant' in prompt}; "
          f"<project_instructions: {'<project_instructions' in prompt}", flush=True)
    for index, body in enumerate(chats, start=1):  # where pi names the server for the model
        for message in body.get("messages", []):
            content = message_text(message)
            start = content.find("mcp__winkickoff")
            if start >= 0 and message.get("role") != "tool":
                print(f"request {index}, role {message.get('role')}: ...{content[max(0, start - 200):start + 300]}...",
                      flush=True)
    results = [message_text(m) for body in chats[1:] for m in body.get("messages", []) if m.get("role") == "tool"]
    if not results:
        fail("pi did not run the codemode call of the stub model: no later request carries a tool result")
    print("the result of the codemode script (first 4000 characters):\n" + results[-1][:4000], flush=True)
    absent = [needle for needle in NEEDLES if needle not in results[-1]]
    if absent:
        fail(f"the codemode script did not reach the WinKickOff tools: {absent} missing in its result")
    probe = probe_result(results[-1])
    keys = probe.get("statusKeys")
    if not isinstance(keys, list) or not {"content", "structuredContent"} <= set(keys) or \
            "has_window" not in (probe.get("status") or {}):
        fail(f"a call in a script must resolve to the whole CallToolResult, as pi-agent/AGENTS.md says: {keys}")
    refusal = probe.get("refusal") or {}
    if not (refusal.get("resolved") is True and refusal.get("isError") is True and refusal.get("kind") == "unknown_id"
            and str(refusal.get("text") or "").startswith("unknown_id:")):
        fail(f"a refused call must resolve in a script with isError true and its kind first in content[0].text and in "
             f"structuredContent.error, as pi-agent/AGENTS.md says: {refusal}")
    resource = probe.get("resource") or {}
    if "error" in resource:
        print(f"WARNING: read_mcp_resource is not callable in a script, section 9 of pi-agent/AGENTS.md fails: {resource}",
              flush=True)
    elif not {"server", "uri", "contents"} <= set(resource.get("keys") or []) or resource.get("text") != "string":
        fail(f"a resource read in a script must give {{server, uri, contents}} with the text in contents[0].text: {resource}")
    print("a codemode script got the CallToolResult of get_status, the resolved refusal of get_rule and a resource",
          flush=True)


def probe_result(result: str) -> dict[str, Any]:
    """The object PROBE returned: codemode prints it as JSON after "Output:"."""
    at = result.find("Output:")
    payload = result[at + len("Output:"):].lstrip() if at >= 0 else result[max(result.find("{"), 0):]
    try:
        value, _ = json.JSONDecoder().raw_decode(payload)
    except ValueError as exc:
        fail(f"the result of the codemode script is not the JSON PROBE returns: {exc}")
    if not isinstance(value, dict):
        fail(f"the result of the codemode script is not an object: {value!r}")
    return value


# --------------------------------------------------------------------------- main


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    image = sys.argv[1]
    check_image(image)
    step("the headless WinKickOff server")
    token = secrets.token_urlsafe(32)
    server, url = start_server(token)
    stub = ThreadingHTTPServer(("127.0.0.1", 0), StubModel)
    threading.Thread(target=stub.serve_forever, daemon=True).start()
    try:
        tools, uris = server_reference(url, token)
        print(f"{url}: {len(tools)} tools, {len(uris)} resources", flush=True)
        env = {**os.environ, "WINKICKOFF_MCP_TOKEN": token}
        with tempfile.TemporaryDirectory(prefix="pi-agent-") as folder:
            agent_dir = Path(folder)
            write_agent_dir(agent_dir, url, stub.server_address[1])
            check_mcp_list(image, agent_dir, env, tools)
            check_model_request(image, agent_dir, env)
    finally:
        stub.shutdown()
        server.terminate()
        try:
            server.wait(10)
        except subprocess.TimeoutExpired:
            server.kill()
    print("\nAll checks passed.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
