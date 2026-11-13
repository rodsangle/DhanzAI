#!/usr/bin/env python3
"""Switch the DHANZ server to the newest AI models its own API keys can use.

Run on the server, from the repository checkout:

    sudo python3 scripts/server/upgrade_models.py                    # report only, changes nothing
    sudo python3 scripts/server/upgrade_models.py --apply --restart  # save and restart the API

For every provider that has a key in deploy/.env, the script lists the models that key may use,
then sends each candidate one tiny chat request built like the app's real requests (streaming,
temperature, token limit). Only models that answer are chosen, and the models already configured
are kept after them as fallbacks while they still work. Image models are chosen from the
provider's model list without generating anything. Keys are read from .env and never printed.

--apply writes .env after saving a timestamped backup next to it. --restart recreates the API
(and Creative Studio worker, if running) with the same compose files they were started with.
Undo: copy the backup over .env and run the same restart.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENV = ROOT / "deploy" / ".env"
MAX_NEW_CHAT_MODELS = 3
PROBE_PROMPT = "Reply with the single word OK."
# A minimal function tool, so the test request has the same shape as a real chat with assistant tools.
PROBE_TOOL = {
    "type": "function",
    "function": {
        "name": "get_time",
        "description": "Current time. Not needed for this reply.",
        "parameters": {"type": "object", "properties": {}},
    },
}

# Model ids that are not general chat models even though they share a family prefix.
_NOT_CHAT = re.compile(
    r"(audio|realtime|live|image|tts|transcribe|search|embed|cyber|research|codex|moderation|"
    r"vision-preview|preview|exp|instruct|computer|robotics|native|veo|imagen|aqa|learnlm|gemma)",
)

Http = Callable[[str, str, dict, dict | None], tuple[int, object]]


def http(method: str, url: str, headers: dict, body: dict | None = None) -> tuple[int, object]:
    """Small JSON client. Returns (status, parsed body or text). Never raises for HTTP errors."""
    if not url.startswith("https://"):
        return 0, "only https URLs are used"
    data = json.dumps(body).encode() if body is not None else None
    headers = {**headers, "User-Agent": "dhanz-upgrade"}
    request = urllib.request.Request(url, data=data, method=method, headers=headers)  # noqa: S310 - https only
    if data is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310 - https only
            raw = response.read(200_000).decode("utf-8", "replace")
            status = response.status
    except urllib.error.HTTPError as exc:
        raw = exc.read(20_000).decode("utf-8", "replace")
        status = exc.code
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return 0, str(exc)
    try:
        return status, json.loads(raw)
    except ValueError:
        return status, raw


# ---------------------------------------------------------------------------------------------
# .env handling


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key.strip()] = value
    return values


def write_env(path: Path, changes: dict[str, str]) -> Path:
    """Apply changes in place (replacing an existing KEY= line or appending). Returns the backup."""
    backup = path.with_name(f"{path.name}.bak-{time.strftime('%Y%m%d-%H%M%S')}")
    shutil.copy2(path, backup)
    backup.chmod(0o600)
    lines = path.read_text().splitlines()
    pending = dict(changes)
    for i, line in enumerate(lines):
        key = line.split("=", 1)[0].strip()
        if not line.lstrip().startswith("#") and "=" in line and key in pending:
            lines[i] = f"{key}={pending.pop(key)}"
    if pending:
        lines.append("# Added by scripts/server/upgrade_models.py")
        lines += [f"{key}={value}" for key, value in pending.items()]
    path.write_text("\n".join(lines) + "\n")
    return backup


def csv(value: str | None) -> list[str]:
    return [item.strip() for item in (value or "").split(",") if item.strip()]


# ---------------------------------------------------------------------------------------------
# Ordering


def version_key(model: str) -> tuple:
    """Newest first: higher version numbers, then dated snapshots last among equals."""
    numbers = re.findall(r"\d+(?:\.\d+)?", model.split("-20")[0])
    parsed = tuple(-float(n) for n in numbers[:2])
    return (*parsed, model.count("-20"), model)


def _numbers(model: str) -> tuple[float, ...]:
    return tuple(float(n) for n in re.findall(r"\d+(?:\.\d+)?", model.split("-20")[0])[:2])


def is_newer(model: str, current: list[str]) -> bool:
    """True when the model's version is above every configured model's version."""
    return not current or _numbers(model) > max(_numbers(c) for c in current)


def newest(models: list[str]) -> list[str]:
    return sorted(dict.fromkeys(models), key=version_key)


# ---------------------------------------------------------------------------------------------
# Providers


@dataclass
class Result:
    setting: str
    current: str
    proposed: str
    notes: list[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return self.proposed != self.current


def _ids(payload: object, key: str = "data", field_name: str = "id") -> list[str]:
    if not isinstance(payload, dict):
        return []
    return [str(item.get(field_name, "")) for item in payload.get(key) or [] if isinstance(item, dict)]


def _reason(status: int, payload: object) -> str:
    """Short, key-free explanation of a failed test request (the provider's own error message)."""
    message = payload
    if isinstance(payload, dict):
        error = payload.get("error", payload)
        message = error.get("message", error) if isinstance(error, dict) else error
    text = re.sub(r"\s+", " ", str(message)).strip()
    text = re.sub(r"(sk|xai|AIza)[-_A-Za-z0-9]{8,}", "[key]", text)
    return f"HTTP {status}: {text[:200]}" if status else text[:200]


def _choose(
    setting: str,
    current: list[str],
    candidates: list[str],
    works: Callable[[str], bool],
    reasons: dict[str, str] | None = None,
) -> Result:
    notes: list[str] = []
    chosen: list[str] = []
    for model in candidates:
        if len(chosen) >= MAX_NEW_CHAT_MODELS:
            break
        if model in current or not is_newer(model, current):
            continue
        if works(model):
            chosen.append(model)
            notes.append(f"{model}: answered the test request")
        else:
            why = (reasons or {}).get(model)
            notes.append(f"{model}: listed but the test request failed, skipped" + (f" ({why})" if why else ""))
    kept = []
    for model in current:
        if works(model):
            kept.append(model)
        else:
            notes.append(f"{model}: no longer answers, removed")
    final = list(dict.fromkeys(chosen + kept))
    if not final:  # never leave a provider with no models
        final = current
        notes.append("nothing answered; left unchanged")
    return Result(setting, ",".join(current), ",".join(final), notes)


_DEFAULT_TEMPERATURE_ONLY = "Only the default (1) value is supported"


def server_adapts_settings() -> bool:
    """True when the running API's OpenAI adapter adjusts refused settings itself (GPT-5.5/5.6/6.x support)."""
    try:
        return _server_adapts_settings()
    except OSError:  # no docker on this machine
        return False


def _server_adapts_settings() -> bool:
    names = subprocess.run(  # noqa: S603 - fixed argv
        ["docker", "ps", "--filter", "label=com.docker.compose.service=api", "--format", "{{.Names}}"],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    ).stdout.split()
    if not names:
        return False
    check = "import dhanz_ai.providers.openai as m; print(getattr(m, 'ADAPTIVE_PARAMS', False))"
    out = subprocess.run(  # noqa: S603 - fixed argv
        ["docker", "exec", names[0], "python", "-c", check],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    return out == "True"


def openai_chat(env: dict[str, str], call: Http, adaptive: bool = False) -> list[Result] | None:
    key = env.get("OPENAI_API_KEY")
    if not key:
        return None
    base = (env.get("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
    auth = {"Authorization": f"Bearer {key}"}
    current = csv(env.get("OPENAI_MODELS") or "gpt-4.1-mini,gpt-4.1")
    status, payload = call("GET", f"{base}/models", auth, None)
    if status != 200:
        return [Result("OPENAI_MODELS", ",".join(current), ",".join(current), [f"model list failed (HTTP {status})"])]
    # "-pro" models only work through the Responses API, which the app does not use.
    listed = [
        m
        for m in _ids(payload)
        if re.fullmatch(r"gpt-\d+(\.\d+)?(-[a-z]+)?", m) and not _NOT_CHAT.search(m) and not m.endswith("-pro")
    ]
    temperature = float(env.get("DEFAULT_TEMPERATURE") or 0.7)
    cache: dict[str, bool] = {}
    reasons: dict[str, str] = {}

    def works(model: str) -> bool:
        if model in cache:
            return cache[model]
        body = {
            "model": model,
            "messages": [{"role": "user", "content": PROBE_PROMPT}],
            "stream": True,
            "stream_options": {"include_usage": True},
            "temperature": temperature,
            "max_completion_tokens": 256,
            # Real chats always offer the assistant tools; some models reject tools on this API.
            "tools": [PROBE_TOOL],
        }
        # An adaptive server drops a refused temperature and sends reasoning_effort "none" with tools;
        # test the same way. Otherwise one refusal means the model cannot be used.
        for _ in range(3):
            status, payload = call("POST", f"{base}/chat/completions", auth, body)
            if status == 200:
                break
            why = _reason(status, payload)
            low = why.lower()
            if adaptive and status == 400 and "temperature" in low and "temperature" in body:
                body.pop("temperature")
            elif adaptive and status == 400 and "reasoning_effort" in low and "'none'" in low:
                body["reasoning_effort"] = "none"
            else:
                break
        cache[model] = status == 200
        if status != 200:
            reasons[model] = why
        return cache[model]

    result = _choose("OPENAI_MODELS", current, newest(listed), works, reasons)
    if not adaptive:
        for i, note in enumerate(result.notes):
            if _DEFAULT_TEMPERATURE_ONLY in note or "reasoning_effort" in note:
                result.notes[i] = note + " [the server needs the GPT-6 support update: deploy_ai_engine.py]"
    return [result]


def gemini_chat(env: dict[str, str], call: Http) -> Result | None:
    key = env.get("GEMINI_API_KEY")
    if not key:
        return None
    base = "https://generativelanguage.googleapis.com/v1beta"
    auth = {"x-goog-api-key": key}
    current = csv(env.get("GEMINI_MODELS") or "gemini-2.5-flash,gemini-2.5-pro")
    status, payload = call("GET", f"{base}/models?pageSize=1000", auth, None)
    if status != 200:
        return Result("GEMINI_MODELS", ",".join(current), ",".join(current), [f"model list failed (HTTP {status})"])
    listed = []
    for item in (payload or {}).get("models", []) if isinstance(payload, dict) else []:
        name = str(item.get("name", "")).removeprefix("models/")
        if "generateContent" not in (item.get("supportedGenerationMethods") or []):
            continue
        if re.fullmatch(r"gemini-\d+(\.\d+)?-[a-z]+(-[a-z]+)?", name) and not _NOT_CHAT.search(name):
            listed.append(name)
    cache: dict[str, bool] = {}
    reasons: dict[str, str] = {}

    def works(model: str) -> bool:
        if model not in cache:
            body = {"contents": [{"role": "user", "parts": [{"text": PROBE_PROMPT}]}]}
            url = f"{base}/models/{model}:streamGenerateContent?alt=sse"
            status, payload = call("POST", url, auth, body)
            cache[model] = status == 200
            if status != 200:
                reasons[model] = _reason(status, payload)
        return cache[model]

    return _choose("GEMINI_MODELS", current, newest(listed), works, reasons)


def anthropic_chat(env: dict[str, str], call: Http) -> Result | None:
    key = env.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    base = "https://api.anthropic.com/v1"
    auth = {"x-api-key": key, "anthropic-version": "2023-06-01"}
    current = csv(env.get("ANTHROPIC_MODELS") or "claude-sonnet-5-5,claude-haiku-5-5,claude-opus-5-5")
    status, payload = call("GET", f"{base}/models?limit=100", auth, None)
    if status != 200:
        return Result("ANTHROPIC_MODELS", ",".join(current), ",".join(current), [f"model list failed (HTTP {status})"])
    # The list is newest first; keep only the newest version of each family (opus, sonnet, haiku).
    listed, families = [], set()
    for model in _ids(payload):
        family = re.match(r"claude-([a-z]+)", model)
        if family and family.group(1) not in families and not re.search(r"-\d{8}$", model):
            families.add(family.group(1))
            listed.append(model)
    cache: dict[str, bool] = {}
    reasons: dict[str, str] = {}

    def works(model: str) -> bool:
        if model not in cache:
            body = {"model": model, "max_tokens": 16, "messages": [{"role": "user", "content": PROBE_PROMPT}]}
            status, payload = call("POST", f"{base}/messages", auth, body)
            cache[model] = status == 200
            if status != 200:
                reasons[model] = _reason(status, payload)
        return cache[model]

    return _choose("ANTHROPIC_MODELS", current, listed, works, reasons)


def image_model(env: dict[str, str], call: Http) -> Result | None:
    if env.get("CREATIVE_ENABLED", "false").lower() != "true":
        return None
    key = env.get("CREATIVE_IMAGE_API_KEY") or env.get("OPENAI_API_KEY")
    if not key:
        return None
    base = (env.get("CREATIVE_IMAGE_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
    current = env.get("CREATIVE_IMAGE_MODEL") or "gpt-image-2.5-sunburst"
    status, payload = call("GET", f"{base}/models", {"Authorization": f"Bearer {key}"}, None)
    if status != 200:
        return Result("CREATIVE_IMAGE_MODEL", current, current, [f"model list failed (HTTP {status})"])
    ids = _ids(payload)
    if "x.ai" in base:
        listed = [m for m in ids if re.fullmatch(r"grok-imagine-image(-\d+(\.\d+)?)?", m)]
    else:
        listed = [m for m in ids if re.fullmatch(r"gpt-image-\d+(\.\d+)?(-[a-z]+)?", m)]
    # Stay with the same variant (e.g. "-sunburst") when a newer version of it exists.
    versioned = re.match(r"^[a-z-]+?-\d+(?:\.\d+)?(.*)$", current)
    variant = versioned.group(1) if versioned else ""
    same = [m for m in listed if variant and m.endswith(variant)] or listed
    best = newest(same)[0] if same else current
    if version_key(best) >= version_key(current):
        best = current
    notes = [f"{best}: newest image model your key can use"] if best != current else ["already the newest"]
    return Result("CREATIVE_IMAGE_MODEL", current, best, notes)


def video_note(env: dict[str, str]) -> str:
    if env.get("RUNWAY_API_KEY"):
        return "Video: Runway gen4.5 is configured (the newest Runway text/image-to-video model the app supports)."
    return "Video: no RUNWAY_API_KEY, so Creative Studio video stays off. Add a Runway key to enable gen4.5."


# ---------------------------------------------------------------------------------------------
# Restart


def restart(env_path: Path) -> int:
    """Recreate the API (and creative worker) with the compose files they were started with."""
    labels = (
        "com.docker.compose.service",
        "com.docker.compose.project.config_files",
        "com.docker.compose.project.working_dir",
    )
    template = "|".join(f'{{{{.Label "{label}"}}}}' for label in labels)
    out = subprocess.run(  # noqa: S603 - fixed argv
        ["docker", "ps", "--format", template],  # noqa: S607 - docker on PATH
        capture_output=True,
        text=True,
        check=False,
    )
    services, files, workdir = [], "", ""
    for line in out.stdout.splitlines():
        service, config_files, working_dir = (line.split("|") + ["", ""])[:3]
        if service == "api" or "worker" in service:
            services.append(service)
            files, workdir = config_files, working_dir
    if not services or not files:
        print("Could not find the running API container; restart it the way you normally do.")
        return 1
    argv = ["docker", "compose"]
    for config_file in files.split(","):
        argv += ["-f", config_file]
    argv += ["up", "-d", "--no-deps", "--force-recreate", *sorted(set(services))]
    print("Running:", " ".join(argv))
    return subprocess.run(argv, cwd=workdir or env_path.parent, check=False).returncode  # noqa: S603


# ---------------------------------------------------------------------------------------------


def plan(env: dict[str, str], call: Http = http, adaptive: bool = False) -> list[Result]:
    results = []
    checks = (lambda e, c: openai_chat(e, c, adaptive), anthropic_chat, gemini_chat, image_model)
    for check in checks:
        result = check(env, call)
        if isinstance(result, list):
            results.extend(result)
        elif result is not None:
            results.append(result)
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--env", type=Path, default=DEFAULT_ENV, help="path to the server .env (default deploy/.env)")
    parser.add_argument("--apply", action="store_true", help="save the new model settings to .env")
    parser.add_argument("--restart", action="store_true", help="with --apply: recreate the API so it uses them")
    args = parser.parse_args(argv)
    if not args.env.is_file():
        print(f"No settings file at {args.env}. Pass --env with the server's .env path.")
        return 2
    env = read_env(args.env)
    print("Checking providers with keys in", args.env, "(keys are not shown)\n")
    adaptive = server_adapts_settings()
    if adaptive:
        print("The API adapts per-model settings (GPT-5.5/5.6/6.x supported); testing models the same way.\n")
    results = plan(env, adaptive=adaptive)
    if not results:
        print("No provider keys found in .env, so there is nothing to upgrade.")
    for result in results:
        mark = "CHANGE" if result.changed else "same  "
        print(f"[{mark}] {result.setting}\n    now: {result.current}\n    new: {result.proposed}")
        for note in result.notes:
            print("     -", note)
    print("\n" + video_note(env))
    changes = {r.setting: r.proposed for r in results if r.changed}
    if not changes:
        print("\nNothing to change.")
        return 0
    if not args.apply:
        print("\nReport only. Run again with --apply --restart to switch.")
        return 0
    backup = write_env(args.env, changes)
    print(f"\nSaved {args.env} (backup: {backup}).")
    if args.restart:
        return restart(args.env)
    print("Restart the API to use the new models, or run again with --restart.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
