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


@pytest.mark.asyncio
async def test_structured_function_submission_becomes_validated_files():
    import json

    def serve(request):
        body = json.loads(request.content)
        assert body["tool_choice"] == {"type": "function", "name": "publish_project"}
        assert body["tools"][0]["strict"] is True
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "output": [
                    {"type": "reasoning", "summary": []},
                    {
                        "type": "function_call",
                        "name": "publish_project",
                        "arguments": json.dumps(
                            {"summary": "Agent ready", "files": [{"path": "agent.py", "content": 'print("Hello")'}]}
                        ),
                    },
                ],
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(serve)) as client:
        files, summary = await builder.generate(
            SimpleNamespace(openai_api_key="test"),
            SimpleNamespace(kind="agent", name="Agent", prompt="Make an agent", model="gpt-5-codex"),
            client=client,
        )
    assert files[0]["path"] == "agent.py" and summary == "Agent ready"


@pytest.mark.parametrize("code", ["insufficient_quota", "model_not_found", "unsupported_parameter", "invalid_api_key"])
def test_provider_errors_are_specific_without_echoing_secrets(code):
    response = httpx.Response(
        400,
        json={"error": {"code": code, "param": "tools", "message": "secret sk-proj-not-for-output and private prompt"}},
    )
    error = builder.failure_message(builder.BuildError(builder.provider_error(response)))
    assert code in error and "HTTP 400" in error
    assert "sk-proj-" not in error and "private prompt" not in error


def test_unknown_provider_error_values_cannot_be_copied_into_feedback():
    response = httpx.Response(500, json={"error": {"code": "sk-proj-private", "param": "private prompt"}})
    assert "sk-proj-private" not in builder.provider_error(response)
    assert "private prompt" not in builder.provider_error(response)
    assert "timed out" in builder.failure_message(TimeoutError())
    assert "redacted" in builder.failure_message(builder.BuildError("key sk-proj-private-value"))


@pytest.mark.asyncio
async def test_token_exhaustion_reports_real_cause_without_publishing_partial_files():
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={
                    "status": "incomplete",
                    "incomplete_details": {"reason": "max_output_tokens"},
                    "output": [{"type": "function_call", "name": "publish_project", "arguments": '{"files":['}],
                },
            )
        )
    ) as client:
        with pytest.raises(builder.BuildError, match="output-token limit"):
            await builder.generate(
                SimpleNamespace(openai_api_key="test"),
                SimpleNamespace(kind="agent", name="Agent", prompt="Make an agent", model="gpt-5-codex"),
                client=client,
            )
