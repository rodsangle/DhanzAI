"""Enable existing PDF OCR while preserving a custom Compose API image and overlays."""

import argparse
import json
import re
import shlex
import subprocess
import tempfile
import time
from pathlib import Path

_METADATA = (
    '{"image":{{json .Image}},'
    '"files":{{json (index .Config.Labels "com.docker.compose.project.config_files")}},'
    '"directory":{{json (index .Config.Labels "com.docker.compose.project.working_dir")}},'
    '"project":{{json (index .Config.Labels "com.docker.compose.project")}},'
    '"service":{{json (index .Config.Labels "com.docker.compose.service")}}}'
)
_PROBE = (
    "import json,shutil; from app.core.config import get_settings; s=get_settings(); "
    'print(json.dumps({"supported":hasattr(s,"ocr_enabled"),'
    '"enabled":getattr(s,"ocr_enabled",False),'
    '"tesseract":bool(shutil.which("tesseract")),"poppler":bool(shutil.which("pdftoppm"))}))'
)


def docker(*args, directory=None):
    result = subprocess.run(  # noqa: S603 - argument array, no shell or user-provided commands.
        ["/usr/bin/sudo", "/usr/bin/docker", *args], text=True, capture_output=True, cwd=directory, check=True
    )
    return result.stdout.strip()


def enable(container="deploy-api-1", *, apply=False):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", container):
        raise ValueError("Invalid container name.")
    status = json.loads(docker("exec", container, "python", "-c", _PROBE))
    if not all(status.get(name) for name in ["supported", "tesseract", "poppler"]):
        raise ValueError("This image must support OCR and include both Tesseract and pdftoppm. Nothing was changed.")
    if status["enabled"]:
        print("OCR is already enabled. Upload the PDF again to extract its scanned pages.")
        return

    metadata = json.loads(docker("inspect", container, "--format", _METADATA))
    if metadata.get("service") != "api" or not metadata.get("project") or not metadata.get("directory"):
        raise ValueError("The API's original Compose metadata is unavailable. Nothing was changed.")
    directory = Path(metadata["directory"])
    files = [Path(name) for name in (metadata.get("files") or "").split(",") if name]
    if not directory.is_dir() or not files or any(not p.is_absolute() or not p.is_file() for p in files):
        raise ValueError("An original Compose file/directory is missing. Nothing was changed.")
    image = metadata["image"]
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", image):
        raise ValueError("Cannot identify the current image safely. Nothing was changed.")

    overlay = directory / "docker-compose.ocr.json"
    if overlay.exists() and json.loads(overlay.read_text()).get("x-dhanz-ocr-helper") != 1:
        raise ValueError("An unrelated OCR overlay already exists. It was left unchanged.")
    tag = "dhanz-api:ocr-base-" + image.removeprefix("sha256:")[:16]
    docker("tag", image, tag)
    # A local image snapshot prevents a changed :latest tag or an accidental pull
    # from replacing the customized running code during the environment update.
    with tempfile.NamedTemporaryFile(mode="w", dir=directory, prefix=".dhanz-ocr-", delete=False) as handle:
        json.dump(
            {"x-dhanz-ocr-helper": 1, "services": {"api": {"image": tag, "environment": {"OCR_ENABLED": "true"}}}},
            handle,
            indent=2,
        )
        handle.write("\n")
        temporary = Path(handle.name)
    temporary.replace(overlay)
    args = ["compose", "--project-name", metadata["project"], "--project-directory", str(directory)]
    for path in [p for p in files if p != overlay] + [overlay]:
        args.extend(["-f", str(path)])
    docker(*args, "config", "--quiet", directory=directory)
    if not apply:
        print("Prepared OCR overlay and a snapshot of the current image. The running API is unchanged.")
        print("To enable OCR, run: python3 " + shlex.quote(str(Path(__file__).resolve())) + " --apply")
        return

    docker(
        *args, "up", "-d", "--no-deps", "--no-build", "--pull", "never", "--force-recreate", "api", directory=directory
    )
    for _ in range(30):
        health = docker(
            "inspect",
            container,
            "--format",
            "{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}",
        )
        if health in {"healthy", "running"}:
            check = json.loads(docker("exec", container, "python", "-c", _PROBE))
            if check.get("enabled"):
                print(
                    "OCR enabled. The API is running with the same image; database and other services were preserved."
                )
                print("Upload the PDF again. Existing uploads are not automatically reprocessed.")
                return
        if health in {"unhealthy", "exited", "dead"}:
            break
        time.sleep(2)
    raise ValueError("The API was recreated, but readiness was not confirmed. Check container health before retrying.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Recreate only the API with OCR enabled.")
    parser.add_argument("--container", default="deploy-api-1")
    args = parser.parse_args()
    try:
        enable(args.container, apply=args.apply)
    except subprocess.CalledProcessError as exc:
        raise SystemExit(f"Docker step failed (exit {exc.returncode}). No configuration values were printed.") from None
    except (ValueError, OSError, KeyError) as exc:
        raise SystemExit(str(exc)) from None


if __name__ == "__main__":
    main()
