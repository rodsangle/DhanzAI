"""Keep explicit city/state information when calling the installed weather tool.

Additive update to the current custom API image. No new API key or database
migration. Requires the existing weather tool. Default prepares; --apply enables.
"""

import argparse
import base64
import gzip
import json
import re
import shlex
import subprocess
import time
from pathlib import Path

_PAYLOAD = (
    "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"
)


def location_source():
    return gzip.decompress(base64.b64decode(_PAYLOAD)).decode()


def patch_source(source):
    if "_DHANZ_WEATHER_LOCATION_FIX_VERSION = 1" in source:
        return source
    if "_register_dhanz_weather(globals())" not in source or "_DHANZ_WEATHER_FIX_VERSION = 1" not in source:
        raise ValueError("The supported weather tool must already be installed. Nothing was changed.")
    if "weather_location" in source:
        raise ValueError("A different weather-location integration already exists. Nothing was changed.")
    result = source + (
        "\n\nfrom app.services.weather_location import install as _bind_dhanz_weather_location\n"
        "_bind_dhanz_weather_location(globals())\n_DHANZ_WEATHER_LOCATION_FIX_VERSION = 1\n"
    )
    compile(result, "assistant_tools.py", "exec")
    return result


def patch_chat(source):
    assignment = "toolbox.ctx.weather_question = turn.question"
    if assignment in source:
        return source
    if "weather_question" in source:
        raise ValueError("A different weather context integration exists. Nothing was changed.")
    lines = source.splitlines(keepends=True)
    indexes = [i for i, line in enumerate(lines) if line.strip() == "toolbox.ctx.capability_report = capabilities"]
    if len(indexes) != 1:
        raise ValueError("The custom chat context differs. Nothing was changed; inspect it first.")
    index = indexes[0]
    indent = re.match(r"[ \t]*", lines[index]).group()
    lines.insert(index + 1, indent + assignment + "\n")
    result = "".join(lines)
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
            "import base64,json,pathlib; import app.services.assistant_tools as m; "
            "import app.services.chat_service as c; "
            "print(json.dumps({'path':m.__file__,'chat_path':c.__file__,'chat_source':base64.b64encode(pathlib.Path(c.__file__).read_bytes()).decode(),'location_exists':pathlib.Path(m.__file__).with_name('weather_location.py').exists(),'source':base64.b64encode(pathlib.Path(m.__file__).read_bytes()).decode()}))",
        )
    )
    path = packet["path"]
    if not path.startswith("/") or not path.endswith("/app/services/assistant_tools.py"):
        raise ValueError("Unexpected tool module path. Nothing was changed.")
    if any(path == m.rstrip("/") or path.startswith(m.rstrip("/") + "/") for m in info["mounts"]):
        raise ValueError("Tool source is mounted over the image. Nothing was changed; inspect the mount first.")
    chat_path = packet["chat_path"]
    if not chat_path.startswith("/") or not chat_path.endswith("/app/services/chat_service.py"):
        raise ValueError("Unexpected chat module path. Nothing was changed.")
    if any(chat_path == m.rstrip("/") or chat_path.startswith(m.rstrip("/") + "/") for m in info["mounts"]):
        raise ValueError("Chat source is mounted over the image. Nothing was changed.")
    chat_source = base64.b64decode(packet["chat_source"]).decode()
    patched_chat = patch_chat(chat_source)
    source = base64.b64decode(packet["source"]).decode()
    patched = patch_source(source)
    if patched == source:
        if patched_chat != chat_source:
            raise ValueError("Partial weather-location update needs review. Nothing was changed.")
        print("Weather location update is already installed.")
        return
    if packet.get("location_exists"):
        raise ValueError("A weather module already exists. Nothing was changed; inspect it first.")
    files = [Path(p) for p in info["files"].split(",")]
    directory = Path(info["directory"])
    if not info["project"] or not directory.is_dir() or not all(p.is_file() and p.is_absolute() for p in files):
        raise ValueError("The original Compose configuration is unavailable. Nothing was changed.")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", info["image"]):
        raise ValueError("Cannot identify the current API image. Nothing was changed.")
    overlay = directory / "docker-compose.weather-location.json"
    if overlay.exists() and json.loads(overlay.read_text()).get("x-dhanz-weather-location-fix") != 1:
        raise ValueError("An unrelated weather overlay exists. Nothing was changed.")
    stamp = str(time.time_ns())
    work = Path.home() / ("dhanz-weather-location-build-" + stamp)
    work.mkdir(mode=0o700)
    (work / "assistant_tools.before.py").write_text(source)
    (work / "assistant_tools.py").write_text(patched)
    (work / "chat_service.before.py").write_text(chat_source)
    (work / "chat_service.py").write_text(patched_chat)
    (work / "weather_location.py").write_text(location_source())
    before = "dhanz-api:before-weather-location-" + stamp
    image = "dhanz-api:weather-location-" + stamp
    docker("tag", info["image"], before)
    (work / "Dockerfile").write_text(
        "FROM "
        + before
        + "\nCOPY "
        + json.dumps(["assistant_tools.py", path])
        + "\nCOPY "
        + json.dumps(["weather_location.py", str(Path(path).with_name("weather_location.py"))])
        + "\nCOPY "
        + json.dumps(["chat_service.py", chat_path])
        + "\n"
    )
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
        "import inspect; from app.services import assistant_tools as m,chat_service as c; "
        "from app.services.weather_location import bind_location; "
        "assert m._DHANZ_WEATHER_LOCATION_FIX_VERSION == 1; "
        "assert 'weather_question = turn.question' in inspect.getsource(c); "
        "assert bind_location({'city':'Houston'},'weather in Houston Texas')['region']=='Texas'; "
        "assert 'region' in m.TOOLS['get_weather'].spec.parameters['required']",
    )
    overlay.write_text(
        json.dumps({"x-dhanz-weather-location-fix": 1, "services": {"api": {"image": image}}}, indent=2) + "\n"
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
    rollback = command.copy()
    rollback_file = work / "rollback.json"
    rollback_file.write_text(json.dumps({"services": {"api": {"image": before}}}))
    rollback_file.chmod(0o600)
    rollback += [
        "-f",
        str(rollback_file),
        "up",
        "-d",
        "--no-deps",
        "--no-build",
        "--pull",
        "never",
        "--force-recreate",
        "api",
    ]
    (work / "rollback-command.txt").write_text(shlex.join(["sudo", "docker", *rollback]) + "\n")
    docker(*command, "up", "-d", "--no-deps", "--no-build", "--pull", "never", "--force-recreate", "api", cwd=directory)
    for _ in range(30):
        state = json.loads(docker("inspect", "deploy-api-1", "--format", "{{json .State}}"))
        if state.get("Health", {}).get("Status") == "healthy":
            print("Weather location fix installed. API is healthy. Existing services and OCR settings were preserved.")
            print("Rollback command saved in: " + str(work / "rollback-command.txt"))
            break
        if not state.get("Running"):
            raise ValueError("API is not running. Rollback command: " + str(work / "rollback-command.txt"))
        time.sleep(2)
    else:
        raise ValueError(
            "Health was not confirmed within 60 seconds. Rollback command: " + str(work / "rollback-command.txt")
        )


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        raise SystemExit(
            f"Docker step failed (exit {exc.returncode}). No source or configuration values were printed."
        ) from None
    except (ValueError, OSError, KeyError) as exc:
        raise SystemExit(str(exc)) from None
