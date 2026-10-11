#!/bin/sh
# Pulls the base model and builds the customised "travel-agent" model inside Ollama.
set -e
BASE_MODEL="${BASE_MODEL:-qwen2.5:7b}"
echo "Waiting for Ollama at $OLLAMA_HOST ..."
until ollama list >/dev/null 2>&1; do sleep 2; done
echo "Pulling $BASE_MODEL (first run downloads several GB)..."
ollama pull "$BASE_MODEL"
sed "s|^FROM .*|FROM $BASE_MODEL|" /ai/Modelfile > /tmp/Modelfile
ollama create travel-agent -f /tmp/Modelfile
echo "Model travel-agent is ready."
