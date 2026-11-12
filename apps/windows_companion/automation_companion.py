"""Windows control panel with local approval and bounded AI navigation."""

import argparse
import ctypes
import getpass
import json
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import uuid
import webbrowser
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

MAX_RESPONSE = 8 * 1024 * 1024
KEYS = {
    "ENTER",
    "TAB",
    "ESCAPE",
    "BACKSPACE",
    "DELETE",
    "UP",
    "DOWN",
    "LEFT",
    "RIGHT",
    "CTRL+A",
    "CTRL+C",
    "CTRL+V",
    "CTRL+Z",
    "CTRL+S",
}


class ApiError(Exception):
    def __init__(self, status):
        self.status = status
        super().__init__(f"Dhanz request failed (HTTP {status}); no action was retried.")


class SignInRequired(Exception):
    pass


def server_origin(value):
    url = urlsplit(value)
    if (
        url.scheme != "https"
        or not url.hostname
        or url.username
        or url.password
        or url.path not in ("", "/")
        or url.query
        or url.fragment
    ):
        raise ValueError("Use an HTTPS server origin such as https://dhanzai.com")
    return value.rstrip("/")


class NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("Server redirected the request; credentials were not forwarded.")


def raw_request(server, method, path, token=None, body=None):
    server_origin(server)
    if not path.startswith("/") or "?" in path or "#" in path:
        raise ValueError("Invalid API path.")
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(  # noqa: S310 - HTTPS origin validated before attaching credentials.
        server + "/api/v1" + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.build_opener(NoRedirects()).open(
            req, timeout=90 if path == "/desktop/next" else 20
        ) as response:
            raw = response.read(MAX_RESPONSE + 1)
            if len(raw) > MAX_RESPONSE:
                raise ValueError("Server response exceeded the companion limit.")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        code = exc.code
        exc.close()
        raise ApiError(code) from None
    except urllib.error.URLError:
        raise ApiError(0) from None


def save_credentials(path, credentials):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    encrypted = protect(json.dumps(credentials).encode())
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(encrypted)
        os.replace(temporary, path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


class Api:
    def __init__(self, server, credentials, save):
        self.server = server_origin(server)
        self.credentials, self.save = credentials, save

    def call(self, method, path, body=None):
        try:
            return raw_request(self.server, method, path, self.credentials["access_token"], body)
        except ApiError as exc:
            if exc.status != 401:
                raise
        # Only an explicit 401 may trigger refresh and one retry. Never retry ambiguous writes.
        try:
            tokens = raw_request(
                self.server,
                "POST",
                "/auth/refresh",
                body={
                    "refresh_token": self.credentials["refresh_token"],
                },
            )
        except ApiError as exc:
            raise SignInRequired("Session expired or revoked. Run again with --login.") from exc
        self.credentials.update(access_token=tokens["access_token"], refresh_token=tokens["refresh_token"])
        self.save(self.credentials)
        return raw_request(self.server, method, path, self.credentials["access_token"], body)


def validate_payload(payload):
    if not isinstance(payload, dict) or payload.get("provider") != "windows":
        raise ValueError("Not a Windows action.")
    operation = payload.get("operation")
    if operation == "open_app":
        if set(payload) != {"provider", "operation", "app"} or payload["app"] not in ("notepad", "calculator"):
            raise ValueError("Only Notepad and Calculator are enabled in this helper.")
        return operation, payload["app"]
    if operation == "open_url":
        if set(payload) != {"provider", "operation", "url"}:
            raise ValueError("Unexpected website action fields.")
        target = payload["url"]
        if not isinstance(target, str) or len(target) > 2000 or any(ord(c) < 32 for c in target):
            raise ValueError("Invalid website URL.")
        url = urlsplit(target)
        if url.scheme != "https" or not url.hostname or url.username or url.password:
            raise ValueError("Only HTTPS websites without embedded credentials are enabled.")
        return operation, target
    if operation == "click":
        if set(payload) != {"provider", "operation", "x", "y", "clicks"}:
            raise ValueError("Unexpected click fields.")
        if any(type(payload[k]) is not int or not 0 <= payload[k] <= 16384 for k in ("x", "y")):
            raise ValueError("Invalid click coordinates.")
        if type(payload["clicks"]) is not int or payload["clicks"] not in (1, 2):
            raise ValueError("Only single/double left clicks are supported.")
        return operation, f"({payload['x']}, {payload['y']}), {payload['clicks']} left click(s)"
    if operation == "scroll":
        if set(payload) != {"provider", "operation", "scroll_delta"}:
            raise ValueError("Unexpected scroll fields.")
        value = payload["scroll_delta"]
        if type(value) is not int or value == 0 or abs(value) > 1200 or value % 120:
            raise ValueError("Scroll must be nonzero, at most 1200, and in increments of 120.")
        return operation, str(value)
    if operation == "type_text":
        if set(payload) != {"provider", "operation", "text"}:
            raise ValueError("Unexpected typing fields.")
        text = payload["text"]
        if not isinstance(text, str) or not text or len(text) > 2000 or any(not 32 <= ord(c) <= 126 for c in text):
            raise ValueError("Typing supports up to 2000 printable ASCII characters, without line breaks.")
        return operation, text
    if operation == "press_key":
        if set(payload) != {"provider", "operation", "key"} or payload["key"] not in KEYS:
            raise ValueError("Unsupported key or shortcut.")
        return operation, payload["key"]
    raise ValueError("This action is not supported by this restricted helper.")


def execute_payload(payload, desktop=None, frame=None):
    operation, target = validate_payload(payload)
    if operation in ("click", "scroll", "type_text", "press_key"):
        if desktop is None:
            raise ValueError("Select a target window in the control panel before using mouse or keyboard actions.")
        desktop.execute(payload, frame)
        return
    if operation == "open_url":
        if not webbrowser.open(target):
            raise OSError("Windows could not open the website.")
        return
    system = ctypes.create_unicode_buffer(32768)
    length = ctypes.windll.kernel32.GetSystemDirectoryW(system, len(system))
    if not length or length >= len(system):
        raise OSError("Cannot locate the Windows system directory.")
    executable = Path(system.value) / ("notepad.exe" if target == "notepad" else "calc.exe")
    subprocess.Popen([str(executable)], shell=False)  # noqa: S603 - fixed app in the Windows system directory.


def process_action(api, action, approve, execute=execute_payload):
    if not isinstance(action, dict) or action.get("provider") != "windows" or action.get("status") != "pending":
        return "ignored"
    try:
        action_id = str(uuid.UUID(action["id"]))
        payload = action["payload"]
        validate_payload(payload)
        expires = datetime.fromisoformat(action["expires_at"].replace("Z", "+00:00"))
        if expires.tzinfo is None:
            return "ignored"
    except (ValueError, KeyError, TypeError, AttributeError):
        return "ignored"
    remaining = (expires - datetime.now(UTC)).total_seconds()
    if remaining <= 0:
        return "expired"
    if not approve(payload, remaining):
        api.call("POST", f"/automation/actions/{action_id}/reject", {})
        return "denied"
    if datetime.now(UTC) >= expires:
        return "expired"
    claimed = api.call("POST", f"/automation/actions/{action_id}/windows-claim", {})
    # Bind the local approval to exactly the payload and action shown to the user.
    if (
        claimed.get("id") != action_id
        or claimed.get("provider") != "windows"
        or claimed.get("status") != "executing"
        or claimed.get("payload") != payload
    ):
        return "mismatch"
    if datetime.now(UTC) >= expires:
        return "expired"
    # Recheck the account session immediately before executing locally.
    api.call("GET", "/users/me")
    if datetime.now(UTC) >= expires:
        return "expired"
    success = False
    try:
        execute(payload)
        success = True
    except (OSError, ValueError):
        pass
    api.call("POST", f"/automation/actions/{action_id}/windows-result", {"success": success})
    return "completed" if success else "failed"


def protect(data, *, decrypt=False):
    """Windows DPAPI encryption bound to the current Windows user."""
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]

    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    output = Blob()
    function = ctypes.windll.crypt32.CryptUnprotectData if decrypt else ctypes.windll.crypt32.CryptProtectData
    function.restype = wintypes.BOOL
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(output)):
        raise OSError("Windows could not protect/unprotect the companion credential.")
    try:
        return ctypes.string_at(output.data, output.size)
    finally:
        ctypes.windll.kernel32.LocalFree.argtypes = [wintypes.HLOCAL]
        ctypes.windll.kernel32.LocalFree(ctypes.cast(output.data, wintypes.HLOCAL))


def ask_approval(window, message, seconds):
    import tkinter as tk

    approved = False
    dialog = tk.Toplevel(window)
    dialog.title("Dhanz PC approval")
    width = min(820, max(320, dialog.winfo_screenwidth() - 80))
    height = min(520, max(280, dialog.winfo_screenheight() - 100))
    left = max(0, (dialog.winfo_screenwidth() - width) // 2)
    top = max(0, (dialog.winfo_screenheight() - height) // 2)
    dialog.geometry(f"{width}x{height}+{left}+{top}")
    dialog.minsize(min(640, width), min(360, height))
    dialog.attributes("-topmost", True)

    def close(allow=False):
        nonlocal approved
        approved = allow
        dialog.destroy()

    buttons = tk.Frame(dialog)
    buttons.pack(side="bottom", fill="x", padx=24, pady=20)
    tk.Button(buttons, text="Allow once", font=("Segoe UI", 14), width=14, command=lambda: close(True)).pack(
        side="right", padx=8, ipady=8
    )
    deny = tk.Button(buttons, text="Deny", font=("Segoe UI", 14), width=14, command=close)
    deny.pack(side="right", padx=8, ipady=8)
    content = tk.Frame(dialog)
    content.pack(fill="both", expand=True, padx=24, pady=(24, 0))
    scroll = tk.Scrollbar(content)
    scroll.pack(side="right", fill="y")
    text = tk.Text(content, wrap="word", font=("Segoe UI", 14), padx=12, pady=12, yscrollcommand=scroll.set)
    text.insert("1.0", message)
    text.configure(state="disabled")
    text.pack(side="left", fill="both", expand=True)
    scroll.configure(command=text.yview)

    def bring_to_front():
        dialog.lift()
        deny.focus_force()

    dialog.protocol("WM_DELETE_WINDOW", close)
    dialog.bind("<Escape>", lambda event: close())
    dialog.after(max(1, int(seconds * 1000)), close)
    dialog.after_idle(bring_to_front)
    dialog.wait_visibility()
    dialog.grab_set()
    window.wait_window(dialog)
    return approved


def main():
    if sys.platform != "win32" or sys.version_info < (3, 12):
        raise SystemExit("Run this helper on Windows with Python 3.12 or newer.")
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", default="https://dhanzai.com")
    parser.add_argument("--login", action="store_true", help="Create a new login session")
    args = parser.parse_args()
    server = server_origin(args.server)
    path = Path(os.environ["LOCALAPPDATA"]) / "DhanzAI" / "automation-session.bin"
    if args.login or not path.exists():
        print("Sign in with your Dhanz account, not your OpenAI key. Credentials stay in Windows DPAPI storage.")
        email = input("Dhanz email: ").strip()
        password = getpass.getpass("Dhanz password: ")
        tokens = raw_request(server, "POST", "/auth/login", body={"email": email, "password": password})
        del password
        if tokens.get("mfa_required"):
            tokens = raw_request(
                server,
                "POST",
                "/auth/mfa/verify",
                body={
                    "mfa_token": tokens["mfa_token"],
                    "code": getpass.getpass("Authenticator or recovery code: ").strip(),
                },
            )
        save_credentials(
            path, {"server": server, "access_token": tokens["access_token"], "refresh_token": tokens["refresh_token"]}
        )
    credentials = json.loads(protect(path.read_bytes(), decrypt=True))
    if credentials["server"] != server:
        raise SystemExit("Saved session belongs to another server. Use --login explicitly.")
    api = Api(server, credentials, lambda c: save_credentials(path, c))
    api.call("GET", "/users/me")
    # Imports from the control panel must share the CLI's exception classes and API session.
    sys.modules.setdefault("automation_companion", sys.modules[__name__])
    from task_control import run

    run(api, server)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Windows helper stopped.")
    except (ApiError, SignInRequired) as error:
        raise SystemExit(str(error)) from None
