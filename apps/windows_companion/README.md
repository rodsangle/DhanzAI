# Dhanz Windows control panel

Python 3.12+ on Windows 11 is required. The helper uses outbound HTTPS only; no
router or inbound firewall port is needed. It is source code, not a signed EXE.

## Two modes

**Browser requests:** the existing AWS `/api/v1/automation` queue supports individual
app/website/mouse/keyboard requests. Each queued request still needs local approval.
Notepad and Calculator work without selecting a window; mouse/keyboard requests
require selecting the target window first. Chrome, Explorer and remote
`capture_window` requests are not implemented in this client.

**AI task mode:** enter an explicit goal in the Windows control panel, select ONE
window, and enable screen sharing. The helper sends a window-only JPEG to the
new authenticated AWS `/api/v1/desktop/next` planner, gets one proposed step,
executes an approved step, observes again, and repeats. The planner does not call
other tools and does not execute code. Tasks start in this panel, not automatically
from arbitrary browser chat text. They stop after 20 steps or five minutes.

This second mode requires deployment of `backend/app/api/routes/desktop.py` and
`DESKTOP_PLANNER_ENABLED=true`, plus a vision-capable model. Existing individual
browser commands keep working if the planner is not installed. No database
migration is needed. Preserve the custom 0010 AWS image and all its Compose
settings; do not replace it with the older public checkout.

## Installation and use

If a `windows-x64.zip` executable asset is present in the preview release, extract
the entire folder and run `DhanzPCCompanion.exe` inside it. Keep its bundled files
together. That build includes Python/dependencies; it is an unsigned preview and
is separate from the main DHANZ AI Windows app. The source instructions below are
for the `windows-companion-source` ZIP, not for that executable bundle.

Keep all these files together: `automation_companion.py`, `desktop_control.py`,
`task_control.py`, `start-companion.cmd`, `requirements-desktop.txt`.

In Windows PowerShell, from that folder:

```powershell
py -3 -m pip install -r requirements-desktop.txt
py -3 -m py_compile automation_companion.py desktop_control.py task_control.py
py -3 automation_companion.py --server https://dhanzai.com
```

Sign in using the same DHANZ account as the browser, not the OpenAI key. The
password is not saved; access/refresh tokens use Windows DPAPI under the current
Windows user at `%LOCALAPPDATA%\DhanzAI\automation-session.bin`. This is a normal
account session with normal account privileges, not a device-restricted token.
Use one helper per account initially: the existing queue is account-scoped.
Revoke the helper's login through Dhanz's account/device security controls. Use
`--login` to sign in again. Removing the local file alone is not revocation.

Select **Select target window**, then click the target application within three
seconds. Mouse coordinates for browser requests are relative to that window's
client area. AI plans use screenshot coordinates that are mapped back to the
same client area. Minimized/closed/replaced windows, changed capture geometry,
failed focus and clicks covered by other windows stop input. Known shell window
classes/titles are blocked. This is a bounded UI controller, not an OS sandbox.

## Automatic approval

Manual approval is the default on every launch. The **Automatic navigation**
checkbox must be enabled locally. It allows ONLY planner steps classified as
navigation clicks/scrolls for at most five minutes and 20 automatic steps in the
selected window. It does not auto-approve unrelated queued browser commands.
Typing, keyboard shortcuts, consequential/uncertain actions, and goals/reasons
matching sensitive operations still prompt. After keyboard/text input, all later
steps require confirmation too. Automation is disarmed when the task ends/errors,
when the target is changed, or when Stop is pressed; settings are not persisted.

Classification and coordinates come from an AI model and can be wrong. Read the
selected window and local prompts. This does not guarantee that every consequential
button is identifiable; use manual mode for sensitive work.

**Stop:** use **Stop task / disable auto**, **Stop helper**, close the panel, press
Ctrl+Alt+Esc, or move the pointer to the primary screen's upper-left corner.
Native input checks stop state before actions and between typed characters.
An already sent click/key or launched application cannot be undone.

## Screen sharing, costs and limitations

Screen sharing is off by default and requires an explicit checkbox for task mode.
Unchecking it stops the current task. Only the selected window's client area is
captured with PrintWindow—there is no full-desktop screenshot fallback. Apps with
blank/unsupported window capture stop the task. Screenshots are downscaled to
1280x960, capped at 250 KiB, and sent to AWS and its selected AI provider. The new
planner does not save them to the database; provider retention policies still
apply. Keep confidential information out of the selected window. Each planning
step uses the configured model API and can incur charges. Local-only privacy
settings require a local vision model; unknown modes fail closed to local vision.

The model can choose clicks, scrolling, single-line ASCII typing and a restricted
key list. No shell-command tool, arbitrary executable launcher, direct file reads
or writes, unattended operation, full-desktop capture or stealth background mode
is provided. UI interactions can still change data, so review confirmations.

Claims/results are not automatically retried when uncertain. Inspect the PC before
repeating a task. A queued action whose result upload fails may remain executing.
The backend's existing atomic claim prevents two helpers from executing the same
queued request, but it does not bind requests to a named PC. Do not approve requests
intended for another machine.

## Validation

Portable tests cover opt-in/bounded automatic navigation, stop after model response,
confirmation after typing, screenshot consent, payload validation, coordinate mapping,
occlusion/geometry guards, exact queue claims, login refresh and no replay. Native
DPAPI tests run on Windows CI; native capture/input/dialog smoke tests still require
Windows. Test on an ordinary low-risk window before relying on task mode. No native
Windows checks have run in the Linux build workspace and this update is not installed
on the user's PC or AWS server by writing these files.
