from io import BytesIO
from types import SimpleNamespace
from zipfile import ZipFile

import httpx
import pytest

from app.assistant_studio import builder


def test_project_paths_and_credentials_are_rejected():
    for name in ("../escape.py", "/tmp/x.py", ".env", "node_modules/../bad.js", "C:/bad.py", "script.exe"):
        with pytest.raises(builder.BuildError):
            builder.validate_files([{"path": name, "content": "x"}])
    with pytest.raises(builder.BuildError):
        builder.validate_files([{"path": "a.py", "content": "-----BEGIN PRIVATE KEY-----"}])
    with pytest.raises(builder.BuildError):
        builder.validate_files([{"path": "A.py", "content": "x"}, {"path": "a.py", "content": "y"}])


def test_real_project_zip_contains_files_not_fake_links():
    data = builder.archive(
        [{"path": "agent.py", "content": 'print("Hello")'}, {"path": "README.md", "content": "Run Python locally."}]
    )
    with ZipFile(BytesIO(data)) as archive:
        assert archive.read("agent.py") == b'print("Hello")'
        assert set(archive.namelist()) == {"agent.py", "README.md"}


@pytest.mark.asyncio
async def test_generation_uses_selected_codex_api_model_without_executing_code():
    seen = []

    def serve(request):
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "output": [
                    {
                        "content": [
                            {
                                "type": "output_text",
                                "text": '{"summary":"Agent files","files":[{"path":"agent.py","content":"print(123)"}]}',
                            }
                        ]
                    }
                ],
            },
        )

    settings = SimpleNamespace(openai_api_key="fake-test-value")
    job = SimpleNamespace(kind="agent", name="Agent", prompt="Create an example agent", model="gpt-example-codex")
    async with httpx.AsyncClient(transport=httpx.MockTransport(serve)) as client:
        files, summary = await builder.generate(settings, job, client=client)
    assert files[0]["path"] == "agent.py" and summary == "Agent files"
    assert b"fake-test-value" not in seen[0].content
    assert b"gpt-example-codex" in seen[0].content
    assert str(seen[0].url) == builder.RESPONSES_URL


@pytest.mark.asyncio
async def test_incomplete_provider_output_is_not_claimed_complete():
    job = SimpleNamespace(kind="app", name="App", prompt="Create an app", model="test")
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"status": "incomplete"}))
    ) as client:
        with pytest.raises(builder.BuildError, match="partial project"):
            await builder.generate(SimpleNamespace(openai_api_key="test"), job, client=client)
