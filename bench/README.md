# Cin-MinAI model bakeoff bench

> Copied into the repo by the lead from the Mint box (`~/cin-minai/bench`), written by Codex. Update
> 2026-09-25: the Vulkan build deps were installed with Ian's approval and `build-vulkan` is built;
> results are in `docs/benchmarks.md`.

Prepared on the Mint test box on 2026-09-25. This is prep infrastructure only: it does not score
models or choose winners.

## Pinned llama.cpp

- Release: `v0.5.0`
- Commit: `7fe450e19305b828c199d602c23a8337aaa1f03b`
- Source: `~/cin-minai/llama.cpp`

The tag is the newest release at prep time and contains all candidate architectures. Architecture
minimums (first supporting build/commit) are recorded per entry in `candidates.toml`. The build
commands below deliberately create separate binaries so a run cannot silently select the wrong
backend.

### CPU build (built)

```bash
cmake -S ~/cin-minai/llama.cpp -B ~/cin-minai/llama.cpp/build-cpu \
  -DCMAKE_BUILD_TYPE=Release \
  -DGGML_NATIVE=OFF \
  -DGGML_CUDA=OFF \
  -DGGML_VULKAN=OFF \
  -DLLAMA_CURL=OFF \
  -DCMAKE_C_COMPILER=/usr/bin/gcc-12 \
  -DCMAKE_CXX_COMPILER=/usr/bin/g++-12
cmake --build ~/cin-minai/llama.cpp/build-cpu --config Release -j4 --target llama-server
```

### CUDA build (built)

The host has NVIDIA CUDA Toolkit 12.0.140 and GCC/G++ 12.4.0. Pascal `sm_61` is the only CUDA
architecture emitted.

```bash
cmake -S ~/cin-minai/llama.cpp -B ~/cin-minai/llama.cpp/build-cuda \
  -DCMAKE_BUILD_TYPE=Release \
  -DGGML_NATIVE=OFF \
  -DGGML_CUDA=ON \
  -DGGML_VULKAN=OFF \
  -DCMAKE_CUDA_ARCHITECTURES=61 \
  -DCMAKE_C_COMPILER=/usr/bin/gcc-12 \
  -DCMAKE_CXX_COMPILER=/usr/bin/g++-12 \
  -DCMAKE_CUDA_HOST_COMPILER=/usr/bin/g++-12 \
  -DLLAMA_CURL=OFF
cmake --build ~/cin-minai/llama.cpp/build-cuda --config Release -j4 --target llama-server
```

### Vulkan build (blocked; packages not installed)

The runtime and NVIDIA Vulkan driver work, but development headers and the shader compiler are
absent. Per the no-sudo rule, nothing was installed. On Mint/Ubuntu, Ian can approve installation of:

```text
libvulkan-dev glslc spirv-headers
```

Then build with:

```bash
cmake -S ~/cin-minai/llama.cpp -B ~/cin-minai/llama.cpp/build-vulkan \
  -DCMAKE_BUILD_TYPE=Release \
  -DGGML_NATIVE=OFF \
  -DGGML_CUDA=OFF \
  -DGGML_VULKAN=ON \
  -DLLAMA_CURL=OFF \
  -DCMAKE_C_COMPILER=/usr/bin/gcc-12 \
  -DCMAKE_CXX_COMPILER=/usr/bin/g++-12
cmake --build ~/cin-minai/llama.cpp/build-vulkan --config Release -j4 --target llama-server
```

## Candidate inventory and downloads

`candidates.toml` pins repository revisions, exact filenames, byte sizes, SHA-256 hashes, licenses,
and minimum llama.cpp architecture builds. Guide quants were not specified in the handoff, so the
inventory explicitly records the reproducible prep choice: Q4_K_M where available and Google's
official QAT Q4_0 for Gemma 4.

Qwen has no vendor-published GGUF repositories for Qwen3.5 2B/4B/9B. Those entries use unmodified
Unsloth conversions and say so. Google, IBM, and the older Qwen candidates use vendor GGUFs.

Run the resumable, checksum-verifying download list with:

```bash
~/cin-minai/bench/download-models.sh
```

The planned download is 45,531,463,264 bytes (42.40 GiB), below the strict 60,000,000,000-byte cap.
It includes all six guide candidates and all smaller big-track candidates. Qwen3-14B is referenced
read-only at its existing testbed path. Qwen3.6-35B-A3B Q4_K_M is inventoried but deliberately not
downloaded: adding its 20,419,565,568 bytes would exceed the cap.

## Harness

`run.py` uses Python 3.12's standard library only. It:

- refuses port 8080 and defaults to 18080;
- selects one of the separate CUDA, Vulkan, or CPU binaries;
- starts `llama-server` with explicit context, GPU layers, q8_0 K/V cache, FlashAttention on, and
  automatic fit disabled; it fixes one server slot and reasoning off for comparable single-user
  tool-call measurements;
- creates a tokenizer-measured ~4,000-token prompt and records prompt/generation throughput and
  streaming time to first token;
- polls process RSS, process VRAM, whole-card used VRAM, and minimum free VRAM;
- loads the exact schemas and prompt function from `spikes/libreoffice/assist.py` without importing
  its machine-specific config, then runs 50 constrained calls and validates both JSON parsing and
  the supported schema subset;
- writes one JSON object per run to `~/cin-minai/bench-results/<machine>/<date>.jsonl`, including
  failures, and always terminates its server process group;
- in `--budget-gb 6` mode, requires an 8K context and a peak model-process allocation no greater
  than 4.7 GiB (4,812 MiB).

Example guide run:

```bash
~/cin-minai/bench/run.py \
  --build cuda \
  --model ~/cin-minai/models/Qwen3.5-2B-Q4_K_M.gguf \
  --quant Q4_K_M \
  --context 8192 \
  --ngl all \
  --budget-gb 6
```

CPU uses the same invocation with `--build cpu`; the harness forces `--device none --gpu-layers 0`.
Use a distinct `--port` for concurrent work, but never 8080.

### GPU etiquette

Before CUDA or Vulkan startup, the harness checks `nvidia-smi`. It tolerates only the unloaded
`qwen14b.service` process (at most 512 MiB). It aborts if that service has its model loaded or if any
other compute process is using the card. It never stops, restarts, or changes that service.
