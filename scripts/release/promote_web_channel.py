"""Decide publication before touching release assets; old reruns must not clobber them."""

import json
import re
import sys
from pathlib import Path


def key(data):
    version = data["version"]
    build = data["build"]
    if not re.fullmatch(r"\d+\.\d+\.\d+", version) or type(build) is not int or build < 0:
        raise ValueError("Invalid web channel version.")
    return (*map(int, version.split(".")), build)


def should_publish(current, candidate):
    candidate_key = key(candidate)
    return current is None or candidate_key > key(current)


if __name__ == "__main__":
    current = Path(sys.argv[1])
    candidate = json.loads(Path(sys.argv[2]).read_text())
    existing = json.loads(current.read_text()) if current.is_file() else None
    print("promote=" + str(should_publish(existing, candidate)).lower())
