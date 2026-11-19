# Adapter tests: real app code path → official Anthropic SDK / Images API call → stand-in server.
import json, time, threading, urllib.request, http.cookiejar, base64, io
A, B = "http://localhost:3100", "http://localhost:3101"
MOCK_BASE = "http://localhost:4010"
LOG = "/tmp/mock-requests.jsonl"
res = []
def check(n, ok, d=""):
    res.append(ok); print(("PASS " if ok else "FAIL ") + n + ("" if ok else f" :: {d}"), flush=True)

jar = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
def call(base, method, path, body=None, raw=None, ctype="application/json", headers=None):
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    h = {"Content-Type": ctype} if data is not None else {}
    h.update(headers or {})
    r = urllib.request.Request(base + path, data=data, method=method, headers=h)
    try:
        with op.open(r, timeout=60) as f: return f.status, f.read()
    except urllib.error.HTTPError as e: return e.code, e.read()
def sse(base, path, body=None, until=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(base + path, data=data, method="POST" if body is not None else "GET", headers={"Content-Type": "application/json"})
    evs = []
    with op.open(r, timeout=120) as f:
        buf = b""
        while True:
            ch = f.read(1)
            if not ch: break
            buf += ch
            if buf.endswith(b"\n\n"):
                line = [l for l in buf.decode().split("\n") if l.startswith("data: ")]
                buf = b""
                if line:
                    e = json.loads(line[0][6:]); evs.append(e)
                    if until and until(e, evs): break
    return evs
def logs(): return [json.loads(l) for l in open(LOG) if l.strip()]
def text_of(evs): return "".join(e.get("text", "") for e in evs if e["type"] == "delta") or next((e["text"] for e in evs if e["type"] == "snapshot"), "")

call(A, "POST", "/api/auth/dev-login", {"email": "dante@rodrech.com"})
# copy the dev cookie for instance B (same host, different port: cookie jar keys by host so it's shared)
projects = json.loads(call(A, "GET", "/api/projects")[1])
fw26 = next(p for p in projects if p["name"] == "FW26 drop")

# --- uploads: png, pdf, txt
def upload(name, mime, data):
    s, b = call(A, "POST", "/api/files", {"name": name, "mime": mime, "bytes": len(data)})
    j = json.loads(b); assert s == 200, b
    s2, _ = call(A, "PUT", j["upload_url"], raw=data, ctype=mime)
    s3, b3 = call(A, "POST", f"/api/files/{j['file']['id']}/complete")
    return json.loads(b3)
png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
pdf = open(__import__("os").path.join(__import__("os").path.dirname(__file__), "../../e2e/files/fw26-tech-pack.pdf"), "rb").read()
f_png = upload("moodboard.png", "image/png", png)
f_pdf = upload("brief.pdf", "application/pdf", pdf)
f_txt = upload("notes.txt", "text/plain", b"Drop is Friday noon. Lowercase captions only.")
check("uploads complete, text is extracted and counted, but not sent back to the browser",
      all(f["status"] == "ready" for f in (f_png, f_pdf, f_txt)) and (f_txt.get("token_count") or 0) > 0 and (f_pdf.get("token_count") or 0) > 0
      and "extracted_text" not in f_txt and "extracted_text" not in f_pdf, str([f_png, f_pdf, f_txt])[:300])
proj_file = upload("brand-guide.md", "text/markdown", b"# Brand guide\nNever use the word 'swag'.")
call(A, "POST", f"/api/projects/{fw26['id']}/files", {"file_id": proj_file["id"]})

# --- 1. streamed answer through the SDK
open(LOG, "w").close()
evs = sse(A, "/api/chat", {"project_id": fw26["id"], "text": "Write captions for the drop", "file_ids": [f_png["id"], f_pdf["id"], f_txt["id"]], "model": "claude-sonnet-5-5"})
meta = evs[0]; done = evs[-1]
txt = text_of(evs)
check("answer streams through the Anthropic SDK and completes", done.get("type") == "done" and done.get("status") == "complete" and txt.startswith("Mock answer from the stand-in API."), json.dumps(evs[-2:])[:300])
check("thinking deltas are not shown to the user", "internal reasoning" not in txt)
reqs = [l for l in logs() if l["path"].startswith("/v1/messages")]
stream_req = next(r for r in reqs if r["body"].get("stream"))
bdy = stream_req["body"]
check("request uses the chosen model and no sampling params", bdy["model"] == "claude-sonnet-5-5" and not any(k in bdy for k in ("temperature", "top_p", "top_k")), json.dumps({k: bdy[k] for k in bdy if k != "messages" and k != "system"}))
hdr = stream_req["headers"]
check("API key and anthropic-version header sent by the SDK", (hdr.get("x-api-key") == "sk-ant-test" or hdr.get("authorization") == "Bearer sk-ant-test") and bool(hdr.get("anthropic-version")), str(hdr)[:200])
sys0 = bdy["system"][0]
check("system prompt is cached and carries project instructions + project file", sys0.get("cache_control") == {"type": "ephemeral"} and "Write captions in lowercase" in sys0["text"] and "Never use the word 'swag'" in sys0["text"] and "About the person" in sys0["text"])
content = bdy["messages"][-1]["content"]
kinds = [(c["type"], c.get("source", {}).get("type"), c.get("source", {}).get("media_type")) for c in content]
check("attachments sent as image / PDF document / text document blocks", kinds[:3] == [("image", "base64", "image/png"), ("document", "base64", "application/pdf"), ("document", "text", "text/plain")] and content[-1] == {"type": "text", "text": "Write captions for the drop"}, str(kinds))
conv = meta["conversation_id"]
time.sleep(0.5)
detail = json.loads(call(A, "GET", f"/api/conversations/{conv}")[1])
check("title written by the title model", detail["conversation"]["title"] == "Mock Title Here", detail["conversation"]["title"])
title_req = next((r for r in reqs if not r["body"].get("stream")), None)
check("title request uses Haiku with a small max_tokens", title_req and title_req["body"]["model"] == "claude-haiku-5-5" and title_req["body"]["max_tokens"] <= 50)

# --- 2. follow-up: alternating history
open(LOG, "w").close()
sse(A, "/api/chat", {"conversation_id": conv, "text": "Shorter please", "model": "claude-sonnet-5-5"})
msgs = next(l for l in logs() if l["body"].get("stream"))["body"]["messages"]
roles = [m["role"] for m in msgs]
check("history alternates user/assistant and ends with the new message", roles == ["user", "assistant", "user"] and "Attached earlier: moodboard.png, brief.pdf, notes.txt" in msgs[0]["content"], str(roles) + " " + str(msgs[0]["content"])[:160])

# --- 3. usage recorded with tokens
# (checked in SQL below)

# --- 4. stop from ANOTHER instance; resume stream on ANOTHER instance
holder = {}
def start_slow():
    holder["evs"] = sse(A, "/api/chat", {"conversation_id": conv, "text": "SLOW long answer please", "model": "claude-sonnet-5-5"})
t = threading.Thread(target=start_slow); t.start()
time.sleep(1.5)
d = json.loads(call(A, "GET", f"/api/conversations/{conv}")[1])
streaming = [m for m in d["messages"] if m["status"] == "streaming"]
mid = streaming[0]["id"] if streaming else None
resumed = {}
def resume_b():
    resumed["evs"] = sse(B, f"/api/messages/{mid}/stream")
t2 = threading.Thread(target=resume_b); t2.start()
time.sleep(2.0)
s, b = call(B, "POST", f"/api/messages/{mid}/stop")
t.join(30); t2.join(30)
row = json.loads(call(A, "GET", f"/api/messages/{mid}")[1])
check("Stop pressed on instance B stops a generation running on instance A", row["status"] == "stopped" and 0 < len(row["text"]) < 400, f"{row['status']} {len(row['text'])}")
rev = resumed.get("evs", [])
check("instance B followed the live answer (polling path) and saw it end", any(e["type"] == "delta" for e in rev) and rev and rev[-1].get("status") == "stopped", json.dumps(rev[-2:])[:200])

# --- 5. overloaded API → friendly retryable error
evs = sse(A, "/api/chat", {"conversation_id": conv, "text": "MOCK_ERROR_529 please", "model": "claude-sonnet-5-5"})
check("API overload becomes a friendly error", evs[-1].get("status") == "error" and "busy" in (evs[-1].get("error") or ""), json.dumps(evs[-1]))

# --- 6. images
evs = sse(A, "/api/chat", {"text": "a bone fitted cap on a plinth", "tools": {"image": True}})
img = next((e for e in evs if e["type"] == "content"), None)
fid = next((b["file_id"] for b in (img or {}).get("content", []) if b["type"] == "image"), None)
s, data = call(A, "GET", f"/api/files/{fid}/download?inline=1") if fid else (0, b"")
check("image request goes to the Images API and saves a PNG", evs[-1].get("status") == "complete" and s == 200 and data[:4] == b"\x89PNG", f"{evs[-1]} {s}")
ireq = next(l for l in logs() if l["path"].startswith("/v1/images"))
check("image request carries the model, prompt and bearer key", ireq["body"]["prompt"] == "a bone fitted cap on a plinth" and ireq["body"]["model"] and ireq["headers"]["authorization"] == "Bearer sk-test")
evs = sse(A, "/api/chat", {"text": "BLOCKME cap", "tools": {"image": True}})
check("image refusal shows the 'declined' message", evs[-1].get("status") == "error" and "declined" in (evs[-1].get("error") or ""), json.dumps(evs[-1]))

# --- 6b. web search: tool offered, citations become [n] links + web sources, pause_turn continues, org-disabled falls back
open(LOG, "w").close()
evs = sse(A, "/api/chat", {"text": "MOCK_SEARCH what's trending in fitted caps", "model": "claude-sonnet-5-5"})
txt = text_of(evs)
content_ev = [e for e in evs if e["type"] == "content"]
srcs = next((b["items"] for b in (content_ev[-1]["content"] if content_ev else []) if b["type"] == "sources"), [])
sreq = next(l for l in logs() if l["body"].get("stream"))["body"]
check("web search tool offered with max_uses", any(t.get("type") == "web_search_20250305" and t.get("name") == "web_search" and t.get("max_uses") == 5 for t in sreq.get("tools", [])), str(sreq.get("tools")))
check("search status shown with the query", any(e["type"] == "status" and e["text"] == "Searching the web: fitted cap trends" for e in evs), str([e for e in evs if e["type"] == "status"]))
check("cited text gets numbered links after it, in source order",
      "Fitted caps are trending again [[1]](https://news.example.org/caps), and deep crowns sell best [[2]](https://shop.example.net/fitted) [[1]](https://news.example.org/caps)" in txt, txt)
check("cited pages listed first as web sources, in the same order",
      [(x["kind"], x.get("url")) for x in srcs][:2] == [("web", "https://news.example.org/caps"), ("web", "https://shop.example.net/fitted")], str(srcs))
import subprocess
subprocess.run(["psql", "-h", "/tmp", "-p", "5499", "-U", "postgres", "rodrech", "-qc", "update memory_summaries set refreshed_at = now() - interval '2 hours'"], check=True)
open(LOG, "w").close()
s_mem, b_mem = call(A, "POST", "/api/memory/refresh")
mreq = next((l["body"] for l in logs() if not l["body"].get("stream") and "short memory" in json.dumps(l["body"].get("system", ""))), None)
check("memory refresh returns the summarizer's bullets", s_mem == 200 and json.loads(b_mem)["body"] == "- Mock memory: runs RODRECH drops.", f"{s_mem} {b_mem[:120]}")
check("memory refresh uses Haiku and sends only the person's own messages",
      mreq is not None and mreq["model"] == "claude-haiku-5-5" and "Fitted caps are trending" not in json.dumps(mreq["messages"]) and "MOCK_SEARCH" in json.dumps(mreq["messages"]), str(mreq)[:200])
open(LOG, "w").close()
evs = sse(A, "/api/chat", {"text": "MOCK_PAUSE fitted caps", "model": "claude-sonnet-5-5"})
calls = [l["body"] for l in logs() if l["body"].get("stream")]
cont = calls[1]["messages"][-1] if len(calls) > 1 else {}
check("pause_turn: the paused content is sent back unchanged and the answer completes",
      len(calls) == 2 and cont.get("role") == "assistant" and any(b.get("type") == "web_search_tool_result" and b["content"][0].get("encrypted_content") == "ENC1" for b in cont.get("content", []))
      and evs[-1].get("status") == "complete" and "deep crowns sell best" in text_of(evs), f"{len(calls)} {json.dumps(evs[-1])}")
open(LOG, "w").close()
evs = sse(A, "/api/chat", {"text": "MOCK_NOSEARCH_ORG hello", "model": "claude-sonnet-5-5"})
calls = [l["body"] for l in logs() if l["body"].get("stream")]
check("search disabled for the org: retried without the tool and answered",
      len(calls) == 2 and "tools" not in calls[1] and evs[-1].get("status") == "complete" and text_of(evs).startswith("Mock answer"), f"{len(calls)} {json.dumps(evs[-1])}")

# --- 6c. app actions through Claude tool use: tool offered, tool_use runs against Slack, tool_result goes back, answer completes
urllib.request.urlopen(urllib.request.Request(f"{MOCK_BASE}/__reset", method="POST")).read()
s_c, _ = call(A, "GET", "/api/apps/slack/connect")
apps = json.loads(call(A, "GET", "/api/apps")[1])
check("Slack connects through OAuth against the stand-in", next(a for a in apps if a["id"] == "slack")["connection"]["status"] == "active", str(apps)[:300])
open(LOG, "w").close()
evs = sse(A, "/api/chat", {"text": "MOCK_TOOL @Slack when is the drop?", "model": "claude-sonnet-5-5"})
calls = [l["body"] for l in logs() if l["body"].get("stream")]
first_tools = {t.get("name") for t in calls[0].get("tools", [])} if calls else set()
check("connected app's actions offered as tools (with the web search tool)", {"slack_search", "slack_read_channel", "slack_post_message", "web_search"} <= first_tools, str(first_tools))
tr = calls[1]["messages"][-1]["content"][0] if len(calls) > 1 else {}
check("tool_use runs against Slack and the result goes back as tool_result",
      len(calls) == 2 and calls[1]["messages"][-2]["role"] == "assistant" and any(b.get("type") == "tool_use" and b.get("input") == {"query": "drop date"} for b in calls[1]["messages"][-2]["content"])
      and tr.get("type") == "tool_result" and tr.get("tool_use_id") == "toolu_mock1" and "Friday noon" in tr.get("content", ""), json.dumps(tr)[:300])
content_ev = [e for e in evs if e["type"] == "content"]
act = next((b["items"] for b in (content_ev[-1]["content"] if content_ev else []) if b["type"] == "tool_activity"), [])
check("answer completes after the app action, with an activity line", evs[-1].get("status") == "complete" and "Friday noon" in text_of(evs) and act and act[0]["text"].startswith("Searched Slack"), f"{json.dumps(evs[-1])} {act}")

# --- 7. cron auth
s1, _ = call(A, "GET", "/api/cron/sweep")
s2, b2 = call(A, "GET", "/api/cron/sweep", headers={"Authorization": "Bearer local-test-secret"})
s3, b3 = call(A, "GET", "/api/cron/purge", headers={"Authorization": "Bearer local-test-secret"})
check("cron routes refuse without the secret and run with it", s1 == 401 and s2 == 200 and s3 == 200, f"{s1} {s2} {s3} {b3[:100]}")

# --- 8. validation & ids
s, b = call(A, "PATCH", "/api/conversations/not-a-uuid", {"title": "x"})
s2, b2 = call(A, "POST", "/api/chat", {"text": 123})
s3, b3 = call(A, "POST", "/api/files", {"name": "big.mov", "mime": "video/quicktime", "bytes": 600_000_000})
check("bad ids → 404, bad bodies → 400, oversize upload → 413", (s, s2, s3) == (404, 400, 413), f"{s} {s2} {s3}")

# --- 8b. memory refresh while the model is busy: a plain 503, not a server error
sse(A, "/api/chat", {"text": "MOCK_MEMORY_BUSY note for later", "model": "claude-sonnet-5-5"})
subprocess.run(["psql", "-h", "/tmp", "-p", "5499", "-U", "postgres", "rodrech", "-qc", "update memory_summaries set refreshed_at = now() - interval '2 hours'"], check=True)
s_busy, b_busy = call(A, "POST", "/api/memory/refresh")
check("memory refresh while the model is busy says so (503)", s_busy == 503 and b"busy" in b_busy, f"{s_busy} {b_busy[:120]}")

# --- 9. usage: tokens and web searches recorded per answer
import subprocess
out = subprocess.run(["psql", "-h", "/tmp", "-p", "5499", "-U", "postgres", "rodrech", "-tAc",
    "select coalesce(sum(web_searches),0), count(*) filter (where input_tokens > 0) from usage_events where metric = 'message'"], capture_output=True, text=True).stdout.strip()
searches, with_tokens = (int(x) for x in out.split("|"))
check("usage records tokens per answer and counts web searches", searches >= 2 and with_tokens >= 3, out)

print(f"\n{sum(res)} / {len(res)} passed")
