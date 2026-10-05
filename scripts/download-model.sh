#!/usr/bin/env bash
# Baixa um modelo ggml do whisper.cpp a partir do repositório oficial no Hugging Face.
# Uso: scripts/download-model.sh [nome] [pasta]
#   nome   padrão: large-v3-turbo-q5_0  (574 MB). Outros: large-v3-turbo (1,6 GB), medium (1,5 GB), small (466 MB), base (142 MB)
#   pasta  padrão: <projeto>/data/models
set -euo pipefail
NAME="${1:-large-v3-turbo-q5_0}"
DIR="${2:-$(cd "$(dirname "$0")/.." && pwd)/data/models}"
FILE="ggml-${NAME}.bin"
URL="https://huggingface.co/ggerganov/whisper.cpp/resolve/main/${FILE}"
mkdir -p "$DIR"
if [ -s "$DIR/$FILE" ]; then
  echo "já existe: $DIR/$FILE"
  exit 0
fi
echo "baixando $URL"
curl -L --fail --progress-bar -C - -o "$DIR/$FILE.part" "$URL"
mv "$DIR/$FILE.part" "$DIR/$FILE"
echo "modelo salvo em $DIR/$FILE ($(du -h "$DIR/$FILE" | cut -f1))"
