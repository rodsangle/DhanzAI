import json, urllib.request, http.cookiejar, time
A = "http://localhost:3100"
res = []
def check(n, ok, d=""):
    res.append(ok); print(("PASS " if ok else "FAIL ") + n + ("" if ok else f" :: {d}"), flush=True)
def client(email):
    jar = http.cookiejar.CookieJar(); op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    def call(method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        r = urllib.request.Request(A + path, data=data, method=method, headers={"Content-Type": "application/json"} if data else {})
        try:
            with op.open(r, timeout=60) as f: return f.status, f.read()
        except urllib.error.HTTPError as e: return e.code, e.read()
    if email: call("POST", "/api/auth/dev-login", {"email": email})
    return call
dante, maya, anon = client("dante@rodrech.com"), client("maya@rodrech.com"), client(None)
J = lambda r: json.loads(r[1])

# Dante's private things
convs = J(dante("GET", "/api/conversations"))
private = next(c for c in convs if c["title"] == "Influencer outreach email")
d = J(dante("GET", f"/api/conversations/{private['id']}"))
msg = d["messages"][-1]["id"]
projects = J(dante("GET", "/api/projects"))
tags = next(p for p in projects if p["name"] == "Hang tags & packaging")
s, b = dante("POST", "/api/files", {"name": "secret-pricing.txt", "mime": "text/plain", "bytes": 11})
f = J((s, b)); dante("PUT", f["upload_url"]) if False else None
import urllib.request as U
r = U.Request(A + f["upload_url"], data=b"cost: $4.10", method="PUT", headers={"Content-Type": "text/plain"})
# upload with Dante's cookie
dj = http.cookiejar.CookieJar(); dop = U.build_opener(U.HTTPCookieProcessor(dj))
dop.open(U.Request(A + "/api/auth/dev-login", data=b'{"email":"dante@rodrech.com"}', headers={"Content-Type": "application/json"})).read()
dop.open(r).read(); dop.open(U.Request(A + f"/api/files/{f['file']['id']}/complete", method="POST")).read()
fid = f["file"]["id"]
dante("POST", f"/api/conversations/{private['id']}/share")

checks = [
    ("read Dante's private chat", maya("GET", f"/api/conversations/{private['id']}"), 404),
    ("read a message in it", maya("GET", f"/api/messages/{msg}"), 404),
    ("stream it", maya("GET", f"/api/messages/{msg}/stream"), 404),
    ("rename it", maya("PATCH", f"/api/conversations/{private['id']}", {"title": "x"}), 404),
    ("delete it", maya("DELETE", f"/api/conversations/{private['id']}"), 404),
    ("regenerate in it", maya("POST", f"/api/messages/{msg}/regenerate", {}), 404),
    ("stop in it", maya("POST", f"/api/messages/{msg}/stop"), 404),
    ("rate it", maya("PATCH", f"/api/messages/{msg}", {"feedback": 1}), 404),
    ("post into it", maya("POST", "/api/chat", {"conversation_id": private["id"], "text": "hi"}), 404),
    ("share it", maya("POST", f"/api/conversations/{private['id']}/share"), 404),
    ("open Dante's unshared project", maya("GET", f"/api/projects/{tags['id']}"), 404),
    ("edit it", maya("PATCH", f"/api/projects/{tags['id']}", {"name": "x"}), 404),
    ("add herself to it", maya("POST", f"/api/projects/{tags['id']}/members", {"user_id": J(maya("GET", "/api/me"))["profile"]["id"], "role": "editor"}), 403),
    ("download Dante's file", maya("GET", f"/api/files/{fid}/download"), 404),
    ("trash Dante's file", maya("PATCH", f"/api/files/{fid}", {"trashed": True}), 404),
    ("attach Dante's file to her chat", maya("POST", "/api/chat", {"text": "read this", "file_ids": [fid]}), 400),
    ("anonymous: list chats", anon("GET", "/api/conversations"), 401),
    ("anonymous: download file", anon("GET", f"/api/files/{fid}/download"), 404),
]
for name, (s, b), want in checks:
    check(f"Maya can't {name} → {want}", s == want, f"got {s} {b[:120]}")
lists = [J(maya("GET", "/api/conversations")), J(maya("GET", "/api/files")), J(maya("GET", "/api/shares")), J(maya("GET", "/api/images"))]
check("Maya's lists contain none of Dante's chats, files, shares or images",
      all(c["id"] != private["id"] for c in lists[0]) and all(x["id"] != fid for x in lists[1]) and lists[2] == [] and lists[3] == [])
hits = J(maya("GET", "/api/search?q=outreach")) + J(maya("GET", "/api/search?q=secret-pricing"))
check("Maya's search finds none of Dante's private chats or files", hits == [], str(hits)[:200])
pers = J(maya("GET", "/api/personalization"))
check("Maya's personalization is her own (empty), not Dante's", pers["about_you"] == "", pers["about_you"][:60])

# Account deletion
s, b = dante("DELETE", "/api/account", {"confirm": "DELETE"})
check("the only owner can't delete their account (409)", s == 409, f"{s} {b[:100]}")
s, b = maya("DELETE", "/api/account", {"confirm": "nope"})
check("deletion needs the typed confirmation (400)", s == 400, str(s))
s, b = maya("DELETE", "/api/account", {"confirm": "DELETE"})
check("Maya deletes her account", s == 200, f"{s} {b[:100]}")
s, b = maya("GET", "/api/me")
check("her session no longer works", s == 401, str(s))
s, b = dante("POST", "/api/auth/dev-login", {"email": "maya@rodrech.com"})
check("she can't sign back in as a deleted user", s == 403, str(s))
print(f"\n{sum(res)} / {len(res)} passed")
