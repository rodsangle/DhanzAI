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
assert any('assistant-studio' in r.path for r in app.routes if hasattr(r,'path'))
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
