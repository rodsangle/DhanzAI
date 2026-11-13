"""Install and test the newer open models on the ROG: Wan 2.2 TI2V-5B (video) and Z-Image-Turbo (photos).

Stage after the ROCm PyTorch check (docs/ROG_AMD_VIDEO.md). It uses a separate environment,
~/.local/share/dhanz-rog/venv-models2026, so the working Wan 2.1 worker and its environment are
not touched. It downloads the two public models (safe-tensor weights, configs and tokenizers only,
revision pinned on first download), then renders one test clip and one test photo on the GPU and
records time and peak GPU memory. It does not pair with AWS, change the worker, or open a port.

    python3 setup_next_models.py                  # plan only
    python3 setup_next_models.py --apply          # install, download, test both
    python3 setup_next_models.py --apply --only photo
    python3 setup_next_models.py --test-only      # re-test with what is installed
"""
import argparse
import fnmatch
import hashlib
import json
import math
import os
import re
import runpy
import shutil
import subprocess
import sys
import time
from fractions import Fraction
from pathlib import Path

STATE = Path.home() / '.local/share/dhanz-rog'
VENV = STATE / 'venv-models2026'
OUT = STATE / 'next-models'
TORCH = runpy.run_path(str(Path(__file__).with_name('setup_torch_wsl.py')))
PACKAGES = [
    'diffusers==0.43.0', 'transformers==5.22.2', 'accelerate==1.15.0', 'huggingface-hub==2.4.0',
    'safetensors==0.8.0', 'tokenizers==0.23.3', 'sentencepiece==0.2.1', 'imageio==2.37.0',
    'imageio-ffmpeg==0.6.0', 'ftfy==6.3.1', 'numpy==2.2.6', 'Pillow==11.3.0', 'protobuf==5.29.5',
]
ALLOWED_MODEL_FILES = ['*.json', '*.safetensors', '*.model', '*.txt', '*.tiktoken']
VIDEO = {
    'model': 'Wan-AI/Wan2.2-TI2V-5B-Diffusers', 'width': 1280, 'height': 704, 'frames': 121, 'fps': 24,
    'steps': 40, 'guidance': 5.0, 'seed': 42,
    'prompt': 'A cinematic ancient forest at night under a bright silver full moon. One continuous slow low camera '
              'glide between tall tree trunks. Thin mist drifts over fallen leaves and moss. Coherent lighting.',
    'negative_prompt': 'text, subtitles, watermark, logo, oversaturated colors, flickering, blurry, low quality',
}
PHOTO = {
    'model': 'Tongyi-MAI/Z-Image-Turbo', 'width': 1024, 'height': 1024, 'steps': 9, 'guidance': 0.0, 'seed': 42,
    'prompt': 'A golden retriever puppy sitting in a sunlit meadow of wildflowers, shallow depth of field, '
              'natural light, detailed fur, photograph.',
}
SPECS = {'video': VIDEO, 'photo': PHOTO}


def run(argv, **kwargs):
    return subprocess.run(argv, check=True, **kwargs)  # noqa: S603 - fixed package/media commands, no shell


def pin_name(model):
    return 'revision-' + re.sub(r'[^A-Za-z0-9]+', '-', model).strip('-').lower() + '.json'


def selected_files(info):
    files = [item for item in info.siblings if any(fnmatch.fnmatch(item.rfilename, p) for p in ALLOWED_MODEL_FILES)]
    if not any(item.rfilename.endswith('.safetensors') for item in files):
        raise ValueError('The model metadata contains no safe tensor weights.')
    if any(not isinstance(item.size, int) or item.size < 0 for item in files):
        raise ValueError('The model download size could not be checked.')
    return files


def model_snapshot(model):
    """Download (or reuse) the pinned revision; returns the local folder."""
    from huggingface_hub import HfApi, snapshot_download
    pin_path = OUT / pin_name(model)
    revision = 'main'
    if pin_path.is_file():
        pin = json.loads(pin_path.read_text())
        if pin.get('model') != model or not re.fullmatch(r'[0-9a-f]{40}', str(pin.get('revision', ''))):
            raise ValueError('The saved model revision is invalid. Share this message before changing it.')
        revision = pin['revision']
    info = HfApi().model_info(model, revision=revision, files_metadata=True)
    if not re.fullmatch(r'[0-9a-f]{40}', info.sha):
        raise ValueError('The model server returned an unrecognized revision.')
    size = sum(item.size for item in selected_files(info))
    if shutil.disk_usage(STATE).free < size + 8 * 1024**3:
        raise ValueError(f'Not enough Linux disk space: {model} needs {size / 1024**3:.1f} GiB plus 8 GiB spare.')
    print(f'{model}: {size / 1024**3:.1f} GiB of model files (reused if already downloaded).', flush=True)
    pin_path.write_text(json.dumps({'model': model, 'revision': info.sha}))
    folder = snapshot_download(model, revision=info.sha, allow_patterns=ALLOWED_MODEL_FILES, max_workers=4)
    return folder, info.sha


def validate_video(path, spec):
    result = run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-count_frames', '-show_entries',
                  'stream=codec_name,width,height,nb_read_frames,avg_frame_rate:format=duration', '-of', 'json',
                  str(path)], capture_output=True, text=True, timeout=60)
    data = json.loads(result.stdout)
    stream = data['streams'][0]
    duration = float(data['format']['duration'])
    expected = spec['frames'] / spec['fps']
    if not math.isfinite(duration) or abs(duration - expected) > 0.2:
        raise ValueError('The rendered MP4 is not the expected length.')
    if (stream['width'], stream['height']) != (spec['width'], spec['height']):
        raise ValueError('The rendered MP4 dimensions are unexpected.')
    if int(stream['nb_read_frames']) != spec['frames'] or abs(float(Fraction(stream['avg_frame_rate'])) - spec['fps']) > 0.01:
        raise ValueError('The MP4 frame count or frame rate is incomplete.')
    return {'seconds': round(duration, 2), 'width': stream['width'], 'height': stream['height'],
            'frames': int(stream['nb_read_frames']), 'codec': stream['codec_name']}


def test_video(destination):
    import torch
    from diffusers import AutoencoderKLWan, WanPipeline
    from diffusers.utils import export_to_video
    folder, revision = model_snapshot(VIDEO['model'])
    print('Loading Wan 2.2 TI2V-5B (VAE float32, transformer and text encoder bfloat16).', flush=True)
    vae = AutoencoderKLWan.from_pretrained(folder, subfolder='vae', torch_dtype=torch.float32)
    pipe = WanPipeline.from_pretrained(folder, vae=vae, torch_dtype=torch.bfloat16).to('cuda')
    started = time.monotonic()

    def progress(pipeline, step, timestep, kwargs):
        done = step + 1
        eta = (time.monotonic() - started) / done * (VIDEO['steps'] - done)
        print(f'  video step {done}/{VIDEO["steps"]}, about {eta / 60:.0f} min left', flush=True)
        return kwargs

    frames = pipe(prompt=VIDEO['prompt'], negative_prompt=VIDEO['negative_prompt'], width=VIDEO['width'],
                  height=VIDEO['height'], num_frames=VIDEO['frames'], num_inference_steps=VIDEO['steps'],
                  guidance_scale=VIDEO['guidance'], generator=torch.Generator('cuda').manual_seed(VIDEO['seed']),
                  callback_on_step_end=progress).frames[0]
    export_to_video(frames, str(destination), fps=VIDEO['fps'])
    return revision, validate_video(destination, VIDEO)


def test_photo(destination):
    import torch
    from diffusers import ZImagePipeline
    from PIL import Image
    folder, revision = model_snapshot(PHOTO['model'])
    print('Loading Z-Image-Turbo (bfloat16).', flush=True)
    pipe = ZImagePipeline.from_pretrained(folder, torch_dtype=torch.bfloat16).to('cuda')
    image = pipe(prompt=PHOTO['prompt'], width=PHOTO['width'], height=PHOTO['height'],
                 num_inference_steps=PHOTO['steps'], guidance_scale=PHOTO['guidance'],
                 generator=torch.Generator('cuda').manual_seed(PHOTO['seed'])).images[0]
    image.save(destination)
    with Image.open(destination) as check:
        if check.size != (PHOTO['width'], PHOTO['height']):
            raise ValueError('The test photo has unexpected dimensions.')
    return revision, {'width': PHOTO['width'], 'height': PHOTO['height']}


def internal_test(kind):
    """Runs inside the new environment: one render, then a receipt with time and peak GPU memory."""
    import torch
    if not torch.cuda.is_available() or not getattr(torch.version, 'hip', None):
        raise ValueError('The ROCm GPU is not visible to PyTorch in the new environment.')
    destination = OUT / ('test_video.mp4' if kind == 'video' else 'test_photo.png')
    temporary = destination.with_name('partial_' + destination.name)
    temporary.unlink(missing_ok=True)
    torch.cuda.reset_peak_memory_stats()
    started = time.monotonic()
    revision, details = (test_video if kind == 'video' else test_photo)(temporary)
    seconds = time.monotonic() - started
    temporary.replace(destination)
    receipt = {
        'kind': kind, 'spec': SPECS[kind], 'model_revision': revision, 'output': details,
        'render_minutes': round(seconds / 60, 1), 'peak_gpu_gib': round(torch.cuda.max_memory_allocated() / 1024**3, 1),
        'sha256': hashlib.sha256(destination.read_bytes()).hexdigest(), 'torch': torch.__version__,
    }
    destination.with_suffix('.json').write_text(json.dumps(receipt, indent=2))
    print(f'{kind.upper()} TEST: PASS in {receipt["render_minutes"]} min, peak GPU memory {receipt["peak_gpu_gib"]} GiB')
    print('Saved: ' + str(destination))
    print('Windows Explorer: ' + '\\\\wsl.localhost\\Ubuntu-24.04' + str(destination).replace('/', '\\'))


def install():
    if not (VENV / 'bin/python').is_file():
        run([sys.executable, '-m', 'venv', str(VENV)])
    python = str(VENV / 'bin/python')
    pip = [python, '-m', 'pip', 'install', '--disable-pip-version-check', '--no-input']
    print('Installing the verified ROCm PyTorch ' + TORCH['TORCH_VERSION'] + ' into the new environment.', flush=True)
    run([*pip, '--index-url', TORCH['INDEX'], TORCH['TORCH_WHEEL']])
    constraints = OUT / 'torch-constraints.txt'
    constraints.write_text('torch==' + TORCH['TORCH_VERSION'] + '\n')
    print('Installing pinned model libraries (diffusers 0.43.0).', flush=True)
    run([*pip, '-c', str(constraints), *PACKAGES])
    run([python, '-m', 'pip', 'check'])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--apply', action='store_true', help='install, download and test')
    parser.add_argument('--test-only', action='store_true', help='test with the environment already installed')
    parser.add_argument('--only', choices=sorted(SPECS), help='test only video or only photo')
    args = parser.parse_args(argv)
    kinds = [args.only] if args.only else ['photo', 'video']
    if not args.apply and not args.test_only:
        print('Plan: separate environment ' + str(VENV) + ' with diffusers 0.43.0 and ROCm PyTorch.')
        print('Photo test: Z-Image-Turbo, one 1024x1024 image.')
        print('Video test: Wan 2.2 TI2V-5B, one 5-second 1280x704 clip at 24 fps.')
        print('Download sizes are shown from the model pages before anything is downloaded.')
        print('The current Wan 2.1 worker is not changed. Run with --apply to start. Nothing was installed.')
        return 0
    if os.geteuid() == 0 or os.environ.get('HSA_ENABLE_DXG_DETECTION') != '1':
        raise ValueError('Run as your Ubuntu-24.04 user after sourcing ~/.local/share/dhanz-rog/amd-env.sh.')
    if not (STATE / 'gpu_check.py').is_file():
        raise ValueError('Complete the ROCm PyTorch GPU check (setup_torch_wsl.py --apply) first.')
    if 'video' in kinds and not shutil.which('ffprobe'):
        raise ValueError('FFmpeg/ffprobe is missing. Complete the runtime setup first.')
    OUT.mkdir(mode=0o700, parents=True, exist_ok=True)
    import fcntl
    with (STATE / 'gpu.lock').open('a') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('Another render is using the GPU (is the DHANZ worker running?). Stop it first.') from None
        if args.apply:
            install()
        python = VENV / 'bin/python'
        if not python.is_file():
            raise ValueError('The new environment is missing. Run with --apply.')
        # Own marker folder, so a failure here never clears the working worker's GPU check.
        run([str(python), str(STATE / 'gpu_check.py'), '--state-dir', str(OUT)], timeout=300)
        environment = dict(os.environ, HF_HOME=str(STATE / 'huggingface'), HF_HUB_DISABLE_TELEMETRY='1',
                           HF_HUB_DOWNLOAD_TIMEOUT='120', HF_HUB_ETAG_TIMEOUT='30')
        for kind in kinds:
            run([str(python), str(Path(__file__).resolve()), '--internal-test', kind], env=environment,
                pass_fds=(handle.fileno(),))
    return 0


if __name__ == '__main__':
    os.umask(0o077)
    try:
        if len(sys.argv) == 3 and sys.argv[1] == '--internal-test' and sys.argv[2] in SPECS:
            internal_test(sys.argv[2])
        else:
            sys.exit(main())
    except KeyboardInterrupt:
        raise SystemExit('Stopped. Downloaded models and finished tests were kept.') from None
    except subprocess.CalledProcessError:
        raise SystemExit('A step failed. Share the last lines above; no success was recorded.') from None
    except Exception as exc:
        message = re.sub(r'(?:hf_|sk-)[A-Za-z0-9_-]{10,}', '[REDACTED]', str(exc))
        raise SystemExit('NEXT MODELS SETUP FAILED (' + type(exc).__name__ + '): ' + message[:1600]) from None
