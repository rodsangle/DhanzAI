"""Window-scoped Win32 mouse/keyboard control and window-only screenshots."""

import io
import os
import threading
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class Frame:
    jpeg: bytes
    width: int
    height: int
    rect: tuple


class Desktop:
    def __init__(self, stop=None):
        if os.name != "nt":
            raise OSError("Desktop control requires Windows.")
        try:
            import pyautogui
            import win32api
            import win32gui
            import win32process
        except ImportError:
            raise OSError("Install desktop dependencies: python -m pip install -r requirements-desktop.txt") from None
        self.mouse, self.gui, self.process, self.api = pyautogui, win32gui, win32process, win32api
        self.mouse.FAILSAFE = True
        self.mouse.PAUSE = 0.2
        self.stop = stop or threading.Event()
        self.hwnd = None
        self.pid = None
        self.deadline = 0.0
        self.cancelled = None

    def select_foreground(self):
        hwnd = self.gui.GetForegroundWindow()
        _, pid = self.process.GetWindowThreadProcessId(hwnd)
        if not hwnd or pid == os.getpid():
            raise ValueError("Select the target application, not the Dhanz control panel.")
        self.hwnd, self.pid = hwnd, pid
        self.check()
        return self.gui.GetWindowText(hwnd)

    def check(self):
        if self.stop.is_set():
            raise ValueError("Stopped.")
        if self.cancelled is not None and self.cancelled():
            raise ValueError("Task stopped.")
        if self.deadline and time.monotonic() >= self.deadline:
            raise ValueError("Task time limit reached.")
        if not self.hwnd or not self.gui.IsWindow(self.hwnd) or self.gui.IsIconic(self.hwnd):
            raise ValueError("Approved window is missing or minimized.")
        _, pid = self.process.GetWindowThreadProcessId(self.hwnd)
        if pid != self.pid:
            raise ValueError("Approved window identity changed.")
        if self.gui.GetClassName(self.hwnd) in ("ConsoleWindowClass", "CASCADIA_HOSTING_WINDOW_CLASS"):
            raise ValueError("Command terminals cannot be controlled by this helper.")
        title = self.gui.GetWindowText(self.hwnd).lower()
        if any(term in title for term in ("powershell", "command prompt", "registry editor")):
            raise ValueError("Shell and security-editor windows cannot be controlled.")
        try:
            self.mouse.failSafeCheck()
        except self.mouse.FailSafeException:
            self.stop.set()
            raise ValueError("Emergency mouse stop activated.") from None

    def rect(self):
        self.check()
        left, top = self.gui.ClientToScreen(self.hwnd, (0, 0))
        _, _, width, height = self.gui.GetClientRect(self.hwnd)
        if width <= 0 or height <= 0:
            raise ValueError("Approved window has no visible client area.")
        return left, top, width, height

    def focus(self):
        self.check()
        if self.gui.GetForegroundWindow() != self.hwnd:
            try:
                self.gui.SetForegroundWindow(self.hwnd)
            except Exception:
                raise ValueError("Select the approved window manually before continuing.") from None
        if self.gui.GetForegroundWindow() != self.hwnd:
            raise ValueError("Windows refused focus; no input was sent.")

    def capture(self):
        import ctypes

        import win32ui
        from PIL import Image, ImageStat

        self.focus()
        rect = self.rect()
        _, _, width, height = rect
        if width * height > 40_000_000:
            raise ValueError("Window is too large to capture.")
        source_handle = self.gui.GetDC(self.hwnd)
        source = win32ui.CreateDCFromHandle(source_handle)
        memory = source.CreateCompatibleDC()
        bitmap = win32ui.CreateBitmap()
        bitmap.CreateCompatibleBitmap(source, width, height)
        old = memory.SelectObject(bitmap)
        try:
            # Print only this window's client area; never fall back to a full-desktop grab.
            from ctypes import wintypes

            print_window = ctypes.windll.user32.PrintWindow
            print_window.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]
            print_window.restype = wintypes.BOOL
            if not print_window(self.hwnd, memory.GetSafeHdc(), 3):
                raise ValueError("This application does not support window-only capture.")
            image = Image.frombuffer("RGB", (width, height), bitmap.GetBitmapBits(True), "raw", "BGRX", 0, 1)
            if sum(ImageStat.Stat(image.resize((64, 64))).stddev) < 1:
                raise ValueError("Window capture is blank; no full-screen fallback is allowed.")
            image.thumbnail((1280, 960))
            for quality in (80, 65, 50):
                output = io.BytesIO()
                image.save(output, "JPEG", quality=quality)
                if len(output.getvalue()) <= 250 * 1024:
                    return Frame(output.getvalue(), *image.size, rect)
            raise ValueError("Screenshot exceeds the upload limit.")
        finally:
            memory.SelectObject(old)
            self.gui.DeleteObject(bitmap.GetHandle())
            memory.DeleteDC()
            source.DeleteDC()
            self.gui.ReleaseDC(self.hwnd, source_handle)

    def execute(self, payload, frame=None):
        from automation_companion import validate_payload

        validate_payload(payload)
        self.focus()
        rect = self.rect()
        if frame is not None and rect != frame.rect:
            raise ValueError("Window moved or resized after observation; no input was sent.")
        left, top, width, height = rect
        operation = payload["operation"]
        if operation == "click":
            x, y = payload["x"], payload["y"]
            if frame is not None:
                if x >= frame.width or y >= frame.height:
                    raise ValueError("Click outside the observed window.")
                x, y = int(x * width / frame.width), int(y * height / frame.height)
            if not 0 <= x < width or not 0 <= y < height:
                raise ValueError("Click outside the approved window.")
            destination = (left + x, top + y)
            hit = self.gui.WindowFromPoint(destination)
            if hit != self.hwnd and not self.gui.IsChild(self.hwnd, hit):
                raise ValueError("Another window covers the click target; no click was sent.")
            self.check()
            self.mouse.click(*destination, clicks=payload["clicks"], interval=0.15)
        elif operation == "scroll":
            destination = (left + width // 2, top + height // 2)
            hit = self.gui.WindowFromPoint(destination)
            if hit != self.hwnd and not self.gui.IsChild(self.hwnd, hit):
                raise ValueError("Another window covers the scroll target.")
            self.mouse.moveTo(*destination)
            self.check()
            self.mouse.scroll(payload["scroll_delta"] // 120)
        elif operation == "type_text":
            for character in payload["text"]:
                self.check()
                if self.gui.GetForegroundWindow() != self.hwnd:
                    raise ValueError("Window focus changed; typing stopped.")
                self.mouse.write(character, interval=0, _pause=False)
                time.sleep(0.02)
        elif operation == "press_key":
            keys = payload["key"].lower().replace("escape", "esc").split("+")
            self.check()
            self.mouse.hotkey(*keys)
        else:
            raise ValueError("This action does not target the selected window.")
