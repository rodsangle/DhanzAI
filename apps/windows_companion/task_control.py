"""Visible local control panel, bounded automatic navigation, and screenshot task loop."""

import base64
import ctypes
import queue
import re
import socket
import threading
import time
from concurrent.futures import Future

from automation_companion import (
    ApiError,
    SignInRequired,
    ask_approval,
    execute_payload,
    process_action,
    validate_payload,
)

SENSITIVE = re.compile(
    r"\b(send|submit|purchase|buy|pay|payment|delete|remove|transfer|publish|post|password|sign.?in|log.?in|"
    r"permission|install|security|save|overwrite|account|checkout|confirm|authorize)\b",
    re.I,
)


class Policy:
    def __init__(self):
        self.enabled = False
        self.deadline = 0.0
        self.remaining = 0

    def arm(self):
        self.enabled = True
        self.deadline = time.monotonic() + 300
        self.remaining = 20

    def disarm(self):
        self.enabled = False

    def automatic(self, plan, goal):
        if (
            not self.enabled
            or time.monotonic() >= self.deadline
            or self.remaining <= 0
            or plan.get("risk") != "navigation"
            or plan.get("operation") not in ("click", "scroll")
            or SENSITIVE.search(goal + " " + plan.get("reason", ""))
        ):
            return False
        self.remaining -= 1
        return True


def plan_payload(plan):
    if not isinstance(plan, dict) or plan.get("risk") not in ("navigation", "consequential", "uncertain"):
        raise ValueError("Planner returned an invalid risk classification.")
    if not isinstance(plan.get("reason"), str) or not 1 <= len(plan["reason"]) <= 500:
        raise ValueError("Planner must supply a short explanation.")
    operation = plan.get("operation")
    if operation in ("done", "need_user"):
        if not isinstance(plan.get("reason"), str) or not plan["reason"]:
            raise ValueError("Planner must explain why it stopped.")
        return None
    keys = {
        "click": ("x", "y", "clicks"),
        "scroll": ("scroll_delta",),
        "type_text": ("text",),
        "press_key": ("key",),
    }.get(operation)
    if keys is None:
        raise ValueError("Unsupported planned operation.")
    payload = {
        "provider": "windows",
        "operation": operation,
        **{k: plan.get(k, 1 if k == "clicks" else None) for k in keys},
    }
    validate_payload(payload)
    return payload


class Bridge:
    def __init__(self, root, stop):
        self.root, self.stop = root, stop
        self.queue = queue.Queue()
        root.after(50, self.drain)

    def call(self, function, *args):
        future = Future()
        self.queue.put((future, function, args))
        while not future.done():
            if self.stop.wait(0.05):
                raise ValueError("Helper stopped.")
        return future.result()

    def drain(self):
        while not self.queue.empty() and not self.stop.is_set():
            future, function, args = self.queue.get_nowait()
            try:
                future.set_result(function(*args))
            except Exception as exc:
                future.set_exception(exc)
        if not self.stop.is_set():
            self.root.after(50, self.drain)


def run_task(api, desktop, goal, share, approve, stopped, status):
    if not share:
        raise ValueError("Screen sharing must be enabled locally before starting a task.")
    if not api.call("GET", "/desktop/status").get("enabled"):
        raise ValueError("The screenshot planner is not enabled on AWS. Manual queued actions still work.")
    deadline = time.monotonic() + 300
    desktop.deadline = deadline
    desktop.cancelled = stopped
    previous = ""
    input_used = False
    for step in range(20):
        if stopped() or time.monotonic() >= deadline:
            return "Task stopped or time limit reached."
        frame = desktop.capture()
        if stopped():
            return "Task stopped."
        status(f"Planning step {step + 1}; selected-window screenshot is being sent to Dhanz.")
        plan = api.call(
            "POST",
            "/desktop/next",
            {
                "goal": goal,
                "screenshot": base64.b64encode(frame.jpeg).decode(),
                "width": frame.width,
                "height": frame.height,
                "step": step,
                "last_action": previous,
                "screen_sharing_consent": True,
            },
        )
        if stopped() or time.monotonic() >= deadline:
            return "Task stopped before input was sent."
        payload = plan_payload(plan)
        if payload is None:
            return ("Model reports completion: " if plan["operation"] == "done" else "Needs your input: ") + plan[
                "reason"
            ]
        if input_used:
            plan = {
                **plan,
                "risk": "uncertain",
                "reason": "Confirm the next action after keyboard/text input. " + plan["reason"],
            }
        if not approve(plan, payload, goal):
            return "Task denied locally."
        if stopped() or time.monotonic() >= deadline:
            return "Task stopped before input was sent."
        # Every step uses a fresh frame; native executor checks window identity, geometry and hit target.
        desktop.execute(payload, frame)
        input_used = input_used or payload["operation"] in ("type_text", "press_key")
        previous = f"{payload['operation']} executed; {plan.get('reason', '')}"[:1000]
        time.sleep(0.5)
    return "Task step limit reached; inspect the window before starting another task."


def run(api, server):
    import tkinter as tk
    from tkinter import messagebox

    from desktop_control import Desktop

    try:
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except (AttributeError, OSError):
        pass
    root = tk.Tk()
    root.title("Dhanz PC control — manual approval")
    root.geometry("640x430")
    root.minsize(560, 400)
    root.attributes("-topmost", True)
    stop = threading.Event()
    cancel_task = threading.Event()
    share_consent = threading.Event()
    bridge = Bridge(root, stop)
    policy = Policy()
    tasks = queue.Queue()
    task_running = threading.Event()
    desktop = None
    control_epoch = 0
    automatic, sharing = tk.BooleanVar(value=False), tk.BooleanVar(value=False)
    state = tk.StringVar(value="Helper running. Select a window to enable mouse actions.")
    window_name = tk.StringVar(value="No window selected")
    goal = tk.StringVar()

    def set_status(text):
        state.set(text)

    def disarm():
        policy.disarm()
        automatic.set(False)
        root.title("Dhanz PC control — manual approval")

    def close():
        stop.set()
        cancel_task.set()
        policy.disarm()
        root.destroy()

    def pause():
        nonlocal control_epoch
        control_epoch += 1
        cancel_task.set()
        disarm()
        state.set("Task stopped. New queued actions require manual approval.")

    def capture_selection(epoch):
        nonlocal desktop
        if epoch != control_epoch or stop.is_set():
            return
        try:
            candidate = Desktop(stop)
            title = candidate.select_foreground()
            desktop = candidate
            window_name.set(title)
            state.set("Window selected. Mouse coordinates are relative to its client area.")
        except (OSError, ValueError) as exc:
            state.set(str(exc))

    def select_window():
        pause()
        state.set("Within 3 seconds, click the application window you want Dhanz to control.")
        epoch = control_epoch
        root.after(3000, lambda: capture_selection(epoch))

    def arm():
        if not automatic.get():
            policy.disarm()
            return
        if desktop is None:
            automatic.set(False)
            state.set("Select a window first.")
            return
        consent = messagebox.askyesno(
            "Automatic navigation",
            "Allow planned navigation clicks and scrolling in the selected "
            "window for at most 5 minutes / 20 steps?\n\nTyping, keys and consequential/uncertain actions "
            "still require approval. "
            "The model can misidentify a click. Stop with Ctrl+Alt+Esc, "
            "move the mouse to the upper-left corner, or use Stop.",
            parent=root,
            default="no",
        )
        if consent:
            policy.arm()
            root.title("Dhanz PC control — automatic navigation armed")
            state.set("Automatic navigation armed for this session only.")
        else:
            automatic.set(False)

    def start_task():
        if desktop is None or not goal.get().strip() or not sharing.get():
            state.set("Select a window, enter a task, and enable screen sharing first.")
            return
        if task_running.is_set() or not tasks.empty():
            state.set("A task is already queued or running. Stop it before starting another.")
            return
        cancel_task.clear()
        share_consent.set()
        task_running.set()
        tasks.put((desktop, goal.get().strip(), sharing.get(), control_epoch))
        state.set("Task queued. The selected window will be observed and controlled.")

    def sharing_changed():
        if sharing.get():
            share_consent.set()
        else:
            share_consent.clear()
            pause()

    def manual_approval(payload, remaining, reason="", target_name=None):
        operation, target = validate_payload(payload)
        text = (
            f"Allow one action on {socket.gethostname()}?\n\n{operation}: {target}"
            f"\nWindow: {target_name if target_name is not None else window_name.get()}\nServer: {server}"
        )
        if reason:
            text += "\n\nPlanner assessment (verify it yourself): " + reason
        return ask_approval(root, text, remaining)

    def task_approval(plan, payload, task):
        if stop.is_set() or cancel_task.is_set():
            return False
        remaining = min(120, desktop.deadline - time.monotonic()) if desktop is not None else 0
        if remaining <= 0:
            return False
        if policy.automatic(plan, task):
            state.set("Automatic navigation: " + plan.get("reason", ""))
            return True
        return manual_approval(payload, remaining, f"{plan.get('risk')}: {plan.get('reason')}")

    tk.Label(root, textvariable=window_name, wraplength=580, font=("Segoe UI", 12)).pack(padx=16, pady=12)
    tk.Button(root, text="Select target window (3 seconds)", command=select_window).pack()
    tk.Checkbutton(
        root, text="Automatic navigation approval (5 minutes / 20 steps)", variable=automatic, command=arm
    ).pack(pady=8)
    tk.Checkbutton(
        root,
        text="Share selected-window screenshots with Dhanz and its AI provider",
        variable=sharing,
        command=sharing_changed,
    ).pack()
    tk.Label(root, text="Task for Dhanz (keep confidential information out of the selected window):").pack(pady=(12, 4))
    tk.Entry(root, textvariable=goal, font=("Segoe UI", 12)).pack(fill="x", padx=16)
    tk.Button(root, text="Run task", command=start_task).pack(pady=8)
    buttons = tk.Frame(root)
    buttons.pack()
    tk.Button(buttons, text="Stop task / disable auto", command=pause).pack(side="left", padx=8)
    tk.Button(buttons, text="Stop helper", command=close).pack(side="left", padx=8)
    tk.Label(root, textvariable=state, wraplength=580, justify="left").pack(padx=16, pady=12)
    root.protocol("WM_DELETE_WINDOW", close)

    def emergency_watch():
        from ctypes import wintypes

        while not stop.wait(0.05):
            user32 = ctypes.windll.user32
            if all(user32.GetAsyncKeyState(key) & 0x8000 for key in (0x11, 0x12, 0x1B)):
                stop.set()
                return
            point = wintypes.POINT()
            if desktop is not None and user32.GetCursorPos(ctypes.byref(point)) and point.x == point.y == 0:
                stop.set()
                return

    def check_stop():
        if stop.is_set():
            try:
                root.destroy()
            except tk.TclError:
                pass
        else:
            root.after(100, check_stop)

    def worker():
        handled = set()
        while not stop.is_set():
            try:
                if not tasks.empty():
                    target, task, share, epoch = tasks.get_nowait()
                    try:
                        result = run_task(
                            api,
                            target,
                            task,
                            share,
                            lambda p, a, g: bridge.call(task_approval, p, a, g),
                            lambda epoch=epoch: (
                                stop.is_set()
                                or cancel_task.is_set()
                                or not share_consent.is_set()
                                or epoch != control_epoch
                            ),
                            lambda text: bridge.call(set_status, text),
                        )
                        bridge.call(set_status, result)
                    finally:
                        target.deadline = 0
                        target.cancelled = None
                        task_running.clear()
                        if not stop.is_set():
                            bridge.call(disarm)
                    continue
                actions = api.call("GET", "/automation/actions").get("actions", [])
                for action in actions:
                    key = action.get("id") if isinstance(action, dict) else None
                    if (
                        not isinstance(key, str)
                        or key in handled
                        or action.get("provider") != "windows"
                        or action.get("status") != "pending"
                    ):
                        continue
                    if stop.is_set():
                        return
                    handled.add(key)
                    target, epoch = desktop, control_epoch
                    target_name = bridge.call(window_name.get)

                    def execute_queued(payload, target=target, epoch=epoch):
                        if stop.is_set() or epoch != control_epoch:
                            raise ValueError("Control selection changed or action stopped.")
                        execute_payload(payload, desktop=target)

                    result = process_action(
                        api,
                        action,
                        lambda p, r, name=target_name: bridge.call(manual_approval, p, r, "", name),
                        execute_queued,
                    )
                    bridge.call(set_status, "Queued PC action: " + result)
                stop.wait(3)
            except SignInRequired:
                if stop.is_set():
                    return
                bridge.call(set_status, "Session revoked or expired. Close and restart with --login.")
                return
            except (ApiError, ValueError, OSError) as exc:
                if stop.is_set():
                    return
                bridge.call(disarm)
                bridge.call(set_status, str(exc))
                stop.wait(3)
            except Exception:
                if stop.is_set():
                    return
                bridge.call(disarm)
                bridge.call(set_status, "Control stopped after an unexpected native/UI error. No action is replayed.")
                stop.wait(3)

    threading.Thread(target=worker, daemon=True).start()
    threading.Thread(target=emergency_watch, daemon=True).start()
    root.after(100, check_stop)
    print("Dhanz control panel running. Automatic approval is OFF until enabled locally.")
    try:
        root.mainloop()
    finally:
        stop.set()
