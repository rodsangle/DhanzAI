"""Freeze reviewed chat-file catalog support into its additive updater."""
import base64
import gzip
import json
import re
from pathlib import Path

root = Path(__file__).resolve().parents[2]
value = base64.b64encode(gzip.compress(json.dumps({
    'module': (root / 'server_extensions/assistant_studio/chat_files.py').read_text(),
}).encode(), mtime=0)).decode()
path = root / 'deploy/updaters/install_chat_files.py'
path.write_text(re.sub(r'^PAYLOAD = .+$', lambda _: 'PAYLOAD = ' + json.dumps(value)
                       + '  # noqa: E501 - frozen chat-file catalog support', path.read_text(), flags=re.M))
