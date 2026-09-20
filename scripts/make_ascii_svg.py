from PIL import Image
from xml.sax.saxutils import escape

RAMP = " .`:-=+*cs#%@"      # açık (seyrek) -> koyu (yoğun)
COLS = 100
FONT_SIZE = 14
CHAR_W = FONT_SIZE * 0.6    # monospace advance
CHAR_H = FONT_SIZE * 1.0
COLOR = "#c9d1d9"
CURSOR = "#39d353"
ROW_DELAY = 0.045           # satırlar arası gecikme
ROW_DUR = 0.35              # bir satırın yazılma süresi
OUT = "mete-ascii.svg"

img = Image.open("source-prepped.png").convert("L")
w, h = img.size
rows = max(1, int(COLS * (h / w) * (CHAR_W / CHAR_H)))
img = img.resize((COLS, rows), Image.LANCZOS)
px = img.load()

W = COLS * CHAR_W
H = rows * CHAR_H
n = len(RAMP) - 1

parts = [
    f'<svg xmlns="http://www.w3.org/2000/svg" width="{W:.0f}" height="{H:.0f}" '
    f'viewBox="0 0 {W:.2f} {H:.2f}" font-family="Consolas,Menlo,monospace" '
    f'font-size="{FONT_SIZE}">',
    f'<rect width="100%" height="100%" fill="#0d1117"/>',
    '<defs>',
]

lines = []
for r in range(rows):
    line = "".join(RAMP[n - int(px[c, r] / 255 * n)] for c in range(COLS))
    lines.append(line.rstrip())
    begin = r * ROW_DELAY
    parts.append(
        f'<clipPath id="w{r}"><rect x="0" y="{r*CHAR_H:.2f}" '
        f'height="{CHAR_H:.2f}" width="0">'
        f'<animate attributeName="width" from="0" to="{W:.2f}" '
        f'begin="{begin:.3f}s" dur="{ROW_DUR}s" fill="freeze" '
        f'calcMode="linear"/></rect></clipPath>'
    )

parts.append('</defs>')

for r, line in enumerate(lines):
    y = (r + 0.8) * CHAR_H
    parts.append(
        f'<text x="0" y="{y:.2f}" fill="{COLOR}" xml:space="preserve" '
        f'clip-path="url(#w{r})">{escape(line)}</text>'
    )

# yazma kenarında ilerleyen imleç
for r in range(rows):
    begin = r * ROW_DELAY
    parts.append(
        f'<rect y="{r*CHAR_H:.2f}" width="{CHAR_W:.2f}" height="{CHAR_H:.2f}" '
        f'fill="{CURSOR}" opacity="0">'
        f'<animate attributeName="x" from="0" to="{W:.2f}" begin="{begin:.3f}s" '
        f'dur="{ROW_DUR}s" fill="freeze"/>'
        f'<set attributeName="opacity" to="0.85" begin="{begin:.3f}s"/>'
        f'<set attributeName="opacity" to="0" begin="{begin + ROW_DUR:.3f}s"/>'
        f'</rect>'
    )

parts.append('</svg>')
open(OUT, "w", encoding="utf-8").write("\n".join(parts))
print(f"yazildi: {OUT}  ({COLS}x{rows} karakter)")