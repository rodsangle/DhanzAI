"""Prepare a derivative of the running API image; never restart production."""

import ast
import hashlib
import json
import subprocess
import textwrap
from pathlib import Path

EXPECTED = "b80a3716a31eba8b1f38d11fa03013cdd7818ec72fed5065fce373253150327a"
PREFIX = """        direct = None
        direct_activity = None
        import os
        if (
            os.getenv("DIRECT_TOOLS_ENABLED", "true").lower() in ("true", "1", "yes")
            and settings.assistant_tools_enabled
            and not turn.attachment_ids and turn.web is not True
            and not turn.routing.explicit_provider and not turn.routing.preferred_model_key
            and not turn.project_instructions and not turn.memories
            and not turn.saved_memory and not turn.memory_off_request
            and not turn.temporary_memory_request and len(turn.question) <= 300
        ):
            from app.services.assistant_tools import evaluate, convert, ToolInputError
            question = turn.question.strip()
            calculation = re.fullmatch(r"(?:calculate|what is)\\s+(.+?)\\??", question, re.I)
            conversion = re.fullmatch(
                r"convert\\s+(-?\\d+(?:\\.\\d+)?)\\s+([\\w°]+)\\s+to\\s+([\\w°]+)\\??", question, re.I
            )
            try:
                if calculation:
                    expression = calculation[1]
                    direct = ("calculate", f"{expression} = {evaluate(expression)}")
                elif conversion:
                    value, source, target = float(conversion[1]), conversion[2], conversion[3]
                    direct = ("convert_units", f"{value:g} {source} = {convert(value, source, target):.10g} {target}")
            except (ToolInputError, TypeError, RecursionError):
                pass
        if direct is not None:
            if await _stop_requested(maker, turn.assistant_message_id):
                outcome = "stopped"
            else:
                tool, text = direct
                provider, model = "server", "direct-tools"
                input_tokens = output_tokens = 0
                yield {"type": "model", "provider": provider, "model": model}
                yield {"type": "tool", "stage": "running", "labels": [ToolBox.label(tool)]}
                direct_activity = [{"tool": tool, "summary": text, "error": False, "action": None}]
                yield {"type": "tool", "stage": "done", "activity": direct_activity}
                parts.append(text)
                yield {"type": "delta", "text": text}
                outcome = "complete"
        else:
"""


def patch_source(source):
    tree = ast.parse(source)
    function = next(
        n
        for n in tree.body
        if isinstance(n, ast.AsyncFunctionDef) and n.name == "run_turn"
    )
    outer = next(n for n in function.body if isinstance(n, ast.Try))
    lines = source.splitlines(keepends=True)
    start, end = outer.body[0].lineno - 1, outer.body[-1].end_lineno
    original = "".join(lines[start:end])
    replacement = PREFIX + textwrap.indent(original, "    ")
    result = "".join(lines[:start]) + replacement + "".join(lines[end:])
    before = "tool_activity=toolbox.activity if toolbox else None,"
    if result.count(before) != 1:
        raise RuntimeError("Unexpected finalizer; no update prepared")
    result = result.replace(
        before,
        "tool_activity=direct_activity or (toolbox.activity if toolbox else None),",
    )
    compile(result, "chat_service.py", "exec")
    return result


def main():
    info = json.loads(
        subprocess.check_output(["sudo", "docker", "inspect", "deploy-api-1"])
    )[0]
    target = "/srv/backend/app/services/chat_service.py"
    for mount in info.get("Mounts", []):
        destination = mount["Destination"].rstrip("/")
        if target == destination or target.startswith(destination + "/"):
            raise RuntimeError(
                "Source is mounted over the image; stop and report this message"
            )
    work = Path.home() / "dhanz-direct-tools-build"
    work.mkdir(mode=0o700, exist_ok=False)
    current = work / "chat_service.py"
    subprocess.run(
        ["sudo", "docker", "cp", "deploy-api-1:" + target, str(current)], check=True
    )
    subprocess.run(
        ["sudo", "chown", f"{work.stat().st_uid}:{work.stat().st_gid}", str(current)], check=True
    )
    source_bytes = current.read_bytes()
    if hashlib.sha256(source_bytes).hexdigest() != EXPECTED:
        raise RuntimeError("Running source changed; no image built")
    source = source_bytes.decode()
    (work / "chat_service.before.py").write_text(source)
    current.write_text(patch_source(source))
    subprocess.run(
        [
            "sudo",
            "docker",
            "image",
            "tag",
            info["Image"],
            "dhanz-api:before-direct-tools",
        ],
        check=True,
    )
    (work / "Dockerfile").write_text(
        "FROM dhanz-api:before-direct-tools\nCOPY chat_service.py " + target + "\n"
    )
    subprocess.run(
        [
            "sudo",
            "docker",
            "build",
            "--network=none",
            "-t",
            "dhanz-api:direct-tools",
            str(work),
        ],
        check=True,
    )
    subprocess.run(
        [
            "sudo",
            "docker",
            "run",
            "--rm",
            "--network=none",
            "--entrypoint",
            "python",
            "dhanz-api:direct-tools",
            "-c",
            "import app.services.chat_service; print('Updated module imports successfully')",
        ],
        check=True,
    )
    overlay = Path.home() / "DhanzAI/deploy/docker-compose.direct-tools.yml"
    if overlay.exists():
        raise RuntimeError("Overlay already exists; inspect it before replacing")
    overlay.write_text("services:\n  api:\n    image: dhanz-api:direct-tools\n")
    print("Prepared image and overlay. Production is still unchanged.")


if __name__ == "__main__":
    main()
