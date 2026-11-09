"""Freeze reviewed worker and additive API source into standalone installers."""
import base64
import gzip
import json
import re
from pathlib import Path

root = Path(__file__).resolve().parents[2]


def embed(target, sources):
    value = base64.b64encode(gzip.compress(json.dumps(sources).encode(), mtime=0)).decode()
    target.write_text(re.sub(r'^PAYLOAD = .+$', lambda _: 'PAYLOAD = ' + json.dumps(value)
                            + '  # noqa: E501 - frozen ROG worker support', target.read_text(), flags=re.M))


embed(root / 'deploy/updaters/install_rog_backend.py', {
    name: (root / 'server_extensions/assistant_studio' / name).read_text()
    for name in ('rog_queue.py', 'rog_video.py')
})
embed(root / 'apps/rog_video_worker/setup_worker.py', {
    'worker.py': (root / 'apps/rog_video_worker/worker.py').read_text(),
    'preview.py': (root / 'apps/rog_video_worker/setup_wan_preview.py').read_text(),
})
