"""Install and test an isolated official ROCm PyTorch build on the ROG's WSL Ubuntu.

No video model, server connection, API key or generation is configured here.
"""
import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

TORCH_VERSION = "2.11.0+rocm7.2"
TORCH_WHEEL = (
    "https://download-r2.pytorch.org/whl/rocm7.2/"
    "torch-2.11.0%2Brocm7.2-cp312-cp312-manylinux_2_28_x86_64.whl"
    "#sha256=8f02a36213288ab5921e277e13f5954cc62afe7cfa899b79d739d4ef2be6510b"
)
INDEX = "https://download.pytorch.org/whl/rocm7.2"

GPU_PROBE = r'''
import argparse
import json
import os
import sys
import time
from pathlib import Path


def validate_backend(version, hip, available, arch):
    if version != '2.11.0+rocm7.2' or not hip or not str(hip).startswith('7.2'):
        raise RuntimeError('The required ROCm PyTorch build is not active. No CPU/CUDA-only fallback is accepted.')
    if not available:
        raise RuntimeError('PyTorch cannot access the AMD GPU. The rocminfo check alone is not sufficient.')
    if str(arch).split(':')[0] != 'gfx1151':
        raise RuntimeError('The detected GPU architecture is not gfx1151. No video model was downloaded.')


def real_probe():
    import torch
    import torch.nn.functional as F
    from torch.nn.attention import SDPBackend, sdpa_kernel
    available = torch.cuda.is_available()
    props = torch.cuda.get_device_properties(0) if available else None
    arch = getattr(props, 'gcnArchName', '') if props else ''
    validate_backend(str(torch.__version__), torch.version.hip, available, arch)
    with torch.inference_mode():
        identity = torch.eye(128, device='cuda', dtype=torch.float32)
        product = identity @ identity
        torch.cuda.synchronize()
        if not torch.equal(product, identity):
            raise RuntimeError('GPU matrix multiplication returned an unexpected result.')
        q = torch.zeros((1, 2, 32, 64), device='cuda', dtype=torch.bfloat16)
        v = torch.ones_like(q)
        # Use portable attention math, not a CUDA-only extension or unverified fused kernel.
        with sdpa_kernel(SDPBackend.MATH):
            attention = F.scaled_dot_product_attention(q, q, v)
        torch.cuda.synchronize()
        if not torch.equal(attention, v):
            raise RuntimeError('GPU bfloat16 attention returned an unexpected result.')
        image = torch.ones((1, 4, 4, 8, 8), device='cuda', dtype=torch.float32)
        weights = torch.ones((4, 4, 3, 3, 3), device='cuda', dtype=torch.float32)
        output = F.conv3d(image, weights, padding=1)
        torch.cuda.synchronize()
        if not torch.isfinite(output).all().item() or output[0, 0, 2, 4, 4].item() != 108:
            raise RuntimeError('GPU float32 VAE-style 3D convolution returned an unexpected result.')
    return {'torch': str(torch.__version__), 'hip': str(torch.version.hip), 'gpu': props.name,
            'architecture': arch, 'reported_gpu_memory_gib': round(props.total_memory / 1024**3, 1),
            'checks': ['matrix multiplication', 'bfloat16 attention (math)', 'float32 VAE-style 3D convolution']}


def check(state, probe=real_probe):
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    marker = state / 'pytorch-check.json'
    marker.unlink(missing_ok=True)
    result = probe()  # A failure leaves no stale success marker.
    result['checked_at'] = time.time()
    temporary = state / 'pytorch-check.tmp'
    temporary.write_text(json.dumps(result, indent=2))
    temporary.replace(marker)
    marker.chmod(0o600)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--state-dir', type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    try:
        data = check(args.state_dir)
        print('PYTORCH GPU CHECK: PASS (gfx1151 / Radeon 8060S)')
        print('PyTorch:', data['torch'], '| ROCm:', data['hip'])
        print('GPU:', data['gpu'])
        print('Reported GPU memory (GiB):', data['reported_gpu_memory_gib'])
        print('Verified:', ', '.join(data['checks']))
        print('No model downloaded. AWS configuration remains unchanged.')
    except Exception as exc:
        print('PYTORCH GPU CHECK: FAILED (' + type(exc).__name__ + ')', file=sys.stderr)
        print(str(exc)[:1800], file=sys.stderr)
        raise SystemExit(1) from None
'''


def environment():
    fields = {}
    for line in Path('/etc/os-release').read_text().splitlines():
        if '=' in line:
            name, value = line.split('=', 1)
            fields[name] = value.strip('"')
    if fields.get('ID') != 'ubuntu' or fields.get('VERSION_ID') != '24.04':
        raise ValueError('Use Ubuntu-24.04 for this Python 3.12 wheel.')
    if 'microsoft' not in platform.release().lower() or platform.machine() != 'x86_64':
        raise ValueError('Run this on the ROG inside Ubuntu-24.04 WSL2.')
    if sys.version_info[:2] != (3, 12):
        raise ValueError('This setup requires Ubuntu-24.04 Python 3.12.')
    if os.geteuid() == 0:
        raise ValueError('Run as your Ubuntu user, not with sudo.')
    if os.environ.get('HSA_ENABLE_DXG_DETECTION') != '1':
        raise ValueError('Source ~/.local/share/dhanz-rog/amd-env.sh before running this helper.')


def run(argv, **kwargs):
    subprocess.run(argv, check=True, **kwargs)  # noqa: S603 - fixed executables/package arguments


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group()
    action.add_argument('--apply', action='store_true')
    action.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    environment()
    state = Path.home() / '.local/share/dhanz-rog'
    venv = state / 'venv-rocm72'
    python = venv / 'bin/python'
    if not args.apply and not args.verify:
        print('Plan: isolated Python 3.12 environment with official PyTorch ' + TORCH_VERSION)
        print('Rerun with --apply to install and test, or --verify to test an existing environment.')
        return
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    (state / 'pytorch-check.json').unlink(missing_ok=True)
    if args.apply:
        if shutil.disk_usage(state).free < 8 * 1024**3:
            raise ValueError('At least 8 GiB free in the Linux filesystem is required for the PyTorch install.')
        if not python.is_file():
            run([sys.executable, '-m', 'venv', str(venv)])
        else:
            run([str(python), '-c', "import sys; assert sys.version_info[:2]==(3,12), 'Existing environment is not Python 3.12'"])
        print('Installing official AMD-compatible PyTorch. This download may take several minutes.', flush=True)
        run([str(python), '-m', 'pip', 'install', '--disable-pip-version-check', '--no-input', '--index-url', INDEX, TORCH_WHEEL])
        # Future model dependencies must not silently replace this ROCm build.
        (state / 'torch-constraints.txt').write_text('torch==' + TORCH_VERSION + '\n')
    if not python.is_file():
        raise ValueError('The isolated PyTorch environment is missing. Run --apply first.')
    script = state / 'gpu_check.py'
    script.write_text(GPU_PROBE)
    script.chmod(0o600)
    run([str(python), str(script), '--state-dir', str(state)], timeout=300)


if __name__ == '__main__':
    os.umask(0o077)
    try:
        main()
    except subprocess.CalledProcessError:
        raise SystemExit('PyTorch setup/check stopped. Share the final error lines; no video model was downloaded.') from None
    except subprocess.TimeoutExpired:
        raise SystemExit('GPU check timed out. No video model was downloaded.') from None
    except (ValueError, OSError) as exc:
        raise SystemExit(str(exc)) from None
