#!/usr/bin/env python3
"""Vintage chart dashboard generator: two CSVs in, one self-contained offline HTML file out.

    python3 build_vintage_dashboard.py [--chart inputs/dashboard_chart.csv]
                                       [--regions inputs/dashboard_regions.csv]
                                       [--out Vintage_Chart.html]

Standard library only. The HTML has the data embedded and makes no network requests, so it works fully offline
(copy it to the phone and open it from My Files). Readiness categories are worked out in the page from the
phone's date, so the file does not go stale as years pass; re-run only when the chart data changes.

Display rules (agreed): score_display shown exactly as exported; sorting on score_dec; no Wine-Searcher figures;
"no source" notes and blank notes show nothing. No tap-to-expand: each row shows year, score, readiness, style tag
and the note to the right, three lines at most (notes kept to 48 characters; check_note_fit.py proves the fit). No confidence marking.
"""
import argparse, csv, json, re, sys
from datetime import date
from pathlib import Path

CHART_COLS = ["node_id", "node_path", "style", "vintage", "score_display", "score_dec", "confidence", "n_voices",
              "voices", "chart_cell", "youthful_from", "at_best_from", "mature_from", "past_best_from",
              "readiness_basis", "borrowed_from", "readiness_sources", "wa_irregular", "variability", "style_tag",
              "note", "sources"]
REGION_COLS = ["node_id", "parent_id", "depth", "node_type", "name", "full_path", "aliases", "cellar_wines"]
STARS = [(36, 3), (12, 2), (1, 1)]   # bottles held in a region incl. its sub-regions: 3+ cases, 1-3 cases, under a case
TAGS = ["Powerful & structured", "Ripe & opulent", "Classic & balanced", "Refined & elegant", "Lean & mineral"]
STYLE_ORDER = ["Red", "White", "Rosé", "Sparkling", "Sweet", "Fortified", "Still", "All"]
CONF = {"low": 0, "medium": 1, "high": 2}
BASIS = {"source": 0, "combined": 1, "borrowed": 2, "estimated": 3}
CRITIC = {"WA": "Wine Advocate", "WS": "Wine Spectator", "WSw": "Wine Spectator wallet card",
          "WE": "Wine Enthusiast", "WSG": "Wine Scholar Guild", "BBR": "Berry Bros & Rudd", "Decanter": "Decanter",
          "Langton's": "Langton's", "Marasby": "Marasby", "Roll-up^": "Roll-up of sub-regions"}
CALL = {"r: ready": "ready", "c: caution/past peak": "caution / past peak", "t: tannic/youthful": "tannic, youthful",
        "e: early maturing": "early maturing", "i: irregular": "irregular", "nyr": "not yet ready",
        "nr": "not ready", "best": "at best", "youth": "youthful", "mature": "mature"}
WINE_SEARCHER = re.compile(r"wine[\s-]?searcher|\bW-S\b|\bWSR\b", re.I)


def read(path, cols):
    with open(path, newline="", encoding="utf-8-sig") as f:
        r = csv.DictReader(f)
        missing = [c for c in cols if c not in (r.fieldnames or [])]
        if missing:
            sys.exit(f"{path}: missing columns {missing}")
        return list(r)


def main():
    here = Path(__file__).resolve().parent
    ap = argparse.ArgumentParser()
    ap.add_argument("--chart", default=str(here.parent / "inputs" / "dashboard_chart.csv"))
    ap.add_argument("--regions", default=str(here.parent / "inputs" / "dashboard_regions.csv"))
    ap.add_argument("--cellar", default=str(here.parent / "inputs" / "dashboard_cellar.csv"),
                    help="optional: node_id, style, vintage, wines held (from the engine's cellar tables)")
    ap.add_argument("--notes", nargs="*", default=sorted(str(x) for x in (here.parent / "inputs").glob("vintage_notes_B*.csv")),
                    help="note batch files (node_id, style, vintage, style_tag, note, sources) laid over the chart's notes")
    ap.add_argument("--out", default=str(here / "Vintage_Chart.html"))
    ap.add_argument("--pwa", default="", help="also write an installable web-app folder here (for GitHub Pages)")
    a = ap.parse_args()

    regions = read(a.regions, REGION_COLS)
    chart = read(a.chart, CHART_COLS)
    idx = {r["node_id"]: i for i, r in enumerate(regions)}
    parent = {r["node_id"]: r["parent_id"] for r in regions}
    name = {r["node_id"]: r["name"] for r in regions}
    held = {}
    if a.cellar and Path(a.cellar).exists():
        for r in read(a.cellar, ["node_id", "style", "vintage", "wines"]):
            k = (r["node_id"], r["style"], int(r["vintage"]))
            held[k] = held.get(k, 0) + int(r["wines"] or 0)
    overlay = {}
    for f in a.notes:
        for r in read(f, ["node_id", "style", "vintage", "style_tag", "note", "sources"]):
            if r["style_tag"].strip() or r["note"].strip() or r["sources"].strip():
                overlay[(r["node_id"], r["style"], int(r["vintage"]))] = r
    changed = 0
    for r in chart:
        o = overlay.get((r["node_id"], r["style"], int(r["vintage"])))
        if o and (o["style_tag"], o["note"], o["sources"]) != (r["style_tag"], r["note"], r["sources"]):
            r["style_tag"], r["note"], r["sources"] = o["style_tag"], o["note"], o["sources"]; changed += 1
    unknown = sorted({r["node_id"] for r in chart} - set(idx))
    if unknown:
        sys.exit(f"chart nodes not in region tree: {unknown}")

    def ancestor(node, n):
        for _ in range(n):
            node = parent.get(node) or node
        return node

    dropped = 0
    labels = []

    def lab(t):  # intern repeated labels to keep the file small
        if t not in labels:
            labels.append(t)
        return labels.index(t)

    def voices(node, s):
        nonlocal dropped
        out = []
        for part in filter(None, (p.strip() for p in s.split(";"))):
            key, _, val = part.rpartition("=")
            if WINE_SEARCHER.search(key):
                dropped += 1; continue
            m = re.match(r"^(.*?)(?:\+(\d+))?$", key)
            base, up = m.group(1), int(m.group(2) or 0)
            d = re.match(r"derived: (.*?) \((.*?)\)$", base)
            if d:
                who = d.group(1).replace("Other press commentary", "Press commentary")
                label = f"{who} (read from text)"
            else:
                label = CRITIC.get(base, base)
            via = idx[ancestor(node, up)] if up else -1
            out.append([lab(label), via, round(float(val), 2)])
        return out

    def calls(s):
        out = []
        for part in filter(None, (p.strip() for p in s.split(";"))):
            k, _, v = part.partition("=")
            if WINE_SEARCHER.search(k):
                continue
            out.append(lab(f"{CRITIC.get(k, k)}: {CALL.get(v.lower(), v.lower())}"))
        return out

    series = {}
    for r in chart:
        node, style = r["node_id"], r["style"]
        src, note, tag = r["sources"].strip(), r["note"].strip(), r["style_tag"].strip()
        if src.lower().startswith("no source") or note.lower().startswith("no source"):
            src = note = tag = ""
        if WINE_SEARCHER.search(src):
            src = "; ".join(p for p in src.split(";") if not WINE_SEARCHER.search(p)).strip("; ")
        basis = r["readiness_basis"]
        b = BASIS[basis.split(" ")[0]] + (4 if "conflict" in basis else 0)
        flags = (1 if r["chart_cell"] == "cellar only" else 0) | (2 if r["wa_irregular"] == "Y" else 0)
        row = [int(r["vintage"]), r["score_display"], float(r["score_dec"]), CONF[r["confidence"]],
               int(r["youthful_from"]), int(r["at_best_from"]), int(r["mature_from"]), int(r["past_best_from"]),
               b, idx.get(r["borrowed_from"], -1), flags, TAGS.index(tag) if tag else -1, note, src,
               voices(node, r["voices"]), calls(r["readiness_sources"]),
               held.get((node, style, int(r["vintage"])), 0)]
        sd = series.setdefault(idx[node], {}).setdefault(style, {"v": "", "r": []})
        sd["v"] = sd["v"] or r["variability"]
        sd["r"].append(row)
    # Roll-up: a row with no note of its own shows its sub-regions' sourced notes for the same style and vintage
    # (an "All styles" row also takes the same region's other styles, and sub-regions' notes of any style).
    own, kids_of = {}, {}
    for k, st in series.items():
        for style, sd in st.items():
            for row in sd["r"]:
                if row[11] >= 0 or row[12]:
                    own[(k, style, row[0])] = [row[11], row[12], row[13]]
    for r in regions:
        kids_of.setdefault(r["parent_id"], []).append(idx[r["node_id"]])

    def desc(k):
        out = []
        for c in kids_of.get(regions[k]["node_id"], []):
            out += [c] + desc(c)
        return out
    rolled = borrowed_notes = 0
    for k, st in series.items():
        d = desc(k)
        for style, sd in st.items():
            others = [x for x in STYLE_ORDER if x != style] if style == "All" else []
            for row in sd["r"]:
                items = []
                if row[11] < 0 and not row[12]:
                    items += [[k, s2] + own[(k, s2, row[0])] for s2 in others if (k, s2, row[0]) in own]
                    for c in d:
                        for s2 in (STYLE_ORDER if style == "All" else [style]):
                            if (c, s2, row[0]) in own:
                                items.append([c, s2 if style == "All" else ""] + own[(c, s2, row[0])])
                merged = []  # one entry per distinct note: batch notes were often written once for several regions
                for it in items:
                    m = next((x for x in merged if x[1:4] == it[1:4]), None)
                    if m:
                        m[0].append(it[0]); m[4] = m[4] if it[4] in m[4] else "; ".join(filter(None, [m[4], it[4]]))
                    else:
                        merged.append([[it[0]]] + it[1:])
                down = 0
                if not merged and row[11] < 0 and not row[12]:  # else borrow the nearest parent's own note
                    a_ = regions[k]["parent_id"]
                    while a_:
                        if (idx[a_], style, row[0]) in own:
                            merged, down = [[[idx[a_]], ""] + own[(idx[a_], style, row[0])]], 1
                            break
                        a_ = parent.get(a_)
                rolled += bool(merged) and not down
                borrowed_notes += down
                row += [merged or 0, down]
    for st in series.values():
        for sd in st.values():
            for row in sd["r"]:  # fields only the old tap-to-expand view used
                row[8], row[9], row[10], row[13], row[14], row[15] = 0, -1, 0, "", 0, 0
                for it in (row[17] or []):
                    it[4] = ""
            sd["r"].sort(key=lambda x: -x[0])
            for row in sd["r"]:  # score_display exactly as exported, without a trailing ".0"
                d = row[1]
                row[1] = d[:-2] if d.endswith(".0") else d

    # holding stars: bottles (or, in an older export, wines) held in each region and its sub-regions; only the star
    # level is embedded, never the count
    held_b = {r["node_id"]: int(r.get("cellar_bottles") or r["cellar_wines"] or 0) for r in regions}
    total = dict(held_b)
    for r in regions:
        n, p = r["node_id"], r["parent_id"]
        while p:
            total[p] = total.get(p, 0) + held_b[n]
            p = parent.get(p)
    star = lambda b: next((s for lim, s in STARS if b >= lim), 0)
    nodes = [{"id": r["node_id"], "p": idx.get(r["parent_id"], -1), "n": r["name"], "t": r["node_type"],
              "a": [x for x in r["aliases"].split("|") if x], "c": star(total[r["node_id"]])} for r in regions]
    data = {"built": date.today().isoformat(), "tags": TAGS, "labels": labels, "cellar": bool(held), "styles": STYLE_ORDER, "nodes": nodes,
            "series": {str(k): v for k, v in series.items()}}
    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    import base64
    icon = lambda n: base64.b64encode((Path(__file__).resolve().parent / f"app_icon_{n}.png").read_bytes()).decode()
    html = (TEMPLATE.replace("__DATA__", blob).replace("__BUILT__", data["built"])
            .replace("__ICON192__", icon(192)).replace("__ICON512__", icon(512)))
    Path(a.out).write_text(html.replace("__PWA_HEAD__", ""), encoding="utf-8")
    if a.pwa:
        write_pwa(Path(a.pwa), html, data["built"])
    long_notes = sorted({v[1] for v in own.values() if len(v[1]) > 48})
    for t in long_notes:
        print(f"WARNING note over 48 characters (may not fit beside score and readiness): {t}")
    n_rows = sum(len(sd["r"]) for st in series.values() for sd in st.values())
    print(f"wrote {a.out}: {len(html.encode()) / 1e6:.2f} MB, {n_rows} rows, {len(series)} regions with data, "
          f"{sum(len(s) for s in series.values())} region-styles, Wine-Searcher voices dropped: {dropped}, "
          f""
          f"note files: {len(a.notes)} ({changed} rows changed vs the chart CSV), own notes: {len(own)}, rolled up from sub-regions: {rolled}, from a parent region: {borrowed_notes}")


def write_pwa(out, html, built):
    """The installable version: index.html + manifest + offline service worker + icons, for GitHub Pages."""
    import hashlib, json as js, shutil
    out.mkdir(parents=True, exist_ok=True)
    here = Path(__file__).resolve().parent
    head = ('<link rel="manifest" href="manifest.webmanifest">\n<meta name="theme-color" content="#142B5E">\n'
            '<link rel="apple-touch-icon" href="icon-192.png">')
    page = html.replace("__PWA_HEAD__", head)
    (out / "index.html").write_text(page, encoding="utf-8")
    for src, dst in (("app_icon_192.png", "icon-192.png"), ("app_icon_512.png", "icon-512.png"),
                     ("app_icon_maskable_512.png", "icon-maskable-512.png")):
        shutil.copyfile(here / src, out / dst)
    man = {"name": "Vintage chart", "short_name": "Vintages", "start_url": "./", "scope": "./", "display": "standalone",
           "background_color": "#16201B", "theme_color": "#142B5E", "description": "Offline vintage chart",
           "icons": [{"src": "icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
                     {"src": "icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"},
                     {"src": "icon-maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"}]}
    (out / "manifest.webmanifest").write_text(js.dumps(man, indent=1), encoding="utf-8")
    ver = built + "-" + hashlib.sha256(page.encode()).hexdigest()[:8]
    (out / "sw.js").write_text(SW.replace("__VER__", ver), encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")
    print(f"wrote web app to {out} (version {ver})")


SW = r"""/* Vintage chart offline worker, version __VER__. Opening the app with a signal fetches the latest page (waiting
   at most 3 seconds); without one, the copy kept on the phone is shown. */
const CACHE = "vintage-chart-__VER__";
const FILES = ["./", "index.html", "manifest.webmanifest", "icon-192.png", "icon-512.png", "icon-maskable-512.png"];
self.addEventListener("install", e => { e.waitUntil(caches.open(CACHE).then(c => c.addAll(FILES))); self.skipWaiting(); });
self.addEventListener("activate", e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});
self.addEventListener("fetch", e => {
  const req = e.request;
  if (req.method !== "GET") return;
  if (req.mode === "navigate") {
    e.respondWith(new Promise(resolve => {
      let done = false;
      const fallback = () => caches.match("index.html").then(r => { if (!done) { done = true; resolve(r || Response.error()); } });
      const timer = setTimeout(fallback, 3000);
      fetch(req).then(r => {
        if (r && r.ok) { const copy = r.clone(); caches.open(CACHE).then(c => c.put("index.html", copy)); }
        clearTimeout(timer); if (!done) { done = true; resolve(r); }
      }).catch(() => { clearTimeout(timer); fallback(); });
    }));
    return;
  }
  e.respondWith(caches.match(req).then(r => r || fetch(req)));
});
"""


TEMPLATE = r"""<!doctype html>
<html lang="en-GB">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="color-scheme" content="light dark">
<meta name="theme-color" content="#E9ECE6" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#16201B" media="(prefers-color-scheme: dark)">
<title>Vintage chart</title>
<meta name="robots" content="noindex, nofollow">
__PWA_HEAD__
<link rel="icon" type="image/png" sizes="192x192" href="data:image/png;base64,__ICON192__">
<link rel="icon" type="image/png" sizes="512x512" href="data:image/png;base64,__ICON512__">
<link rel="apple-touch-icon" sizes="192x192" href="data:image/png;base64,__ICON192__">
<meta name="application-name" content="Vintage chart">
<meta name="apple-mobile-web-app-title" content="Vintage chart">
<meta name="mobile-web-app-capable" content="yes">
<style>
:root{
  --bg:#E9ECE6; --surface:#F6F7F3; --ink:#1C2420; --ink2:#59635D; --ink3:#8A938C; --rule:#D2D8CF;
  --accent:#7B2240; --accent-ink:#FFFFFF; --tint:#F1E3E7; --tawny:#B9772F; --tawny-tint:#F3E6D6;
  --g0:#E2F1E1; --g0i:#356B3E; --g1:#9FD39E; --g1i:#173F1F; --g2:#22A845; --g2i:#FFFFFF; --g3:#1C5230; --g3i:#FFFFFF;
  --serif:Georgia,"Noto Serif","Droid Serif","Times New Roman",serif;
  --sans:system-ui,-apple-system,"Roboto","Segoe UI","Noto Sans",sans-serif;
  box-sizing:border-box; padding-top:env(safe-area-inset-top,0px); padding-bottom:env(safe-area-inset-bottom,0px);
}
@media (prefers-color-scheme:dark){ :root:not([data-theme="light"]){
  --bg:#16201B; --surface:#1D2923; --ink:#E3E8E1; --ink2:#A1ABA4; --ink3:#6F7A73; --rule:#2D3A33;
  --accent:#D88A9F; --accent-ink:#2A0F18; --tint:#3A2730; --tawny:#D9A462; --tawny-tint:#3A3022;
  --g0:#20352A; --g0i:#9ED0A3; --g1:#3C7A4A; --g1i:#EAF7EC; --g2:#3DD162; --g2i:#08210F; --g3:#1E6638; --g3i:#E3F3E6; } }
:root[data-theme="dark"]{
  --bg:#16201B; --surface:#1D2923; --ink:#E3E8E1; --ink2:#A1ABA4; --ink3:#6F7A73; --rule:#2D3A33;
  --accent:#D88A9F; --accent-ink:#2A0F18; --tint:#3A2730; --tawny:#D9A462; --tawny-tint:#3A3022;
  --g0:#20352A; --g0i:#9ED0A3; --g1:#3C7A4A; --g1i:#EAF7EC; --g2:#3DD162; --g2i:#08210F; --g3:#1E6638; --g3i:#E3F3E6; }
*,*::before,*::after{box-sizing:inherit}
html{height:100%;scroll-padding-top:env(safe-area-inset-top,0px)}
body{height:100%;margin:0;background:var(--bg);color:var(--ink);font:16px/1.4 var(--sans);
  -webkit-tap-highlight-color:transparent;overflow:hidden}
button{font:inherit;color:inherit;background:none;border:0;padding:0;cursor:pointer}
button:focus-visible,input:focus-visible,select:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.app{display:flex;flex-direction:column;height:100%}
/* top bar */
.bar{display:flex;align-items:center;gap:2px;padding:2px 6px 0 2px;background:var(--bg)}
.iconbtn{width:48px;height:48px;display:grid;place-items:center;border-radius:12px;flex:none}
.iconbtn:active{background:var(--rule)}
.iconbtn svg{width:24px;height:24px;stroke:currentColor;fill:none;stroke-width:2;stroke-linecap:round}
.title{flex:1;min-width:0;padding:0 4px}
.title h1{margin:0;font:600 21px/1.15 var(--serif);letter-spacing:-.01em;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.title .path{font-size:13px;color:var(--ink2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
/* sub bar */
.sub{padding:2px 10px 6px;background:var(--bg);border-bottom:1px solid var(--rule)}
.subrow{display:flex;align-items:center;gap:8px}
.subrow .tabs{flex:1;min-width:0}
.subrow .count{flex:none;font-size:12px;color:var(--ink2);font-variant-numeric:tabular-nums;white-space:nowrap}
.tabs{display:flex;gap:6px;overflow-x:auto;scrollbar-width:none;align-items:center}
.tabs::-webkit-scrollbar{display:none}
.tab{min-height:36px;padding:0 12px;border-radius:999px;border:1px solid var(--rule);white-space:nowrap;font-size:15px}
.tab[aria-selected="true"]{background:var(--accent);border-color:var(--accent);color:var(--accent-ink)}
/* list */
.list{flex:1;overflow-y:auto;-webkit-overflow-scrolling:touch;overscroll-behavior:contain;padding-bottom:40px}
.row{display:grid;grid-template-columns:48px 36px 76px 1fr;align-items:center;column-gap:6px;width:100%;
  min-height:42px;padding:1px 8px 1px 10px;text-align:left;border-bottom:1px solid var(--rule)}
.yr{font:600 16px var(--serif);font-variant-numeric:tabular-nums lining-nums}
.chip{position:relative;width:36px;height:28px;border-radius:7px;display:grid;place-items:center;
  font:700 14px var(--sans);font-variant-numeric:tabular-nums}
.pill{justify-self:start;max-width:100%;padding:3px 5px;border-radius:999px;font-size:12px;font-weight:600;
  white-space:nowrap;border:1.5px solid transparent;line-height:1.2}
/* readiness: greens through a wine's life (pale, mid, bright at its best, dark once mature); past best uncoloured */
.r0{background:var(--g0);color:var(--g0i);border-color:var(--g0)}
.r1{background:var(--g1);color:var(--g1i);border-color:var(--g1)}
.r2{background:var(--g2);color:var(--g2i);border-color:var(--g2)}
.r3{background:var(--g3);color:var(--g3i);border-color:var(--g3)}
.r4{color:var(--ink2);border-color:var(--rule)}
.rnote b{font-weight:600;color:var(--ink)}
.rnote{min-width:0;font-size:12px;line-height:1.12;color:var(--ink2);display:-webkit-box;
  -webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
.tag{display:inline-block;padding:1px 7px;margin-right:5px;white-space:nowrap;border-radius:5px;background:var(--bg);border:1px solid var(--rule);
  color:var(--ink);font:600 12px/1.5 var(--sans);vertical-align:1px}
.gap{display:flex;align-items:center;gap:8px;padding:0 12px;line-height:14px;color:var(--ink3);font-size:11px;font-variant-numeric:tabular-nums}
.gap::before,.gap::after{content:"";flex:1;border-top:1px dotted var(--ink3);opacity:.7}
.gap::before{flex:0 0 32px}
/* home page */
.hhead{display:flex;justify-content:space-between;padding:8px 16px 4px;font:600 13px var(--serif);color:var(--ink2);border-bottom:1px solid var(--rule)}
.hrow{display:flex;align-items:center;min-height:46px;padding:0 16px 0 6px;border-bottom:1px solid var(--rule);cursor:pointer}
.hrow:active{background:var(--rule)}
.hrow .hv{flex:none;width:34px;height:34px;display:grid;place-items:center;color:var(--ink2)}
.hrow .hv svg{width:18px;height:18px;stroke:currentColor;fill:none;stroke-width:2.2;stroke-linecap:round;transition:transform .15s}
.hrow .hv.open svg{transform:rotate(90deg)}
.hrow .hv.none{visibility:hidden}
.hrow .hn{flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.hrow .hc{flex:none;margin-left:12px;font-size:13px;color:var(--ink2);letter-spacing:1px}
.hrow.d0{font:600 17px var(--serif)}
.hrow.d1{padding-left:22px;font-size:16px}
.hrow.d2{padding-left:38px;font-size:15px}
.hrow.d3{padding-left:54px;font-size:15px}
.hrow.all .hn{color:var(--accent);font-weight:600}
@media (prefers-reduced-motion:reduce){.hrow .hv svg{transition:none}}
/* drawer */
.scrim{position:fixed;inset:0;background:rgba(10,14,12,.45);opacity:0;pointer-events:none;transition:opacity .2s;z-index:10}
.drawer{position:fixed;top:0;bottom:0;left:0;width:min(88vw,380px);background:var(--surface);z-index:11;transform:translateX(-102%);
  transition:transform .22s ease;display:flex;flex-direction:column;padding-top:env(safe-area-inset-top,0px);
  padding-bottom:env(safe-area-inset-bottom,0px);box-shadow:4px 0 24px rgba(0,0,0,.18)}
body.dopen .scrim{opacity:1;pointer-events:auto}
body.dopen .drawer{transform:none}
@media (prefers-reduced-motion:reduce){.drawer,.scrim{transition:none}}
.dhead{display:flex;align-items:center;gap:6px;padding:8px 8px 8px 12px}
.search{flex:1;min-height:48px;border-radius:12px;border:1px solid var(--rule);background:var(--bg);color:var(--ink);
  font:16px var(--sans);padding:0 14px}
.dbody{flex:1;overflow-y:auto;overscroll-behavior:contain;padding-bottom:16px}
.sect{padding:14px 16px 4px;font:600 14px var(--serif);color:var(--ink2)}
.item{display:flex;align-items:center;width:100%;min-height:48px;text-align:left}
.item .go{flex:1;min-width:0;min-height:48px;display:flex;flex-direction:column;justify-content:center;padding:4px 8px 4px 0;text-align:left}
.item .go b{font-weight:500;font-size:16px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.item .go span{font-size:12px;color:var(--ink2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.item .go:active{background:var(--bg)}
.item.cur .go b{color:var(--accent);font-weight:700}
.item.nodata .go b{color:var(--ink3)}
.tw{width:44px;height:48px;flex:none;display:grid;place-items:center;color:var(--ink2)}
.tw svg{width:18px;height:18px;stroke:currentColor;fill:none;stroke-width:2;transition:transform .15s}
.tw[aria-expanded="true"] svg{transform:rotate(90deg)}
.tw.none{visibility:hidden}
.count{flex:none;margin-right:16px;min-width:28px;text-align:right;font-size:13px;color:var(--ink2);font-variant-numeric:tabular-nums}
.key{border-top:1px solid var(--rule);padding:12px 16px 4px;font-size:13px;color:var(--ink2)}
.key .pills{display:flex;flex-wrap:wrap;gap:6px;margin:6px 0 10px}
.key p{margin:6px 0}
.ramp{display:flex;gap:2px;margin:6px 0 10px}
.ramp span{flex:1;height:22px;border-radius:4px;display:grid;place-items:center;font-size:11px;font-weight:700}
.themes{display:flex;gap:6px;margin:6px 0}
.themes button{min-height:40px;padding:0 14px;border-radius:999px;border:1px solid var(--rule);font-size:14px}
.themes button[aria-pressed="true"]{background:var(--ink);color:var(--bg)}
</style>
</head>
<body>
<div class="app">
  <header class="bar">
    <button class="iconbtn" id="menu" aria-label="Open regions"><svg viewBox="0 0 24 24"><path d="M4 7h16M4 12h16M4 17h16"/></svg></button>
    <div class="title" id="title"></div>
    <button class="iconbtn" id="home" aria-label="All regions"><svg viewBox="0 0 24 24"><path d="M4 11l8-7 8 7M6 10v10h12V10"/></svg></button>
  </header>
  <div class="sub" id="sub"></div>
  <main class="list" id="list"></main>
</div>
<div class="scrim" id="scrim"></div>
<nav class="drawer" id="drawer" aria-label="Regions">
  <div class="dhead">
    <input class="search" id="q" type="search" placeholder="Search regions" autocomplete="off" aria-label="Search regions">
    <button class="iconbtn" id="dclose" aria-label="Close"><svg viewBox="0 0 24 24"><path d="M6 6l12 12M18 6L6 18"/></svg></button>
  </div>
  <div class="dbody" id="dbody"></div>
</nav>
<script id="data" type="application/json">__DATA__</script>
<script>
(function(){
"use strict";
var D = JSON.parse(document.getElementById("data").textContent);
var N = D.nodes, S = D.series, L = D.labels, TAGS = D.tags, STYLES = D.styles;
var NOW = new Date().getFullYear();
var RNAMES = ["Not ready","Youthful","Peak","Mature","Past best"];  /* engine category "At best" shows as "Peak" (Charlie, 03-Oct) */
var SHORT = ["Powerful","Ripe","Classic","Refined","Lean"];
var $ = function(id){ return document.getElementById(id); };
var esc = function(s){ return String(s).replace(/[&<>"]/g, function(c){ return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]; }); };
var norm = function(s){ return String(s).normalize("NFD").replace(/[\u0300-\u036f]/g,"").toLowerCase().replace(/[^a-z0-9]+/g," ").trim(); };
var store = { get:function(k){ try{ return localStorage.getItem("vc:"+k); }catch(e){ return null; } },
              set:function(k,v){ try{ localStorage.setItem("vc:"+k,v); }catch(e){} } };

/* tree helpers */
var kids = N.map(function(){ return []; });
N.forEach(function(n,i){ if(n.p>=0) kids[n.p].push(i); });
var hasData = function(i){ return !!S[i]; };
var subHas = N.map(function(){ return null; });
function sub(i){ if(subHas[i]!==null) return subHas[i]; var r = hasData(i); kids[i].forEach(function(k){ if(sub(k)) r = true; }); return (subHas[i]=r); }
function pathOf(i){ var a=[]; for(var p=N[i].p; p>=0; p=N[p].p) a.unshift(N[p].n); return a; }
var hay = N.map(function(n,i){ return { name:norm(n.n), alias:norm(n.a.join(" ")), path:norm(pathOf(i).join(" ")) }; });

/* readiness, from today's year */
function stage(r){ return NOW < r[4] ? 0 : NOW < r[5] ? 1 : NOW < r[6] ? 2 : NOW < r[7] ? 3 : 4; }
function pill(r){
  return '<span class="pill r'+stage(r)+'">'+RNAMES[stage(r)]+'</span>';
}
/* score colour: ash -> sand -> olive -> green -> teal -> indigo, by displayed score (1-10) */
/* score colour: one scale, pale grey (low) to dark blue (high); most chart scores sit 6-10, so most of the range is spent there */
var LIGHT = [[1,[226,228,231]],[5,[200,205,212]],[6,[170,180,196]],[7,[133,151,181]],[8,[90,119,166]],[9,[47,83,144]],[10,[20,43,94]]];
var DARK  = [[1,[52,58,64]],[5,[60,68,80]],[6,[62,78,104]],[7,[64,90,138]],[8,[62,104,176]],[9,[66,118,214]],[10,[78,136,245]]];  /* white text throughout */
function isDark(){ var t = document.documentElement.getAttribute("data-theme");
  return t ? t==="dark" : !!(window.matchMedia && matchMedia("(prefers-color-scheme: dark)").matches); }
function rgb(v){
  var STOPS = isDark() ? DARK : LIGHT;
  v = Math.max(1, Math.min(10, v));
  for (var i=1;i<STOPS.length;i++){ if (v<=STOPS[i][0]){ var a=STOPS[i-1], b=STOPS[i], t=(v-a[0])/(b[0]-a[0]);
    return a[1].map(function(x,k){ return Math.round(x+(b[1][k]-x)*t); }); } }
  return STOPS[STOPS.length-1][1];
}
function chip(r){
  var c = rgb(parseFloat(r[1])), lum = (0.299*c[0]+0.587*c[1]+0.114*c[2]);
  return '<span class="chip" style="background:rgb('+c.join(",")+');color:'+(lum>150?'#1C2420':'#fff')+'">'+esc(r[1])+'</span>';
}
function rollTag(it){ var t = []; it.forEach(function(x){ if (x[2]>=0 && t.indexOf(x[2])<0) t.push(x[2]); });
  return t.length===1 ? SHORT[t[0]] : t.length ? "Mixed" : ""; }
function rollName(x, own, all){ if (all && x[0].length>1) return "Sub-regions";
  return x[0].map(function(k){ return k===own ? x[1] : N[k].n; }).join("/") + (x[0][0]!==own && x[1] ? " "+x[1].toLowerCase() : ""); }
function txt(r){  /* tag in bold, then the note, to the right of score and readiness; three lines at most */
  var tag = function(t){ return t>=0 ? '<b>'+SHORT[t]+'</b> ' : ''; };
  if (r[17]){
    if (rollTag(r[17])==="Mixed")
    { var g = {}, order = [];   /* group sub-regions by style tag: "Médoc/St-Émilion classic, Graves/Pomerol refined" */
      r[17].forEach(function(x){ var t = x[2]; if (!(t in g)){ g[t] = []; order.push(t); } g[t].push(rollName(x, st.node)); });
      return '<span class="rnote">'+order.map(function(t){ return '<b>'+esc(g[t].join("/")).replace(/\//g,"/\u200b")+'</b>'
        + (t>=0?" "+SHORT[t].toLowerCase():""); }).join(", ")+'</span>'; }
    return '<span class="rnote">'+tag(r[17][0][2])+esc(r[17][0][3])+'</span>';
  }
  return (r[11]>=0 || r[12]) ? '<span class="rnote">'+tag(r[11])+esc(r[12]||"")+'</span>' : '<span></span>';
}

/* state + routing via the URL hash so Android back works */
var st = { view:"home", node:-1, style:"" };
function stylesOf(i){ return S[i] ? STYLES.filter(function(s){ return S[i][s]; }) : []; }
function defStyle(i){
  var mem = store.get("style:"+N[i].id), list = stylesOf(i);
  if (mem && list.indexOf(mem)>=0) return mem;
  return list.slice().sort(function(a,b){ return S[i][b].r.length - S[i][a].r.length; })[0];
}
var byId = {}; N.forEach(function(n,i){ byId[n.id]=i; });
function readHash(){
  var h = {}; location.hash.replace(/^#/,"").split("&").forEach(function(kv){ var p=kv.split("="); if(p[0]) h[p[0]]=decodeURIComponent(p[1]||""); });
  if (h.r && byId[h.r]!==undefined && S[byId[h.r]]){ st.view="region"; st.node=byId[h.r]; var sl=stylesOf(st.node); st.style = sl.indexOf(h.s)>=0 ? h.s : defStyle(st.node); }
  else st.view = "home";
  return true;
}
function hashFor(){ return st.view==="home" ? "#home" : "#r="+N[st.node].id+"&s="+encodeURIComponent(st.style); }
function nav(replace){
  var h = hashFor();
  try { if (replace) history.replaceState(null,"",h); else if (h!==location.hash) history.pushState(null,"",h); } catch(e){}
  if (st.view==="region") store.set("style:"+N[st.node].id, st.style);
  render();
}
function goHome(push, fresh){ st.view="home"; if (fresh){ homeOpen = {}; homeScroll = 0; } try{ if (push) history.pushState(null,"","#home"); else history.replaceState(null,"","#home"); }catch(e){} render(); }

/* home page: countries first; tapping a row with sub-regions opens it out (the arrow turns); a region that has its
   own chart gets an "All <region>" row first; a row without sub-regions opens its vintages */
var homeOpen = {}, homeScroll = 0;
function renderHome(){
  $("title").innerHTML = '<h1>Vintage chart</h1>';
  $("sub").innerHTML = '';
  var h = '<div class="hhead"><span>Regions</span><span>Holding</span></div>';
  var arrow = '<svg viewBox="0 0 24 24"><path d="M9 6l6 6-6 6"/></svg>';
  function row(i, d, cls, label, attr, chev){
    var c = cls.indexOf("all")>=0 ? 0 : count(i);   /* the region's total already shows on its own row */
    return '<div class="hrow d'+Math.min(d,3)+' '+cls+'" '+attr+'><span class="hv'+(chev===null?' none':'')+(chev?' open':'')+'">'+arrow+'</span>'
      + '<span class="hn">'+label+'</span><span class="hc">'+(c||'')+'</span></div>';
  }
  function walk(i, d){
    if (!sub(i)) return;
    var ks = kids[i].filter(sub), open = !!homeOpen[i];
    if (!ks.length){ h += row(i, d, 'go', esc(N[i].n), 'data-h="'+i+'"', null); return; }
    h += row(i, d, 'tg', esc(N[i].n), 'data-t="'+i+'" aria-expanded="'+open+'"', open);
    if (!open) return;
    if (hasData(i)) h += row(i, d+1, 'go all', 'All '+esc(N[i].n), 'data-h="'+i+'"', null);
    ks.forEach(function(k){ walk(k, d+1); });
  }
  N.forEach(function(n,i){ if (n.p<0) walk(i,0); });
  $("list").innerHTML = h;
}

/* region screen */
function renderRegion(){
  var i = st.node, sd = S[i][st.style], rows = sd.r, p = pathOf(i);
  $("title").innerHTML = '<h1>'+(p.length?esc(p[p.length-1])+': ':'')+esc(N[i].n)+'</h1>';
  var tabs = stylesOf(i).map(function(s){ return '<button class="tab" role="tab" aria-selected="'+(s===st.style)+'" data-style="'+esc(s)+'">'+(s==="All"?"All styles":esc(s))+'</button>'; }).join("");
  $("sub").innerHTML = '<div class="subrow"><div class="tabs" role="tablist">'+tabs+'</div>'
    + '<span class="count">'+span(rows)+'</span></div>';
  var h = '', prevY = null;
  rows.forEach(function(r){
    if (prevY !== null && prevY-r[0] > 1) h += gap(r[0]+1, prevY-1);
    h += '<div class="row"><span class="yr">'+r[0]+'</span>'+chip(r)+pill(r)+txt(r)+'</div>';
    prevY = r[0];
  });
  $("list").innerHTML = h;
}
function span(rows){  /* "17 years, 2009-25"; the full end year only when the century changes */
  var lo = rows[rows.length-1][0], hi = rows[0][0], n = rows.length;
  return n+(n===1?' year, ':' years, ')+(lo===hi ? lo : lo+'-'+(Math.floor(lo/100)===Math.floor(hi/100) ? String(hi).slice(2) : hi));
}
function gap(a,b){ return '<div class="gap" aria-label="No chart for '+a+(a<b?' to '+b:'')+'">'+(a===b ? a : a+'–'+String(b).slice(a<b && String(a).slice(0,2)===String(b).slice(0,2) ? 2 : 0))+'</div>'; }

var shownHash = "";
function render(){
  shownHash = location.hash;
  $("home").style.visibility = st.view==="home" ? "hidden" : "visible";
  if (st.view==="home") renderHome(); else renderRegion();
  $("list").scrollTop = st.view==="home" ? homeScroll : 0;
  if (dOpen) buildDrawer();
}

$("list").addEventListener("click", function(e){
  var r = e.target.closest(".hrow"); if (!r) return;
  if (r.dataset.t){
    var i=+r.dataset.t, open=!homeOpen[i];
    /* a region directly under a country (Bordeaux, California) opens out everything beneath it in one tap */
    var deep = N[i].p>=0 && N[N[i].p].p<0;
    homeOpen[i]=open;
    if (deep) (function all(k){ kids[k].forEach(function(c){ if (kids[c].length){ homeOpen[c]=open; all(c); } }); })(i);
    renderHome(); return;
  }
  if (r.dataset.h){ homeScroll = $("list").scrollTop; st.view="region"; st.node=+r.dataset.h; st.style=defStyle(st.node); nav(); }
});
$("home").onclick = function(){ goHome(true, true); };
/* coming back after more than 10 minutes away: start again from the home page */
var hiddenAt = 0;
document.addEventListener("visibilitychange", function(){
  if (document.hidden) hiddenAt = Date.now();
  else if (hiddenAt && Date.now()-hiddenAt > 10*60*1000){ if (dOpen) closeDrawer(true); if (st.view!=="home") goHome(true, true); else goHome(false, true); }
});
$("sub").addEventListener("click", function(e){
  var t = e.target.closest("button"); if (!t) return;
  if (t.dataset.style){ st.style=t.dataset.style; nav(true); }
});
/* drawer: search and one region tree, with cellar wines per region (sub-regions included) on the right */
var dOpen = false, openSet = {};
var cnt = N.map(function(){ return null; });
function count(i){ return N[i].c ? "★★★".slice(0, N[i].c) : ""; }   /* holding stars, set at build time */
function openDrawer(){ if (dOpen) return; dOpen = true; $("q").value = "";
  openSet = {};   /* the menu always opens at the top level, everything folded (Charlie, 5-Oct) */
  buildDrawer(); $("dbody").scrollTop = 0; document.body.classList.add("dopen");
  try{ history.pushState({drawer:1},"",location.hash); }catch(e){} }
function closeDrawer(viaBack){ if (!dOpen) return; dOpen = false; document.body.classList.remove("dopen");
  if (!viaBack){ try{ if (history.state && history.state.drawer) history.back(); }catch(e){} } }
$("menu").onclick = openDrawer; $("scrim").onclick = function(){ closeDrawer(); }; $("dclose").onclick = function(){ closeDrawer(); };
window.addEventListener("popstate", function(){ if (dOpen && !(history.state && history.state.drawer)){ dOpen=false; document.body.classList.remove("dopen"); }
  if (location.hash!==shownHash){ readHash(); render(); } });
function item(i, depth, opts){
  opts = opts || {};
  var ks = kids[i].filter(sub), exp = !!openSet[i], cls = "item"+(i===st.node?" cur":"")+(hasData(i)||ks.length?"":" nodata");
  var tw = opts.flat ? '' : '<button class="tw'+(ks.length?'':' none')+'" data-tw="'+i+'" aria-expanded="'+exp+'" aria-label="Show '+esc(N[i].n)+' sub-regions"><svg viewBox="0 0 24 24"><path d="M9 6l6 6-6 6"/></svg></button>';
  var h = '<div class="'+cls+'" style="padding-left:'+(opts.flat?16:4+depth*16)+'px">'+tw
    + '<button class="go" data-n="'+i+'"><b>'+esc(N[i].n)+'</b>'+(opts.sub?'<span>'+esc(opts.sub)+'</span>':'')+'</button>'
    + '<span class="count">'+(count(i)||'')+'</span></div>';
  if (!opts.flat && exp) ks.forEach(function(k){ h += item(k, depth+1); });
  return h;
}
function buildDrawer(){
  var q = norm($("q").value), h = '';
  if (q){
    var toks = q.split(" "), res = [];
    N.forEach(function(n,i){
      if (!sub(i)) return;
      var x = hay[i], all = x.name+" "+x.alias+" "+x.path;
      if (!toks.every(function(t){ return all.indexOf(t)>=0; })) return;
      var rank = x.name.indexOf(q)===0 ? 0 : (" "+x.name).indexOf(" "+toks[0])>=0 ? 1 : (" "+x.alias).indexOf(" "+toks[0])>=0 ? 2 : 3;
      if (!hasData(i)) rank += 4;
      res.push([rank, i]);
    });
    res.sort(function(a,b){ return a[0]-b[0] || N[a[1]].n.localeCompare(N[b[1]].n); });
    h = res.length ? res.slice(0,60).map(function(x){ var i=x[1], al = N[i].a.filter(function(a){ return norm(a).indexOf(q)>=0 && hay[i].name.indexOf(q)<0; });
          return item(i,0,{flat:1, sub:(al.length?"Also "+al[0]+". ":"")+(pathOf(i).join(" › ")||(hasData(i)?"Country":"No chart of its own"))}); }).join("")
      : '<p class="empty">No region matches “'+esc($("q").value)+'”. Try a country or a shorter name.</p>';
  } else {
    h += '<div class="sect" style="display:flex;justify-content:space-between;padding-right:16px"><span>Regions</span><span>Holding</span></div>';
    N.forEach(function(n,i){ if (n.p<0 && sub(i)) h += item(i,0); });
    h += keyHtml();
  }
  $("dbody").innerHTML = h;
}
function keyHtml(){
  var th = store.get("theme")||"auto";
  var ramp = [1,2,3,4,5,6,7,8,9,10].map(function(v){ var c=rgb(v), l=0.299*c[0]+0.587*c[1]+0.114*c[2];
      return '<span style="background:rgb('+c.join(",")+');color:'+(l>150?'#1C2420':'#fff')+'">'+v+'</span>'; }).join("");
  return '<div class="key"><div class="sect" style="padding:0 0 4px">Key</div>'
    + '<div class="ramp">'+ramp+'</div>'
    + '<div class="pills">'+RNAMES.map(function(n,k){ return '<span class="pill r'+k+'">'+n+'</span>'; }).join("")+'</div>'
    + '<p>Readiness as of '+NOW+'.</p>'
    + '<div class="sect" style="padding:6px 0 0">Appearance</div><div class="themes">'
    + ["auto","light","dark"].map(function(t){ return '<button data-theme="'+t+'" aria-pressed="'+(th===t)+'">'+(t==="auto"?"Match phone":t[0].toUpperCase()+t.slice(1))+'</button>'; }).join("")
    + '</div><p>Chart data built __BUILT__.</p></div>';
}
$("q").addEventListener("input", buildDrawer);
$("dbody").addEventListener("click", function(e){
  var t = e.target.closest("button"); if (!t) return;
  if (t.dataset.tw){ var i=+t.dataset.tw, open=!openSet[i]; openSet[i]=open;
    if (N[i].p>=0 && N[N[i].p].p<0) (function all(k){ kids[k].forEach(function(c){ if (kids[c].length){ openSet[c]=open; all(c); } }); })(i);
    buildDrawer(); return; }
  if (t.dataset.theme){ setTheme(t.dataset.theme); buildDrawer(); return; }
  if (t.dataset.n){
    var i=+t.dataset.n;
    if (!hasData(i)){ if (kids[i].some(sub)){ openSet[i]=!openSet[i]; $("q").value=""; for(var p=N[i].p;p>=0;p=N[p].p) openSet[p]=true; buildDrawer(); } return; }
    st.view="region"; st.node=i; st.style=defStyle(i);
    dOpen=false; document.body.classList.remove("dopen");
    try{ if (history.state && history.state.drawer) history.replaceState(null,"",hashFor()); else history.pushState(null,"",hashFor()); }catch(e){}
    render();
  }
});
function setTheme(t){ store.set("theme",t); if (t==="auto") document.documentElement.removeAttribute("data-theme"); else document.documentElement.setAttribute("data-theme",t);
  render(); }
try { matchMedia("(prefers-color-scheme: dark)").addEventListener("change", function(){ render(); }); } catch(e){}
setTheme(store.get("theme")||"auto");

/* start: always the home page (a saved shortcut address or the last region is ignored on a fresh start) */
goHome(false, true);
})();
</script>
<script>/* installed web app: keep a copy on the phone for offline use (only on https; does nothing in the file version) */
if ("serviceWorker" in navigator && (location.protocol === "https:" || location.hostname === "localhost")) {
  window.addEventListener("load", function(){ navigator.serviceWorker.register("sw.js").catch(function(){}); });
}</script>
</body>
</html>
"""

if __name__ == "__main__":
    main()
