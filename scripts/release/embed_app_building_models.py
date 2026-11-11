"""Freeze the reviewed app-building model catalog into its additive installer."""
import base64
import gzip
import json
import re
from pathlib import Path

root = Path(__file__).resolve().parents[2]
module = (root / 'server_extensions/assistant_studio/app_building_models.py').read_text()
value = base64.b64encode(gzip.compress(json.dumps({'module': module}).encode(), mtime=0)).decode()
path = root / 'deploy/updaters/install_app_building_model.py'
path.write_text(re.sub(r'^PAYLOAD = .+$', lambda _: 'PAYLOAD = ' + json.dumps(value)
    + '  # noqa: E501 - frozen app-building model catalog', path.read_text(), flags=re.M))
