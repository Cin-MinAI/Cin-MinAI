#!/usr/bin/env bash
# User-level training environment for the guide fine-tune (no sudo): uv + a venv in ~/cinminai-train.
set -euo pipefail
export PATH=$HOME/.local/bin:$PATH
command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh
mkdir -p ~/cinminai-train && cd ~/cinminai-train
[ -d .venv ] || uv venv --python 3.12 .venv
. .venv/bin/activate
uv pip install --quiet torch --index-url https://download.pytorch.org/whl/cu128
uv pip install --quiet transformers peft trl datasets accelerate bitsandbytes huggingface_hub sentencepiece protobuf
python - <<'PY'
import torch, transformers, peft, trl
print("torch", torch.__version__, "cuda", torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available() else "")
print("transformers", transformers.__version__, "peft", peft.__version__, "trl", trl.__version__)
PY
# official base weights, pinned revisions
python - <<'PY'
from huggingface_hub import snapshot_download
for repo, rev in [("google/gemma-4-E2B-it", "3e22461f65"), ("Qwen/Qwen3.5-4B", "851bf6e806")]:
    p = snapshot_download(repo, revision=None, local_dir=f"base/{repo.split('/')[1]}")
    print(repo, "->", p)
PY
du -sh base/*
