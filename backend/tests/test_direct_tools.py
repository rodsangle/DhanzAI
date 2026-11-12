import pytest

from app.services.direct_tools import direct_answer
from tests.conftest import parse_sse


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Calculate 12 * 7", ("calculate", "12 * 7 = 84")),
        ("What is sqrt(144)?", ("calculate", "sqrt(144) = 12")),
        ("convert 100 cm to m", ("convert_units", "100 cm = 1 m")),
        ("calculate 1 / 0", None),
        ("calculate __import__('os')", None),
        ("convert 20 USD to EUR", None),
        ("calculate the total of my spreadsheet", None),
        ("calculate 2+2 and explain why", None),
        ("what is it?", None),
    ],
)
def test_direct_command_scope(text, expected):
    assert direct_answer(text) == expected


def test_direct_reply_needs_no_provider_and_is_persisted(client, auth, provider):
    from dhanz_ai import ProviderError

    provider.fail_with = ProviderError("echo", "Must not call the model", retryable=False)
    headers = auth["headers"]
    conversation = client.post("/api/v1/conversations", headers=headers, json={}).json()
    response = client.post(
        f"/api/v1/conversations/{conversation['id']}/messages",
        headers=headers,
        json={"content": "Calculate 12 * 7"},
    )
    assert response.status_code == 200
    events = parse_sse(response.text)
    assert events[-1]["type"] == "done"
    message = events[-1]["message"]
    assert message["content"] == "12 * 7 = 84"
    assert message["provider"] == "server"
    assert message["model"] == "direct-tools"
    assert message["tool_activity"][0]["tool"] == "calculate"
    assert provider.last_messages == []
    saved = client.get(f"/api/v1/conversations/{conversation['id']}", headers=headers).json()
    assert saved["messages"][-1]["content"] == "12 * 7 = 84"


def test_explicit_model_still_uses_model(client, auth, provider):
    headers = auth["headers"]
    conversation = client.post("/api/v1/conversations", headers=headers, json={}).json()
    response = client.post(
        f"/api/v1/conversations/{conversation['id']}/messages",
        headers=headers,
        json={"content": "Calculate 12 * 7", "provider": "echo", "model": "echo-1"},
    )
    events = parse_sse(response.text)
    assert events[-1]["type"] == "done"
    assert events[-1]["message"]["provider"] == "echo"
    assert provider.last_messages
