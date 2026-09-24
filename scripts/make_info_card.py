import os

W, H = 490, 264
BG = "#0d1117"
BORDER = "#30363d"
KEY = "#39d353"
VAL = "#c9d1d9"
DIM = "#8b949e"
FONT = "Consolas,Menlo,monospace"
STATIC = os.environ.get("STATIC") == "1"
OUT = "info-card.svg"

TITLE = "Mete Uçar"
ROWS = [
    ("OS",        "Windows 11 / WSL2"),
    ("Role",      "Frontend Developer @ 32Bit"),
    ("Domain",    "Enterprise Insurance - Allianz TR"),
    ("Stack",     "React / TypeScript / MUI v7"),
    ("Forms",     "React Hook Form + Zod"),
    ("Backend",   "Docker / nginx / Spring Boot"),
    ("Education", "Computer Eng. - Sakarya Uni '25"),
]

PAD = 22
LINE_H = 24
TITLE_Y = 44
FIRST_Y = 92
KEY_W = 110
DELAY = 0.09

p = [
    f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
    f'viewBox="0 0 {W} {H}" font-family="{FONT}" font-size="13">',
    f'<rect width="{W}" height="{H}" rx="8" fill="{BG}" stroke="{BORDER}"/>',
]

def anim(begin):
    if STATIC:
        return ""
    return (f'<animate attributeName="opacity" from="0" to="1" '
            f'begin="{begin:.2f}s" dur="0.3s" fill="freeze"/>'
            f'<animateTransform attributeName="transform" type="translate" '
            f'from="-8 0" to="0 0" begin="{begin:.2f}s" dur="0.3s" fill="freeze"/>')

op = '1' if STATIC else '0'

# başlık
p.append(
    f'<g opacity="{op}"><text x="{PAD}" y="{TITLE_Y}" fill="{KEY}" '
    f'font-size="15" font-weight="bold">{TITLE}</text>{anim(0)}</g>'
)
p.append(
    f'<g opacity="{op}"><line x1="{PAD}" y1="{TITLE_Y+10}" x2="{W-PAD}" '
    f'y2="{TITLE_Y+10}" stroke="{BORDER}"/>{anim(0.05)}</g>'
)

for i, (k, v) in enumerate(ROWS):
    y = FIRST_Y + i * LINE_H
    b = 0.15 + i * DELAY
    p.append(
        f'<g opacity="{op}">'
        f'<text x="{PAD}" y="{y}" fill="{KEY}">{k}</text>'
        f'<text x="{PAD+KEY_W}" y="{y}" fill="{VAL}">{v}</text>'
        f'{anim(b)}</g>'
    )

p.append('</svg>')
open(OUT, "w", encoding="utf-8").write("\n".join(p))
print(f"yazildi: {OUT}")