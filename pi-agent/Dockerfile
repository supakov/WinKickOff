# The WinKickOff assistant: the pi agent with a local model, run with pi's defaults. It reaches WinKickOff only over the
# MCP server of WinKickOff, from codemode scripts; the image holds nothing of WinKickOff but the assistant's instructions.
# Setup, networking, security and troubleshooting: README.md next to this file.
#
# Build (from the folder of this file) and run. Nothing is mounted except the volume with pi's settings:
#   podman build -t winkickoff-pi:local .
#   podman run -it --rm --name winkickoff-pi -v pi-winkickoff:/home/pi/.pi --network=host winkickoff-pi:local
# A second shell in the running container (for the setup below, or "pi mcp list"):
#   podman exec -it winkickoff-pi sh
#
# One-time setup of the volume (in that second shell; inside pi prefix each command with !!):
#
# cat > ~/.pi/agent/settings.json <<'EOF'
# {
#   "enableInstallTelemetry": false,
#   "defaultProvider": "llama-cpp",
#   "defaultModel": "Qwen3.6-35B",
#   "defaultTools": ["+codemode"]
# }
# EOF
#
# cat > ~/.pi/agent/models.json <<'EOF'
# {
#   "providers": {
#     "llama-cpp": {
#       "baseUrl": "http://localhost:8088/v1",
#       "api": "openai-completions",
#       "apiKey": "none",
#       "models": [
#         { "id": "Qwen3.6-35B", "name": "Qwen3.6-35B", "contextWindow": 262144, "maxTokens": 196608 }
#       ]
#     }
#   }
# }
# EOF
#
# "+codemode" keeps pi's script tool among its default tools even without a server entry; for the codemode entry below
# pi also turns it on by itself at the start of every session.
#
# The MCP entry: "Copy client configuration (HTTP)" in the "MCP" menu of the WinKickOff window, pasted unchanged (pi's
# default exposure codemode: the model calls the WinKickOff tools from codemode scripts). Keep the name winkickoff (the
# instructions of the assistant name it) and no other server in this file: its tools would be callable from scripts too.
# cat > ~/.pi/agent/mcp.json <<'EOF'
# {
#   "mcpServers": {
#     "winkickoff": {
#       "type": "http",
#       "url": "http://127.0.0.1:47831/mcp",
#       "headers": { "Authorization": "Bearer <token copied from the window>" }
#     }
#   }
# }
# EOF

# The full image name: Podman does not have to resolve a short name (it may refuse or ask which registry to use).
FROM docker.io/library/ubuntu:26.04

ENV DEBIAN_FRONTEND=noninteractive

# bash: pi's bash tool and the person's own "!" commands in pi. ripgrep and fd-find: the interactive pi looks for them at every start and
# would otherwise download them from GitHub into the volume. curl: the Node.js download below.
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        bash \
        ca-certificates \
        curl \
        ripgrep \
        fd-find && \
    rm -rf /var/lib/apt/lists/*

ENV HOME=/home/pi
ENV PI_CODING_AGENT_DIR=/home/pi/.pi/agent
ENV PI_SKIP_VERSION_CHECK=1
# No install ping to pi.dev, not even on the first start of a new volume, before settings.json exists.
ENV PI_TELEMETRY=0
ENV XDG_CONFIG_HOME=/home/pi/.config
ENV XDG_CACHE_HOME=/home/pi/.cache
ENV XDG_DATA_HOME=/home/pi/.local/share

# Node.js from the official release archive, checked against the SHA-256 pinned here (nodejs.org/dist/v<version>/
# SHASUMS256.txt). Not the NodeSource package: it depends on a script interpreter the agent must not have. Another
# version: --build-arg NODE_VERSION=... with both checksums of that release.
ARG NODE_VERSION=22.23.3
ARG NODE_SHA256_AMD64=1084aa36196bba4c3a5e69a1ee388a6e4ff729dad09445fbcd434b28fe3c24af
ARG NODE_SHA256_ARM64=5ced2d48d1d7198739b7f86804de0171aefb6823b684b12341d3321afc3cb0b2
RUN arch="$(dpkg --print-architecture)" && \
    case "$arch" in \
        amd64) node_arch=x64; sum="$NODE_SHA256_AMD64" ;; \
        arm64) node_arch=arm64; sum="$NODE_SHA256_ARM64" ;; \
        *) echo "no Node.js archive for $arch" >&2; exit 1 ;; \
    esac && \
    archive="node-v${NODE_VERSION}-linux-${node_arch}.tar.gz" && \
    curl -fsSLo "/tmp/$archive" "https://nodejs.org/dist/v${NODE_VERSION}/$archive" && \
    echo "$sum  /tmp/$archive" | sha256sum -c - && \
    mkdir -p /opt/node && \
    tar -xzf "/tmp/$archive" -C /opt/node --strip-components=1 --no-same-owner && \
    rm -f "/tmp/$archive"
# Node.js and the commands npm installs globally, pi among them.
ENV PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/opt/node/bin

# The tested pi version (MCP is built in since 0.99.0, Node.js 22.19 or later); --ignore-scripts as pi's documentation
# installs it, so no package script runs as root during the build. Another version: --build-arg PI_VERSION=x.y.z
ARG PI_VERSION=1.0.0
# pi starts with its defaults: its own tools, the built-in MCP extension and codemode, its default system prompt with
# /work/AGENTS.md as the context file. The customer removed the wrapper that restricted it (02.10.2026): it took away the
# additional tools and codemode and replaced the system instructions, and the whole agent worked worse.
RUN npm install -g --ignore-scripts "@earendil-works/pi-coding-agent@${PI_VERSION}" && \
    npm cache clean --force && \
    test "$(command -v pi)" = "$(npm prefix -g)/bin/pi" && \
    pi --version

RUN mkdir -p /home/pi/.pi/agent /work && \
    chmod -R 777 /home/pi

# The folder pi starts in holds only the instructions of the assistant; pi loads them as its context file.
WORKDIR /work
COPY AGENTS.md /work/AGENTS.md

CMD ["pi"]
