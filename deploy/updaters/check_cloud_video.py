"""Privately validate a Runway key, moderation and existing media storage.

No video is generated, settings changed or service restarted. A validated key is
saved outside the repository in a private file for the subsequent setup step.
"""
import argparse
import getpass
import json
import math
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
import warnings
from pathlib import Path

PROBE = r'''
import asyncio, io, json
import httpx
from PIL import Image
from app.core.config import get_settings
from app.media_storage import build_storage
async def main():
    s=get_settings()
    result={'storage_mode':s.creative_storage,
            'local_rendering_enabled':getattr(s,'creative_local_enabled',False),
            'moderation_mode':getattr(s,'creative_moderation_provider','unknown'),
            'openai_key_configured':bool(s.openai_api_key)}
    if s.openai_api_key:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response=await client.post('https://api.openai.com/v1/moderations',
                    headers={'Authorization':'Bearer '+s.openai_api_key},
                    json={'model':'omni-moderation-latest','input':'A peaceful moonlit forest with drifting mist.'})
            result['moderation_http']=response.status_code
            items=response.json().get('results',[]) if response.status_code==200 else []
            result['moderation_ready']=bool(items) and all(item.get('flagged') is False for item in items)
        except Exception as exc:
            result['moderation_error_type']=type(exc).__name__
            result['moderation_ready']=False
    else:
        result['moderation_ready']=False
    storage=None
    key=None
    result['storage_ready']=False
    try:
        storage=build_storage(s)
        buffer=io.BytesIO()
        Image.new('RGB',(2,2),'black').save(buffer,format='PNG')
        content=buffer.getvalue()
        key=await asyncio.wait_for(storage.put(content),30)
        result['storage_ready']=await asyncio.wait_for(storage.get(key),30)==content
    except Exception as exc:
        result['storage_error_type']=type(exc).__name__
    finally:
        if storage is not None and key is not None:
            try:
                await asyncio.wait_for(storage.delete(key),30)
            except Exception:
                result['temporary_probe_cleanup_failed']=True
        if storage is not None and hasattr(storage,'aclose'):
            await storage.aclose()
    print('CLOUD_VIDEO_CHECK:'+json.dumps(result))
asyncio.run(main())
'''


def validate_key(key):
    if key.startswith('sk-'):
        raise ValueError('This looks like an OpenAI key. A Runway developer API key is required.')
    if not re.fullmatch(r'[A-Za-z0-9_.=/+\-]{20,2048}', key):
        raise ValueError('The key contains unexpected characters or spaces. Copy the Runway API key again.')


def organization(key, opener=urllib.request.urlopen):
    validate_key(key)
    request = urllib.request.Request('https://api.dev.runwayml.com/v1/organization', headers={
        'Authorization': 'Bearer ' + key, 'X-Runway-Version': '2024-11-06', 'Accept': 'application/json',
    })
    try:
        with opener(request, timeout=30) as response:
            data = json.load(response)
    except urllib.error.HTTPError as exc:
        raise ValueError(f'Runway rejected the account check (HTTP {exc.code}). No video was submitted.') from None
    except (OSError, ValueError):
        raise ValueError('The Runway account check could not complete. No video was submitted.') from None
    balance = data.get('creditBalance') if isinstance(data, dict) else None
    if not isinstance(balance, (int, float)) or isinstance(balance, bool) or not math.isfinite(balance):
        raise ValueError('Runway returned an unrecognized credit balance. Nothing was configured.')
    if balance <= 0:
        raise ValueError('The Runway API account has no available credits. Add API credits before setup.')
    return balance


def save_key(path, key):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.parent.is_symlink() or path.is_symlink():
        raise ValueError('The private key location is a symbolic link. Nothing was saved.')
    path.parent.chmod(0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as handle:
        os.fchmod(handle.fileno(), 0o600)
        handle.write(key)


def probe():
    result = subprocess.run(  # noqa: S603 - fixed Docker executable and secret-free Python script
        ['/usr/bin/sudo', '/usr/bin/docker', 'exec', '-i', 'deploy-api-1', 'python', '-'],
        input=PROBE, text=True, capture_output=True, timeout=150, check=False,
    )
    for line in result.stdout.splitlines():
        if line.startswith('CLOUD_VIDEO_CHECK:'):
            data = json.loads(line.removeprefix('CLOUD_VIDEO_CHECK:'))
            allowed = {'storage_mode', 'local_rendering_enabled', 'moderation_mode', 'openai_key_configured',
                       'moderation_http', 'moderation_ready', 'moderation_error_type', 'storage_ready',
                       'storage_error_type', 'temporary_probe_cleanup_failed'}
            return {k: v for k, v in data.items() if k in allowed}
    raise ValueError('The AWS readiness check did not complete. Raw output withheld to protect secrets.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--new-key', action='store_true', help='Replace a previously validated pending key.')
    args = parser.parse_args()
    path = Path.home() / '.local/share/dhanz-cloud-video/runway.key'
    if path.is_symlink() or path.parent.is_symlink():
        raise ValueError('The private key location is a symbolic link. Nothing was read or saved.')
    if path.exists() and not args.new_key:
        key = path.read_text().strip()
    else:
        if not sys.stdin.isatty():
            raise ValueError('Run this script directly in the interactive AWS terminal for hidden key entry.')
        warnings.simplefilter('error', getpass.GetPassWarning)
        try:
            key = getpass.getpass('Runway API key (hidden; paste it here, not in ChatGPT): ').strip()
        except getpass.GetPassWarning:
            raise ValueError('Hidden entry is unavailable. Use an interactive SSH terminal; no key was saved.') from None
    balance = organization(key)
    save_key(path, key)
    print('Runway authentication: OK')
    print('Runway API credit balance:', balance)
    print('Validated key saved privately for setup. No video was submitted.')
    for name, value in probe().items():
        print(name + ':', value)
    print('CHECK COMPLETE. Server configuration is unchanged. Paste these status lines, never the key.')


if __name__ == '__main__':
    os.umask(0o077)
    try:
        main()
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        if isinstance(exc, ValueError):
            raise SystemExit(str(exc)) from None
        raise SystemExit('The check could not finish. Raw output withheld; no video was submitted.') from None
