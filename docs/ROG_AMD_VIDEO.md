# Radeon 8060S video worker: staged setup

The current target is the user's Ryzen AI Max+ 395 / Radeon 8060S (gfx1151), Windows 11,
and a separate Ubuntu 24.04 WSL2 distribution. AWS continues hosting Dhanz. It cannot
run Wan on its 2-vCPU/4-GB Lightsail plan; a working GPU worker must be connected first.

`apps/rog_video_worker/setup_amd_wsl.sh --apply` installs only the ROCm 7.2.4 HIP runtime,
rocminfo, and AMD ROCDXG 1.2.1 bridge, plus Ubuntu prerequisites. It verifies the bridge's
SHA256 and uses AMD's signed, versioned Noble APT repository. It refuses unrelated
existing ROCm repository configuration and simulates the package plan before applying.
Kernel/DKMS package additions cause it to stop. Windows continues providing the GPU
kernel driver through WSL; this helper installs Linux user-space packages.

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
