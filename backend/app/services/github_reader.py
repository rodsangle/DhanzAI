"""Scoped GitHub access, with exact repository allowlisting and bounded output."""

import base64
import binascii
import re
from urllib.parse import quote

import httpx

MAX_FILE_BYTES = 64 * 1024
MAX_RESPONSE_BYTES = 2 * 1024 * 1024


class GitHubReadError(Exception):
    pass


def repository_name(value, allowed):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", value):
        raise GitHubReadError("Use an exact owner/repository name, not a URL.")
    if any(part in (".", "..") for part in value.split("/")):
        raise GitHubReadError("Invalid repository name.")
    names = {item.strip().lower() for item in allowed.split(",") if item.strip()}
    if value.lower() not in names:
        raise GitHubReadError("This repository is not in GITHUB_ALLOWED_REPOSITORIES.")
    return value


async def request_json(settings, endpoint, params=None, *, method="GET", payload=None, missing_ok=False):
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if settings.github_token:
        headers["Authorization"] = f"Bearer {settings.github_token}"
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
            async with client.stream(
                method, "https://api.github.com/repos/" + endpoint, headers=headers, params=params, json=payload
            ) as r:
                if missing_ok and r.status_code == 404:
                    return None
                if r.status_code not in (200, 201):
                    raise GitHubReadError(
                        f"GitHub returned HTTP {r.status_code}. Check repository access, token permissions, "
                        "rate limits and the selected ref. Redirects are not followed."
                    )
                data = bytearray()
                async for chunk in r.aiter_bytes():
                    data.extend(chunk)
                    if len(data) > MAX_RESPONSE_BYTES:
                        raise GitHubReadError("GitHub response is too large; select a smaller directory.")
                import json

                return json.loads(data)
    except (httpx.HTTPError, ValueError) as exc:
        raise GitHubReadError("GitHub could not be read. Check network access and try again.") from exc


async def read_repository(settings, args, *, file=False):
    repo = repository_name(args.get("repository"), settings.github_allowed_repositories)
    path, ref = args.get("path", ""), args.get("ref", "")
    if not isinstance(path, str) or len(path) > 500 or path.startswith("/") or "\\" in path:
        raise GitHubReadError("Use a relative repository path.")
    if any(part in (".", "..", "") for part in path.split("/")) and path:
        raise GitHubReadError("Path must not contain empty, dot or parent segments.")
    if not isinstance(ref, str) or len(ref) > 200:
        raise GitHubReadError("Invalid branch, tag or commit ref.")
    endpoint = repo + "/contents" + ("/" + quote(path, safe="/") if path else "")
    data = await request_json(settings, endpoint, {"ref": ref} if ref else {})
    if not file:
        if not isinstance(data, list):
            raise GitHubReadError("This path is a file; use github_read_file instead.")
        return {
            "repository": repo,
            "path": path,
            "ref": ref or "default branch",
            "entries": [
                {"path": item.get("path"), "type": item.get("type"), "size": item.get("size")} for item in data[:200]
            ],
            "truncated": len(data) > 200,
            "note": "GitHub contents listings are limited to 1000 entries; this is not a recursive tree.",
        }
    if not isinstance(data, dict) or data.get("type") != "file" or data.get("encoding") != "base64":
        raise GitHubReadError("Only ordinary UTF-8 text files can be read; no symlinks or submodules.")
    if data.get("target") or data.get("submodule_git_url") or data.get("size", MAX_FILE_BYTES + 1) > MAX_FILE_BYTES:
        raise GitHubReadError("File is not an ordinary text file, or exceeds 64 KiB.")
    try:
        raw = base64.b64decode("".join(data["content"].split()), validate=True)
        if len(raw) > MAX_FILE_BYTES or b"\x00" in raw:
            raise ValueError("Not a bounded text file")
        text = raw.decode("utf-8")
    except (KeyError, ValueError, binascii.Error) as exc:
        raise GitHubReadError("File is not readable UTF-8 text.") from exc
    return {
        "repository": repo,
        "path": path,
        "ref": ref or "default branch",
        "blob_sha": data.get("sha"),
        "content": text,
        "untrusted_repository_content": True,
    }


def branch_name(value):
    if (
        not isinstance(value, str)
        or not re.fullmatch(r"dhanz/[A-Za-z0-9][A-Za-z0-9_/-]{0,100}", value)
        or value.endswith("/")
        or "//" in value
    ):
        raise GitHubReadError("Use a branch name such as dhanz/fix-login (no dots or spaces).")
    return value


def bounded_text(value, name, limit):
    if not isinstance(value, str) or not value.strip() or len(value.encode()) > limit:
        raise GitHubReadError(f"{name} must be nonempty text within {limit} bytes.")
    return value


async def change_repository(settings, args, action):
    if not settings.github_write_enabled or not settings.github_token:
        raise GitHubReadError("GitHub writes require GITHUB_WRITE_ENABLED=true and a scoped GITHUB_TOKEN.")
    repo = repository_name(args.get("repository"), settings.github_allowed_repositories)
    branch = branch_name(args.get("branch"))
    metadata = await request_json(settings, repo)
    default = metadata["default_branch"]
    if branch == default:
        raise GitHubReadError("The default branch cannot be modified by these tools.")
    if action == "branch":
        base = args.get("base") or default
        bounded_text(base, "Base branch", 200)
        ref = await request_json(settings, repo + "/git/ref/heads/" + quote(base, safe=""))
        result = await request_json(
            settings,
            repo + "/git/refs",
            method="POST",
            payload={
                "ref": "refs/heads/" + branch,
                "sha": ref["object"]["sha"],
            },
        )
        return {"repository": repo, "branch": branch, "commit": result["object"]["sha"]}
    if action == "file":
        path = bounded_text(args.get("path"), "Path", 500)
        if path.startswith("/") or "\\" in path or any(part in ("", ".", "..") for part in path.split("/")):
            raise GitHubReadError("Use a relative path without dot or empty segments.")
        content = args.get("content")
        if not isinstance(content, str) or len(content.encode()) > MAX_FILE_BYTES or "\x00" in content:
            raise GitHubReadError("Content must be UTF-8 text of at most 64 KiB.")
        expected = args.get("expected_sha")
        if not isinstance(expected, str) or (expected and not re.fullmatch(r"[0-9a-f]{40}", expected)):
            raise GitHubReadError("Supply the blob SHA from github_read_file, or empty text only for a new file.")
        # Verify the branch exists; a new file must not implicitly create a branch.
        await request_json(settings, repo + "/git/ref/heads/" + quote(branch, safe=""))
        endpoint = repo + "/contents/" + quote(path, safe="/")
        current = await request_json(settings, endpoint, {"ref": branch}, missing_ok=True)
        if current is None:
            if expected:
                raise GitHubReadError("File no longer exists; read the branch again before editing.")
        elif current.get("type") != "file" or current.get("target") or current.get("submodule_git_url"):
            raise GitHubReadError("Only ordinary files can be edited.")
        elif not expected or current.get("sha") != expected:
            raise GitHubReadError("File changed or expected_sha is missing. Read it again before editing.")
        payload = {
            "branch": branch,
            "message": bounded_text(args.get("message"), "Commit message", 200),
            "content": base64.b64encode(content.encode()).decode(),
        }
        if expected:
            payload["sha"] = expected
        result = await request_json(settings, endpoint, method="PUT", payload=payload)
        return {
            "repository": repo,
            "branch": branch,
            "path": path,
            "blob_sha": result["content"]["sha"],
            "commit": result["commit"]["sha"],
        }
    if action == "pull_request":
        title = bounded_text(args.get("title"), "PR title", 200)
        body = bounded_text(args.get("body"), "PR description", 12000)
        result = await request_json(
            settings,
            repo + "/pulls",
            method="POST",
            payload={
                "head": branch,
                "base": default,
                "title": title,
                "body": body,
                "draft": True,
            },
        )
        return {"repository": repo, "number": result["number"], "url": result["html_url"], "draft": True}
    raise GitHubReadError("Unknown GitHub action.")
