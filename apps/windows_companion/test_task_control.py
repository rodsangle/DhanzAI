import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

DIRECTORY = Path(__file__).parent
sys.path.insert(0, str(DIRECTORY))

from automation_companion import execute_payload, validate_payload  # noqa: E402
from desktop_control import Desktop, Frame  # noqa: E402
from task_control import Policy, run_task  # noqa: E402


def test_auto_is_opt_in_bounded_and_navigation_only(monkeypatch):
    policy = Policy()
    plan = {"operation": "click", "risk": "navigation", "reason": "Open next tab"}
    assert not policy.automatic(plan, "Browse documentation")
    policy.arm()
    assert not policy.automatic({**plan, "risk": "uncertain"}, "Browse documentation")
    assert not policy.automatic({**plan, "operation": "type_text"}, "Browse documentation")
    assert not policy.automatic(plan, "Send a message")
    assert all(policy.automatic(plan, "Browse documentation") for _ in range(20))
    assert not policy.automatic(plan, "Browse documentation")
    policy.arm()
    monkeypatch.setattr("task_control.time.monotonic", lambda: policy.deadline + 1)
    assert not policy.automatic(plan, "Browse documentation")


@pytest.mark.parametrize(
    "payload",
    [
        {"provider": "windows", "operation": "click", "x": True, "y": 2, "clicks": 1},
        {"provider": "windows", "operation": "click", "x": 1, "y": 2, "clicks": 3},
        {"provider": "windows", "operation": "scroll", "scroll_delta": 10},
        {"provider": "windows", "operation": "type_text", "text": "line\nbreak"},
        {"provider": "windows", "operation": "press_key", "key": "WIN+R"},
    ],
)
def test_invalid_input_is_rejected(payload):
    with pytest.raises(ValueError):
        validate_payload(payload)


def test_mouse_requires_selected_window():
    with pytest.raises(ValueError, match="Select a target"):
        execute_payload({"provider": "windows", "operation": "click", "x": 1, "y": 2, "clicks": 1})


class FakeDesktop:
    def __init__(self):
        self.captured = 0
        self.executed = []
        self.deadline = 0

    def capture(self):
        self.captured += 1
        return Frame(b"test-frame", 100, 100, (10, 10, 200, 200))

    def execute(self, payload, frame):
        self.executed.append(payload)


class FakeApi:
    def __init__(self, plans, enabled=True):
        self.plans, self.enabled = iter(plans), enabled
        self.requests = []

    def call(self, method, path, body=None):
        self.requests.append((method, path, body))
        if path == "/desktop/status":
            return {"enabled": self.enabled}
        assert body["screen_sharing_consent"] is True
        return next(self.plans)


def test_no_capture_without_consent_or_enabled_backend():
    desktop = FakeDesktop()
    for share, enabled in ((False, True), (True, False)):
        with pytest.raises(ValueError):
            run_task(FakeApi([], enabled), desktop, "Read docs", share, lambda *a: True, lambda: False, lambda s: None)
    assert desktop.captured == 0


def test_observe_execute_and_observe_again(monkeypatch):
    monkeypatch.setattr("task_control.time.sleep", lambda seconds: None)
    desktop = FakeDesktop()
    api = FakeApi(
        [
            {"operation": "click", "risk": "navigation", "reason": "Open section", "x": 20, "y": 30},
            {"operation": "done", "risk": "navigation", "reason": "Section is visible"},
        ]
    )
    result = run_task(api, desktop, "Read docs", True, lambda *a: True, lambda: False, lambda s: None)
    assert result.startswith("Model reports completion")
    assert desktop.captured == 2 and len(desktop.executed) == 1
    assert api.requests[-1][2]["step"] == 1
    assert "click executed" in api.requests[-1][2]["last_action"]


def test_stop_after_network_response_prevents_input():
    desktop = FakeDesktop()
    stopped = threading.Event()
    api = FakeApi([])
    call = api.call

    def request(method, path, body=None):
        if path == "/desktop/status":
            return call(method, path, body)
        stopped.set()
        return {"operation": "click", "risk": "navigation", "reason": "Open section", "x": 1, "y": 1}

    api.call = request
    run_task(api, desktop, "Read docs", True, lambda *a: True, stopped.is_set, lambda s: None)
    assert not desktop.executed


def test_consent_revocation_during_capture_prevents_upload():
    desktop = FakeDesktop()
    stopped = threading.Event()
    capture = desktop.capture

    def stop_capture():
        frame = capture()
        stopped.set()
        return frame

    desktop.capture = stop_capture
    api = FakeApi([])
    run_task(api, desktop, "Read docs", True, lambda *a: True, stopped.is_set, lambda s: None)
    assert [request[1] for request in api.requests] == ["/desktop/status"]


def test_typing_forces_confirmation_on_later_clicks(monkeypatch):
    monkeypatch.setattr("task_control.time.sleep", lambda seconds: None)
    plans = [
        {"operation": "type_text", "risk": "uncertain", "reason": "Enter search words", "text": "flowers"},
        {"operation": "click", "risk": "navigation", "reason": "Open result", "x": 1, "y": 1},
        {"operation": "done", "risk": "navigation", "reason": "Visible"},
    ]
    risks = []
    run_task(
        FakeApi(plans),
        FakeDesktop(),
        "Find flowers",
        True,
        lambda plan, *_: risks.append(plan["risk"]) or True,
        lambda: False,
        lambda s: None,
    )
    assert risks == ["uncertain", "uncertain"]


def native_fake(covered=False):
    desktop = Desktop.__new__(Desktop)
    desktop.hwnd, desktop.pid, desktop.deadline = 100, 1, 0
    desktop.cancelled = None
    desktop.stop = threading.Event()
    desktop.gui = SimpleNamespace(
        IsWindow=lambda hwnd: True,
        IsIconic=lambda hwnd: False,
        GetClassName=lambda hwnd: "Application",
        GetWindowText=lambda hwnd: "Example",
        GetForegroundWindow=lambda: 100,
        ClientToScreen=lambda hwnd, xy: (10, 20),
        GetClientRect=lambda hwnd: (0, 0, 200, 100),
        WindowFromPoint=lambda point: 999 if covered else 100,
        IsChild=lambda a, b: False,
    )
    desktop.process = SimpleNamespace(GetWindowThreadProcessId=lambda hwnd: (1, 1))
    clicks = []
    desktop.mouse = SimpleNamespace(
        failSafeCheck=lambda: None, click=lambda *a, **kw: clicks.append(a), FailSafeException=RuntimeError
    )
    return desktop, clicks


def test_click_maps_observation_pixels_to_selected_client():
    desktop, clicks = native_fake()
    desktop.execute(
        {"provider": "windows", "operation": "click", "x": 50, "y": 25, "clicks": 1},
        Frame(b"", 100, 50, (10, 20, 200, 100)),
    )
    assert clicks == [(110, 70)]


def test_occlusion_and_changed_geometry_stop_click():
    desktop, clicks = native_fake(covered=True)
    payload = {"provider": "windows", "operation": "click", "x": 10, "y": 10, "clicks": 1}
    with pytest.raises(ValueError, match="covers"):
        desktop.execute(payload)
    assert clicks == []
    desktop, clicks = native_fake()
    with pytest.raises(ValueError, match="moved or resized"):
        desktop.execute(payload, Frame(b"", 100, 50, (0, 0, 200, 100)))
    assert not clicks
