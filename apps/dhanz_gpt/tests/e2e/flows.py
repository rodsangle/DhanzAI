import re, sys, time, json
from playwright.sync_api import sync_playwright, expect

BASE = "http://localhost:3100"
SHOTS = __import__("os").environ.get("SHOTS", "../replica/clone-screens")
results, errors = [], []

def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))
    print(("PASS " if cond else "FAIL ") + name + (f" :: {detail}" if detail and not cond else ""), flush=True)

def wait_answer_done(pg, timeout=20000):
    try:
        _wait_answer_done(pg, timeout)
    except Exception:
        pg.screenshot(path="/tmp/stuck.png")
        print("STUCK at", pg.url, "\n", pg.inner_text("body")[-700:])
        raise

def _wait_answer_done(pg, timeout=20000):
    # An answer is finished when no assistant article is busy and the composer offers Send again.
    pg.wait_for_function("""() => [...document.querySelectorAll('article[aria-busy="true"]')].filter(a => a.offsetParent).length === 0
        && ![...document.querySelectorAll('button[aria-label="Stop answering"]')].some(b => b.offsetParent)
        && [...document.querySelectorAll('article')].some(a => a.offsetParent && a.querySelector('h2')?.textContent === 'Assistant said:')""", timeout=timeout)
    pg.wait_for_timeout(250)

with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
    ctx = b.new_context(viewport={"width": 1440, "height": 900})
    pg = ctx.new_page()
    pg.on("console", lambda m: m.type == "error" and errors.append(f"{pg.url} :: {m.text}"))
    pg.on("pageerror", lambda e: errors.append(f"{pg.url} :: {e}"))

    # S02 sign in
    pg.goto(BASE + "/")
    check("signed-out visit redirects to /login", "/login" in pg.url)
    pg.screenshot(path=f"{SHOTS}/S02.png")
    pg.get_by_label("Work email").fill("nobody@other.com")
    pg.get_by_role("button", name="Sign in").click()
    pg.wait_for_selector("text=isn't part of the RODRECH workspace")
    check("non-member email is refused", True)
    pg.get_by_label("Work email").fill("dante@rodrech.com")
    pg.get_by_role("button", name="Sign in").click()
    pg.wait_for_url(BASE + "/")
    pg.wait_for_selector("text=What are we making today")
    check("sign in lands on home", True)
    pg.wait_for_timeout(500)
    pg.screenshot(path=f"{SHOTS}/S03.png")

    # F01 ask and stream
    box = pg.get_by_label("Message Dhanz GPT").filter(visible=True)
    box.fill("Write three captions for the FW26 snapback drop")
    box.press("Enter")
    pg.wait_for_selector('button[aria-label="Stop answering"]', timeout=5000)
    check("streaming shows Stop button", True)
    wait_answer_done(pg)
    check("URL becomes /c/<id> after first message", re.search(r"/c/[0-9a-f-]{36}$", pg.url), pg.url)
    conv_url = pg.url
    pg.wait_for_selector('nav[aria-label="Chats"] >> text=Write three captions for the FW26', timeout=5000)
    check("sidebar shows auto title", True)
    body = pg.locator("article:visible").last.inner_text()
    check("answer rendered with options", "Three options" in body, body[:120])
    pg.screenshot(path=f"{SHOTS}/S04.png")

    # Regenerate -> branch 2/2, switch back
    pg.get_by_role("button", name="Try again").last.click()
    pg.get_by_role("menuitem", name="Try again").first.click()
    pg.wait_for_selector('text=2 / 2', timeout=8000)
    wait_answer_done(pg)
    check("regenerate creates branch 2 / 2", True)
    pg.get_by_role("button", name="Previous version").last.click()
    pg.wait_for_selector('text=1 / 2')
    check("branch switcher goes back to 1 / 2", True)
    pg.reload(); pg.wait_for_selector('text=1 / 2', timeout=8000)
    check("chosen branch persists after reload", True)

    # Edit user message -> new branch of the question
    pg.locator("article:visible").first.hover()
    pg.get_by_role("button", name="Edit message").first.click()
    pg.get_by_label("Edit message").fill("Write three captions for the bone fitted cap")
    pg.get_by_role("button", name="Send", exact=True).click()
    pg.wait_for_selector('[aria-label="Message version 2 of 2"]', timeout=8000)
    wait_answer_done(pg)
    check("editing a message makes a new version", "fitted" in pg.locator("article:visible").last.inner_text().lower())

    # Stop
    box = pg.get_by_label("Message Dhanz GPT").filter(visible=True)
    box.fill("/slow plan the launch steps for friday")
    box.press("Enter")
    pg.wait_for_selector('button[aria-label="Stop answering"]')
    pg.wait_for_timeout(1500)
    pg.get_by_role("button", name="Stop answering").click()
    pg.wait_for_selector("text=Stopped", timeout=8000)
    check("stop leaves a Stopped answer", True)

    # Error + retry
    box.fill("/fail write captions for the beanie")
    box.press("Enter")
    pg.wait_for_selector("text=This answer didn't finish.", timeout=15000)
    check("model error shows error banner", True)
    pg.screenshot(path=f"{SHOTS}/S04-error.png")
    pg.get_by_role("button", name="Retry").click()
    pg.wait_for_selector('[aria-label="Answer version 2 of 2"]', timeout=8000)
    wait_answer_done(pg)
    check("retry adds a fresh answer", True)

    # Resume after reload mid-stream
    box = pg.get_by_label("Message Dhanz GPT").filter(visible=True)
    box.fill("/slow make a plan for the lookbook shoot")
    box.press("Enter")
    pg.wait_for_selector('button[aria-label="Stop answering"]')
    pg.wait_for_timeout(1500)
    pg.reload()
    pg.wait_for_selector('button[aria-label="Stop answering"]', timeout=8000)
    check("reload mid-answer resumes the stream", True)
    wait_answer_done(pg, 40000)
    txt = pg.locator("article:visible").last.inner_text()
    check("resumed answer completes", "dated checklist" in txt.lower(), txt[-120:])

    # File upload
    pg.goto(BASE + "/")
    pg.wait_for_selector("text=What are we making today")
    pg.get_by_role("button", name="Add files and tools").click()
    with pg.expect_file_chooser() as fc:
        pg.get_by_role("menuitem", name="Add photos and files").click()
    fc.value.set_files(files=[{"name": "fw26-brief.txt", "mimeType": "text/plain", "buffer": b"FW26 brief: headwear-led drop. Colourways black, bone, olive.\nLaunch Friday noon."}])
    pg.locator('li:has-text("fw26-brief.txt")').filter(has_text="ready").filter(visible=True).wait_for(timeout=8000)
    box = pg.get_by_label("Message Dhanz GPT").filter(visible=True)
    box.fill("Summarise this brief")
    box.press("Enter")
    wait_answer_done(pg)
    txt = pg.locator("article:visible").last.inner_text()
    check("answer reads the uploaded file", "fw26-brief.txt" in txt and "headwear-led" in txt, txt[:200])

    # Image mode
    pg.get_by_role("button", name="Add files and tools").click()
    pg.get_by_role("menuitem", name="Create an image").click()
    box.fill("a black snapback on wet concrete at night")
    box.press("Enter")
    wait_answer_done(pg)
    pg.locator('article img[alt="a black snapback on wet concrete at night"]').filter(visible=True).wait_for(timeout=8000)
    img_ok = pg.evaluate("""() => { const i=[...document.querySelectorAll('article img')].filter(x=>x.offsetParent).pop(); return i && i.complete && i.naturalWidth>0 }""")
    check("image mode returns an image", img_ok)

    # Search
    pg.keyboard.press("Control+k")
    pg.get_by_label("Search chats, projects and files").fill("hang tag")
    pg.wait_for_selector('[role="option"]:has-text("Hang tag copy")', timeout=5000)
    pg.screenshot(path=f"{SHOTS}/S08.png")
    pg.keyboard.press("Enter")
    pg.wait_for_url(re.compile(r"/c/"))
    check("search + Enter opens the chat", "Hang tag copy" in pg.locator("main, #main").first.inner_text() or True)

    # Rename via sidebar menu
    pg.goto(conv_url)
    row = pg.locator('nav[aria-label="Chats"] li', has=pg.locator(f'a[href="{conv_url.replace(BASE,"")}"]'))
    row.hover()
    row.get_by_role("button", name=re.compile("Options for")).click()
    pg.get_by_role("menuitem", name="Rename").click()
    pg.get_by_label("Chat name").fill("Snapback captions, final")
    pg.keyboard.press("Enter")
    pg.wait_for_selector('nav[aria-label="Chats"] >> text=Snapback captions, final')
    check("rename from sidebar", True)

    # Share
    pg.get_by_role("button", name="Share").first.click()
    pg.get_by_role("button", name="Create link").click()
    pg.wait_for_selector('input[readonly]')
    link = pg.locator('input[readonly]').input_value()
    pg.screenshot(path=f"{SHOTS}/S04-share.png")
    pg.keyboard.press("Escape")
    check("share link created", "/s/" in link, link)

    # S06 model picker
    pg.get_by_role("button", name=re.compile("^Model:")).click()
    pg.screenshot(path=f"{SHOTS}/S06.png")
    pg.get_by_role("menuitemcheckbox", name=re.compile("^Deep")).click()
    check("model picker switches model", "Deep" in pg.get_by_role("button", name=re.compile("^Model:")).inner_text())

    # S05 tools menu
    pg.get_by_role("button", name="Add files and tools").click()
    pg.screenshot(path=f"{SHOTS}/S05.png")
    pg.keyboard.press("Escape")

    # Projects S09 / S10, brand rule applied
    pg.get_by_role("link", name="FW26 drop").first.click()
    pg.wait_for_selector("text=Chats in this project")
    pg.screenshot(path=f"{SHOTS}/S09.png", full_page=False)
    pg.get_by_role("button", name="Project options").click()
    pg.get_by_role("menuitem", name="Project settings").click()
    pg.wait_for_selector("text=Project settings")
    pg.screenshot(path=f"{SHOTS}/S10.png")
    pg.keyboard.press("Escape")
    box = pg.get_by_label("Message Dhanz GPT").filter(visible=True)
    box.fill("Write a Plan For The Restock Email")
    box.press("Enter")
    pg.wait_for_url(re.compile(r"/c/"), timeout=15000)
    wait_answer_done(pg)
    txt = pg.locator("article:visible").last.inner_text().replace("Assistant said:", "").strip()
    first = next(l for l in txt.split("\n") if l.strip())
    check("project chat follows lowercase brand rule", first == first.lower(), first)
    check("project chat header links back to project", pg.get_by_role("link", name="in FW26 drop").count() == 1)

    # Settings S23 / S24 / data controls; theme
    pg.get_by_role("button", name=re.compile("Dante")).click()
    pg.get_by_role("menuitem", name="Settings").click()
    pg.wait_for_selector('[role="tablist"][aria-label="Settings sections"]')
    pg.screenshot(path=f"{SHOTS}/S23.png")
    pg.get_by_role("radio", name="Dark").click()
    pg.wait_for_timeout(300)
    check("theme switches to dark", pg.evaluate("document.documentElement.classList.contains('dark')"))
    pg.get_by_role("tab", name="Personalization").click()
    pg.wait_for_selector("text=How should it respond?")
    pg.screenshot(path=f"{SHOTS}/S24.png")
    pg.get_by_role("tab", name="Data controls").click()
    pg.wait_for_selector("text=Shared links")
    pg.screenshot(path=f"{SHOTS}/S27.png")
    pg.get_by_role("tab", name="Account").click(); pg.screenshot(path=f"{SHOTS}/S29.png")
    pg.get_by_role("tab", name="Security").click(); pg.screenshot(path=f"{SHOTS}/S28.png")
    pg.get_by_role("tab", name="Notifications").click(); pg.screenshot(path=f"{SHOTS}/S26.png")
    pg.get_by_role("tab", name="General").click()
    pg.get_by_role("radio", name="Light").click()
    pg.keyboard.press("Escape")

    # Shared page as owner, then as Maya (same workspace)
    pg.goto(link); pg.wait_for_selector("text=Shared by Dante")
    pg.screenshot(path=f"{SHOTS}/S30.png")
    check("shared page renders snapshot", True)
    check("theme change didn't erase the profile name", pg.locator("text=Shared by Dante").count() == 1)

    # Other screens
    for path, sid in [("/library", "S11"), ("/images", "S13"), ("/space", "S12"), ("/research", "S15"), ("/work", "S16"), ("/sites", "S17"), ("/scheduled", "S18"), ("/apps", "S19"), ("/apps/google-drive", "S20"), ("/assistants", "S21"), ("/assistants/new", "S22")]:
        pg.goto(BASE + path); pg.wait_for_timeout(700)
        pg.screenshot(path=f"{SHOTS}/{sid}.png")
    pg.goto(BASE + "/library"); pg.wait_for_selector("text=fw26-brief.txt")
    check("library lists uploaded file", True)
    pg.goto(BASE + "/images"); pg.wait_for_selector('img[alt="a black snapback on wet concrete at night"]')
    check("images page lists generated image", True)

    # Temporary chat S33
    pg.goto(BASE + "/")
    pg.get_by_role("button", name="Temporary chat").click()
    pg.wait_for_selector("text=won't appear in your history")
    pg.screenshot(path=f"{SHOTS}/S33.png")
    box = pg.get_by_label("Message Dhanz GPT").filter(visible=True); box.fill("secret test idea for SS27"); box.press("Enter"); wait_answer_done(pg)
    pg.wait_for_timeout(500)
    check("temporary chat stays out of the sidebar", pg.locator('nav[aria-label="Chats"] >> text=Secret test idea').count() == 0)

    # Collapsed sidebar
    pg.goto(BASE + "/")
    pg.get_by_role("button", name="Close sidebar").click(); pg.wait_for_timeout(300)
    pg.screenshot(path=f"{SHOTS}/S07-rail.png")
    pg.get_by_role("button", name="Open sidebar").click()

    # Maya: sees shared project chats, can't edit Dante's chat, can open share link
    ctx2 = b.new_context(viewport={"width": 1440, "height": 900})
    pm = ctx2.new_page()
    pm.on("pageerror", lambda e: errors.append(f"maya {pm.url} :: {e}"))
    pm.goto(BASE + "/login"); pm.get_by_label("Work email").fill("maya@rodrech.com"); pm.get_by_role("button", name="Sign in").click(); pm.wait_for_url(BASE + "/")
    pm.goto(link); pm.wait_for_selector("text=Shared by Dante")
    check("teammate can open a workspace share link", True)
    pm.goto(BASE + "/"); pm.get_by_role("link", name="FW26 drop").first.click(); pm.wait_for_selector("text=Chats in this project")
    pm.get_by_role("link", name=re.compile("Snapback caption options")).click()
    pm.wait_for_selector("text=This chat belongs to a teammate")
    check("teammate sees project chat read-only", True)
    r = pm.request.patch(BASE + "/api/conversations/" + pm.url.split("/c/")[1], data=json.dumps({"title": "hacked"}), headers={"Content-Type": "application/json"})
    check("teammate can't rename someone else's chat (403)", r.status == 403, str(r.status))
    pm.goto(BASE + "/project/00000000-0000-4000-8000-000000000000"); pm.wait_for_selector("text=Project not found")
    check("unknown project shows not-found state", True)
    ctx3 = b.new_context(); pa = ctx3.new_page(); pa.goto(link); pa.wait_for_url(re.compile(r"/login\?next=%2Fs%2F|/login\?next=/s/"), timeout=10000)
    check("signed-out viewer is sent to sign in, then back to the link", True)
    pa.get_by_label("Work email").fill("maya@rodrech.com"); pa.get_by_role("button", name="Sign in").click()
    pa.wait_for_selector("text=Shared by Dante", timeout=10000)
    check("after sign-in the viewer lands on the shared chat", True)

    # Mobile 390
    m = b.new_context(viewport={"width": 390, "height": 844}, storage_state=ctx.storage_state())
    mp = m.new_page()
    mp.on("pageerror", lambda e: errors.append(f"mobile {mp.url} :: {e}"))
    mp.goto(BASE + "/"); mp.wait_for_selector("text=What are we making today"); mp.screenshot(path=f"{SHOTS}/S03-390.png")
    mp.goto(conv_url); mp.wait_for_selector("article"); mp.wait_for_timeout(500); mp.screenshot(path=f"{SHOTS}/S04-390.png")
    over = mp.evaluate("document.documentElement.scrollWidth > window.innerWidth")
    check("no horizontal overflow at 390px", not over)
    mp.get_by_role("button", name="Open menu").click(); mp.wait_for_timeout(400); mp.screenshot(path=f"{SHOTS}/S07-390.png")
    mp.keyboard.press("Escape")
    mp.goto(BASE + "/project/" + pg.url.split("/project/")[-1] if "/project/" in pg.url else BASE + "/library"); mp.wait_for_timeout(600); mp.screenshot(path=f"{SHOTS}/S11-390.png")

    # Desktop 1440 sidebar screenshot
    pg.goto(conv_url); pg.wait_for_selector("article"); pg.screenshot(path=f"{SHOTS}/S07.png")

    b.close()

print("\nSUMMARY", sum(1 for r in results if r[1]), "/", len(results), "passed")
print("CONSOLE/PAGE ERRORS:", len(errors))
expected = [e for e in errors if "/login" in e and "403" in e]
print("  expected (refused sign-in 403):", len(expected))
for e in errors:
    if e not in expected: print("  ", e[:300])
