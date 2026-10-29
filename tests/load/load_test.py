"""Load test for a running DHANZ AI API.

    python tests/load/load_test.py --base-url http://localhost:8000 --users 20 --rounds 10
    python tests/load/load_test.py --base-url https://api.example.com --users 5 --rounds 3 --chat

Each virtual user registers, then repeatedly lists conversations, creates one, opens it and
(with --chat) sends a message and reads the streamed reply to the end. Reports throughput and
latency percentiles per operation, and the error count. `--chat` calls the real AI provider
configured on the server and therefore costs money; without it only the API itself is measured.

Raise RATE_LIMIT_AUTH_PER_MINUTE / RATE_LIMIT_CHAT_PER_MINUTE on a test server first, otherwise
you measure the rate limiter. Accounts created by the test are deleted at the end.
"""

from __future__ import annotations

import argparse
import asyncio
import secrets
import statistics
import time
from collections import defaultdict

import httpx

PASSWORD = "Load-test-" + secrets.token_hex(4)


class Stats:
    def __init__(self) -> None:
        self.timings: dict[str, list[float]] = defaultdict(list)
        self.errors: dict[str, int] = defaultdict(int)

    async def measure(self, name: str, call):
        start = time.perf_counter()
        try:
            response = await call()
        except httpx.HTTPError:
            self.errors[name] += 1
            return None
        self.timings[name].append(time.perf_counter() - start)
        if response.status_code >= 400:
            self.errors[name] += 1
            return None
        return response

    def report(self, wall: float) -> None:
        total = sum(len(t) for t in self.timings.values())
        print(f"\n{total} requests in {wall:.1f}s = {total / wall:.1f} req/s")
        print(f"{'operation':<22}{'count':>7}{'p50 ms':>9}{'p95 ms':>9}{'max ms':>9}{'errors':>8}")
        for name, times in sorted(self.timings.items()):
            ordered = sorted(times)
            p95 = ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))]
            print(
                f"{name:<22}{len(times):>7}{statistics.median(times) * 1000:>9.1f}"
                f"{p95 * 1000:>9.1f}{ordered[-1] * 1000:>9.1f}{self.errors[name]:>8}"
            )


async def virtual_user(client: httpx.AsyncClient, api: str, rounds: int, chat: bool, stats: Stats) -> None:
    email = f"load-{secrets.token_hex(6)}@example.com"
    r = await stats.measure(
        "register",
        lambda: client.post(
            f"{api}/auth/register", json={"email": email, "password": PASSWORD, "display_name": "Load"}
        ),
    )
    if r is None:
        return
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    try:
        for i in range(rounds):
            await stats.measure("list conversations", lambda: client.get(f"{api}/conversations", headers=headers))
            r = await stats.measure(
                "create conversation", lambda: client.post(f"{api}/conversations", json={}, headers=headers)
            )
            if r is None:
                continue
            cid = r.json()["id"]
            if chat:

                async def send(cid=cid, i=i):
                    async with client.stream(
                        "POST",
                        f"{api}/conversations/{cid}/messages",
                        json={"content": f"Reply with the single word ok. ({i})", "web": False},
                        headers=headers,
                    ) as resp:
                        async for _ in resp.aiter_bytes():
                            pass  # read the whole stream: the time is "until the reply is complete"
                        return resp

                await stats.measure("chat (full reply)", send)
            await stats.measure(
                "open conversation", lambda cid=cid: client.get(f"{api}/conversations/{cid}", headers=headers)
            )
    finally:
        await client.request("DELETE", f"{api}/users/me", json={"password": PASSWORD}, headers=headers)


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--users", type=int, default=10, help="concurrent virtual users")
    parser.add_argument("--rounds", type=int, default=5, help="iterations per user")
    parser.add_argument("--chat", action="store_true", help="also send chat messages (uses the AI provider)")
    args = parser.parse_args()
    api = args.base_url.rstrip("/") + "/api/v1"
    stats = Stats()
    limits = httpx.Limits(max_connections=args.users * 2)
    async with httpx.AsyncClient(timeout=120, limits=limits) as client:
        start = time.perf_counter()
        await asyncio.gather(*(virtual_user(client, api, args.rounds, args.chat, stats) for _ in range(args.users)))
        wall = time.perf_counter() - start
    stats.report(wall)
    if sum(stats.errors.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
