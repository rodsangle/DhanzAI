"""Bounded file-generation jobs. Never executes model-produced code or host commands."""

import asyncio
import io
import json
import re
import time
from datetime import timedelta
from pathlib import PurePosixPath
from zipfile import ZIP_DEFLATED, ZipFile

import httpx
from sqlalchemy import or_, select, update

from app.db.base import utcnow

from .models import BuilderLease, BuilderProject

MODEL_URL = "https://api.openai.com/v1/models"
RESPONSES_URL = "https://api.openai.com/v1/responses"
_catalog = {}
ALLOWED = {
    ".html",
    ".css",
    ".js",
    ".mjs",
    ".ts",
    ".tsx",
    ".jsx",
    ".json",
    ".py",
    ".md",
    ".txt",
    ".toml",
    ".yaml",
    ".yml",
    ".svg",
}


class BuildError(ValueError):
    pass


async def models(settings):
    if not settings.openai_api_key or settings.openai_base_url.rstrip("/") != "https://api.openai.com/v1":
        return []
    cached = _catalog.get("value")
    if cached and cached[0] > time.monotonic():
        return cached[1]
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
            response = await client.get(MODEL_URL, headers={"Authorization": "Bearer " + settings.openai_api_key})
            response.raise_for_status()
            ids = [item["id"] for item in response.json().get("data", []) if isinstance(item.get("id"), str)]
    except (httpx.HTTPError, ValueError, KeyError):
        raise BuildError(
            "OpenAI model discovery failed. Check the configured API key, account access and network."
        ) from None
    ids = [m for m in ids if "codex" in m or m in {"gpt-4.1-mini", "gpt-4.1", "gpt-4o", "gpt-4o-mini"}]
    ids = sorted(set(ids), key=lambda s: ("codex" not in s, s))[:30]
    _catalog["value"] = (time.monotonic() + 300, ids)
    return ids


def validate_files(raw):
    if not isinstance(raw, list) or not 1 <= len(raw) <= 32:
        raise BuildError("The model must return 1–32 project files.")
    result = []
    seen = set()
    total = 0
    for item in raw:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("path"), str)
            or not isinstance(item.get("content"), str)
        ):
            raise BuildError("A generated file is invalid.")
        name = item["path"]
        path = PurePosixPath(name)
        if (
            len(name) > 160
            or path.is_absolute()
            or ".." in path.parts
            or "\\" in name
            or ":" in name
            or any(part.startswith(".") for part in path.parts)
            or path.suffix.lower() not in ALLOWED
            or path.as_posix() != name
            or name.casefold() in seen
        ):
            raise BuildError("A generated file path is unsafe or unsupported.")
        content = item["content"]
        size = len(content.encode("utf-8"))
        total += size
        if size > 150000 or total > 600000 or "\x00" in content:
            raise BuildError("Generated code exceeds the project size limit.")
        if re.search(r"sk-(?:proj-|ant-)[A-Za-z0-9_-]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY", content):
            raise BuildError("The generated project contains apparent credentials and was not saved.")
        seen.add(name.casefold())
        result.append({"path": name, "content": content})
    return result


async def generate(settings, job, *, client=None):
    if not settings.openai_api_key:
        raise BuildError("An OpenAI API connection is required.")
    if client is None:
        async with httpx.AsyncClient(timeout=180, follow_redirects=False) as owned:
            return await generate(settings, job, client=owned)
    instructions = (
        "Create a real downloadable project, not a description. Return only JSON with keys summary and files; "
        "files is an array of objects with path and content. At most 32 files/600KB total. Never include actual credentials, "
        "private keys or user tokens; use environment-variable placeholders and explain setup in README.md. "
        "Never claim deployment or tests were run. For an app include a usable static index.html, local CSS/JS for a sandboxed "
        "preview; clearly document server-dependent features. For an agent include runnable Python source and requirements.txt, "
        "with explicit user control over external actions. Do not include dotfiles. No shell execution is available here."
    )
    response = await client.post(
        RESPONSES_URL,
        headers={"Authorization": "Bearer " + settings.openai_api_key},
        json={
            "model": job.model,
            "instructions": instructions,
            "input": f"Project type: {job.kind}\nName: {job.name}\nTask: {job.prompt}",
            "max_output_tokens": 12000,
            "store": False,
        },
    )
    if response.status_code >= 400:
        raise BuildError(
            f"The selected model could not build this project (HTTP {response.status_code}). Check model access and API quota."
        )
    if len(response.content) > 2000000:
        raise BuildError("The model response exceeded the safe limit.")
    data = response.json()
    if data.get("status") not in {None, "completed"}:
        raise BuildError("The model did not finish; no partial project was published.")
    text = "".join(
        p.get("text", "")
        for output in data.get("output", [])
        for p in output.get("content", [])
        if p.get("type") == "output_text"
    )
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        parsed = json.loads(text)
    except ValueError:
        raise BuildError("The model did not return a valid project. No files were published.") from None
    if not isinstance(parsed, dict):
        raise BuildError("The model did not return a project object.")
    files = validate_files(parsed.get("files"))
    if job.kind == "app" and not any(f["path"] == "index.html" for f in files):
        raise BuildError("The generated app has no index.html.")
    if job.kind == "agent" and not any(f["path"].endswith(".py") for f in files):
        raise BuildError("The generated agent has no Python source.")
    return files, str(parsed.get("summary") or "Project files generated.")[:3000]


def archive(files):
    output = io.BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as zipped:
        for file in validate_files(files):
            zipped.writestr(file["path"], file["content"])
    return output.getvalue()


async def claim(maker):
    now = utcnow()
    async with maker() as db:
        # Compare-and-update lease serializes claims across all API workers.
        acquired = await db.execute(
            update(BuilderLease)
            .where(BuilderLease.id == 1, or_(BuilderLease.expires_at.is_(None), BuilderLease.expires_at < now))
            .values(expires_at=now + timedelta(minutes=5))
        )
        if acquired.rowcount != 1:
            await db.rollback()
            return None
        await db.execute(
            update(BuilderProject)
            .where(BuilderProject.status == "running", BuilderProject.updated_at < now - timedelta(minutes=5))
            .values(
                status="failed",
                error="Build was interrupted. Start another build explicitly; it was not automatically replayed.",
            )
        )
        job = await db.scalar(
            select(BuilderProject).where(BuilderProject.status == "queued").order_by(BuilderProject.created_at).limit(1)
        )
        if job is None:
            await db.execute(update(BuilderLease).where(BuilderLease.id == 1).values(expires_at=None, job_id=None))
            await db.commit()
            return None
        job.status = "running"
        job.updated_at = now
        await db.execute(update(BuilderLease).where(BuilderLease.id == 1).values(job_id=job.id))
        await db.commit()
        return job


async def worker(maker, settings):
    while True:
        try:
            job = await claim(maker)
        except Exception:
            await asyncio.sleep(5)
            continue
        if job is None:
            await asyncio.sleep(3)
            continue
        try:
            from app.models import User

            async with maker() as db:
                user = await db.get(User, job.user_id)
                if user is None or not user.is_active or user.routing_policy == "local_only":
                    raise BuildError("External generation is disabled for this account.")
            files, summary = await asyncio.wait_for(generate(settings, job), timeout=210)
            values = {"files": files, "summary": summary, "status": "complete", "error": None}
        except Exception:
            values = {
                "status": "failed",
                "error": "The provider did not produce a valid complete project. Check model access, quota or retry explicitly.",
            }
        try:
            async with maker() as db:
                await db.execute(
                    update(BuilderProject)
                    .where(BuilderProject.id == job.id, BuilderProject.status == "running")
                    .values(**values, updated_at=utcnow())
                )
                await db.execute(
                    update(BuilderLease)
                    .where(BuilderLease.id == 1, BuilderLease.job_id == job.id)
                    .values(expires_at=None, job_id=None)
                )
                await db.commit()
        except Exception:
            await asyncio.sleep(5)
