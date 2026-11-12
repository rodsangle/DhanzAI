import importlib.util
import json
from pathlib import Path


def test_api_copy_permissions_are_independent_of_private_host_modes(tmp_path):
    path = Path(__file__).parents[2] / "deploy/updaters/install_spreadsheet_tools.py"
    spec = importlib.util.spec_from_file_location("installer_permissions", path)
    installer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(installer)
    source = tmp_path / "website_tools.py"
    source.write_text("VALUE = 1\n")
    source.chmod(0o600)
    dockerfile = installer.image_dockerfile(
        "dhanz-api:before-test", "/srv/backend/app/assistant_studio/bootstrap.py", ["website_tools.py"]
    )
    copies = [line for line in dockerfile.splitlines() if line.startswith("COPY")]
    assert len(copies) == 2
    assert all(line.startswith("COPY --chmod=0755 ") for line in copies)
    assert json.loads(copies[1].removeprefix("COPY --chmod=0755 ")) == [
        "website_tools.py",
        "/srv/backend/app/assistant_studio/website_tools.py",
    ]
    assert source.stat().st_mode & 0o777 == 0o600
    assert not any(line.startswith(("USER ", "RUN chmod")) for line in dockerfile.splitlines())
