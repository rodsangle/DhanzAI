"""Render the DHANZ AI app icon (same geometry as lib/widgets/dhanz_logo.dart).

python scripts/generate_icon.py
cd apps/dhanz_flutter && dart run flutter_launcher_icons
"""

import math
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parents[1] / "apps/dhanz_flutter/assets/branding"
SIZE = 1024
SS = 4  # supersampling for smooth edges

NAVY_LIGHT, NAVY, BLACK = (19, 40, 77), (11, 26, 51), (7, 9, 14)
GOLD_LIGHT, GOLD, GOLD_DARK = (233, 204, 107), (212, 175, 55), (169, 131, 31)


def lerp(a, b, t):
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b, strict=True))


def gradient(size, stops):
    img = Image.new("RGB", (size, size))
    px = img.load()
    for y in range(size):
        for x in range(size):
            t = (x + y) / (2 * (size - 1))
            if t < 0.5:
                px[x, y] = lerp(stops[0], stops[1], t * 2)
            else:
                px[x, y] = lerp(stops[1], stops[2], (t - 0.5) * 2)
    return img


def mark(draw, s, color, width):
    """The "D": outer outline minus inner outline, so the stroke is centred like Flutter's."""
    h = width / 2
    stem_x, cx, cy, r = s * 0.33, s * 0.45, s / 2, s * 0.23
    top, bottom = cy - r, cy + r
    draw.rounded_rectangle([stem_x - h, top - h, cx, bottom + h], radius=int(h), fill=color)
    draw.rectangle([stem_x, top - h, cx + 1, bottom + h], fill=color)  # square off the right-hand corners
    draw.pieslice([cx - r - h, cy - r - h, cx + r + h, cy + r + h], -90, 90, fill=color)
    draw.rectangle([stem_x + h, top + h, cx, bottom - h], fill=0)
    draw.pieslice([cx - r + h, cy - r + h, cx + r - h, cy + r - h], -90, 90, fill=0)


def spark(draw, s, color):
    cx, cy, r = s * 0.74, s * 0.26, s * 0.09
    pts = []
    for i in range(8):
        a = i * math.pi / 4
        rad = r if i % 2 == 0 else r * 0.32
        pts.append((cx + math.cos(a) * rad, cy + math.sin(a) * rad))
    draw.polygon(pts, fill=color)


def render(with_background: bool) -> Image.Image:
    s = SIZE * SS
    gold_layer = gradient(s // 8, (GOLD_LIGHT, GOLD, GOLD_DARK)).resize((s, s))
    mask = Image.new("L", (s, s), 0)
    mark(ImageDraw.Draw(mask), s, 255, int(s * 0.085))
    if with_background:
        bg = gradient(s // 8, (NAVY_LIGHT, NAVY, BLACK)).resize((s, s)).convert("RGBA")
        tile = Image.new("L", (s, s), 0)
        ImageDraw.Draw(tile).rounded_rectangle([0, 0, s - 1, s - 1], radius=int(s * 0.24), fill=255)
        img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        img.paste(bg, (0, 0), tile)
    else:
        img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    img.paste(gold_layer, (0, 0), mask)
    spark(ImageDraw.Draw(img), s, GOLD_LIGHT + (255,))
    return img.resize((SIZE, SIZE), Image.LANCZOS)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    render(True).save(OUT / "app_icon.png")
    # Android adaptive icon foreground: mark scaled into the 66% safe zone on transparency.
    fg = render(False).resize((int(SIZE * 0.66), int(SIZE * 0.66)), Image.LANCZOS)
    canvas = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    canvas.paste(fg, ((SIZE - fg.width) // 2, (SIZE - fg.height) // 2), fg)
    canvas.save(OUT / "app_icon_foreground.png")
    print(f"Wrote icons to {OUT}")


if __name__ == "__main__":
    main()
