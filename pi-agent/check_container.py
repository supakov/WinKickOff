"""Checks of the pi agent container: what the agent runs there, and pi's connection to WinKickOff's MCP server.

Run it inside the container:

    python3 /projects/pi-agent/check_container.py            everything (a few minutes)
    python3 /projects/pi-agent/check_container.py --quick    without the unit tests

The checks:
1. the tools of the image: Python 3.14 or later, Node.js, pi, ripgrep and fd;
2. the unit tests of WinKickOff, run as pi-agent/AGENTS.md tells the agent to run them;
3. the dash check of pi-agent/AGENTS.md;
4. the headless commands of WinKickOff (--version, --mcp-config);
5. pi's own MCP client against two headless WinKickOff servers started here: one over stdio, one over HTTP on a free
   port with a random token. pi gets a temporary agent folder, so the settings, the model list and the token in the
   volume of the container are not touched, and no model is needed.

The CI job pi-agent-container runs this script in a freshly built image. Exit code 0: every check passed.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECTS = Path(__file__).resolve().parents[1]
WINKICKOFF = PROJECTS / "WinKickOff"
TOOLS = ("get_status", "list_rules", "get_rule", "preview_build", "write_answer_file")  # some of the 18 tools
URL_RE = re.compile(r"http://127\.0\.0\.1:\d+/mcp")


def step(title: str) -> None:
    print(f"\n== {title}", flush=True)


def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
    print("$ " + " ".join(command), flush=True)
    return subprocess.run(command, text=True, **kwargs)  # type: ignore[call-overload]


def fail(message: str) -> None:
    raise SystemExit(f"FAILED: {message}")


def check_tools() -> None:
    step("tools of the image")
    if sys.version_info < (3, 14):
        fail(f"Python 3.14 or later is required, this is {sys.version.split()[0]}")
    for command in (["python3", "--version"], ["node", "--version"], ["pi", "--version"], ["rg", "--version"],
                    ["fdfind", "--version"]):
        try:
            result = run(command, capture_output=True, timeout=60)
        except (OSError, subprocess.TimeoutExpired) as exc:
            fail(f"{command[0]} does not run: {exc}")
        output = (result.stdout or result.stderr).strip()
        if result.returncode != 0 or not output:
            fail(f"{command[0]} answered {result.returncode}: {output}")
        print(output.splitlines()[0], flush=True)


def check_tests() -> None:
    step("unit tests of WinKickOff")
    if run([sys.executable, "-m", "unittest", "discover", "-s", "tests"], cwd=WINKICKOFF).returncode != 0:
        fail("the unit tests of WinKickOff")


def check_dashes() -> None:
    step("no em or en dash in the tree")
    result = run(["rg", "-n", r"[\x{2013}\x{2014}]", "-g", "!docs/appendices/**", "."], cwd=PROJECTS,
                 capture_output=True)
    if result.returncode == 0:  # ripgrep: 0 found, 1 nothing found, 2 error
        print(result.stdout, flush=True)
        fail("dashes found")
    if result.returncode != 1:
        fail(f"ripgrep failed: {result.stderr.strip()}")
    print("none", flush=True)


def check_headless() -> None:
    step("headless commands of WinKickOff")
    version = run([sys.executable, "-m", "winkickoff", "--version"], cwd=WINKICKOFF, capture_output=True)
    if version.returncode != 0 or not version.stdout.startswith("WinKickOff "):
        fail(f"--version answered {version.returncode}: {version.stdout}{version.stderr}")
    print(version.stdout.strip(), flush=True)
    config = run([sys.executable, "-m", "winkickoff", "--mcp-config", "stdio"], cwd=WINKICKOFF, capture_output=True)
    try:
        entry = json.loads(config.stdout)["mcpServers"]["winkickoff"]
    except (ValueError, KeyError) as exc:
        fail(f"--mcp-config stdio printed no client entry ({exc}): {config.stdout}{config.stderr}")
    if entry.get("args") != ["-m", "winkickoff", "--mcp", "stdio"]:
        fail(f"unexpected stdio entry: {entry}")
    print(f"stdio entry: {entry['command']} {' '.join(entry['args'])}", flush=True)


def start_http_server(token: str) -> tuple[subprocess.Popen[str], str]:
    server = subprocess.Popen([sys.executable, "-m", "winkickoff", "--mcp", "http", "--port", "0", "--token", token],
                              cwd=WINKICKOFF, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    line = server.stdout.readline() if server.stdout else ""  # printed right after the bind, or the error
    found = URL_RE.search(line)
    if not found:
        server.kill()
        fail(f"the headless HTTP server did not start: {line.strip()}")
    return server, found.group(0)


def check_pi_mcp() -> None:
    step("pi connects to WinKickOff over stdio and over HTTP")
    token = secrets.token_urlsafe(32)
    server, url = start_http_server(token)
    print(f"headless HTTP server: {url}", flush=True)
    try:
        with tempfile.TemporaryDirectory(prefix="pi-agent-") as agent_dir:
            servers = {
                "winkickoff-local": {"command": sys.executable,
                                     "args": ["-m", "winkickoff", "--mcp", "stdio", "--mode", "read", "--profile", "office"],
                                     "cwd": str(WINKICKOFF), "env": {"PYTHONPATH": str(WINKICKOFF)}, "exposure": "direct"},
                "winkickoff": {"type": "http", "url": url, "exposure": "direct",
                               "headers": {"Authorization": "Bearer ${WINKICKOFF_MCP_TOKEN}"}},
            }
            Path(agent_dir, "mcp.json").write_text(json.dumps({"mcpServers": servers}, indent=2), encoding="utf-8")
            env = {**os.environ, "PI_CODING_AGENT_DIR": agent_dir, "PI_OFFLINE": "1", "PI_TELEMETRY": "0",
                   "WINKICKOFF_MCP_TOKEN": token}
            try:
                result = run(["pi", "mcp", "list"], cwd=PROJECTS, env=env, capture_output=True, timeout=180)
            except subprocess.TimeoutExpired:
                fail("pi mcp list did not finish within 180 s")
    finally:
        server.terminate()
        try:
            server.wait(10)
        except subprocess.TimeoutExpired:
            server.kill()
    output = result.stdout + result.stderr
    print(output, flush=True)
    if result.returncode != 0:
        fail(f"pi mcp list exited with {result.returncode}: a server did not connect")
    missing = [name for name in TOOLS if output.count(name) < 2]  # each tool once for each of the two servers
    if "winkickoff-local" not in output or missing:
        fail(f"pi does not list the tools of both servers; missing: {missing or ['winkickoff-local']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Checks of the pi agent container (pi-agent/README.md)")
    parser.add_argument("--quick", action="store_true", help="skip the unit tests of WinKickOff")
    args = parser.parse_args()
    check_tools()
    if not args.quick:
        check_tests()
    check_dashes()
    check_headless()
    check_pi_mcp()
    print("\nAll checks passed.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
