"""Freeze the bulk workbook modules into the additive AWS updater."""
import base64
import gzip
import json
import re
from pathlib import Path

root = Path(__file__).resolve().parents[2]
modules = {name: (root / 'server_extensions/assistant_studio' / name).read_text() for name in (
    'spreadsheet_engine.py', 'spreadsheet_package.py', 'workbook_copy.py', 'workbook_copy_tools.py',
)}
value = base64.b64encode(gzip.compress(json.dumps(modules).encode(), mtime=0)).decode()
path = root / 'deploy/updaters/install_bulk_workbooks.py'
path.write_text(re.sub(r'^PAYLOAD = .+$', lambda _: 'PAYLOAD = ' + json.dumps(value)
                       + '  # noqa: E501 - frozen bulk workbook support', path.read_text(), flags=re.M))
