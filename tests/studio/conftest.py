import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for name in ("backend", "ai_engine", "knowledge_engine"):
    value = str(ROOT / name)
    if value not in sys.path:
        sys.path.append(value)
import app

app.__path__.append(str(ROOT / "server_extensions"))
