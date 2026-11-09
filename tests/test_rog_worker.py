import base64
import concurrent.futures
import contextlib
import gzip
import importlib.util
import json
import runpy
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
import urllib.error
import uuid
from pathlib import Path
from typing import Annotated
from unittest.mock import patch

from fastapi import Depends, FastAPI, HTTPException, Request
import httpx

ROOT = Path(__file__).resolve().parents[1]
QUEUE_SOURCE = ROOT / 'server_extensions/assistant_studio/rog_queue.py'
qmod = runpy.run_path(str(QUEUE_SOURCE))
Queue, QueueError = qmod['Queue'], qmod['QueueError']
worker = runpy.run_path(str(ROOT / 'apps/rog_video_worker/worker.py'))


class QueueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.now = 1000000
        self.q = Queue(self.temp.name, clock=lambda: self.now)
        self.a, self.b = uuid.uuid4(), uuid.uuid4()
        self.ta, self.tb = self.q.pair(self.a), self.q.pair(self.b)

    def submit(self, owner):
        self.q.heartbeat(owner)
        return self.q.submit(uuid.uuid4(), owner, 'A peaceful moonlit forest')

    def test_offline_worker_cannot_receive_a_new_job(self):
        with self.assertRaisesRegex(QueueError, 'offline'):
            self.q.submit(uuid.uuid4(), self.a, 'Forest')
        self.q.heartbeat(self.a)
        self.now += 46
        self.assertFalse(self.q.status(self.a)['online'])
        with self.assertRaisesRegex(QueueError, 'offline'):
            self.q.submit(uuid.uuid4(), self.a, 'Forest')

    def test_accounts_are_isolated_and_tokens_revoked(self):
        a, b = self.submit(self.a), self.submit(self.b)
        ca, cb = self.q.claim(self.a), self.q.claim(self.b)
        self.assertEqual(ca['id'], a)
        self.assertEqual(cb['id'], b)
        with self.assertRaises(QueueError):
            self.q.finish(a, self.b, ca['claim'])
        with self.assertRaises(QueueError):
            self.q.finish(a, self.a, cb['claim'])
        with self.assertRaises(QueueError):
            self.q.worker_status(a, self.b)
        self.q.revoke(self.a)
        with self.assertRaises(QueueError):
            self.q.authenticate(self.ta)
        self.assertEqual(self.q.poll(a)['status'], 'CANCELLED')
        self.assertEqual(self.q.authenticate(self.tb), str(self.b))

    def test_claim_is_atomic_and_never_automatically_replayed(self):
        task = self.submit(self.a)
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            claims = list(pool.map(lambda _: self.q.claim(self.a), range(4)))
        self.assertEqual(sum(c is not None for c in claims), 1)
        restarted = Queue(self.temp.name, clock=lambda: self.now)
        self.assertIsNone(restarted.claim(self.a))
        self.now += qmod['LIFETIME'] + 1
        self.assertEqual(restarted.poll(task)['status'], 'FAILED')
        self.assertIsNone(restarted.claim(self.a))

    def test_pending_id_is_idempotent_and_different_prompt_rejected(self):
        task = self.submit(self.a)
        self.assertEqual(self.q.submit(task, self.a, 'A peaceful moonlit forest'), task)
        with self.assertRaises(QueueError):
            self.q.submit(task, self.a, 'Changed prompt')
        with self.assertRaises(QueueError):
            self.q.pair(self.a)
        with self.assertRaises(QueueError):
            self.submit(self.a)

    def test_cancelled_and_competing_results_cannot_replace_accepted_bytes(self):
        task = self.submit(self.a)
        claim = self.q.claim(self.a)['claim']
        first = Path(self.temp.name) / 'first.upload'
        first.write_bytes(b'accepted')
        self.q.upload(task, self.a, claim, 'digest1', first)
        second = Path(self.temp.name) / 'second.upload'
        second.write_bytes(b'rejected')
        with self.assertRaises(QueueError):
            self.q.upload(task, self.a, claim, 'digest2', second)
        self.assertEqual(self.q.content_path(task).read_bytes(), b'accepted')
        self.q.upload(task, self.a, claim, 'digest1', second)
        self.assertEqual(self.q.content_path(task).read_bytes(), b'accepted')
        other = self.submit(self.b)
        claim2 = self.q.claim(self.b)['claim']
        self.q.cancel(other)
        with self.assertRaises(QueueError):
            self.q.upload(other, self.b, claim2, 'digest3', second)
        self.assertFalse(self.q.content_path(other).exists())

    def test_credentials_are_hashed_and_private(self):
        data = (Path(self.temp.name) / 'queue.sqlite3').read_bytes()
        self.assertNotIn(self.ta.encode(), data)
        self.assertEqual((Path(self.temp.name) / 'queue.sqlite3').stat().st_mode & 0o777, 0o600)
        self.assertEqual(Path(self.temp.name).stat().st_mode & 0o777, 0o700)


class ApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.a, self.b = uuid.uuid4(), uuid.uuid4()
        self.active = True
        settings = types.SimpleNamespace(storage_dir=self.temp.name, api_prefix='/api/v1', creative_local_enabled=True)

        async def current(request: Request):
            if request.headers.get('x-test-owner') not in (str(self.a), str(self.b)):
                raise HTTPException(401)
            return types.SimpleNamespace(id=uuid.UUID(request.headers['x-test-owner']))

        async def get_settings():
            return settings

        async def get_user(_, key):
            return types.SimpleNamespace(is_active=self.active) if key in (self.a, self.b) else None

        async def database():
            return types.SimpleNamespace(get=get_user)

        deps = types.ModuleType('app.api.deps')
        deps.CurrentUser = Annotated[object, Depends(current)]
        deps.SettingsDep = Annotated[object, Depends(get_settings)]
        deps.DbDep = Annotated[object, Depends(database)]
        models = types.ModuleType('app.models')
        models.User = object
        package = types.ModuleType('rog_test_studio')
        package.__path__ = [str(QUEUE_SOURCE.parent)]
        modules = {'app.api.deps': deps, 'app.models': models, 'rog_test_studio': package}
        self.patcher = patch.dict(sys.modules, modules)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        for name in ('rog_queue', 'rog_video'):
            fullname = 'rog_test_studio.' + name
            spec = importlib.util.spec_from_file_location(fullname, QUEUE_SOURCE.with_name(name + '.py'))
            mod = importlib.util.module_from_spec(spec)
            sys.modules[fullname] = mod
            spec.loader.exec_module(mod)
            self.addCleanup(sys.modules.pop, fullname, None)
        self.api = sys.modules['rog_test_studio.rog_video']
        self.settings = settings
        self.q = self.api.queue(settings)
        app = FastAPI()
        app.include_router(self.api.router, prefix='/api/v1')
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="https://testserver")
        self.addAsyncCleanup(self.client.aclose)

    async def pair(self, owner):
        r = await self.client.post('/api/v1/rog-worker/pair', headers={'x-test-owner': str(owner)})
        self.assertEqual(r.status_code, 200)
        self.assertIn('no-store', r.headers['cache-control'])
        return {'Authorization': 'Bearer ' + r.json()['worker_token']}

    async def test_http_pairing_worker_scope_and_revocation(self):
        path = '/api/v1/rog-worker/'
        self.assertEqual((await self.client.post(path + 'pair')).status_code, 401)
        a, b = await self.pair(self.a), await self.pair(self.b)
        self.assertEqual((await self.client.post(path + 'heartbeat', headers=a)).status_code, 200)
        task = self.q.submit(uuid.uuid4(), self.a, 'Forest')
        self.assertIsNone((await self.client.post(path + 'claim', headers=b)).json()['job'])
        claim = (await self.client.post(path + 'claim', headers=a)).json()['job']
        denied = await self.client.post(path + f'jobs/{task}/failed', headers={**b, 'X-Dhanz-Claim': claim['claim']})
        self.assertEqual(denied.status_code, 409)
        self.assertEqual(self.q.poll(task)['status'], 'RUNNING')
        self.active = False
        self.assertEqual((await self.client.post(path + 'heartbeat', headers=a)).status_code, 401)
        self.active = True
        await self.client.delete(path + 'pair', headers={'x-test-owner': str(self.a)})
        self.assertEqual((await self.client.post(path + 'heartbeat', headers=a)).status_code, 401)

    async def test_runtime_hook_preserves_images_moderation_storage_and_shutdown(self):
        closed = []

        async def close():
            closed.append(True)

        previous = types.SimpleNamespace(client=object(), aclose=close)
        image, moderator, storage = object(), object(), object()

        class Runtime:
            def __init__(self, settings):
                self.video = previous
                self.image, self.moderator, self.storage = image, moderator, storage

        module = types.ModuleType('app.generation_jobs')
        module.CreativeRuntime = Runtime
        app = FastAPI()
        app.state.settings = self.settings
        with patch.dict(sys.modules, {'app.generation_jobs': module}):
            self.api.install(app)
            runtime = Runtime(self.settings)
        self.assertIs(runtime.image, image)
        self.assertIs(runtime.moderator, moderator)
        self.assertIs(runtime.storage, storage)
        self.assertEqual(runtime.video.capabilities()['model'], qmod['MODEL'])
        await runtime.video.aclose()
        self.assertEqual(closed, [True])

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'Real MP4 validation')
    async def test_real_video_delivered_once_and_provider_limits(self):
        headers = await self.pair(self.a)
        await self.client.post('/api/v1/rog-worker/heartbeat', headers=headers)
        provider = self.api.RogVideoProvider(self.settings, types.SimpleNamespace(client=None))
        job = types.SimpleNamespace(id=uuid.uuid4(), user_id=self.a, prompt='Forest', model=qmod['MODEL'],
                                    options={'duration': 5, 'ratio': '16:9', 'resolution': '512x288'})
        task = await provider.submit(job)
        claim = (await self.client.post('/api/v1/rog-worker/claim', headers=headers)).json()['job']
        path = '/api/v1/rog-worker/jobs/' + task + '/result'
        headers['X-Dhanz-Claim'] = claim['claim']
        bad = await self.client.post(path, content=b'not a video', headers=headers)
        self.assertEqual(bad.status_code, 422)
        self.assertEqual(self.q.poll(task)['status'], 'RUNNING')
        video = Path(self.temp.name) / 'codec-test.mp4'
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'color=c=blue:s=512x288:r=16:d=5',
                        '-c:v', 'libx264', '-threads', '1', '-pix_fmt', 'yuv420p', str(video)], check=True)
        data = video.read_bytes()
        self.assertEqual((await self.client.post(path, content=data, headers=headers)).status_code, 200)
        self.assertEqual((await self.client.post(path, content=data, headers=headers)).status_code, 200)
        poll = await provider.poll(task)
        self.assertEqual(poll['status'], 'SUCCEEDED')
        self.assertEqual(await provider.download(poll['output'][0], 10000000), data)
        with self.assertRaises(ValueError):
            await provider.download('https://example.com/video.mp4', 1000000)
        job.options['duration'] = 25
        with self.assertRaises(ValueError):
            await provider.submit(job)
        self.assertEqual(provider.capabilities()['durations'], [5])
        self.assertFalse(provider.capabilities()['audio'])


class PackagingTests(unittest.TestCase):
    def test_frozen_installers_match_reviewed_modules(self):
        api = runpy.run_path(str(ROOT / 'deploy/updaters/install_rog_backend.py'))
        frozen = api['payload']()
        for name in ('rog_queue.py', 'rog_video.py'):
            self.assertEqual(frozen[name], QUEUE_SOURCE.with_name(name).read_text())
        source = 'def install(app):\n    _install_reference_video(app)\n'
        patched = api['patch_bootstrap'](source)
        self.assertEqual(api['patch_bootstrap'](patched), patched)
        with self.assertRaises(ValueError):
            api['patch_bootstrap']('def install(app): pass\n')
        installer = runpy.run_path(str(ROOT / 'apps/rog_video_worker/setup_worker.py'))
        bundle = json.loads(gzip.decompress(base64.b64decode(installer['PAYLOAD'])))
        self.assertEqual(bundle['worker.py'], (ROOT / 'apps/rog_video_worker/worker.py').read_text())
        self.assertEqual(bundle['preview.py'], (ROOT / 'apps/rog_video_worker/setup_wan_preview.py').read_text())

    def test_worker_refuses_insecure_server_urls_and_credential_redirects(self):
        self.assertEqual(worker['origin']('https://dhanzai.com/'), 'https://dhanzai.com')
        for value in ('http://dhanzai.com', 'https://user:secret@dhanzai.com', 'https://dhanzai.com/path', 'https://dhanzai.com/?key=secret'):
            with self.assertRaises(ValueError):
                worker['origin'](value)
        self.assertIsNone(worker['NoRedirect']().redirect_request(None, None, 302, '', {}, 'https://other.example'))

    def test_uncertain_delivery_retries_bytes_without_rendering_again(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            job = {'id': str(uuid.uuid4()), 'claim': 'a' * 48}
            video = root / (job['id'] + '.mp4')
            video.write_bytes(b'verified-test-bytes')
            (root / 'current.json').write_text(json.dumps(job))
            calls = []

            def upload(*args, **kwargs):
                calls.append(kwargs['raw'])
                if len(calls) == 1:
                    raise urllib.error.URLError('test disconnect')
                return {'status': 'complete'}

            fake = types.SimpleNamespace(validate_video=lambda path: None)
            with patch.dict(worker['deliver'].__globals__, {'ROOT': root, 'call': upload, 'preview_module': lambda: fake}):
                with self.assertRaises(urllib.error.URLError):
                    worker['deliver']({'server': 'https://example.com', 'token': 'test'}, job)
                self.assertTrue((root / 'current.json').exists())
                with contextlib.redirect_stdout(__import__('io').StringIO()):
                    worker['deliver']({'server': 'https://example.com', 'token': 'test'}, job)
                self.assertFalse((root / 'current.json').exists())
                self.assertEqual(calls, [b'verified-test-bytes', b'verified-test-bytes'])
                self.assertTrue(video.exists())


if __name__ == '__main__':
    unittest.main()
