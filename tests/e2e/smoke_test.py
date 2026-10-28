"""End-to-end smoke test against a running DHANZ AI API.

    python tests/e2e/smoke_test.py --base-url http://localhost:8000

Exercises registration, login, conversations, streaming chat, search, export and
account deletion. If no AI provider is configured on the server, the chat step
expects the documented "no provider" error event instead of a reply.
"""

from __future__ import annotations

import argparse
import json
import secrets
import sys

import httpx


def sse_events(response: httpx.Response) -> list[dict]:
    events, data = [], []
    for line in response.iter_lines():
        if line.startswith("data: "):
            data.append(line[6:])
        elif line == "" and data:
            events.append(json.loads("\n".join(data)))
            data = []
    if data:
        events.append(json.loads("\n".join(data)))
    return events


def check(condition: bool, label: str) -> None:
    print(("PASS " if condition else "FAIL ") + label)
    if not condition:
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    args = parser.parse_args()
    api = args.base_url.rstrip("/") + "/api/v1"

    with httpx.Client(timeout=120) as c:
        check(c.get(f"{api}/health").json() == {"status": "ok"}, "health")
        ready = c.get(f"{api}/health/ready").json()
        providers = ready.get("providers", [])
        print(f"     configured providers: {providers or 'none'}")

        email = f"smoke-{secrets.token_hex(4)}@example.com"
        password = "Smoke-test-" + secrets.token_hex(4)
        r = c.post(f"{api}/auth/register", json={"email": email, "password": password, "display_name": "Smoke"})
        check(r.status_code == 201, "register")
        r = c.post(f"{api}/auth/login", json={"email": email, "password": password})
        check(r.status_code == 200, "login")
        tokens = r.json()
        h = {"Authorization": f"Bearer {tokens['access_token']}"}

        r = c.post(f"{api}/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
        check(r.status_code == 200, "refresh rotation")
        h = {"Authorization": f"Bearer {r.json()['access_token']}"}

        models = c.get(f"{api}/models", headers=h).json()
        check(models["greeting"].startswith("Hello! I'm Dhanz"), "greeting")

        conv = c.post(f"{api}/conversations", headers=h, json={}).json()
        with c.stream(
            "POST",
            f"{api}/conversations/{conv['id']}/messages",
            headers=h,
            json={"content": "In one sentence, who are you?"},
        ) as resp:
            check(resp.status_code == 200, "send message (SSE)")
            events = sse_events(resp)
        final = events[-1]
        if providers:
            check(final["type"] == "done" and final["message"]["content"].strip() != "", "assistant reply streamed")
            print("     reply:", final["message"]["content"][:200].replace("\n", " "))
        else:
            check(final["type"] == "error" and "No AI provider" in final["detail"], "no-provider error reported")

        found = c.get(f"{api}/conversations", headers=h, params={"q": "who are you"}).json()
        check(found["total"] == 1, "search")
        c.patch(f"{api}/conversations/{conv['id']}", headers=h, json={"pinned": True, "title": "Smoke"})
        md = c.get(f"{api}/conversations/{conv['id']}/export", headers=h)
        check(md.status_code == 200 and "# Smoke" in md.text, "export markdown")

        r = c.request("DELETE", f"{api}/users/me", headers=h, json={"password": password})
        check(r.status_code == 204, "delete account")
        check(c.get(f"{api}/users/me", headers=h).status_code == 401, "token invalid after deletion")
    print("Smoke test passed.")


if __name__ == "__main__":
    main()
