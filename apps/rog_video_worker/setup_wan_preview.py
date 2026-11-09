"""Install a pinned Wan preview stack and render one local, silent five-second clip.

Run on the ROG in Ubuntu-24.04, after sourcing the AMD environment. No AWS settings,
API credentials, paid video providers, or queued Dhanz jobs are changed.
"""
import argparse
import contextlib
import fnmatch
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
from fractions import Fraction
from pathlib import Path

MODEL = 'Wan-AI/Wan2.1-T2V-1.3B-Diffusers'
TORCH = '2.11.0+rocm7.2'
PACKAGES = [
    'diffusers==0.35.2', 'transformers==4.57.1', 'accelerate==1.10.1',
    'huggingface-hub==0.36.0', 'sentencepiece==0.2.1', 'imageio==2.37.0',
    'imageio-ffmpeg==0.6.0', 'ftfy==6.3.1', 'numpy==2.2.6', 'Pillow==11.3.0', 'protobuf==5.29.5',
]
SPEC = {
    'model': MODEL, 'width': 512, 'height': 288, 'model_frames': 81,
    'output_frames': 80, 'fps': 16, 'steps': 24, 'guidance': 5.0, 'seed': 42,
    'prompt': 'A cinematic ancient forest at night under a bright silver full moon. One continuous slow low camera glide between tall tree trunks. Thin mist drifts gently over fallen leaves and moss. Cool moonlight filters through the canopy. Clear natural detail, coherent lighting, subtle flowing motion, mysterious peaceful atmosphere.',
    'negative_prompt': 'text, subtitles, watermark, logo, oversaturated colors, distorted trees, flickering, blurry, low quality',
}
FINGERPRINT = hashlib.sha256(json.dumps(SPEC, sort_keys=True).encode()).hexdigest()
ALLOWED_MODEL_FILES = ['*.json', '*.safetensors', '*.model', '*.txt']


def run(argv, **kwargs):
    return subprocess.run(argv, check=True, **kwargs)  # noqa: S603 - fixed package/media commands, no shell


def validate_video(path):
    result = run([
        'ffprobe', '-v', 'error', '-select_streams', 'v:0', '-count_frames',
        '-show_entries', 'stream=codec_name,width,height,nb_read_frames,avg_frame_rate:format=duration',
        '-of', 'json', str(path),
    ], capture_output=True, text=True, timeout=60)
    data = json.loads(result.stdout)
    stream = data['streams'][0]
    duration = float(data['format']['duration'])
    rate = float(Fraction(stream['avg_frame_rate']))
    if not math.isfinite(duration) or abs(duration - 5) > 0.15:
        raise ValueError('The rendered MP4 is not a complete five-second clip.')
    if (stream['width'], stream['height']) != (SPEC['width'], SPEC['height']):
        raise ValueError('The rendered MP4 dimensions are unexpected.')
    if int(stream['nb_read_frames']) != SPEC['output_frames'] or abs(rate - SPEC['fps']) > 0.01:
        raise ValueError('The MP4 frame count or frame rate is incomplete.')
    if stream['codec_name'] != 'h264':
        raise ValueError('The output codec is not H.264.')
    return {'duration_seconds': duration, 'width': stream['width'], 'height': stream['height'],
            'frames': int(stream['nb_read_frames']), 'fps': rate, 'codec': stream['codec_name']}


def reusable(path):
    if not path.exists():
        return False
    receipt = path.with_suffix('.json')
    if not receipt.is_file():
        raise ValueError('The existing preview has no receipt. Use --new-preview to create a separate file.')
    data = json.loads(receipt.read_text())
    if data.get('fingerprint') != FINGERPRINT or data.get('sha256') != hashlib.sha256(path.read_bytes()).hexdigest():
        raise ValueError('The existing preview was changed. Use --new-preview to create a separate file.')
    validate_video(path)
    return True


def selected_files(info):
    files = [item for item in info.siblings if any(fnmatch.fnmatch(item.rfilename, pat) for pat in ALLOWED_MODEL_FILES)]
    if not any(item.rfilename.endswith('.safetensors') for item in files):
        raise ValueError('The model metadata contains no safe tensor weights.')
    if any(not isinstance(item.size, int) or item.size < 0 for item in files):
        raise ValueError('The model download size could not be checked. Nothing was rendered.')
    return files


def model_snapshot(state):
    from huggingface_hub import HfApi, hf_hub_download, snapshot_download
    api = HfApi()
    pin_path = state / 'wan-model-revision.json'
    revision = 'main'
    if pin_path.is_file():
        pin = json.loads(pin_path.read_text())
        if pin.get('model') != MODEL or not re.fullmatch(r'[0-9a-f]{40}', str(pin.get('revision', ''))):
            raise ValueError('The saved model revision is invalid. Share this message before changing it.')
        revision = pin['revision']
    info = api.model_info(MODEL, revision=revision, files_metadata=True)
    if not re.fullmatch(r'[0-9a-f]{40}', info.sha):
        raise ValueError('The model server returned an unrecognized revision.')
    files = selected_files(info)
    size = sum(item.size for item in files)
    missing = 0
    for item in files:
        try:
            cached = hf_hub_download(MODEL, filename=item.rfilename, revision=info.sha,
                                     cache_dir=str(state / 'huggingface/hub'), local_files_only=True)
            if Path(cached).stat().st_size != item.size:
                missing += item.size
        except Exception:
            missing += item.size
    reserve = missing + 8 * 1024**3
    if shutil.disk_usage(state).free < reserve:
        raise ValueError('Insufficient Linux disk space for the model plus an 8 GiB working reserve.')
    powershell = shutil.which('powershell.exe')
    if powershell:
        result = run([powershell, '-NoProfile', '-NonInteractive', '-Command', '[long](Get-PSDrive -Name C).Free'],
                     capture_output=True, text=True, timeout=30)
        host_free = int(result.stdout.strip())
        print(f'Windows C: free space: {host_free / 1024**3:.1f} GiB', flush=True)
        if host_free < reserve:
            raise ValueError('Windows C: does not have enough physical space for the model and reserve.')
    print(f'Model files: {size / 1024**3:.1f} GiB total, up to {missing / 1024**3:.1f} GiB remaining; cache reused.', flush=True)
    print('Downloading public Wan model files. The generation prompt stays on this PC.', flush=True)
    temporary = state / 'wan-model-revision.tmp'
    temporary.write_text(json.dumps({'model': MODEL, 'revision': info.sha}))
    temporary.replace(pin_path)
    snapshot = snapshot_download(MODEL, revision=info.sha, allow_patterns=ALLOWED_MODEL_FILES,
                                 cache_dir=str(state / 'huggingface/hub'), max_workers=4)
    return snapshot, info.sha


def render(state, destination):
    import torch
    from diffusers import AutoencoderKLWan, WanPipeline
    from diffusers.utils import export_to_video
    from torch.nn.attention import SDPBackend, sdpa_kernel
    if str(torch.__version__) != TORCH or not torch.version.hip or not torch.cuda.is_available():
        raise ValueError('The verified AMD PyTorch environment is not active.')
    snapshot, revision = model_snapshot(state)
    print('Loading Wan 1.3B. VAE uses float32; the text encoder/transformer use bfloat16.', flush=True)
    vae = AutoencoderKLWan.from_pretrained(snapshot, subfolder='vae', torch_dtype=torch.float32,
                                         use_safetensors=True, local_files_only=True)
    pipe = WanPipeline.from_pretrained(snapshot, vae=vae, torch_dtype=torch.bfloat16,
                                      use_safetensors=True, local_files_only=True, trust_remote_code=False)
    pipe.vae.enable_tiling()
    pipe.to('cuda')
    pipe.set_progress_bar_config(disable=False)
    started = time.monotonic()
    def progress(pipeline, step, timestep, callback_kwargs):
        print(f'Render step {step + 1}/{SPEC["steps"]} (elapsed {(time.monotonic() - started)/60:.1f} min)', flush=True)
        return callback_kwargs
    print('Rendering Forest Awakens: 512x288, five seconds, silent hardware-preview quality.', flush=True)
    temporary = destination.with_name(destination.stem + '.partial.mp4')
    try:
        with torch.inference_mode(), sdpa_kernel(SDPBackend.MATH):
            frames = pipe(prompt=SPEC['prompt'], negative_prompt=SPEC['negative_prompt'],
                          width=SPEC['width'], height=SPEC['height'], num_frames=SPEC['model_frames'],
                          num_inference_steps=SPEC['steps'], guidance_scale=SPEC['guidance'],
                          max_sequence_length=256, generator=torch.Generator(device='cuda').manual_seed(SPEC['seed']),
                          callback_on_step_end=progress).frames[0]
        if len(frames) < SPEC['output_frames']:
            raise ValueError('The model returned fewer frames than required.')
        export_to_video(frames[:SPEC['output_frames']], str(temporary), fps=SPEC['fps'])
        verified = validate_video(temporary)
        receipt = {'fingerprint': FINGERPRINT, 'spec': SPEC, 'model_revision': revision,
                   'sha256': hashlib.sha256(temporary.read_bytes()).hexdigest(), **verified}
        temporary.replace(destination)
        destination.with_suffix('.json').write_text(json.dumps(receipt, indent=2))
        return receipt
    finally:
        temporary.unlink(missing_ok=True)
        del pipe
        torch.cuda.empty_cache()


def print_output(path):
    print('WAN PREVIEW: COMPLETE (verified 5 seconds / 80 frames / H.264)', flush=True)
    print('Preview file:', path)
    print('Windows Explorer folder: ' + chr(92)*2 + 'wsl.localhost' + chr(92) + 'Ubuntu-24.04' + str(path.parent).replace('/', chr(92)))
    print('This is a low-resolution silent preview of Forest Awakens. No other scenes were submitted.')
    print('AWS settings are unchanged; no paid video API was used.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='Install dependencies and render the one preview.')
    parser.add_argument('--render-only', action='store_true', help='Render using dependencies already installed.')
    parser.add_argument('--new-preview', action='store_true', help='Create a separate preview file instead of reusing the first.')
    args = parser.parse_args()
    state = Path.home() / '.local/share/dhanz-rog'
    python = state / 'venv-rocm72/bin/python'
    check = state / 'gpu_check.py'
    if not args.apply and not args.render_only:
        print('Plan: public Wan 1.3B model, one local five-second 512x288 Forest Awakens preview.')
        print('Use --apply after the ROCm PyTorch GPU check passes. No video was generated.')
        return
    if os.geteuid() == 0 or os.environ.get('HSA_ENABLE_DXG_DETECTION') != '1':
        raise ValueError('Run as your Ubuntu-24.04 user after sourcing the AMD environment file.')
    if not python.is_file() or not check.is_file():
        raise ValueError('Complete the isolated PyTorch GPU setup first.')
    if not shutil.which('ffprobe'):
        raise ValueError('FFmpeg/ffprobe is missing. Complete the runtime setup first.')
    import fcntl
    with (state / 'gpu.lock').open('a') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('Another preview setup/render is running. Wait for it to finish.') from None
        outputs = state / 'outputs'
        outputs.mkdir(mode=0o700, exist_ok=True)
        destination = outputs / ('Forest_Awakens_preview' + ('_' + uuid.uuid4().hex[:8] if args.new_preview else '') + '.mp4')
        if reusable(destination):
            print('Reusing the existing verified preview; no repeat generation.')
            print_output(destination)
            return
        run([str(python), str(check), '--state-dir', str(state)], timeout=300)
        constraints = state / 'torch-constraints.txt'
        constraints.write_text('torch==' + TORCH + '\n')
        if args.apply:
            print('Installing model libraries into the isolated ROCm environment.', flush=True)
            run([str(python), '-m', 'pip', 'install', '--disable-pip-version-check', '--no-input',
                 '-c', str(constraints), *PACKAGES])
            run([str(python), '-m', 'pip', 'check'])
        environment = dict(os.environ)
        environment.update(HF_HOME=str(state / 'huggingface'), HF_HUB_DISABLE_TELEMETRY='1',
                           HF_HUB_DOWNLOAD_TIMEOUT='120', HF_HUB_ETAG_TIMEOUT='30')
        # Use the same helper inside the venv; keep the lock in this parent process.
        run([str(python), str(Path(__file__).resolve()), '--internal-render', str(destination)], env=environment,
            pass_fds=(handle.fileno(),))


if __name__ == '__main__':
    os.umask(0o077)
    try:
        if len(sys.argv) == 3 and sys.argv[1] == '--internal-render':
            state = Path.home() / '.local/share/dhanz-rog'
            path = Path(sys.argv[2])
            if path.parent != state / 'outputs' or not path.name.startswith('Forest_Awakens_preview') or path.suffix != '.mp4':
                raise ValueError('Invalid preview output path.')
            if path.exists():
                raise ValueError('The preview file already exists; it was preserved.')
            render(state, path)
            print_output(path)
        else:
            main()
    except KeyboardInterrupt:
        raise SystemExit('Preview stopped. Completed previews and downloaded model cache were preserved.') from None
    except subprocess.CalledProcessError:
        raise SystemExit('A dependency or media check failed. Share the final error lines; no success was recorded.') from None
    except Exception as exc:
        message = re.sub(r'(?:hf_|sk-)[A-Za-z0-9_-]{10,}', '[REDACTED]', str(exc))
        raise SystemExit('WAN PREVIEW FAILED (' + type(exc).__name__ + '): ' + message[:1600]) from None
