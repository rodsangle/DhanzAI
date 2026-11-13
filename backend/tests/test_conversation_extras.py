"""Branch, archive and share conversations."""

from tests.test_chat import new_conv, send


def chat(client, auth, *prompts):
    cid = new_conv(client, auth)
    for prompt in prompts:
        r, _ = send(client, auth, cid, prompt)
        assert r.status_code == 200
    return cid


def messages(client, auth, cid):
    return client.get(f"/api/v1/conversations/{cid}", headers=auth["headers"]).json()["messages"]


def other_user(client):
    r = client.post(
        "/api/v1/auth/register",
        json={"email": "eve@example.com", "password": "correct-horse-9", "display_name": "Eve"},
    )
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_branch_copies_messages_up_to_the_chosen_reply(client, auth):
    cid = chat(client, auth, "first question", "second question")
    original = messages(client, auth, cid)
    assert [m["role"] for m in original] == ["user", "assistant", "user", "assistant"]

    r = client.post(
        f"/api/v1/conversation-extras/{cid}/branch", headers=auth["headers"], json={"message_id": original[1]["id"]}
    )
    assert r.status_code == 201, r.text
    branch_id = r.json()["id"]
    assert r.json()["title"].startswith("Branch · ")
    copied = messages(client, auth, branch_id)
    assert [(m["role"], m["content"]) for m in copied] == [(m["role"], m["content"]) for m in original[:2]]
    assert messages(client, auth, cid) == original  # the original chat is untouched

    r, events = send(client, auth, branch_id, "continue here")  # the branch is a normal chat
    assert r.status_code == 200 and len(messages(client, auth, branch_id)) == 4


def test_branch_and_share_are_owner_only_and_refuse_temporary_chats(client, auth):
    cid = chat(client, auth, "hello")
    first = messages(client, auth, cid)[0]["id"]
    eve = other_user(client)
    assert (
        client.post(f"/api/v1/conversation-extras/{cid}/branch", headers=eve, json={"message_id": first}).status_code
        == 404
    )
    assert client.post(f"/api/v1/conversation-extras/{cid}/share", headers=eve).status_code == 404
    assert client.put(f"/api/v1/conversation-extras/{cid}/archive", headers=eve).status_code == 404

    temp = new_conv(client, auth, temporary=True)
    send(client, auth, temp, "secret")
    temp_first = messages(client, auth, temp)[0]["id"]
    assert (
        client.post(
            f"/api/v1/conversation-extras/{temp}/branch", headers=auth["headers"], json={"message_id": temp_first}
        ).status_code
        == 400
    )
    assert client.post(f"/api/v1/conversation-extras/{temp}/share", headers=auth["headers"]).status_code == 400


def test_archive_and_restore(client, auth):
    cid = chat(client, auth, "keep me")
    h = auth["headers"]
    assert client.get("/api/v1/conversation-extras/archived", headers=h).json() == []
    assert client.put(f"/api/v1/conversation-extras/{cid}/archive", headers=h).status_code == 204
    assert client.put(f"/api/v1/conversation-extras/{cid}/archive", headers=h).status_code == 204  # idempotent
    archived = client.get("/api/v1/conversation-extras/archived", headers=h).json()
    assert [a["id"] for a in archived] == [cid] and archived[0]["title"]
    assert client.get(f"/api/v1/conversations/{cid}", headers=h).status_code == 200  # still readable
    assert client.delete(f"/api/v1/conversation-extras/{cid}/archive", headers=h).status_code == 204
    assert client.get("/api/v1/conversation-extras/archived", headers=h).json() == []


def test_share_is_a_frozen_public_snapshot_without_private_details(client, auth):
    cid = chat(client, auth, "what is pgvector?")
    h = auth["headers"]
    r = client.post(f"/api/v1/conversation-extras/{cid}/share", headers=h)
    assert r.status_code == 201, r.text
    token = r.json()["token"]
    assert len(token) >= 32 and r.json()["message_count"] == 2

    send(client, auth, cid, "a later private question")
    public = client.get(f"/api/v1/shared/{token}")  # no sign-in
    assert public.status_code == 200
    body = public.json()
    assert [m["role"] for m in body["messages"]] == ["user", "assistant"]  # later messages are not shared
    text = public.text
    assert "a later private question" not in text
    for private in ("ada@example.com", "Ada", "attachments", "tool_activity", "user_id", "input_tokens"):
        assert private not in text
    assert set(body["messages"][1]) == {"role", "content", "model", "sources", "created_at"}

    listed = client.get("/api/v1/conversation-extras/shares", headers=h).json()
    assert [s["token"] for s in listed] == [token]
    assert client.delete(f"/api/v1/conversation-extras/shares/{token}", headers=other_user(client)).status_code == 404
    assert client.delete(f"/api/v1/conversation-extras/shares/{token}", headers=h).status_code == 204
    assert client.get(f"/api/v1/shared/{token}").status_code == 404
    assert client.get("/api/v1/shared/not-a-real-token-at-all-000").status_code == 404


def test_deleting_the_chat_removes_its_shares_and_archive_mark(client, auth):
    cid = chat(client, auth, "short lived")
    h = auth["headers"]
    token = client.post(f"/api/v1/conversation-extras/{cid}/share", headers=h).json()["token"]
    client.put(f"/api/v1/conversation-extras/{cid}/archive", headers=h)
    assert client.delete(f"/api/v1/conversations/{cid}", headers=h).status_code == 204
    assert client.get(f"/api/v1/shared/{token}").status_code == 404
    assert client.get("/api/v1/conversation-extras/shares", headers=h).json() == []
    assert client.get("/api/v1/conversation-extras/archived", headers=h).json() == []


def test_nothing_to_share_yet(client, auth):
    cid = new_conv(client, auth)
    assert client.post(f"/api/v1/conversation-extras/{cid}/share", headers=auth["headers"]).status_code == 400
