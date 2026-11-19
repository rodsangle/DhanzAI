import json, re
from playwright.sync_api import sync_playwright
BASE="http://localhost:3100"
AXE=open(__import__("pathlib").Path(__file__).resolve().parents[2] / "node_modules/axe-core/axe.min.js").read()
out=[]
with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
    ctx = b.new_context(viewport={"width":1440,"height":900}); pg = ctx.new_page()
    pg.goto(BASE+"/login"); pg.get_by_label("Work email").fill("dante@rodrech.com"); pg.get_by_role("button", name="Sign in").click(); pg.wait_for_url(BASE+"/")

    # ---------- keyboard only: reach composer, send, wait, search, open a row menu
    pg.goto(BASE+"/"); pg.wait_for_selector("text=What are we making today")
    unfocused=[]; reached=False
    for i in range(40):
        pg.keyboard.press("Tab")
        info = pg.evaluate("""() => { const a=document.activeElement; const cs=getComputedStyle(a);
          const f=a.closest('form'); const fcs=f?getComputedStyle(f):null;
          const visible = cs.outlineStyle!=='none' && cs.outlineWidth!=='0px' || (fcs && fcs.outlineStyle!=='none');
          return {tag:a.tagName, label:a.getAttribute('aria-label')||a.textContent.trim().slice(0,30), visible} }""")
        if not info["visible"]: unfocused.append(info)
        if info["label"]=="" and info["tag"]=="TEXTAREA" or info["tag"]=="TEXTAREA":
            reached=True; break
    out.append(("keyboard: composer reachable by Tab", reached, f"{i+1} tabs"))
    out.append(("keyboard: every focused control shows a focus ring", not unfocused, str(unfocused[:4])))
    pg.keyboard.type("Draft hang tag copy for the olive beanie"); pg.keyboard.press("Enter")
    pg.wait_for_url(re.compile(r"/c/"), timeout=15000)
    pg.wait_for_function("""() => !document.querySelector('[aria-busy="true"]') && !!document.querySelector('button[aria-label="Send message"]')""", timeout=20000)
    out.append(("keyboard: send with Enter and get an answer", True, ""))
    pg.keyboard.press("Control+k"); pg.keyboard.type("lookbook"); pg.wait_for_selector('[role="option"]'); pg.keyboard.press("Enter")
    pg.wait_for_function("() => document.title && location.pathname.startsWith('/c/')")
    pg.wait_for_selector("text=Shot list")
    out.append(("keyboard: ⌘K search and open with Enter", True, ""))
    # Esc stops a stream from the composer
    pg.get_by_label("Message Dhanz GPT").filter(visible=True).focus()
    pg.keyboard.type("/slow plan the shoot day"); pg.keyboard.press("Enter")
    pg.wait_for_selector('button[aria-label="Stop answering"]'); pg.wait_for_timeout(1200)
    pg.get_by_label("Message Dhanz GPT").filter(visible=True).focus(); pg.keyboard.press("Escape")
    pg.wait_for_selector("text=Stopped", timeout=8000)
    out.append(("keyboard: Esc stops the answer", True, ""))

    # ---------- axe on each built screen, light and dark
    conv = pg.url
    proj = pg.evaluate("() => document.querySelector('a[href^=\"/project/\"]')?.getAttribute('href')")
    pages = [("/", "S03"), (conv.replace(BASE,""), "S04"), (proj, "S09"), ("/library","S11"), ("/images","S13"), ("/scheduled","S18 stub")]
    for theme in ("light","dark"):
        pg.evaluate(f"localStorage.setItem('theme','{theme}')")
        for path, sid in pages:
            pg.goto(BASE+path); pg.wait_for_timeout(900)
            pg.evaluate(f"document.documentElement.classList.toggle('dark', {str(theme=='dark').lower()}); document.documentElement.classList.toggle('light', {str(theme=='light').lower()})")
            pg.add_script_tag(content=AXE)
            res = pg.evaluate("""async () => { const r = await axe.run(document, {runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21a','wcag21aa']}}); return r.violations.map(v=>({id:v.id,impact:v.impact,n:v.nodes.length,help:v.help,t:v.nodes.slice(0,2).map(n=>n.target.join(' '))})) }""")
            out.append((f"axe {theme} {sid} {path[:30]}", not res, json.dumps(res)[:600]))
    # dialogs
    pg.evaluate("localStorage.setItem('theme','light')")
    pg.goto(BASE+"/"); pg.wait_for_timeout(600)
    pg.get_by_role("button", name=re.compile("Dante")).click(); pg.get_by_role("menuitem", name="Settings").click(); pg.wait_for_timeout(400)
    pg.add_script_tag(content=AXE)
    res = pg.evaluate("""async () => (await axe.run(document.querySelector('[role=dialog]'), {runOnly:{type:'tag',values:['wcag2a','wcag2aa']}})).violations.map(v=>({id:v.id,n:v.nodes.length,help:v.help,t:v.nodes.slice(0,2).map(n=>n.target.join(' '))}))""")
    out.append(("axe settings dialog", not res, json.dumps(res)[:600]))
    pg.goto(BASE+"/login"); pg.wait_for_timeout(500); pg.add_script_tag(content=AXE)
    res = pg.evaluate("""async () => (await axe.run(document, {runOnly:{type:'tag',values:['wcag2a','wcag2aa']}})).violations.map(v=>({id:v.id,n:v.nodes.length,help:v.help,t:v.nodes.slice(0,2).map(n=>n.target.join(' '))}))""")
    out.append(("axe login S02", not res, json.dumps(res)[:600]))
    b.close()
for name, ok, d in out:
    print(("PASS " if ok else "FAIL ")+name+("" if ok else "  "+d))
