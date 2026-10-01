# Setup, the MCP connection, security notes and the acceptance test: README.md in this folder.
# Instructions for the agent: AGENTS.md in this folder, linked once into the volume (inside pi):
# !!ln -sf /projects/pi-agent/AGENTS.md ~/.pi/agent/AGENTS.md
#
# podman build -t winkickoff-pi:local ./pi-agent/
# podman run -it --rm --name winkickoff-pi -v .:/projects:rw,Z,U -v pi-winkickoff:/home/pi/.pi --network=host --userns=keep-id winkickoff-pi:local
# podman exec -it winkickoff-pi sh
# Check the image and pi's MCP connection (temporary settings, the volume is not touched):
# podman exec -it winkickoff-pi python3 /projects/pi-agent/check_container.py
#
# disable telemetry (the image sets PI_TELEMETRY=0 as well)
# !!cat > ~/.pi/agent/settings.json <<EOF
# {
# 	"enableInstallTelemetry":false
# }
# EOF
#
# Add your model
# !!cat > ~/.pi/agent/models.json << EOF
# {
#   "providers": {
#     "llama-cpp": {
#       "baseUrl": "http://localhost:8088/v1",
#       "api": "openai-completions",
#       "apiKey": "?",
#       "models": [
#         {
#           "id": "Qwen3.6-35B",
#           "name": "Qwen3.6-35B",
#           "contextWindow": 262144,
#           "maxTokens": 196608
#         }
#       ]
#     }
#   }
# }
# EOF
#
# !!cat > ~/.pi/agent/mcp.json <<EOF
# {
#   "mcpServers": {
#     "winkickoff": {
#       "type": "http",
#       "url": "http://127.0.0.1:47831/mcp",
#       "headers": {
#         "Authorization": "Bearer ????????????"
#       }
#     }
#   }
# }
# EOF

# The full image name: Podman does not have to resolve a short name (it may refuse or ask which registry to use).
FROM docker.io/library/ubuntu:26.04

ENV DEBIAN_FRONTEND=noninteractive

# fd-find: pi's find tool uses fd (as fdfind) and would otherwise download it from GitHub into the volume.
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        bash \
        ca-certificates \
        curl \
        git \
        python3 \
        python3-pip \
        python3-venv \
        ripgrep \
        fd-find \
        file && \
    rm -rf /var/lib/apt/lists/*

# The tested pi version (MCP is built in since 0.99.0); --ignore-scripts as pi's documentation installs it, so no
# package script runs as root during the build. Another version: podman build --build-arg PI_VERSION=x.y.z ...
ARG PI_VERSION=0.99.2
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - && \
    apt-get update && \
    apt-get install -y --no-install-recommends nodejs && \
    npm install -g --ignore-scripts "@earendil-works/pi-coding-agent@${PI_VERSION}" && \
    npm cache clean --force && \
    rm -rf /var/lib/apt/lists/*

RUN mkdir -p \
        /projects \
        /projects/specification \
        /projects/sources \
        /home/pi \
        /home/pi/.pi/agent && \
    chmod -R 777 /projects /home/pi

WORKDIR /projects

ENV HOME=/home/pi
ENV PI_CODING_AGENT_DIR=/home/pi/.pi/agent
ENV PI_SKIP_VERSION_CHECK=1
# No install ping to pi.dev, not even on the first start of a new volume, before settings.json exists.
ENV PI_TELEMETRY=0

ENV XDG_CONFIG_HOME=/home/pi/.config
ENV XDG_CACHE_HOME=/home/pi/.cache
ENV XDG_DATA_HOME=/home/pi/.local/share

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1
ENV PIP_NO_CACHE_DIR=1

CMD ["pi"]
