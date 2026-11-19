import json, re
from playwright.sync_api import sync_playwright
BASE="http://localhost:3100"; AXE=open(__import__("pathlib").Path(__file__).resolve().parents[2] / "node_modules/axe-core/axe.min.js").read()
with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
    pg = b.new_page(viewport={"width":1440,"height":900})
    pg.goto(BASE+"/login"); pg.get_by_label("Work email").fill("dante@rodrech.com"); pg.get_by_role("button", name="Sign in").click(); pg.wait_for_url(BASE+"/")
    ids = pg.evaluate("fetch('/api/conversations').then(r=>r.json()).then(xs=>xs.map(x=>[x.id,x.title]))")
    # make one with a code block + image in it
    pg.goto(BASE+"/"); box=pg.get_by_label("Message Dhanz GPT").filter(visible=True)
    box.fill("write the json for the drop"); box.press("Enter"); pg.wait_for_url(re.compile("/c/")); pg.wait_for_selector('button[aria-label="Send message"]', timeout=20000)
    pg.get_by_role("button", name="Add files and tools").click(); pg.get_by_role("menuitem", name="Create an image").click()
    box.fill("bone fitted cap on a white plinth"); box.press("Enter"); pg.wait_for_timeout(500); pg.wait_for_selector('button[aria-label="Send message"]', timeout=20000)
    pg.wait_for_timeout(800)
    targets = [pg.url] + [BASE+"/c/"+i for i,t in ids if t in ("Lookbook shot list","Hang tag copy, round 3")]
    for theme in ("light","dark"):
        for u in targets:
            pg.goto(u); pg.wait_for_selector("article"); pg.wait_for_timeout(700)
            pg.evaluate(f"document.documentElement.classList.toggle('dark', {str(theme=='dark').lower()}); document.documentElement.classList.toggle('light', {str(theme=='light').lower()})")
            pg.add_script_tag(content=AXE)
            res = pg.evaluate("""async () => (await axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21a','wcag21aa']}})).violations.map(v=>({id:v.id,impact:v.impact,n:v.nodes.length,help:v.help,t:v.nodes.slice(0,3).map(n=>n.target.join(' ')),h:v.nodes.slice(0,1).map(n=>n.failureSummary)}))""")
            print(("PASS " if not res else "FAIL ")+f"axe {theme} S04 {u.split('/c/')[1][:8]} " + ("" if not res else json.dumps(res)[:900]))
    pg.goto(targets[0]); pg.wait_for_selector("article img"); pg.screenshot(path="" + __import__("os").environ.get("SHOTS", "../replica/clone-screens") + "/S04-image-code.png", full_page=False)
    b.close()
