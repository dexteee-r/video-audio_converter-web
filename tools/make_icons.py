"""Generate the PWA icons (web/icons/*.png). Dev-time only, needs Pillow.

    python tools/make_icons.py

The mark is the same `>_` prompt as the logo, drawn with shapes (no font needed).
"""

from pathlib import Path

from PIL import Image, ImageDraw

BG = (10, 10, 15, 255)          # --bg
MAUVE = (183, 148, 246, 255)    # --mauve
OUT = Path(__file__).resolve().parent.parent / "web" / "icons"


def draw_icon(size: int, *, maskable: bool) -> Image.Image:
    scale = 4  # supersample for smooth edges
    s = size * scale
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    if maskable:
        d.rectangle([0, 0, s, s], fill=BG)       # full bleed: the OS crops the shape
        inner = 0.58                              # keep the mark inside the 80% safe zone
    else:
        d.rounded_rectangle([0, 0, s - 1, s - 1], radius=int(s * 0.22), fill=BG)
        inner = 0.66

    w = int(s * 0.075)                            # stroke width
    box = s * inner
    left = (s - box) / 2
    top = (s - box) / 2

    # chevron ">"
    p1 = (left, top + box * 0.12)
    p2 = (left + box * 0.40, top + box * 0.50)
    p3 = (left, top + box * 0.88)
    d.line([p1, p2, p3], fill=MAUVE, width=w, joint="curve")
    for p in (p1, p3):
        d.ellipse([p[0] - w / 2, p[1] - w / 2, p[0] + w / 2, p[1] + w / 2], fill=MAUVE)

    # underscore "_"
    y = top + box * 0.88
    x1, x2 = left + box * 0.56, left + box
    d.line([(x1, y), (x2, y)], fill=MAUVE, width=w)
    for x in (x1, x2):
        d.ellipse([x - w / 2, y - w / 2, x + w / 2, y + w / 2], fill=MAUVE)

    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for size in (192, 512):
        draw_icon(size, maskable=False).save(OUT / f"icon-{size}.png")
    draw_icon(512, maskable=True).save(OUT / "icon-maskable-512.png")
    draw_icon(180, maskable=False).save(OUT / "apple-touch-icon.png")
    print("wrote", sorted(p.name for p in OUT.iterdir()))


if __name__ == "__main__":
    main()
