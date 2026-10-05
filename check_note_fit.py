"""Prove every row keeps its single height: each note (to the right of score and readiness) fits in three lines and
no row grows past its minimum. Needs playwright + chromium (CHROME env var for a custom binary).
Usage: python3 check_note_fit.py [width px, default 340] [html]"""
import asyncio, json, os, re, sys
from pathlib import Path
from playwright.async_api import async_playwright
W = int(sys.argv[1]) if len(sys.argv) > 1 else 340
F = str(Path(sys.argv[2] if len(sys.argv) > 2 else Path(__file__).with_name("Vintage_Chart.html")).resolve())
html = open(F, encoding="utf-8").read()
D = json.loads(re.search(r'<script id="data" type="application/json">(.*?)</script>', html, re.S).group(1).replace('<\\/', '</'))
pairs = [(D["nodes"][int(k)]["id"], s) for k, st in D["series"].items() for s in st]

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path=os.environ.get("CHROME") or None, args=["--no-sandbox"])
        pg = await (await b.new_context(viewport={"width": W, "height": 780}, device_scale_factor=2, is_mobile=True, offline=True)).new_page()
        errs, bad, n, tallest = [], [], 0, 0
        pg.on("pageerror", lambda e: errs.append(str(e)))
        await pg.goto("file://" + F)          # a fresh start opens the home page; regions are reached by address
        for nid, s in pairs:
            await pg.evaluate("h => new Promise(r => { location.hash = h; setTimeout(r, 30); })", "#r=" + nid + "&s=" + s)
            res = await pg.evaluate("""()=>[...document.querySelectorAll('.row')].map(r=>{const n=r.querySelector('.rnote');
                return [r.querySelector('.yr').textContent, n?n.textContent:'', n?n.scrollHeight>n.clientHeight+1:false, r.offsetHeight]})""")
            for y, t, over, h in res:
                n += 1; tallest = max(tallest, h)
                if over or h > 43: bad.append((nid, s, y, h, len(t), t))
        print(f"width {W}: {n} rows, {len(bad)} too long (over 3 lines or taller than 42 px), tallest {tallest} px, errors {errs}")
        for x in bad: print(x)
        await b.close()
        return 1 if bad or errs else 0
sys.exit(asyncio.run(main()))
