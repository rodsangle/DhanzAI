"""Discover app-building models from the existing official OpenAI connection."""

import hashlib
import re
import time

import httpx

_CACHE = {}
_MODEL = re.compile(r"^gpt-(\d+(?:\.\d+)*)(?:-(?:codex|max|mini|nano|\d{4}-\d{2}-\d{2}))*$")


def select_models(ids):
    """Prefer current coding aliases; never invent an ID or include specialty endpoints."""
    candidates = {name for name in ids if isinstance(name, str) and (
        _MODEL.fullmatch(name) or name in {"codex-mini-latest", "gpt-4o", "gpt-4o-mini"}
    )}

    def priority(name):
        match = _MODEL.fullmatch(name)
        version = tuple(int(n) for n in match[1].split('.')) if match else (4, 0) if name.startswith('gpt-4o') else (0,)
        version = (version + (0, 0))[:3]
        small = 2 if 'nano' in name else 1 if 'mini' in name else 0
        snapshot = bool(re.search(r"-\d{4}-\d{2}-\d{2}$", name))
        return ('codex' not in name, tuple(-n for n in version), small, '-max' in name, snapshot, name)

    return sorted(candidates, key=priority)[:30]


async def models(settings):
    from .builder import BuildError

    key = settings.openai_api_key
    if not key or settings.openai_base_url.rstrip('/') != 'https://api.openai.com/v1':
        return []
    cache_key = hashlib.sha256(key.encode()).hexdigest()
    cached = _CACHE.get(cache_key)
    if cached and cached[0] > time.monotonic():
        return list(cached[1])
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
            response = await client.get(
                'https://api.openai.com/v1/models', headers={'Authorization': 'Bearer ' + key}
            )
            response.raise_for_status()
            data = response.json()['data']
            if not isinstance(data, list):
                raise ValueError('Invalid model list')
            ids = select_models([item.get('id') for item in data if isinstance(item, dict)])
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        raise BuildError('App-building model discovery failed. Check OpenAI API access and billing.') from None
    if len(_CACHE) >= 16:
        _CACHE.pop(next(iter(_CACHE)))
    _CACHE[cache_key] = (time.monotonic() + 300, tuple(ids))
    return ids


def install(app=None):
    from . import app_builder_tools, builder

    builder.models = models
    guidance = (
        '\nApp-building model: check build_app models and use the first returned model for new apps or agents '
        'unless the user chooses a different listed model. These are existing OpenAI API models, not a newly '
        'trained Dhanz model. Model listing does not verify quota or successful generation. Provider charges '
        'apply to generation. Report actual job status and never claim tests or deployment without results.'
    )
    if guidance not in app_builder_tools.GUIDANCE:
        app_builder_tools.GUIDANCE += guidance
