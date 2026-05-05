#!/bin/bash
# Setup script for the conversion server.
# Tested on Ubuntu 22.04 with NVIDIA H100. Run as root or with sudo.
set -e

echo "=== Installing system dependencies ==="
apt-get update -qq
apt-get install -y --no-install-recommends \
    git tmux curl ca-certificates \
    python3 python3-pip python3-venv

echo ""
echo "=== Installing Python packages ==="
pip3 install --quiet --upgrade pip
pip3 install --quiet -r requirements.txt

# vLLM is optional — only install if user wants to serve the model locally
read -p "Install vLLM for local model serving? (y/N) " install_vllm
if [[ $install_vllm =~ ^[Yy]$ ]]; then
    echo "Installing vLLM (this takes a few minutes)..."
    pip3 install --quiet vllm
fi

echo ""
echo "=== Setup complete ==="
echo ""
echo "Next steps:"
echo "  1. cp config.yaml.example config.yaml"
echo "  2. Copy raw_docs.jsonl from your scraper VPS into data/raw/"
echo "  3. Start the model server (one of these):"
echo ""
echo "     vLLM:    python3 -m vllm.entrypoints.openai.api_server \\"
echo "                --model Qwen/Qwen2.5-72B-Instruct-AWQ \\"
echo "                --quantization awq --port 8000"
echo ""
echo "     Ollama:  ollama serve && ollama pull qwen2.5:32b"
echo ""
echo "  4. python3 main.py --check-model   # verify server is reachable"
echo "  5. python3 main.py                 # run full pipeline (~10 days)"
echo ""
