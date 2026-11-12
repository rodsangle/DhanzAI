"""Install a city-based weather tool into the current custom API image.

Uses Open-Meteo's free non-commercial service; review its terms before commercial
use (https://open-meteo.com/en/terms). No API key or GPS collection is added.
Default: prepare only. --apply activates only the API container.
"""

import argparse
import ast
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
    "8j++UL9fCx0AAA=="
)


def weather_source():
    return gzip.decompress(base64.b64decode(_PAYLOAD)).decode()


def patch_source(source):
    if "_DHANZ_WEATHER_FIX_VERSION = 1" in source:
        return source
    tree = ast.parse(source)
    classes = {n.name: n for n in tree.body if isinstance(n, ast.ClassDef)}
    if not {"Tool", "ToolBox", "ToolOutcome", "ToolInputError"}.issubset(classes):
        raise ValueError("Unsupported tool interface; nothing was changed.")
    fields = {
        n.target.id for n in classes["Tool"].body if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name)
    }
    if not {"spec", "label", "run"}.issubset(fields):
        raise ValueError("Unsupported Tool fields; nothing was changed.")
    toolbox = ast.get_source_segment(source, classes["ToolBox"])
    if "TOOLS.values()" not in toolbox or "TOOLS.get(" not in toolbox:
        raise ValueError("Unsupported tool registry; nothing was changed.")
    if "get_weather" in source or "weather_tools" in source:
        raise ValueError("An existing weather integration needs review; nothing was changed.")
    result = (
        source + "\n\nfrom app.services.weather_tools import register as _register_dhanz_weather\n"
        "_register_dhanz_weather(globals())\n_DHANZ_WEATHER_FIX_VERSION = 1\n"
    )
    compile(result, "assistant_tools.py", "exec")
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
            "print(json.dumps({'path':m.__file__,'weather_exists':pathlib.Path(m.__file__).with_name('weather_tools.py').exists(),'source':base64.b64encode(pathlib.Path(m.__file__).read_bytes()).decode()}))",
        )
    )
    path = packet["path"]
    if not path.startswith("/") or not path.endswith("/app/services/assistant_tools.py"):
        raise ValueError("Unexpected tool module path. Nothing was changed.")
    if any(path == m.rstrip("/") or path.startswith(m.rstrip("/") + "/") for m in info["mounts"]):
        raise ValueError("Tool source is mounted over the image. Nothing was changed; inspect the mount first.")
    source = base64.b64decode(packet["source"]).decode()
    patched = patch_source(source)
    if patched == source:
        print("Weather update is already installed.")
        return
    if packet.get("weather_exists"):
        raise ValueError("A weather module already exists. Nothing was changed; inspect it first.")
    files = [Path(p) for p in info["files"].split(",")]
    directory = Path(info["directory"])
    if not info["project"] or not directory.is_dir() or not all(p.is_file() and p.is_absolute() for p in files):
        raise ValueError("The original Compose configuration is unavailable. Nothing was changed.")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", info["image"]):
        raise ValueError("Cannot identify the current API image. Nothing was changed.")
    overlay = directory / "docker-compose.weather.json"
    if overlay.exists() and json.loads(overlay.read_text()).get("x-dhanz-weather-fix") != 1:
        raise ValueError("An unrelated weather overlay exists. Nothing was changed.")
    stamp = str(time.time_ns())
    work = Path.home() / ("dhanz-weather-build-" + stamp)
    work.mkdir(mode=0o700)
    (work / "assistant_tools.before.py").write_text(source)
    (work / "assistant_tools.py").write_text(patched)
    (work / "weather_tools.py").write_text(weather_source())
    before = "dhanz-api:before-weather-" + stamp
    image = "dhanz-api:weather-" + stamp
    docker("tag", info["image"], before)
    (work / "Dockerfile").write_text(
        "FROM "
        + before
        + "\nCOPY "
        + json.dumps(["assistant_tools.py", path])
        + "\nCOPY "
        + json.dumps(["weather_tools.py", str(Path(path).with_name("weather_tools.py"))])
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
        "from app.services import assistant_tools as m; "
        "assert m._DHANZ_WEATHER_FIX_VERSION == 1; "
        "assert 'get_weather' in m.TOOLS; "
        "assert m.TOOLS['get_weather'].spec.parameters['required'] == ['city']",
    )
    overlay.write_text(json.dumps({"x-dhanz-weather-fix": 1, "services": {"api": {"image": image}}}, indent=2) + "\n")
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
            print("Weather tool installed. API is healthy. Existing services and OCR settings were preserved.")
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
