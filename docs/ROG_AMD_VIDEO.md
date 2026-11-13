# Radeon 8060S video worker: staged setup

The current target is the user's Ryzen AI Max+ 395 / Radeon 8060S (gfx1151), Windows 11,
and a separate Ubuntu 24.04 WSL2 distribution. AWS continues hosting Dhanz. It cannot
run Wan on its 2-vCPU/4-GB Lightsail plan; a working GPU worker must be connected first.

`apps/rog_video_worker/setup_amd_wsl.sh --apply` installs only the ROCm 7.2.4 HIP runtime,
rocminfo, and AMD ROCDXG 1.2.1 bridge, plus Ubuntu prerequisites. It verifies the bridge's
SHA256 and uses AMD's signed, versioned Noble APT repository. A dedicated APT preference
gives AMD's repository priority 600; the runtime and rocminfo versions are selected
explicitly from the runtime's dependency metadata, avoiding Ubuntu's higher-versioned
but incompatible rocminfo build. It refuses unrelated
existing ROCm repository configuration and simulates the package plan before applying.
Kernel/DKMS package additions cause it to stop. Windows continues providing the GPU
kernel driver through WSL; this helper installs Linux user-space packages.

Use `--verify` to resume GPU testing from already installed packages without APT changes.
The helper discovers the executable from `dpkg-query -L rocminfo`, supporting versioned
ROCm paths and retaining both runtime and WSL-bridge library directories.

The helper tests for gfx1151 using rocminfo with `HSA_ENABLE_DXG_DETECTION=1` and the
Microsoft DXCore library available in WSL. It writes a private, explicit environment
activation file at `~/.local/share/dhanz-rog/amd-env.sh`. It does not change shell startup
files, Windows drivers, WSL memory limits, or AWS configuration. It downloads no model
and starts no video generation. Run as the regular Ubuntu user with sudo access.
Installation failure may leave prerequisite packages or the dedicated AMD repository
installed; package installation is not transactional. Share final output to diagnose.

A passing rocminfo check is not proof that PyTorch or Wan works. Next stages are an
isolated ROCm-compatible PyTorch environment, a real tensor/attention test, then one
short Wan preview. AWS pairing and the original 13-scene request follow only after
that preview is verified. No GPU is attached to the managed Codex execution environment;
local tests validate script syntax, non-WSL refusal, and the official bridge checksum.
The actual GPU test must run on the ROG.

Sources consulted:

- [AMD ROCDXG 1.2.1 guide](https://github.com/ROCm/librocdxg/blob/v1.2.1/README.md)
  recommends ROCm 7.2.4 for production, includes Ryzen AI Max+ 395, and documents the
  legacy ROCm `HSA_ENABLE_DXG_DETECTION` requirement.
- [AMD Ubuntu installation guide](https://github.com/ROCm/rocm-install-on-linux/blob/develop/docs/install/install-methods/package-manager/package-manager-ubuntu.rst)
  documents the signing key and versioned APT repository. Its release configuration
  was 7.2.4 when preparing this helper.
- [AMD release configuration](https://github.com/ROCm/rocm-install-on-linux/blob/develop/docs/conf.py)
- [Verified bridge asset](https://github.com/ROCm/librocdxg/releases/download/v1.2.1/rocdxg-roct_1.2.1_amd64.deb)
  SHA256 `7889eef45a1132ed2dde88d8ea1356bf791ec9c05802a18940bc81b970e850e0`.

## PyTorch stage

After a passing gfx1151 rocminfo test, source `~/.local/share/dhanz-rog/amd-env.sh`
and run `apps/rog_video_worker/setup_torch_wsl.py --apply` with Ubuntu 24.04's
Python 3.12. It creates `~/.local/share/dhanz-rog/venv-rocm72`, installs the official
PyTorch `2.11.0+rocm7.2` CPython 3.12 wheel with a pinned SHA256, and uses the official
ROCm 7.2 package index for dependencies. The wheel URL/hash were checked against
[the official index](https://download.pytorch.org/whl/rocm7.2/torch/).
It does not install a CPU-only/NVIDIA build or change system Python.

The GPU test requires HIP 7.2 and gfx1151, and performs actual GPU matrix multiplication,
bfloat16 portable math attention, and float32 VAE-style 3D convolution. A real kernel
failure stops setup and clears any stale success marker. Successful results are stored
privately in `pytorch-check.json`. `--verify` repeats the checks using the existing venv.
No model is downloaded, no video rendered, and no AWS/connection setting is changed.
The runtime API namespace remains `torch.cuda` on AMD, as required by PyTorch's HIP
implementation; `torch.version.hip` distinguishes the AMD build.

Local unit tests validate backend guards, marker handling and the wheel pin without
pretending to execute GPU kernels. The real kernel test must complete on the ROG.

## One-scene Wan preview

After the real PyTorch kernel check passes, `setup_wan_preview.py --apply` installs
version-pinned Diffusers/Transformers dependencies into the same isolated environment,
constraining torch to the verified ROCm build. It downloads the public
`Wan-AI/Wan2.1-T2V-1.3B-Diffusers` model and records the resolved Hugging Face revision
before retrieving only JSON, text/tokenizer models and safe-tensor weight files.
Remote Python code and pickle weight files are not downloaded; remote-code loading
is disabled. Missing download size and free disk space are checked before retrieving
weights, including Windows C: when PowerShell interop is available. This assumes the
default WSL installation on the Windows system drive. Existing model cache is reused.

The helper renders one continuous Forest Awakens shot: 512x288, 81 model frames,
24 denoising steps, seed 42, portable math attention, bfloat16 transformer/text encoder,
and tiled float32 VAE decoding. Export uses the first 80 frames at 16 FPS for exactly
five seconds. This is a low-resolution silent visual preview, not the complete film.
It verifies the H.264 file with ffprobe before reporting completion. The final MP4
and receipt are saved under `~/.local/share/dhanz-rog/outputs/`. It prints the Windows
Explorer UNC folder path. Existing verified output is reused; a changed file is never
overwritten. `--new-preview` creates another file; `--render-only` skips dependency
installation. A shared GPU lock prevents overlapping setup/render processes, including
if the parent process exits while a render child remains alive.

Tests validate data-file filtering, output preservation, Windows folder paths, and
real ffprobe checks using temporary synthetic codec-test clips. These synthetic files
are never delivered as model output. The managed environment has no matching AMD GPU,
so actual model inference must be verified on the ROG. No AWS settings, server pairing,
moderation settings or failed Dhanz jobs are changed by this preview helper. Connecting
the working ROG model to the existing server is a subsequent step after visual review.

Source: [version-pinned Wan pipeline documentation](https://github.com/huggingface/diffusers/blob/v0.35.2/docs/source/en/api/pipelines/wan.md).

## Newer models: Wan 2.2 TI2V-5B (video) and Z-Image-Turbo (photos)

For the ROG with 64 GB assigned to the GPU. `setup_next_models.py` installs diffusers 0.43.0
(with the same verified ROCm PyTorch 2.11 wheel) into a separate environment,
`~/.local/share/dhanz-rog/venv-models2026`, so the working Wan 2.1 worker is untouched. It
downloads the two public Apache-2.0 models (safe-tensor weights, configs and tokenizers only,
revision pinned on first download), then renders one 1024x1024 test photo and one 5-second
1280x704 test clip, and records render time and peak GPU memory next to each output in
`~/.local/share/dhanz-rog/next-models/`. Stop the DHANZ worker first; the GPU lock is shared.

```bash
source ~/.local/share/dhanz-rog/amd-env.sh
cd ~/DhanzAI/apps/rog_video_worker
python3 setup_next_models.py                 # plan only
python3 setup_next_models.py --apply         # install, download, test photo then video
python3 setup_next_models.py --test-only --only video   # repeat one test
```

Connecting these models to dhanzai.com (worker and server queue changes) comes after both
tests pass on the ROG, using the measured times. Larger options that fit only with offloading:
Wan 2.2 A14B (video) and Qwen-Image (photos).
