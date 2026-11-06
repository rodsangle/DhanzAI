import ast
import base64
import gzip
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("app_installer", ROOT / "deploy/updaters/install_app_builder_chat.py")
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


def test_mobile_patches_preserve_existing_hooks_and_custom_code():
    bootstrap = (ROOT / "server_extensions/assistant_studio/bootstrap.py").read_text()
    data = installer.payload()
    baseline = bootstrap.replace(data["boot_new"], data["boot_anchor"])
    baseline += "\nCUSTOM_EXISTING_FEATURE = True\n"
    updated = installer.patch_bootstrap(baseline)
    assert "CUSTOM_EXISTING_FEATURE = True" in updated
    assert installer.patch_bootstrap(updated) == updated
    compile(updated, "bootstrap.py", "exec")
    assert "COPY --chmod=0755" in installer.image_dockerfile("base:fixed", "/srv/app/bootstrap.py", installer.MODULES)


def test_known_protocol_builder_is_patched_without_replacing_other_features():
    tree = ast.parse((ROOT / "deploy/updaters/install_builder_protocol.py").read_text())
    encoded = next(
        ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "PAYLOAD" for t in node.targets)
    )
    original = gzip.decompress(base64.b64decode(encoded)).decode()
    original += "\nCUSTOM_EXISTING_FEATURE = True\n"
    updated = installer.patch_builder(original)
    assert "CUSTOM_EXISTING_FEATURE = True" in updated
    assert "if mobile and not " in updated
    assert installer.patch_builder(updated) == updated
    compile(updated, "builder.py", "exec")
    with pytest.raises(ValueError, match="Unknown project generation"):
        installer.patch_builder("unsupported = True")


def test_installer_payload_and_inline_checks_are_current():
    assert (
        installer.payload()["module"] == (ROOT / "server_extensions/assistant_studio/app_builder_tools.py").read_text()
    )
    tree = ast.parse((ROOT / "deploy/updaters/install_app_builder_chat.py").read_text())
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and ("import json,pathlib" in node.value or "OFFLINE_CHECK_FAILED:" in node.value and "\n" in node.value)
        ):
            compile(node.value, "inline.py", "exec")
    # The patch must compile even when applied to today's public builder too.
    public = (ROOT / "server_extensions/assistant_studio/builder.py").read_text()
    fragment = installer.payload()["builder_fragment"]
    validation = installer.payload()["builder_validation"]
    baseline = public.replace(fragment, "").replace(
        validation, '    if job.kind == "app" and not any(f["path"] == "index.html" for f in files):\n'
    )
    compile(installer.patch_builder(baseline), "builder.py", "exec")
