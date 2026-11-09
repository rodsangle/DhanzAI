"""Outbound HTTPS worker for the tested AMD Wan preview. No listening ports."""
import argparse
import contextlib
import fcntl
import getpass
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

STATE = Path.home() / '.local/share/dhanz-rog'
ROOT = STATE / 'worker'
MODEL = 'wan-rog-1.3b-preview'


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # credentials never follow a redirect


def origin(value):
    p = urllib.parse.urlsplit(value)
    if p.scheme != 'https' or not p.hostname or p.username or p.password or p.query or p.fragment or p.path not in ('', '/'):
        raise ValueError('Use an HTTPS Dhanz server address without a path, credentials or query.')
    return value.rstrip('/')


def call(server, path, *, token=None, data=None, raw=None, claim=None, method='POST'):
    headers = {'User-Agent': 'Dhanz-ROG-Wan/1', 'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    if claim:
        headers['X-Dhanz-Claim'] = claim
    body = json.dumps(data or {}).encode()
    if raw is not None:
        body = raw
        headers['Content-Type'] = 'application/octet-stream'
    request = urllib.request.Request(origin(server) + '/api/v1/' + path.lstrip('/'),
                                     data=body if method != 'GET' else None, headers=headers, method=method)
    with urllib.request.build_opener(NoRedirect()).open(request, timeout=120) as response:
        payload = response.read(65537)
    if len(payload) > 65536:
        raise ValueError('Unexpectedly large server response.')
    return json.loads(payload) if payload else {}


def save(path, data):
    temporary = path.with_suffix('.tmp')
    with temporary.open('w') as handle:
        temporary.chmod(0o600)
        json.dump(data, handle)
    temporary.replace(path)


def preview_module():
    spec = importlib.util.spec_from_file_location('rog_preview', ROOT / 'preview.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def cached_snapshot(state):
    from huggingface_hub import snapshot_download
    pin = json.loads((state / 'wan-model-revision.json').read_text())
    if pin.get('model') != 'Wan-AI/Wan2.1-T2V-1.3B-Diffusers' or not re.fullmatch('[0-9a-f]{40}', pin.get('revision', '')):
        raise ValueError('The verified Wan model pin is missing or invalid.')
    path = snapshot_download(pin['model'], revision=pin['revision'],
                             cache_dir=str(state / 'huggingface/hub'), local_files_only=True)
    if not (Path(path) / 'model_index.json').is_file() or not list(Path(path).rglob('*.safetensors')):
        raise ValueError('Complete the successful Wan preview setup first.')
    return path, pin['revision']


def preflight():
    if os.environ.get('HSA_ENABLE_DXG_DETECTION') != '1' or os.geteuid() == 0:
        raise ValueError('Run as your WSL user after sourcing amd-env.sh.')
    subprocess.run([sys.executable, str(STATE / 'gpu_check.py'), '--state-dir', str(STATE)],
                   check=True, timeout=300)
    cached_snapshot(STATE)  # no model download; reuse the exact approved snapshot
    module = preview_module()
    module.validate_video(STATE / 'outputs/Forest_Awakens_preview.mp4')


def pair(server):
    server = origin(server)
    if (ROOT / 'current.json').exists():
        raise ValueError('A prior video result is pending. Start the worker to finish reporting it before pairing again.')
    preflight()
    print('Pairing only with:', server, flush=True)
    print('Enter your Dhanz sign-in details locally. Do not paste them in ChatGPT.', flush=True)
    email = input('Dhanz sign-in email: ').strip()
    password = getpass.getpass('Dhanz password (hidden): ')
    login = call(server, 'auth/login', data={'email': email, 'password': password})
    password = None
    access = login.get('access_token')
    if not access:
        raise ValueError('Sign-in requires an additional step; no worker was paired.')
    try:
        result = call(server, 'rog-worker/pair', token=access)
        token = result.get('worker_token', '')
        if not isinstance(token, str) or not 40 <= len(token) <= 128:
            raise ValueError('The server did not return a valid worker credential.')
        save(ROOT / 'connection.json', {'server': server, 'token': token})
    finally:
        if login.get('refresh_token'):
            with contextlib.suppress(Exception):
                call(server, 'auth/logout', data={'refresh_token': login['refresh_token']})
        login.clear()
    print('ROG paired privately for your account. No video was submitted.', flush=True)


def render_job(task):
    task = str(uuid.UUID(task))
    data = json.loads((ROOT / 'current.json').read_text())
    if data.get('id') != task or data.get('model') != MODEL:
        raise ValueError('The local video request changed.')
    prompt = data.get('prompt')
    if not isinstance(prompt, str) or not 1 <= len(prompt.strip()) <= 4000:
        raise ValueError('The local video prompt is invalid.')
    destination = ROOT / (task + '.mp4')
    if destination.exists():
        raise ValueError('A completed result already exists; generation was not replayed.')
    module = preview_module()
    module.model_snapshot = cached_snapshot
    module.SPEC = {**module.SPEC, 'prompt': prompt}
    module.FINGERPRINT = hashlib.sha256(json.dumps(module.SPEC, sort_keys=True).encode()).hexdigest()
    module.render(STATE, destination)


def deliver(connection, job):
    task = str(uuid.UUID(job['id']))
    path = ROOT / (task + '.mp4')
    if not path.is_file():
        call(connection['server'], f'rog-worker/jobs/{task}/failed', token=connection['token'], claim=job['claim'])
        (ROOT / 'current.json').unlink(missing_ok=True)
        return
    preview_module().validate_video(path)
    if path.stat().st_size > 32 * 1024 * 1024:
        raise ValueError('The video exceeds the server upload limit.')
    call(connection['server'], f'rog-worker/jobs/{task}/result', token=connection['token'],
         claim=job['claim'], raw=path.read_bytes())
    print('Video delivered to Dhanz:', task, flush=True)
    # Preserve the MP4 and its receipt locally, but discard its prompt and claim.
    (ROOT / 'current.json').unlink(missing_ok=True)


def work():
    connection = json.loads((ROOT / 'connection.json').read_text())
    origin(connection['server'])
    with (STATE / 'gpu.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('Another renderer is using this ROG GPU. Stop it before starting the worker.') from None
        preflight()
        print('ROG worker running. Five-second silent Wan previews; no incoming port.', flush=True)
        print('Keep this terminal and the ROG on. Ctrl+C stops the worker.', flush=True)
        uncertain = False
        while True:
            try:
                call(connection['server'], 'rog-worker/heartbeat', token=connection['token'])
                if (ROOT / 'current.json').is_file():
                    deliver(connection, json.loads((ROOT / 'current.json').read_text()))
                response = call(connection['server'], 'rog-worker/claim', token=connection['token'])
                job = response.get('job')
                if job:
                    job['id'] = str(uuid.UUID(job['id']))
                    if job.get('model') != MODEL or not re.fullmatch('[0-9a-f]{48}', str(job.get('claim', ''))):
                        raise ValueError('The server returned an unsupported rendering task.')
                    save(ROOT / 'current.json', job)  # durable before the single render attempt
                    log_path = ROOT / (job['id'] + '.log')
                    print('Rendering one five-second video. Private progress log:', log_path, flush=True)
                    with log_path.open('w') as log:
                        log_path.chmod(0o600)
                        child = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '--render', job['id']],
                                                 stdout=log, stderr=subprocess.STDOUT, pass_fds=(lock.fileno(),))
                        start = time.monotonic()
                        try:
                            while child.poll() is None:
                                if time.monotonic() - start > 100 * 60:
                                    raise ValueError('The render exceeded 100 minutes; it will not be replayed.')
                                try:
                                    child.wait(timeout=10)
                                except subprocess.TimeoutExpired:
                                    with contextlib.suppress(urllib.error.URLError, TimeoutError):
                                        check = call(connection['server'], 'rog-worker/heartbeat?task=' + job['id'], token=connection['token'])
                                        if check.get('task_status') in ('CANCELLED', 'FAILED'):
                                            child.terminate()
                                            break
                        finally:
                            if child.poll() is None:
                                child.terminate()
                                try:
                                    child.wait(timeout=15)
                                except subprocess.TimeoutExpired:
                                    child.kill()
                                    child.wait()
                    if child.returncode:
                        print('Rendering failed; private local log:', log_path, flush=True)
                    deliver(connection, job)
                uncertain = False
            except urllib.error.HTTPError as exc:
                if exc.code in (401, 403):
                    raise ValueError('Worker authorization expired or was revoked. Pair again locally.') from None
                if exc.code == 409 and (ROOT / 'current.json').is_file():
                    (ROOT / 'current.json').unlink()
                    print('Server closed the video request. No generation was replayed.', flush=True)
                elif not uncertain:
                    print('Server request failed (HTTP ' + str(exc.code) + '); no generation is replayed.', flush=True)
                uncertain = True
            except (urllib.error.URLError, TimeoutError, ConnectionError):
                if not uncertain:
                    print('Connection interrupted. Polling/delivery may retry; video generation will not replay.', flush=True)
                uncertain = True
            time.sleep(5)


def main():
    os.umask(0o077)
    os.environ.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', HF_HUB_DISABLE_TELEMETRY='1')
    ROOT.mkdir(parents=True, mode=0o700, exist_ok=True)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pair', action='store_true')
    parser.add_argument('--server', default='https://dhanzai.com')
    parser.add_argument('--render')
    parser.add_argument('--disconnect', action='store_true')
    args = parser.parse_args()
    if args.render:
        render_job(args.render)
    elif args.disconnect:
        connection = json.loads((ROOT / 'connection.json').read_text())
        call(connection['server'], 'rog-worker/disconnect', token=connection['token'])
        (ROOT / 'connection.json').unlink()
        print('ROG worker credential revoked. Model files and completed videos were preserved.')
    elif args.pair:
        pair(args.server)
    else:
        work()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        raise SystemExit('ROG worker stopped. No job will automatically render again.') from None
    except urllib.error.HTTPError as exc:
        raise SystemExit('Dhanz request failed (HTTP ' + str(exc.code) + '). No credentials were printed.') from None
    except Exception as exc:
        # Exception strings/HTTP bodies can contain credentials or URLs.
        raise SystemExit('ROG worker stopped (' + type(exc).__name__ + '). Share this message; local files were preserved.') from None
