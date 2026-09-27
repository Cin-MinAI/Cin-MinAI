#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
set -euo pipefail

models_dir="${1:-$HOME/cin-minai/models}"
limit_bytes=60000000000
planned_bytes=45531463264

if (( planned_bytes > limit_bytes )); then
    echo "planned downloads exceed the 60 GB cap" >&2
    exit 1
fi

mkdir -p "$models_dir"

# Guide candidates first, then big-track files from smallest to largest.
entries=(
"unsloth/Qwen3.5-2B-GGUF|f6d5376be1edb4d416d56da11e5397a961aca8ae|Qwen3.5-2B-Q4_K_M.gguf|aaf42c8b7c3cab2bf3d69c355048d4a0ee9973d48f16c731c0520ee914699223"
"unsloth/Qwen3.5-4B-GGUF|e87f176479d0855a907a41277aca2f8ee7a09523|Qwen3.5-4B-Q4_K_M.gguf|00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4"
"google/gemma-4-E2B-it-qat-q4_0-gguf|675cff42a74c774d6cb76f76d8eacb49b48c9b93|gemma-4-E2B_q4_0-it.gguf|fa401b55b07ee70a54c6dae3903c783a6e65064312529ea57175cb5f8dec6634"
"google/gemma-4-E4B-it-qat-q4_0-gguf|4b4a2c1d584be7264f87aac328a1bc739ce81b6c|gemma-4-E4B_q4_0-it.gguf|676c35070db6dbe52f93e9c864ee0fba4eddea94b9c875d9cb10daff453fbaee"
"ibm-granite/granite-4.2-3b-GGUF|c40945d71cd90f249a56985e8155551a9188dc30|granite-4.2-3b-Q4_K_M.gguf|e0406663965846ae22a403456eb826ccce5f450840491f71952f18a7cb78e7d5"
"Qwen/Qwen2.5-1.5B-Instruct-GGUF|91cad51170dc346986eccefdc2dd33a9da36ead9|qwen2.5-1.5b-instruct-q4_k_m.gguf|6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e"
"unsloth/Qwen3.5-4B-GGUF|e87f176479d0855a907a41277aca2f8ee7a09523|Qwen3.5-4B-Q8_0.gguf|10cc391b403021dd11c614679d2fd92f611c3681d29e29651b717316965d61e1"
"Qwen/Qwen2.5-Coder-7B-Instruct-GGUF|13fb94bfda8c8cf22497dc57b78f391a9acb426a|qwen2.5-coder-7b-instruct-q5_k_m.gguf|586844eac4d6d6321689f0192c8aa8e69cd8625974a5cc2d925b1a03366e4d16"
"unsloth/Qwen3.5-9B-GGUF|3885219b6810b007914f3a7950a8d1b469d598a5|Qwen3.5-9B-Q4_K_M.gguf|03b74727a860a56338e042c4420bb3f04b2fec5734175f4cb9fa853daf52b7e8"
"unsloth/Qwen3.5-9B-GGUF|3885219b6810b007914f3a7950a8d1b469d598a5|Qwen3.5-9B-Q5_K_M.gguf|dc2a39aef291f91a9116ad214058da0d86eb648743a124bd8c333787c4b9c91c"
"unsloth/Qwen3.5-9B-GGUF|3885219b6810b007914f3a7950a8d1b469d598a5|Qwen3.5-9B-Q6_K.gguf|91898433cf5ce0a8f45516a4cc3e9343b6e01d052d01f684309098c66a326c59"
)

for entry in "${entries[@]}"; do
    IFS='|' read -r repo revision file expected_sha <<<"$entry"
    final="$models_dir/$file"
    part="$final.part"
    if [[ -f "$final" ]]; then
        actual_sha=$(sha256sum "$final" | awk '{print $1}')
        if [[ "$actual_sha" != "$expected_sha" ]]; then
            echo "checksum mismatch for existing file: $final" >&2
            exit 1
        fi
        echo "verified existing $file"
        continue
    fi
    url="https://huggingface.co/$repo/resolve/$revision/$file?download=true"
    echo "downloading $file"
    curl --fail --location --retry 5 --retry-all-errors --continue-at - \
         --output "$part" --silent --show-error "$url"
    actual_sha=$(sha256sum "$part" | awk '{print $1}')
    if [[ "$actual_sha" != "$expected_sha" ]]; then
        echo "checksum mismatch for downloaded file: $part" >&2
        exit 1
    fi
    mv "$part" "$final"
    echo "verified $file"
done

actual_bytes=$(find "$models_dir" -maxdepth 1 -type f -name '*.gguf' -printf '%s\n' | awk '{s += $1} END {print s + 0}')
echo "downloaded_model_bytes=$actual_bytes"
if (( actual_bytes > limit_bytes )); then
    echo "model directory exceeds the 60 GB cap" >&2
    exit 1
fi
