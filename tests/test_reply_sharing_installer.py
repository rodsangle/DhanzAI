import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "reply_sharing_installer", ROOT / "deploy/updaters/install_pwa_sharing.py"
)
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


def metadata(folder, version, number, release, commit):
    (folder / "version.json").write_text(json.dumps({"version": version, "build_number": number}))
    (folder / "release.json").write_text(json.dumps({"release_id": release, "source_commit": commit}))


def test_only_known_client_sources_are_accepted_and_current_release_is_idempotent(tmp_path):
    for version, number, release, commit in installer.KNOWN_BASES:
        metadata(tmp_path, version, number, release, commit)
        assert installer.require_base(tmp_path) is True
        metadata(tmp_path, version, number, release, "unknown-source")
        with pytest.raises(ValueError, match="not a verified"):
            installer.require_base(tmp_path)
    metadata(tmp_path, "0.9.6", "24", installer.RELEASE, "share-release-source")
    assert installer.require_base(tmp_path) is False
