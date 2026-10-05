#!/usr/bin/env bash
# Downloads a whisper.cpp ggml model from the official repository on Hugging Face.
# Usage: scripts/download-model.sh [name] [folder]
#   name    default: large-v3-turbo-q5_0  (574 MB). Others: large-v3-turbo (1.6 GB), medium (1.5 GB), small (466 MB), base (142 MB)
#   folder  default: <project>/data/models
set -euo pipefail
NAME="${1:-large-v3-turbo-q5_0}"
DIR="${2:-$(cd "$(dirname "$0")/.." && pwd)/data/models}"
FILE="ggml-${NAME}.bin"
# VAD models (silero-*) live in another repository of the same project.
case "$NAME" in
  silero-*) URL="https://huggingface.co/ggml-org/whisper-vad/resolve/main/${FILE}" ;;
  *)        URL="https://huggingface.co/ggerganov/whisper.cpp/resolve/main/${FILE}" ;;
esac
mkdir -p "$DIR"
if [ -s "$DIR/$FILE" ]; then
  echo "already exists: $DIR/$FILE"
  exit 0
fi
echo "downloading $URL"
curl -L --fail --progress-bar -C - -o "$DIR/$FILE.part" "$URL"
mv "$DIR/$FILE.part" "$DIR/$FILE"
echo "model saved to $DIR/$FILE ($(du -h "$DIR/$FILE" | cut -f1))"
