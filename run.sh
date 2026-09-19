#!/usr/bin/env bash
# Jalankan Clipping Studio di http://localhost:8765
set -e
# Redam log bawaan MediaPipe/TensorFlow Lite.
export GLOG_minloglevel=2 TF_CPP_MIN_LOG_LEVEL=3 GRPC_VERBOSITY=ERROR
cd "$(dirname "$0")"
PORT="${PORT:-8765}"
if [ ! -x .venv/bin/python ]; then
  echo "Menyiapkan environment Python (sekali saja)…"
  if command -v uv >/dev/null; then
    uv venv --python 3.12 .venv
    uv pip install --python .venv/bin/python -r requirements.txt
  else
    python3 -m venv .venv
    .venv/bin/pip install -r requirements.txt
  fi
fi
( sleep 2 && open "http://localhost:$PORT" 2>/dev/null || true ) &
exec .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT"
