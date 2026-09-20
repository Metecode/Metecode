import json
from datetime import date

PALETTE = ["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353", "#69f0a0"]
BG = "#0d1117"
DIM = "#8b949e"
FONT = "Consolas,Menlo,monospace"
CELL, GAP, R = 12, 3, 2
PAD_L, PAD_T = 34, 26
OUT = "contrib-heatmap.svg"

data = json.load(open("data/contributions.json", encoding="utf-8"))
days = data["days"]

# ilk gunun haftanin kacinci gunu oldugu (pazar=0)
first = date.fromisoformat(days[0]["date"])
offset = (first.weekday() + 1) % 7

cells = []
for i, d in enumerate(days):
    idx = i + offset
    cells.append((idx // 7, idx % 7, d))
weeks = max(c[0] for c in cells) + 1

W = PAD_L + weeks * (CELL + GAP) + 20
H = PAD_T + 7 * (CELL + GAP) + 58

p = [
    f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
    f'viewBox="0 0 {W} {H}" font-family="{FONT}" font-size="10">',
    f'<rect width="{W}" height="{H}" rx="8" fill="{BG}" stroke="#30363d"/>',
    '<style>'
    '.c{opacity:0;animation:pop .35s ease-out forwards}'
    '@keyframes pop{from{opacity:0;transform:translateY(-6px)}'
    'to{opacity:1;transform:translateY(0)}}'
    '</style>',
]

for lbl, row in [("Mon", 1), ("Wed", 3), ("Fri", 5)]:
    y = PAD_T + row * (CELL + GAP) + CELL - 2
    p.append(f'<text x="6" y="{y}" fill="{DIM}">{lbl}</text>')

for wk, dw, d in cells:
    x = PAD_L + wk * (CELL + GAP)
    y = PAD_T + dw * (CELL + GAP)
    lvl = min(d["level"], len(PALETTE) - 1)
    delay = (wk + dw) * 0.012          # capraz dalga
    p.append(
        f'<rect class="c" x="{x}" y="{y}" width="{CELL}" height="{CELL}" rx="{R}" '
        f'fill="{PALETTE[lvl]}" style="animation-delay:{delay:.3f}s">'
        f'<title>{d["date"]}: {d["count"]}</title></rect>'
    )

# legend
ly = PAD_T + 7 * (CELL + GAP) + 18
lx = W - 20 - len(PALETTE) * (CELL + GAP) - 60
p.append(f'<text x="{lx}" y="{ly + CELL - 2}" fill="{DIM}">Less</text>')
for i, c in enumerate(PALETTE):
    p.append(f'<rect x="{lx + 30 + i*(CELL+GAP)}" y="{ly}" width="{CELL}" '
             f'height="{CELL}" rx="{R}" fill="{c}"/>')
p.append(f'<text x="{lx + 30 + len(PALETTE)*(CELL+GAP) + 4}" y="{ly + CELL - 2}" '
         f'fill="{DIM}">More</text>')

# istatistik satiri
s = (f'{data["total"]:,} contributions in the last year  ·  '
     f'current streak {data["current_streak"]}d  ·  '
     f'longest {data["longest_streak"]}d')
p.append(f'<text x="{PAD_L}" y="{ly + CELL - 2}" fill="{DIM}">{s}</text>')

p.append('</svg>')
open(OUT, "w", encoding="utf-8").write("\n".join(p))
print(f"yazildi: {OUT}  ({weeks} hafta)")