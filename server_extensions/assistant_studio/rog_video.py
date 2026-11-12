"""Integrate the ROG pull queue without replacing storage, images or moderation."""
import asyncio
import hashlib
import json
import math
import shutil
import subprocess
import uuid

from fastapi import APIRouter, HTTPException, Request, Response

from app.api.deps import CurrentUser, DbDep, SettingsDep
from app.models import User

from .rog_queue import MAX_BYTES, MODEL, Queue, QueueError, identifier

router = APIRouter(prefix='/rog-worker', tags=['rog-worker'])
_DHANZ_ROG_VIDEO_VERSION = 1


def queue(settings):
    from pathlib import Path
    return Queue(Path(settings.storage_dir) / 'rog-worker')


@router.post('/pair')
async def pair(user: CurrentUser, settings: SettingsDep, response: Response):
    response.headers['Cache-Control'] = 'private, no-store'
    try:
        token = queue(settings).pair(user.id)
        return {'worker_token': token, 'expires_in_days': 90, 'model': MODEL}
    except QueueError as exc:
        raise HTTPException(409, str(exc)) from None


@router.get('/status')
async def status(user: CurrentUser, settings: SettingsDep):
    return queue(settings).status(user.id)


@router.delete('/pair')
async def revoke(user: CurrentUser, settings: SettingsDep):
    queue(settings).revoke(user.id)
    return {'status': 'revoked'}


async def worker(request, settings, db):
    try:
        authorization = request.headers.get('authorization', '')
        if not authorization.startswith('Bearer '):
            raise QueueError('Missing worker token.')
        q = queue(settings)
        owner = q.authenticate(authorization[7:])
        user = await db.get(User, uuid.UUID(owner))
        if user is None or not user.is_active:
            raise QueueError('Worker account is unavailable.')
        return q, owner
    except QueueError:
        raise HTTPException(401, 'Worker token is invalid or expired.') from None


@router.post('/heartbeat')
async def heartbeat(request: Request, settings: SettingsDep, db: DbDep):
    q, owner = await worker(request, settings, db)
    q.heartbeat(owner)
    task = request.query_params.get('task')
    try:
        return {'status': 'ok', 'task_status': q.worker_status(task, owner) if task else None}
    except ValueError:
        raise HTTPException(404, 'Video task not found for this account.') from None


@router.post('/claim')
async def claim(request: Request, settings: SettingsDep, db: DbDep):
    q, owner = await worker(request, settings, db)
    q.heartbeat(owner)
    q.prune()
    return {'job': q.claim(owner)}


@router.post('/disconnect')
async def disconnect(request: Request, settings: SettingsDep, db: DbDep):
    q, owner = await worker(request, settings, db)
    q.revoke(owner)
    return {'status': 'revoked'}


def validate_video(path):
    result = subprocess.run(  # fixed argv and private filename, no shell or URLs
        ['ffprobe', '-v', 'error', '-protocol_whitelist', 'file,pipe', '-f', 'mov',
         '-enable_drefs', '0', '-use_absolute_path', '0', '-select_streams', 'v:0', '-count_frames',
         '-show_entries', 'stream=codec_name,width,height,nb_read_frames:format=duration',
         '-of', 'json', str(path)], check=True, capture_output=True, text=True, timeout=60)
    data = json.loads(result.stdout)
    stream = data['streams'][0]
    if (stream['codec_name'], stream['width'], stream['height'], int(stream['nb_read_frames'])) != ('h264', 512, 288, 80):
        raise ValueError('Worker output does not match the tested video profile.')
    duration = float(data['format']['duration'])
    if not math.isfinite(duration) or abs(duration - 5) > .15:
        raise ValueError('Worker returned an incomplete video.')


@router.post('/jobs/{task}/result')
async def result(task: uuid.UUID, request: Request, settings: SettingsDep, db: DbDep):
    q, owner = await worker(request, settings, db)
    claim_key = request.headers.get('x-dhanz-claim', '')
    temporary = q.root / (uuid.uuid4().hex + '.upload')
    try:
        row = q.owned_claim(task, owner, claim_key)
        if row['status'] not in ('RUNNING', 'SUCCEEDED'):
            raise QueueError('This video no longer accepts results.')
        if shutil.disk_usage(q.root).free < MAX_BYTES + 1024**3:
            raise HTTPException(507, 'Insufficient private video storage.')
        size, digest = 0, hashlib.sha256()
        with temporary.open('xb') as handle:
            temporary.chmod(0o600)
            async for chunk in request.stream():
                size += len(chunk)
                if size > MAX_BYTES:
                    raise HTTPException(413, 'Video exceeds 32 MiB.')
                handle.write(chunk)
                digest.update(chunk)
        await asyncio.to_thread(validate_video, temporary)
        # A retry only acknowledges the same bytes; it never renders again.
        if row['status'] == 'SUCCEEDED':
            if row['sha256'] != digest.hexdigest():
                raise QueueError('A different result already exists for this video.')
            return {'status': 'complete'}
        q.upload(task, owner, claim_key, digest.hexdigest(), temporary)
        return {'status': 'complete'}
    except QueueError as exc:
        raise HTTPException(409, str(exc)) from None
    except (ValueError, KeyError, IndexError, subprocess.SubprocessError):
        raise HTTPException(422, 'The video failed MP4 validation.') from None
    finally:
        temporary.unlink(missing_ok=True)


@router.post('/jobs/{task}/failed')
async def failed(task: uuid.UUID, request: Request, settings: SettingsDep, db: DbDep):
    q, owner = await worker(request, settings, db)
    try:
        q.finish(task, owner, request.headers.get('x-dhanz-claim', ''))
    except QueueError as exc:
        raise HTTPException(409, str(exc)) from None
    return {'status': 'failed'}


class RogVideoProvider:
    def __init__(self, settings, previous):
        self.queue = queue(settings)
        self.previous = previous
        self.client = previous.client  # preserve normal runtime client shutdown

    async def aclose(self):
        await self.previous.aclose()

    def capabilities(self):
        return {'kind': 'video', 'provider': 'local-diffusers', 'model': MODEL, 'quality_rank': 2,
                'label': 'ROG Wan 1.3B · 5-second silent preview', 'ratios': ['16:9'], 'qualities': [],
                'formats': ['mp4'], 'reference': False, 'operations': ['generate'], 'durations': [5],
                'resolutions': ['512x288'], 'fps': 16, 'audio': False,
                'description': 'Paired ROG must be running. Low-resolution text-to-video preview; no video provider API fee. Existing app credit policy applies.'}

    def all_capabilities(self):
        return [self.capabilities()]

    async def submit(self, job, reference=None):
        if reference is not None:
            raise ValueError('This tested ROG preview profile accepts text only, without a reference image or video.')
        options = job.options
        if job.model != MODEL or options.get('duration') != 5 or options.get('ratio') != '16:9' or options.get('resolution') != '512x288':
            raise ValueError('Choose ROG Wan 1.3B, five seconds, 16:9 and 512x288.')
        return self.queue.submit(job.id, job.user_id, job.prompt)

    async def poll(self, task_id):
        return self.queue.poll(task_id)

    async def cancel(self, task_id):
        self.queue.cancel(task_id)

    async def download(self, url, limit):
        if not isinstance(url, str) or not url.startswith('rog-video:'):
            raise ValueError('Unexpected ROG video output location.')
        task = identifier(url[len('rog-video:'):])
        if self.queue.poll(task)['status'] != 'SUCCEEDED':
            raise ValueError('ROG video is not complete.')
        path = self.queue.content_path(task)
        if path.stat().st_size > min(limit, MAX_BYTES):
            raise ValueError('ROG video exceeds the configured media size limit.')
        data = await asyncio.to_thread(path.read_bytes)
        if len(data) < 12 or data[4:8] != b'ftyp':
            raise ValueError('The ROG result is not an MP4.')
        return data


def install(app):
    from app.generation_jobs import CreativeRuntime
    app.include_router(router, prefix=app.state.settings.api_prefix)
    original = CreativeRuntime.__init__
    if getattr(original, '_dhanz_rog_video', False):
        return

    def initialize(self, settings, *args, **kwargs):
        original(self, settings, *args, **kwargs)
        if self.video is not None and settings.creative_local_enabled:
            self.video = RogVideoProvider(settings, self.video)

    initialize._dhanz_rog_video = True
    CreativeRuntime.__init__ = initialize
