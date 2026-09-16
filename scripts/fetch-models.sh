#!/usr/bin/env bash
# Download the Whisper models the browser page uses. They are not kept in git (~117 MB).
set -euo pipefail
WEB="$(cd "$(dirname "$0")/.." && pwd)/src/flipframe/web"

for model in whisper-tiny.en whisper-base.en; do
  base="https://huggingface.co/Xenova/$model/resolve/main"
  mkdir -p "$WEB/models/$model/onnx"
  for f in config.json tokenizer.json tokenizer_config.json preprocessor_config.json generation_config.json; do
    curl -sfL "$base/$f" -o "$WEB/models/$model/$f"
  done
  for f in encoder_model_quantized.onnx decoder_model_merged_quantized.onnx; do
    echo "fetching $model/$f"
    curl -#fL "$base/onnx/$f" -o "$WEB/models/$model/onnx/$f"
  done
done
echo "done: $(du -sh "$WEB/models" | cut -f1) in $WEB/models"
