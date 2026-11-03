"""Patch only the attachment reader in the running custom API; preserve its other features."""

import argparse
import ast
import base64
import gzip
import hashlib
import json
import re
import shlex
import subprocess
import time
from pathlib import Path

_EXPECTED_READER_SHA = "9a7244da3cfe50fa73791faea3d09702795c3562f605b91eb664326468e1c76b"
_BUNDLED_SOURCE = (
    "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"
)
# END_BUNDLED_SOURCE


def _digest(node):
    return hashlib.sha256(ast.dump(node, include_attributes=False).encode()).hexdigest()


def patch_source(source):
    tree = ast.parse(source)
    functions = {n.name: n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    if "_DHANZ_ATTACHMENT_FIX_VERSION = 1" in source:
        return source
    reader = functions.get("_attachment_passages")
    research = functions.get("_research")
    if reader is None or _digest(reader) != _EXPECTED_READER_SHA or research is None:
        raise ValueError("The attachment reader differs from the supported baseline. The API was left unchanged.")
    calls = [n for n in ast.walk(research) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)]
    reads = [n for n in calls if n.func.id == "_attachment_passages"]
    budgets = [n for n in calls if n.func.id == "attachment_context_budget"]
    if len(reads) != 1 or ast.unparse(reads[0]) != "_attachment_passages(db, turn, notes)":
        raise ValueError("The custom attachment call is different. The API was left unchanged.")
    if len(budgets) != 1 or ast.unparse(budgets[0]) != "attachment_context_budget(window)":
        raise ValueError("The custom context budget is different. The API was left unchanged.")
    bundled = gzip.decompress(base64.b64decode(_BUNDLED_SOURCE)).decode()
    payload = ast.parse(bundled)
    definitions = {n.name: n for n in payload.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    new_reader = definitions.pop("_attachment_passages")
    if functions.keys() & definitions.keys():
        raise ValueError("An attachment helper already exists; inspect it before replacing anything.")
    raw = source.encode()
    lines = raw.splitlines(keepends=True)

    def span(node):
        return sum(map(len, lines[: node.lineno - 1])) + node.col_offset, sum(
            map(len, lines[: node.end_lineno - 1])
        ) + node.end_col_offset

    changes = [
        (*span(reader), ast.get_source_segment(bundled, new_reader)),
        (
            *span(reads[0]),
            "_attachment_passages(db, turn, notes, budget_chars=_attachment_budget_for_turn(orchestrator, turn))",
        ),
        (*span(budgets[0]), "_attachment_budget_for_turn(orchestrator, turn, window=window)"),
    ]
    for start, end, replacement in sorted(changes, reverse=True):
        raw = raw[:start] + replacement.encode() + raw[end:]
    helpers = "\n\n".join(ast.get_source_segment(bundled, n) for n in definitions.values())
    result = raw.decode() + (
        "\n\n# Additive attachment conversion update; existing custom code is retained.\n"
        "import re\nFULL_ATTACHMENT_CONTEXT_BUDGET = 160_000\n_DHANZ_ATTACHMENT_FIX_VERSION = 1\n\n" + helpers + "\n"
    )
    compile(result, "chat_service.py", "exec")
    return result


def docker(*args, **kwargs):
    return subprocess.run(  # noqa: S603 - fixed executable with argument arrays, never a shell.
        ["/usr/bin/sudo", "/usr/bin/docker", *args], check=True, text=True, capture_output=True, **kwargs
    ).stdout.strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    metadata = (
        '{"image":{{json .Image}},"files":{{json (index .Config.Labels "com.docker.compose.project.config_files")}},'
        '"directory":{{json (index .Config.Labels "com.docker.compose.project.working_dir")}},'
        '"project":{{json (index .Config.Labels "com.docker.compose.project")}},'
        '"mounts":[{{range $i,$m := .Mounts}}{{if $i}},{{end}}{{json $m.Destination}}{{end}}]}'
    )
    info = json.loads(docker("inspect", "deploy-api-1", "--format", metadata))
    packet = json.loads(
        docker(
            "exec",
            "deploy-api-1",
            "python",
            "-c",
            "import base64,json,pathlib; import app.services.chat_service as m; "
            "print(json.dumps({'path':m.__file__,'source':base64.b64encode(pathlib.Path(m.__file__).read_bytes()).decode()}))",
        )
    )
    path = packet["path"]
    if not path.startswith("/") or not path.endswith("/app/services/chat_service.py"):
        raise ValueError("Unexpected chat module path. Nothing was changed.")
    if any(path == m.rstrip("/") or path.startswith(m.rstrip("/") + "/") for m in info["mounts"]):
        raise ValueError("Chat source is mounted over the image. Nothing was changed; inspect the mount first.")
    source = base64.b64decode(packet["source"]).decode()
    patched = patch_source(source)
    if patched == source:
        print("Attachment conversion update is already installed.")
        return
    files = [Path(p) for p in info["files"].split(",")]
    directory = Path(info["directory"])
    if not info["project"] or not directory.is_dir() or not all(p.is_file() and p.is_absolute() for p in files):
        raise ValueError("The original Compose configuration is unavailable. Nothing was changed.")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", info["image"]):
        raise ValueError("Cannot identify the current API image. Nothing was changed.")
    overlay = directory / "docker-compose.attachments.json"
    if overlay.exists() and json.loads(overlay.read_text()).get("x-dhanz-attachment-fix") != 1:
        raise ValueError("An unrelated attachment overlay exists. Nothing was changed.")
    stamp = str(time.time_ns())
    work = Path.home() / ("dhanz-attachment-build-" + stamp)
    work.mkdir(mode=0o700)
    (work / "chat_service.before.py").write_text(source)
    (work / "chat_service.py").write_text(patched)
    before = "dhanz-api:before-attachments-" + stamp
    image = "dhanz-api:attachments-" + stamp
    docker("tag", info["image"], before)
    (work / "Dockerfile").write_text("FROM " + before + "\nCOPY " + json.dumps(["chat_service.py", path]) + "\n")
    print("Building an additive update from your current image...", flush=True)
    docker("build", "--network=none", "-t", image, str(work))
    docker(
        "run",
        "--rm",
        "--network=none",
        "-e",
        "APP_ENV=test",
        "--entrypoint",
        "python",
        image,
        "-c",
        "from app.services.chat_service import _DHANZ_ATTACHMENT_FIX_VERSION,_complete_attachment_requested; "
        "assert _DHANZ_ATTACHMENT_FIX_VERSION == 1; assert _complete_attachment_requested('Convert PDF to Excel')",
    )
    overlay.write_text(
        json.dumps({"x-dhanz-attachment-fix": 1, "services": {"api": {"image": image}}}, indent=2) + "\n"
    )
    overlay.chmod(0o600)
    command = ["compose", "--project-name", info["project"], "--project-directory", str(directory)]
    for file in [p for p in files if p != overlay] + [overlay]:
        command += ["-f", str(file)]
    docker(*command, "config", "--quiet", cwd=directory)
    print("Existing custom features, OCR settings, image snapshot and Compose files were preserved.")
    if not args.apply:
        print("Prepared only. To activate: python3 " + shlex.quote(str(Path(__file__).resolve())) + " --apply")
        return
    docker(*command, "up", "-d", "--no-deps", "--no-build", "--pull", "never", "--force-recreate", "api", cwd=directory)
    print("Attachment backend update activated. No database migration was added. Verify API readiness before use.")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        raise SystemExit(
            f"Docker step failed (exit {exc.returncode}). No source or configuration values were printed."
        ) from None
    except (ValueError, OSError, KeyError) as exc:
        raise SystemExit(str(exc)) from None
