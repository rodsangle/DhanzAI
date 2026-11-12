"""Microsoft Graph and Google APIs. Fixed hosts; never sends mail or overwrites files."""

import asyncio
import base64
import fcntl
import hashlib
import json
import logging
import os
import re
import secrets
import uuid
from email.message import EmailMessage
from urllib.parse import quote, urlencode, urlsplit

import httpx

from .integration_store import IntegrationError, owner, provider

AUTH = {
    "microsoft": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
    "google": "https://accounts.google.com/o/oauth2/v2/auth",
}
TOKEN = {
    "microsoft": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
    "google": "https://oauth2.googleapis.com/token",
}
GRAPH = "https://graph.microsoft.com/v1.0"
DRIVE = "https://www.googleapis.com/drive/v3"
GMAIL = "https://gmail.googleapis.com/gmail/v1/users/me"
SCOPES = {
    "microsoft": {
        "base": ["openid", "profile", "email", "offline_access", "User.Read"],
        "files": ["Files.ReadWrite"],
        "mail": ["Mail.ReadWrite"],
    },
    "google": {
        "base": ["openid", "email", "profile"],
        "files": ["https://www.googleapis.com/auth/drive.readonly", "https://www.googleapis.com/auth/drive.file"],
        "mail": ["https://www.googleapis.com/auth/gmail.readonly", "https://www.googleapis.com/auth/gmail.compose"],
    },
}
EXPORTS = {
    "application/vnd.google-apps.spreadsheet": (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".xlsx",
    ),
    "application/vnd.google-apps.document": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".docx",
    ),
    "application/vnd.google-apps.presentation": (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        ".pptx",
    ),
}


class PrivateDownloadLogFilter(logging.Filter):
    _dhanz_private_downloads = True

    def filter(self, record):
        if isinstance(record.args, tuple):
            values = []
            for value in record.args:
                if isinstance(value, httpx.URL) and any(
                    value.host == host or value.host.endswith("." + host)
                    for host in ("1drv.com", "sharepoint.com", "sharepointonline.com", "onedrive.com")
                ):
                    value = "https://" + value.host + "/[private-download]"
                values.append(value)
            record.args = tuple(values)
        return True


_ADDRESS_FORBIDDEN = frozenset("<>@,;")


def single_address(value):
    """One plain email address: local@domain.tld, no spaces, brackets, commas or semicolons.

    Same rule as the former pattern `[^\\s<>@,;]+@[^\\s<>@,;]+\\.[^\\s<>@,;]+`, checked without a
    backtracking regular expression.
    """
    if not isinstance(value, str) or not 0 < len(value) <= 254 or value.count("@") != 1:
        return False
    local, domain = value.split("@")
    if any(c.isspace() or c in _ADDRESS_FORBIDDEN for c in local + domain):
        return False
    # The domain needs a dot with at least one character on each side.
    return bool(local) and "." in domain[1:-1]


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_!+=/-]{1,512}", value):
        raise IntegrationError("Use the file or message ID returned by the integration.")
    return quote(value, safe="")


def filename(value):
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= 150
        or re.search(r'[\\/<>:"|?*\x00-\x1f]', value)
        or value in (".", "..")
    ):
        raise IntegrationError("Use a plain filename between 1 and 150 characters.")
    return value


def callback(config, name):
    return config["origin"] + "/api/v1/integrations/callback/" + provider(name)


def cookie_name(state):
    return "dhanz_link_" + hashlib.sha256(state.encode()).hexdigest()[:20]


class Service:
    def __init__(self, store, http=None):
        self.store, self.http = store, http
        self.owns_http = http is None

    async def __aenter__(self):
        logger = logging.getLogger("httpx")
        if not any(getattr(f, "_dhanz_private_downloads", False) for f in logger.filters):
            logger.addFilter(PrivateDownloadLogFilter())
        if self.http is None:
            self.http = httpx.AsyncClient(timeout=30, follow_redirects=False)
        return self

    async def __aexit__(self, *args):
        if self.owns_http:
            await self.http.aclose()

    def status(self, uid):
        result = []
        for name in AUTH:
            try:
                config = self.store.config(name)
            except IntegrationError:
                config = None
            connection = self.store.connection(uid, name)
            valid = bool(
                config
                and connection
                and not connection.get("reauthorize")
                and connection.get("revision") == self.store.revision(config)
            )
            result.append(
                {
                    "provider": name,
                    "configured": bool(config),
                    "connected": valid,
                    "account": connection.get("account") if valid else None,
                    "services": connection.get("services", []) if valid else [],
                    "reconnect_required": bool(connection and not valid),
                }
            )
        return result

    def begin(self, uid, name, services, session_id=None):
        config = self.store.config(name)
        if (
            not isinstance(services, list)
            or not services
            or len(services) > 2
            or any(x not in ("files", "mail") for x in services)
        ):
            raise IntegrationError("Select files, mail, or both.")
        services = sorted(set(services))
        verifier, browser_cookie = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
        value = {
            "verifier": verifier,
            "cookie_digest": hashlib.sha256(browser_cookie.encode()).hexdigest(),
            "services": services,
            "revision": self.store.revision(config),
            "session_id": str(session_id) if session_id else None,
        }
        state = self.store.pending(uid, name, value)
        scopes = SCOPES[name]["base"] + [scope for item in services for scope in SCOPES[name][item]]
        params = {
            "client_id": config["client_id"],
            "redirect_uri": callback(config, name),
            "response_type": "code",
            "scope": " ".join(scopes),
            "state": state,
            "code_challenge_method": "S256",
            "code_challenge": base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("="),
        }
        if name == "google":
            params.update(access_type="offline", prompt="consent")
        else:
            params.update(response_mode="query", prompt="select_account")
        return {"authorization_url": AUTH[name] + "?" + urlencode(params), "state": state, "cookie": browser_cookie}

    @staticmethod
    def checked(response):
        if response.status_code == 429:
            raise IntegrationError("The provider is rate limiting requests. Try again later; no write was retried.")
        if response.status_code in (401, 403):
            raise IntegrationError(
                "The provider denied access. Check this connection’s granted permissions or reconnect."
            )
        if not 200 <= response.status_code < 300:
            raise IntegrationError(
                "The provider could not complete this request (HTTP "
                + str(response.status_code)
                + "). No write was retried."
            )
        return response

    async def complete(self, uid, name, code, pending):
        config = self.store.config(name)
        if (
            pending["revision"] != self.store.revision(config)
            or not isinstance(code, str)
            or not 1 <= len(code) <= 4000
        ):
            raise IntegrationError("Application settings changed or sign-in expired. Start again in Integrations.")
        response = self.checked(
            await self.http.post(
                TOKEN[name],
                data={
                    "grant_type": "authorization_code",
                    "client_id": config["client_id"],
                    "client_secret": config["client_secret"],
                    "code": code,
                    "code_verifier": pending["verifier"],
                    "redirect_uri": callback(config, name),
                },
            )
        )
        token = response.json()
        if not token.get("access_token") or not token.get("refresh_token"):
            raise IntegrationError("Background access was not granted. Reconnect and approve offline access.")
        if name == "microsoft":
            url, params = GRAPH + "/me", {"$select": "id,displayName,mail,userPrincipalName"}
        else:
            url, params = "https://www.googleapis.com/oauth2/v3/userinfo", None
        profile = self.checked(
            await self.http.get(url, params=params, headers={"Authorization": "Bearer " + token["access_token"]})
        ).json()
        subject = profile.get("id") if name == "microsoft" else profile.get("sub")
        if not subject:
            raise IntegrationError("The provider did not identify the connected account.")
        granted = token.get("scope", "")
        normalized = {s.casefold().removeprefix("https://graph.microsoft.com/") for s in granted.split()}
        for service in pending["services"]:
            if not all(s.casefold() in normalized for s in SCOPES[name][service]):
                raise IntegrationError(
                    "The selected service permissions were not granted. Reconnect and review consent."
                )
        value = {
            "access_token": token["access_token"],
            "refresh_token": token["refresh_token"],
            "expires": self.store.clock() + max(60, min(int(token.get("expires_in", 3600)), 86400)),
            "services": pending["services"],
            "subject": str(subject),
            "revision": pending["revision"],
            "account": profile.get("mail")
            or profile.get("email")
            or profile.get("userPrincipalName")
            or profile.get("displayName")
            or "Connected account",
        }
        self.store.save(uid, name, value, expected_epoch=pending["epoch"])
        return {"provider": name, "account": value["account"], "services": value["services"]}

    async def access(self, uid, name, service):
        config = self.store.config(name)
        lock_path = self.store.root / (owner(uid) + "-" + provider(name) + ".lock")
        with os.fdopen(os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600), "a") as handle:
            for _ in range(100):
                try:
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    await asyncio.sleep(0.1)
            else:
                raise IntegrationError("This connection is refreshing. Try again shortly.")
            try:
                value = self.store.connection(uid, name)
                if (
                    not value
                    or value.get("reauthorize")
                    or value.get("revision") != self.store.revision(config)
                    or service not in value.get("services", [])
                ):
                    raise IntegrationError(
                        "Connect this account with access to the requested service in Settings → Integrations."
                    )
                if value["expires"] <= self.store.clock() + 60:
                    response = await self.http.post(
                        TOKEN[name],
                        data={
                            "grant_type": "refresh_token",
                            "refresh_token": value["refresh_token"],
                            "client_id": config["client_id"],
                            "client_secret": config["client_secret"],
                        },
                    )
                    if response.status_code in (400, 401, 403):
                        value["reauthorize"] = True
                        self.store.update_existing(uid, name, value)
                        raise IntegrationError("This connection needs sign-in again. Reconnect it in Integrations.")
                    self.checked(response)
                    fresh = response.json()
                    if not fresh.get("access_token"):
                        raise IntegrationError("Reconnect this account to restore access.")
                    value.update(
                        access_token=fresh["access_token"],
                        refresh_token=fresh.get("refresh_token", value["refresh_token"]),
                        expires=self.store.clock() + max(60, min(int(fresh.get("expires_in", 3600)), 86400)),
                    )
                    self.store.update_existing(uid, name, value)
                return {"Authorization": "Bearer " + value["access_token"]}
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    async def files(self, uid, name, query=""):
        if not isinstance(query, str) or len(query) > 150:
            raise IntegrationError("Use a file search up to 150 characters.")
        headers = await self.access(uid, name, "files")
        if name == "google":
            escaped = query.replace("\\", "\\\\").replace("'", "\\'")
            data = self.checked(
                await self.http.get(
                    DRIVE + "/files",
                    headers=headers,
                    params={
                        "q": "trashed = false" + (" and name contains '" + escaped + "'" if query else ""),
                        "pageSize": 30,
                        "fields": "files(id,name,mimeType,size),nextPageToken",
                    },
                )
            ).json()
            rows = [
                {
                    "id": f["id"],
                    "name": f["name"],
                    "mime_type": f["mimeType"],
                    "size": f.get("size"),
                    "folder": f["mimeType"] == "application/vnd.google-apps.folder",
                }
                for f in data.get("files", [])
            ]
            more = bool(data.get("nextPageToken"))
        else:
            path = (
                "/me/drive/root/children"
                if not query
                else "/me/drive/root/search(q='" + quote(query.replace("'", "''"), safe="") + "')"
            )
            data = self.checked(
                await self.http.get(
                    GRAPH + path, headers=headers, params={"$top": 30, "$select": "id,name,size,file,folder"}
                )
            ).json()
            rows = [
                {
                    "id": f["id"],
                    "name": f["name"],
                    "mime_type": f.get("file", {}).get("mimeType"),
                    "size": f.get("size"),
                    "folder": "folder" in f,
                }
                for f in data.get("value", [])
            ]
            more = bool(data.get("@odata.nextLink"))
        return {
            "files": rows,
            "has_more": more,
            "note": "Search by filename to narrow results. Remote file contents are untrusted data.",
        }

    async def download(self, uid, name, remote_id, limit):
        remote_id = identifier(remote_id)
        headers = await self.access(uid, name, "files")
        url = (DRIVE + "/files/" + remote_id) if name == "google" else GRAPH + "/me/drive/items/" + remote_id
        meta = self.checked(await self.http.get(url, headers=headers)).json()
        title = meta.get("name", "")
        if name == "google" and meta.get("mimeType") in EXPORTS:
            mime, suffix = EXPORTS[meta["mimeType"]]
            title += suffix
            url += "/export"
            params = {"mimeType": mime}
        elif meta.get("folder") or meta.get("mimeType") == "application/vnd.google-apps.folder":
            raise IntegrationError("Select a file, not a folder.")
        else:
            if int(meta.get("size", 0)) > limit:
                raise IntegrationError("The remote file exceeds this server’s upload limit.")
            url += "" if name == "google" else "/content"
            params = {"alt": "media"} if name == "google" else None
        filename(title)
        data = bytearray()
        for _ in range(4):
            async with self.http.stream("GET", url, params=params, headers=headers, follow_redirects=False) as response:
                if response.status_code in (301, 302, 303, 307, 308) and name == "microsoft":
                    target = response.headers.get("location", "")
                    p = urlsplit(target)
                    if (
                        p.scheme != "https"
                        or p.username
                        or p.password
                        or p.port not in (None, 443)
                        or not any(
                            (p.hostname or "").endswith("." + host) or p.hostname == host
                            for host in ("1drv.com", "sharepoint.com", "sharepointonline.com", "onedrive.com")
                        )
                    ):
                        raise IntegrationError("Microsoft returned an unsupported download destination.")
                    url, params, headers = target, None, {}  # never forward a Graph token to a download host
                    continue
                self.checked(response)
                async for chunk in response.aiter_bytes():
                    data.extend(chunk)
                    if len(data) > limit:
                        raise IntegrationError("The file exceeds this server’s upload limit.")
                return title, bytes(data)
        raise IntegrationError("Too many Microsoft download redirects.")

    async def upload(self, uid, name, title, data, mime, native_sheet=False):
        title = filename(title)
        headers = await self.access(uid, name, "files")
        if native_sheet and (name != "google" or not title.lower().endswith(".xlsx")):
            raise IntegrationError("Create a Google Sheet from an XLSX workbook.")
        if name == "google":
            boundary = "dhanz_" + secrets.token_hex(24)
            metadata = {"name": title[:-5] if native_sheet else title}
            if native_sheet:
                metadata["mimeType"] = "application/vnd.google-apps.spreadsheet"
            body = (
                f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n".encode()
                + json.dumps(metadata).encode()
                + f"\r\n--{boundary}\r\nContent-Type: {mime}\r\n\r\n".encode()
                + data
                + f"\r\n--{boundary}--\r\n".encode()
            )
            response = await self.http.post(
                "https://www.googleapis.com/upload/drive/v3/files",
                params={"uploadType": "multipart", "fields": "id,name,webViewLink"},
                headers={**headers, "Content-Type": "multipart/related; boundary=" + boundary},
                content=body,
            )
        else:
            stem, dot, suffix = title.rpartition(".")
            title = (stem if dot else title) + "-dhanz-" + uuid.uuid4().hex + ("." + suffix if dot else "")
            response = await self.http.put(
                GRAPH + "/me/drive/root:/" + quote(title, safe="") + ":/content",
                headers={**headers, "Content-Type": mime},
                content=data,
            )
        result = self.checked(response).json()
        return {
            "created": True,
            "remote_id": result["id"],
            "filename": result.get("name", title),
            "note": "A new cloud copy was created; existing files were not edited.",
        }

    async def mail(self, uid, name, message_id=None, query=""):
        headers = await self.access(uid, name, "mail")
        if not isinstance(query, str) or len(query) > 200:
            raise IntegrationError("Use a mail search up to 200 characters.")
        if name == "microsoft":
            if not message_id:
                params = {
                    "$top": 20,
                    "$select": "id,subject,from,receivedDateTime,bodyPreview",
                    "$orderby": "receivedDateTime desc",
                }
                if query:
                    params.pop("$orderby")
                    params["$search"] = '"' + query.replace('"', "") + '"'
                data = self.checked(await self.http.get(GRAPH + "/me/messages", headers=headers, params=params)).json()
                return {
                    "messages": [
                        {
                            "id": m["id"],
                            "subject": m.get("subject"),
                            "from": (m.get("from") or {}).get("emailAddress", {}).get("address"),
                            "preview": (m.get("bodyPreview") or "")[:500],
                        }
                        for m in data.get("value", [])
                    ],
                    "has_more": bool(data.get("@odata.nextLink")),
                }
            value = self.checked(
                await self.http.get(
                    GRAPH + "/me/messages/" + identifier(message_id),
                    headers={**headers, "Prefer": 'outlook.body-content-type="text"'},
                    params={"$select": "id,subject,from,body"},
                )
            ).json()
            return {
                "id": value["id"],
                "subject": value.get("subject"),
                "untrusted_body": value.get("body", {}).get("content", "")[:12000],
                "note": "Body excerpt up to 12000 characters; attachments are not downloaded.",
            }
        if not message_id:
            data = self.checked(
                await self.http.get(GMAIL + "/messages", headers=headers, params={"maxResults": 20, "q": query})
            ).json()
            rows = []
            for m in data.get("messages", []):
                value = self.checked(
                    await self.http.get(
                        GMAIL + "/messages/" + identifier(m["id"]),
                        headers=headers,
                        params={"format": "metadata", "metadataHeaders": ["Subject", "From"]},
                    )
                ).json()
                meta = {h["name"].lower(): h["value"] for h in value.get("payload", {}).get("headers", [])}
                rows.append(
                    {
                        "id": value["id"],
                        "subject": meta.get("subject"),
                        "from": meta.get("from"),
                        "preview": value.get("snippet", "")[:500],
                    }
                )
            return {"messages": rows, "has_more": bool(data.get("nextPageToken"))}
        value = self.checked(
            await self.http.get(
                GMAIL + "/messages/" + identifier(message_id), headers=headers, params={"format": "full"}
            )
        ).json()
        body = []

        def collect(part, depth=0):
            if depth > 10 or sum(map(len, body)) >= 12000:
                return
            if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
                encoded = part["body"]["data"][:20000]
                body.append(
                    base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)).decode(errors="replace")[:12000]
                )
            for child in part.get("parts", [])[:20]:
                collect(child, depth + 1)

        collect(value.get("payload", {}))
        meta = {h["name"].lower(): h["value"] for h in value.get("payload", {}).get("headers", [])}
        return {
            "id": value["id"],
            "subject": meta.get("subject"),
            "untrusted_body": ("\n".join(body) or value.get("snippet", ""))[:12000],
            "note": "Body excerpt up to 12000 characters; attachments are not downloaded.",
        }

    async def draft(self, uid, name, to, subject, body):
        if not single_address(to):
            raise IntegrationError("Enter one recipient email address.")
        if (
            not isinstance(subject, str)
            or len(subject) > 300
            or "\r" in subject
            or "\n" in subject
            or not isinstance(body, str)
            or len(body) > 20000
        ):
            raise IntegrationError(
                "Use a single-line subject up to 300 characters and a draft body up to 20000 characters."
            )
        headers = await self.access(uid, name, "mail")
        if name == "google":
            message = EmailMessage()
            message["To"], message["Subject"] = to, subject
            account = (self.store.connection(uid, name) or {}).get("account", "")
            if re.fullmatch(r"[^\s<>@,;]+@[^\s<>@,;]+\.[^\s<>@,;]+", account):
                message["From"] = account
            message.set_content(body)
            raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
            response = await self.http.post(GMAIL + "/drafts", headers=headers, json={"message": {"raw": raw}})
        else:
            response = await self.http.post(
                GRAPH + "/me/messages",
                headers=headers,
                json={
                    "subject": subject,
                    "body": {"contentType": "Text", "content": body},
                    "toRecipients": [{"emailAddress": {"address": to}}],
                },
            )
        result = self.checked(response).json()
        return {
            "draft_created": True,
            "draft_id": result["id"],
            "sent": False,
            "note": "The draft is saved in your mailbox for review. No email was sent.",
        }
