"""Add ratings, private app/agent file builds and full-page PDF-to-Excel conversion.

Prepare by default; --apply migrates additive tables and recreates only the API.
The payload is embedded by scripts/release/embed_assistant_studio.py.
"""
import argparse
import ast
import base64
import gzip
import json
import os
import re
import shlex
import subprocess
import tempfile
import time
from pathlib import Path

PAYLOAD = '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'


def payload():
    return json.loads(gzip.decompress(base64.b64decode(PAYLOAD)))


def patch_sources(main, models, chat):
    marker = '_DHANZ_ASSISTANT_STUDIO_VERSION = 1'
    if marker in main:
        raise ValueError('Assistant studio is already installed; no files were changed.')
    anchor = '    app.include_router(web_routes.router)'
    if main.count(anchor) != 1 or 'app.assistant_studio' in main:
        raise ValueError('Main application differs from the supported interface. Nothing changed.')
    main = main.replace(anchor, anchor + '\n    from app.assistant_studio.bootstrap import install as _install_assistant_studio\n    _install_assistant_studio(app)\n    ' + marker)
    if 'app.assistant_studio' in models:
        raise ValueError('An existing studio model integration needs review.')
    models += '\nfrom app.assistant_studio.models import ResponseFeedback, BuilderProject, BuilderLease  # noqa: F401,E402\n'
    anchor = '    research = _Research()'
    if chat.count(anchor) != 1 or 'app.assistant_studio' in chat:
        raise ValueError('Chat application differs from the supported interface. Nothing changed.')
    hook = '''    from app.assistant_studio.pdf_turn import requested as _pdf_excel_requested, run as _run_pdf_excel
    if settings.assistant_tools_enabled and turn.attachment_ids and _pdf_excel_requested(turn.question):
        async for event in _run_pdf_excel(maker, settings, turn, files, _finalize, _stop_requested):
            yield event
        return

'''
    chat = chat.replace(anchor, hook + anchor)
    for name, source in [('main.py', main), ('models.py', models), ('chat_service.py', chat)]:
        ast.parse(source, filename=name)
    return main, models, chat


def docker(*args, **kwargs):
    return subprocess.run(['/usr/bin/sudo', '/usr/bin/docker', *args], check=True,
                          capture_output=True, text=True, **kwargs).stdout.strip()


def healthy():
    for _ in range(45):
        state = docker('inspect', 'deploy-api-1', '--format', '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}')
        if state == 'healthy':
            return True
        time.sleep(2)
    return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    info = json.loads(docker('inspect', 'deploy-api-1', '--format',
        '{"image":{{json .Image}},"labels":{{json .Config.Labels}},"mounts":{{json .Mounts}}}'))
    labels = info['labels']
    directory = Path(labels['com.docker.compose.project.working_dir'])
    original_files = labels['com.docker.compose.project.config_files'].split(',')
    project = labels['com.docker.compose.project']
    if not directory.is_dir() or not project or not all(Path(p).is_absolute() and Path(p).is_file() for p in original_files):
        raise ValueError('The active Compose configuration is unavailable. Nothing changed.')
    packet = json.loads(docker('exec', 'deploy-api-1', 'python', '-c', '''
import base64,json,pathlib,app.main,app.models,app.services.chat_service
paths=[pathlib.Path(m.__file__) for m in [app.main,app.models,app.services.chat_service]]
print(json.dumps({'root':str(paths[0].parent.parent),'paths':[str(p) for p in paths],'sources':[base64.b64encode(p.read_bytes()).decode() for p in paths]}))
'''))
    root = Path(packet['root'])
    expected = [root/'app/main.py', root/'app/models/__init__.py', root/'app/services/chat_service.py']
    if packet['paths'] != [str(p) for p in expected] or not root.is_absolute():
        raise ValueError('Unexpected backend module paths. Nothing changed.')
    destinations = [str(p) for p in expected] + [str(root/'app/assistant_studio'),str(root/'alembic/versions')]
    for mount in info['mounts']:
        mounted = mount['Destination'].rstrip('/')
        if any(p == mounted or p.startswith(mounted+'/') for p in destinations):
            raise ValueError('Backend source is mounted over the image; inspect it before updating.')
    patched = patch_sources(*(base64.b64decode(s).decode() for s in packet['sources']))
    current = docker('exec', 'deploy-api-1', 'python', '-c', '''
import asyncio
from sqlalchemy import text
from app.core.config import get_settings
from sqlalchemy.ext.asyncio import create_async_engine
async def main():
    engine=create_async_engine(get_settings().database_url)
    async with engine.connect() as db: print(','.join((await db.execute(text('SELECT version_num FROM alembic_version'))).scalars()))
    await engine.dispose()
asyncio.run(main())
''')
    if current != '0010':
        raise ValueError('Expected database revision 0010; found '+current+'. Nothing changed.')
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', info['image']):
        raise ValueError('Cannot identify the current immutable API image.')
    build = Path(tempfile.mkdtemp(prefix='dhanz-assistant-studio-', dir=Path.home()))
    os.chmod(build, 0o700)
    for destination, source in zip(expected, patched, strict=True):
        relative = destination.relative_to(root)
        path = build/relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source)
    for relative, source in payload().items():
        path = build/relative
        if not path.is_relative_to(build) or '..' in Path(relative).parts:
            raise ValueError('Unsafe embedded source path')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source)
    stamp = str(time.time_ns())
    before_image = 'dhanz-api:before-assistant-studio-'+stamp
    docker('tag',info['image'],before_image)
    image = 'dhanz-api:assistant-studio-'+stamp
    (build/'Dockerfile').write_text('FROM '+before_image+'\nUSER root\nRUN python -m pip install --no-cache-dir "openpyxl==3.1.5"\nCOPY app/ '+str(root/'app')+'/\nCOPY alembic/ '+str(root/'alembic')+'/\n')
    # The original effective user is restored, including non-root deployments.
    user = docker('inspect', 'deploy-api-1', '--format', '{{.Config.User}}')
    if user:
        if not re.fullmatch(r'[a-zA-Z0-9_:-]+',user): raise ValueError('Unexpected container user')
        with (build/'Dockerfile').open('a') as f: f.write('USER '+user+'\n')
    print('Building an additive update from the current custom API image...',flush=True)
    docker('build','--tag',image,str(build),timeout=600)
    smoke = '''
import shutil
import app.assistant_studio.routes as routes
from app.assistant_studio.pdf_excel import workbook,Page,Cell
from app.main import create_app
from app.core.config import Settings
app=create_app(Settings(app_env='test',_env_file=None))
assert any('assistant-studio' in path for path in app.openapi()['paths'])
assert all(shutil.which(n) for n in ('pdfinfo','pdftotext','pdftoppm','tesseract'))
data,audit=workbook([('test.pdf',[Page(1,[[Cell(0,'00001')]])])])
assert data.startswith(b'PK') and audit[0]['pages']==1
print('Offline image checks passed')
'''
    docker('run','--rm','--network','none','--entrypoint','python',image,'-c',smoke,timeout=60)
    overlay = build/'docker-compose.assistant-studio.json'
    overlay.write_text(json.dumps({'services':{'api':{'image':image,'pull_policy':'never'}}}))
    prefix = ['compose','--project-directory',str(directory),'-p',project]
    for file in original_files: prefix += ['-f',file]
    updated = prefix + ['-f',str(overlay)]
    rollback_overlay=build/'docker-compose.rollback.json'
    rollback_overlay.write_text(json.dumps({'services':{'api':{'image':info['image'],'pull_policy':'never'}}}))
    rollback = ['/usr/bin/sudo','/usr/bin/docker',*prefix,'-f',str(rollback_overlay),'up','-d','--no-deps','--no-build','--pull','never','api']
    (build/'rollback-command.txt').write_text(shlex.join(rollback)+'\n')
    if not args.apply:
        print('Image prepared and checked. Production is unchanged. Run this installer with --apply to enable.')
        return
    if docker('inspect', 'deploy-api-1', '--format', '{{.Image}}') != info['image']:
        raise ValueError('The active API changed during preparation. Nothing was deployed; rerun against the new image.')
    # Snapshot privately before additive schema changes; never print database credentials.
    db_id=docker(*prefix,'ps','-q','db')
    if not db_id or '\n' in db_id: raise ValueError('Cannot identify exactly one database service; nothing changed.')
    dump=build/'database-before-studio.dump'
    with dump.open('wb') as out:
        subprocess.run(['/usr/bin/sudo','/usr/bin/docker','exec',db_id,'sh','-c','exec pg_dump -Fc -U "$POSTGRES_USER" "$POSTGRES_DB"'],stdout=out,stderr=subprocess.PIPE,check=True,timeout=300)
    if dump.stat().st_size<20: raise ValueError('Database backup was empty; no migration applied.')
    print('Private database backup saved. Applying additive tables...',flush=True)
    docker(*updated,'run','--rm','--no-deps','--entrypoint','alembic','api','upgrade','0011',timeout=180)
    try:
        docker(*updated,'up','-d','--no-deps','--no-build','--pull','never','api',timeout=120)
        if not healthy(): raise ValueError('Updated API did not become healthy')
        check=docker('exec','deploy-api-1','python','-c',"import httpx; r=httpx.get('http://127.0.0.1:8000/api/v1/assistant-studio/projects'); print(r.status_code)")
        if check!='401': raise ValueError('Authenticated studio route check failed')
    except Exception:
        subprocess.run(rollback,check=True,capture_output=True)
        print('Previous API image restored. New additive tables were retained; no records were deleted.')
        raise
    print('Assistant studio installed. API is healthy. Ratings, project builds and PDF conversion routes are ready.')
    print('Existing web client, search, weather, OCR and other services were preserved.')
    print('Rollback command: '+str(build/'rollback-command.txt'))
    print('Private database backup: '+str(dump))


if __name__ == '__main__':
    try:
        main()
    except subprocess.CalledProcessError:
        raise SystemExit('An installer command failed. No command output or secrets were printed. Keep the private build folder for diagnosis.') from None
    except (ValueError, KeyError, OSError) as exc:
        raise SystemExit(str(exc)) from None
