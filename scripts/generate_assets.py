"""Genere un jeu d'assets de demonstration inspire des maquettes.

    python3 scripts/generate_assets.py

Ecrit dans apps/api/media/ :
    backgrounds/   8 fonds        + index.json (ordre, libelles fr/en/es)
    objects/       20 objets      + index.json
    base/shape.json               geometrie de la planche de bord (masque)

Le studio remplace ces fichiers par les visuels definitifs : seul index.json
fait foi pour l'ordre d'affichage et le texte au survol. Formats acceptes :
PNG (avec transparence pour les objets), JPG, WebP.
"""

from __future__ import annotations

import json
import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

MEDIA = Path(__file__).resolve().parent.parent / "apps" / "api" / "media"
BG_SIZE = (1600, 800)
OBJ_SIZE = 600

FONTS = {
    "impact": "/System/Library/Fonts/Supplemental/Impact.ttf",
    "chalk": "/System/Library/Fonts/Supplemental/Chalkduster.ttf",
    "marker": "/System/Library/Fonts/Supplemental/Comic Sans MS Bold.ttf",
    "party": "/System/Library/Fonts/Supplemental/PartyLET-plain.ttf",
}


def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    path = FONTS.get(name)
    try:
        return ImageFont.truetype(path, size)  # type: ignore[arg-type]
    except Exception:
        return ImageFont.load_default(size)


def rgb(hexa: str) -> tuple[int, int, int]:
    hexa = hexa.lstrip("#")
    return tuple(int(hexa[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def lerp(a: tuple[int, ...], b: tuple[int, ...], t: float) -> tuple[int, ...]:
    return tuple(int(x + (y - x) * t) for x, y in zip(a, b))


# --------------------------------------------------------------------------- fonds


def bg_sunburst() -> Image.Image:
    w, h = BG_SIZE
    img = Image.new("RGB", (w, h), rgb("#F9E9D2"))
    draw = ImageDraw.Draw(img)
    cx, cy = int(w * 0.75), int(h * 0.55)
    colors = [rgb("#F5A623"), rgb("#F9E9D2"), rgb("#E8735A"), rgb("#F9E9D2"), rgb("#F2A7B5")]
    rays = 36
    radius = max(w, h) * 1.5
    for i in range(rays):
        a0 = math.radians(i * 360 / rays)
        a1 = math.radians((i + 1) * 360 / rays)
        draw.polygon(
            [(cx, cy), (cx + radius * math.cos(a0), cy + radius * math.sin(a0)),
             (cx + radius * math.cos(a1), cy + radius * math.sin(a1))],
            fill=colors[i % len(colors)],
        )
    # bandes ondulees a gauche
    for k, color in enumerate(["#F5A623", "#F2A7B5", "#E8735A"]):
        pts = [(x, int(h * (0.35 + 0.12 * k) + 40 * math.sin(x / 160 + k))) for x in range(0, w // 2 + 40, 8)]
        pts += [(w // 2 + 40, h), (0, h)]
        draw.polygon(pts, fill=rgb(color))
    for cx2, cy2, r, c in [(190, 190, 90, "#F2B233"), (640, 150, 60, "#E8735A"), (1180, 240, 55, "#F5A623")]:
        _flower(draw, cx2, cy2, r, rgb(c), rgb("#FFF3D6"))
    return img


def _flower(draw: ImageDraw.ImageDraw, cx: int, cy: int, r: int, color, center) -> None:
    for i in range(6):
        a = math.radians(i * 60)
        px, py = cx + r * 0.6 * math.cos(a), cy + r * 0.6 * math.sin(a)
        draw.ellipse((px - r * 0.45, py - r * 0.45, px + r * 0.45, py + r * 0.45), fill=color)
    draw.ellipse((cx - r * 0.3, cy - r * 0.3, cx + r * 0.3, cy + r * 0.3), fill=center)


def bg_artdeco(dark: bool = False) -> Image.Image:
    w, h = BG_SIZE
    base, line = (rgb("#123B2E"), rgb("#D9B25C")) if dark else (rgb("#F7F3EC"), rgb("#C9B07A"))
    img = Image.new("RGB", (w, h), base)
    draw = ImageDraw.Draw(img)
    step = 160
    for row in range(-1, h // step + 2):
        for col in range(-1, w // step + 2):
            cx = col * step + (step // 2 if row % 2 else 0)
            cy = row * step
            for r in range(20, step, 24):
                draw.arc((cx - r, cy - r, cx + r, cy + r), 180, 360, fill=line, width=3)
    return img


def bg_matrix() -> Image.Image:
    w, h = BG_SIZE
    img = Image.new("RGB", (w, h), rgb("#0B1030"))
    draw = ImageDraw.Draw(img)
    rnd = random.Random(7)
    for _ in range(420):
        x = rnd.randint(0, w)
        y0 = rnd.randint(-200, h)
        length = rnd.randint(60, 320)
        color = rnd.choice([rgb("#5EA8FF"), rgb("#C76BFF"), rgb("#3DE0C8"), rgb("#8AB4FF")])
        for i in range(0, length, 10):
            t = i / length
            draw.line((x, y0 + i, x, y0 + i + 6), fill=lerp(color, rgb("#0B1030"), t), width=2)
    return img.filter(ImageFilter.GaussianBlur(0.6))


def bg_graffiti() -> Image.Image:
    w, h = BG_SIZE
    img = Image.new("RGB", (w, h), rgb("#1B1B22"))
    draw = ImageDraw.Draw(img)
    rnd = random.Random(3)
    for _ in range(30):
        x, y = rnd.randint(0, w), rnd.randint(0, h)
        color = rnd.choice(["#FF3B8D", "#38E4FF", "#FFE03D", "#7CFF4D", "#FF7A2F"])
        pts = [(x + i * 12, y + int(60 * math.sin(i / 3 + rnd.random()))) for i in range(rnd.randint(8, 30))]
        draw.line(pts, fill=rgb(color), width=rnd.randint(10, 26), joint="curve")
    f = font("chalk", 150)
    draw.text((80, 520), "CHANGE", font=f, fill=rgb("#FFFFFF"))
    draw.text((960, 120), "THE RULES", font=font("chalk", 110), fill=rgb("#FFE03D"))
    _smiley(draw, 1250, 560, 130, rgb("#FFFFFF"), width=12)
    return img


def _smiley(draw, cx, cy, r, color, width=8, fill=None):
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), outline=color, width=width, fill=fill)
    draw.ellipse((cx - r * 0.45 - 12, cy - r * 0.3 - 12, cx - r * 0.45 + 12, cy - r * 0.3 + 12), fill=color)
    draw.ellipse((cx + r * 0.45 - 12, cy - r * 0.3 - 12, cx + r * 0.45 + 12, cy - r * 0.3 + 12), fill=color)
    draw.arc((cx - r * 0.6, cy - r * 0.3, cx + r * 0.6, cy + r * 0.65), 20, 160, fill=color, width=width)


def bg_gradient() -> Image.Image:
    w, h = BG_SIZE
    img = Image.new("RGB", (w, h))
    px = img.load()
    a, b, c = rgb("#FF8FB8"), rgb("#FFC9A8"), rgb("#7FB6FF")
    for x in range(w):
        for y in range(0, h, 1):
            t = (x / w) * 0.7 + (y / h) * 0.3
            px[x, y] = lerp(a, b, t * 2) if t < 0.5 else lerp(b, c, (t - 0.5) * 2)
    return img


def bg_circuit() -> Image.Image:
    w, h = BG_SIZE
    img = Image.new("RGB", (w, h), rgb("#0E4A1F"))
    draw = ImageDraw.Draw(img)
    rnd = random.Random(11)
    trace = rgb("#4CF06A")
    for _ in range(140):
        x, y = rnd.randrange(0, w, 40), rnd.randrange(0, h, 40)
        pts = [(x, y)]
        for _ in range(rnd.randint(2, 6)):
            dx, dy = rnd.choice([(80, 0), (-80, 0), (0, 80), (0, -80), (60, 60), (-60, 60)])
            pts.append((pts[-1][0] + dx, pts[-1][1] + dy))
        draw.line(pts, fill=trace, width=6)
        draw.ellipse((pts[-1][0] - 10, pts[-1][1] - 10, pts[-1][0] + 10, pts[-1][1] + 10), fill=rgb("#D9F2DD"))
    for _ in range(6):
        x, y = rnd.randint(100, w - 200), rnd.randint(80, h - 200)
        draw.rectangle((x, y, x + 140, y + 140), fill=rgb("#0A2E14"), outline=trace, width=5)
    return img


def bg_neon_maze() -> Image.Image:
    w, h = BG_SIZE
    img = Image.new("RGB", (w, h), rgb("#12102A"))
    glow = Image.new("RGB", (w, h), rgb("#12102A"))
    gd = ImageDraw.Draw(glow)
    rnd = random.Random(5)
    colors = ["#FF3FA4", "#3FE0FF", "#FFD23F", "#8C4DFF", "#3FFF9C"]
    for _ in range(60):
        x, y = rnd.randrange(0, w, 60), rnd.randrange(0, h, 60)
        color = rgb(rnd.choice(colors))
        pts = [(x, y)]
        for _ in range(rnd.randint(3, 8)):
            dx, dy = rnd.choice([(120, 0), (-120, 0), (0, 120), (0, -120)])
            pts.append((pts[-1][0] + dx, pts[-1][1] + dy))
        gd.line(pts, fill=color, width=22, joint="curve")
    glow = glow.filter(ImageFilter.GaussianBlur(18))
    img = Image.blend(img, glow, 0.9)
    draw = ImageDraw.Draw(img)
    rnd = random.Random(5)
    for _ in range(60):
        x, y = rnd.randrange(0, w, 60), rnd.randrange(0, h, 60)
        color = rgb(rnd.choice(colors))
        pts = [(x, y)]
        for _ in range(rnd.randint(3, 8)):
            dx, dy = rnd.choice([(120, 0), (-120, 0), (0, 120), (0, -120)])
            pts.append((pts[-1][0] + dx, pts[-1][1] + dy))
        draw.line(pts, fill=lerp(color, (255, 255, 255), 0.35), width=10, joint="curve")
    return img


def bg_holographic() -> Image.Image:
    w, h = BG_SIZE
    img = Image.new("RGB", (w, h), rgb("#EAF2FF"))
    draw = ImageDraw.Draw(img)
    rnd = random.Random(21)
    step = 130
    palette = ["#FFD1E8", "#D1F0FF", "#E4D1FF", "#D1FFE9", "#FFF1C9", "#FFFFFF"]
    for row in range(-1, h // step + 2):
        for col in range(-1, w // step + 2):
            x, y = col * step + rnd.randint(-30, 30), row * step + rnd.randint(-30, 30)
            pts = [(x, y), (x + step + rnd.randint(-40, 40), y + rnd.randint(-40, 40)),
                   (x + rnd.randint(-40, 40), y + step + rnd.randint(-40, 40))]
            draw.polygon(pts, fill=rgb(rnd.choice(palette)))
            pts2 = [pts[1], pts[2], (x + step, y + step)]
            draw.polygon(pts2, fill=rgb(rnd.choice(palette)))
    return img.filter(ImageFilter.GaussianBlur(1.2))


def bg_smileys() -> Image.Image:
    w, h = BG_SIZE
    img = Image.new("RGB", (w, h), rgb("#F3D23B"))
    draw = ImageDraw.Draw(img)
    rnd = random.Random(9)
    step = 220
    for row in range(-1, h // step + 2):
        for col in range(-1, w // step + 2):
            cx = col * step + (step // 2 if row % 2 else 0) + rnd.randint(-10, 10)
            cy = row * step + rnd.randint(-10, 10)
            color = rgb(rnd.choice(["#FF3B8D", "#1B1B22", "#38A9FF", "#7CFF4D"]))
            _smiley(draw, cx, cy, 70, color, width=9)
    return img


def bg_brush() -> Image.Image:
    w, h = BG_SIZE
    img = Image.new("RGB", (w, h), rgb("#0E2F3A"))
    draw = ImageDraw.Draw(img)
    rnd = random.Random(13)
    for _ in range(26):
        x0, y0 = rnd.randint(-200, w), rnd.randint(-100, h + 100)
        color = rnd.choice(["#2BB5A0", "#59D9C4", "#1C8C8C", "#9FE8DA", "#F4EBD0"])
        pts = [(x0 + i * 60, y0 + int(45 * math.sin(i / 2.2 + rnd.random() * 3))) for i in range(16)]
        draw.line(pts, fill=rgb(color), width=rnd.randint(28, 70), joint="curve")
    return img.filter(ImageFilter.GaussianBlur(0.8))


def bg_checker() -> Image.Image:
    w, h = BG_SIZE
    img = Image.new("RGB", (w, h), rgb("#F5F1E8"))
    draw = ImageDraw.Draw(img)
    size = 100
    for row in range(h // size + 1):
        for col in range(w // size + 1):
            if (row + col) % 2 == 0:
                draw.rectangle((col * size, row * size, (col + 1) * size, (row + 1) * size), fill=rgb("#1B1B22"))
    return img


def bg_stripes() -> Image.Image:
    w, h = BG_SIZE
    img = Image.new("RGB", (w, h), rgb("#F9E9D2"))
    draw = ImageDraw.Draw(img)
    colors = ["#D9482B", "#F5A623", "#F2C14E", "#6B8E4E", "#2F5D8A"]
    band = 90
    for i in range(-2, (w + int(h * 0.6)) // band + 2):
        x = i * band
        draw.polygon([(x, 0), (x + band, 0), (x + band - h * 0.6, h), (x - h * 0.6, h)], fill=rgb(colors[i % len(colors)]))
    return img


def bg_dots() -> Image.Image:
    w, h = BG_SIZE
    img = Image.new("RGB", (w, h), rgb("#F27AB3"))
    draw = ImageDraw.Draw(img)
    step, r = 110, 30
    for row in range(-1, h // step + 2):
        for col in range(-1, w // step + 2):
            cx = col * step + (step // 2 if row % 2 else 0)
            cy = row * step
            draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=rgb("#FFFFFF"))
    return img


def bg_swirl() -> Image.Image:
    w, h = BG_SIZE
    img = Image.new("RGB", (w, h))
    px = img.load()
    palette = [rgb("#FF4D9D"), rgb("#FFB84D"), rgb("#4DE0FF"), rgb("#9C4DFF")]
    cx, cy = w * 0.5, h * 0.5
    for y in range(0, h, 2):
        for x in range(0, w, 2):
            dx, dy = (x - cx) / w, (y - cy) / h
            t = (math.atan2(dy, dx) / math.pi + 4 * math.hypot(dx, dy)) % 1
            i = int(t * len(palette))
            f = t * len(palette) - i
            c = lerp(palette[i % len(palette)], palette[(i + 1) % len(palette)], f)
            px[x, y] = px[x + 1, y] = px[x, y + 1] = px[x + 1, y + 1] = c
    return img


def bg_night_city() -> Image.Image:
    w, h = BG_SIZE
    img = Image.new("RGB", (w, h))
    px = img.load()
    top, bottom = rgb("#0B1030"), rgb("#4B2A6B")
    for y in range(h):
        c = lerp(top, bottom, y / h)
        for x in range(w):
            px[x, y] = c
    draw = ImageDraw.Draw(img)
    rnd = random.Random(23)
    for _ in range(160):
        draw.point((rnd.randint(0, w), rnd.randint(0, h // 2)), fill=rgb("#FFFFFF"))
    x = 0
    while x < w:
        bw, bh = rnd.randint(50, 140), rnd.randint(120, 420)
        draw.rectangle((x, h - bh, x + bw, h), fill=rgb("#120C24"))
        for wy in range(h - bh + 15, h - 10, 26):
            for wx in range(x + 10, x + bw - 12, 22):
                if rnd.random() < 0.55:
                    draw.rectangle((wx, wy, wx + 10, wy + 14), fill=rgb(rnd.choice(["#FFE08A", "#FFB347", "#8AD6FF"])))
        x += bw + rnd.randint(6, 30)
    return img


BACKGROUNDS = [
    ("sunburst", bg_sunburst, {"fr": "Soleil rétro", "en": "Retro sunburst", "es": "Sol retro"}),
    ("artdeco-cream", lambda: bg_artdeco(False), {"fr": "Art déco crème", "en": "Cream art deco", "es": "Art déco crema"}),
    ("matrix", bg_matrix, {"fr": "Pluie numérique", "en": "Digital rain", "es": "Lluvia digital"}),
    ("graffiti", bg_graffiti, {"fr": "Mur graffiti", "en": "Graffiti wall", "es": "Muro grafiti"}),
    ("pastel", bg_gradient, {"fr": "Dégradé pastel", "en": "Pastel gradient", "es": "Degradado pastel"}),
    ("circuit", bg_circuit, {"fr": "Circuit imprimé", "en": "Circuit board", "es": "Circuito impreso"}),
    ("neon-maze", bg_neon_maze, {"fr": "Labyrinthe néon", "en": "Neon maze", "es": "Laberinto neón"}),
    ("holographic", bg_holographic, {"fr": "Holographique", "en": "Holographic", "es": "Holográfico"}),
    ("artdeco-green", lambda: bg_artdeco(True), {"fr": "Art déco vert", "en": "Green art deco", "es": "Art déco verde"}),
    ("smileys", bg_smileys, {"fr": "Smileys", "en": "Smileys", "es": "Smileys"}),
    ("brush", bg_brush, {"fr": "Coups de pinceau", "en": "Brush strokes", "es": "Pinceladas"}),
    ("checker", bg_checker, {"fr": "Damier", "en": "Checkerboard", "es": "Damero"}),
    ("stripes", bg_stripes, {"fr": "Rayures rétro", "en": "Retro stripes", "es": "Rayas retro"}),
    ("dots", bg_dots, {"fr": "Pois", "en": "Polka dots", "es": "Lunares"}),
    ("swirl", bg_swirl, {"fr": "Tourbillon", "en": "Swirl", "es": "Remolino"}),
    ("night-city", bg_night_city, {"fr": "Ville la nuit", "en": "Night city", "es": "Ciudad nocturna"}),
]


# --------------------------------------------------------------------------- objets


def _canvas() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGBA", (OBJ_SIZE, OBJ_SIZE), (0, 0, 0, 0))
    return img, ImageDraw.Draw(img)


def obj_text(text: str, fill: str, outline: str, face: str = "marker", size: int = 150, tilt: float = -6) -> Image.Image:
    img, draw = _canvas()
    f = font(face, size)
    left, top, right, bottom = draw.textbbox((0, 0), text, font=f)
    tw, th = right - left, bottom - top
    layer = Image.new("RGBA", (tw + 80, th + 80), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    # ombre portee puis contour puis remplissage : effet bubble/graffiti
    ld.text((40 - left + 10, 40 - top + 12), text, font=f, fill=(20, 10, 40, 200))
    ld.text((40 - left, 40 - top), text, font=f, fill=rgb(outline), stroke_width=14, stroke_fill=rgb(outline))
    ld.text((40 - left, 40 - top), text, font=f, fill=rgb(fill))
    layer = layer.rotate(tilt, expand=True, resample=Image.BICUBIC)
    layer.thumbnail((OBJ_SIZE - 20, OBJ_SIZE - 20))
    img.alpha_composite(layer, ((OBJ_SIZE - layer.width) // 2, (OBJ_SIZE - layer.height) // 2))
    return img


def obj_flower(color: str, center: str = "#FFF3D6") -> Image.Image:
    img, draw = _canvas()
    _flower(draw, OBJ_SIZE // 2, OBJ_SIZE // 2, 230, rgb(color), rgb(center))
    return _outline(img)


def obj_heart(color: str) -> Image.Image:
    img, draw = _canvas()
    c = OBJ_SIZE // 2
    r = 140
    draw.ellipse((c - r * 1.6, c - r * 1.4, c, c), fill=rgb(color))
    draw.ellipse((c, c - r * 1.4, c + r * 1.6, c), fill=rgb(color))
    draw.polygon([(c - r * 1.6 + 6, c - r * 0.55), (c + r * 1.6 - 6, c - r * 0.55), (c, c + r * 1.75)], fill=rgb(color))
    return img


def obj_paisley(color: str, accent: str) -> Image.Image:
    img, draw = _canvas()
    c = OBJ_SIZE // 2
    pts = []
    for i in range(80):
        t = i / 79 * math.pi * 2
        r = 200 * (1 + 0.55 * math.cos(t)) / 1.5
        pts.append((c + r * math.cos(t), c + r * math.sin(t) * 0.8))
    draw.polygon(pts, fill=rgb(color), outline=rgb("#1B1B22"), width=8)
    for k in range(3):
        rr = 90 - k * 25
        draw.ellipse((c - 40 - rr, c - rr, c - 40 + rr, c + rr), outline=rgb(accent), width=10)
    return img


def obj_branch(color: str) -> Image.Image:
    img, draw = _canvas()
    rnd = random.Random(hash(color) % 1000)
    pts = [(60 + i * 30, 320 + int(70 * math.sin(i / 3))) for i in range(17)]
    draw.line(pts, fill=rgb(color), width=6, joint="curve")
    for x, y in pts[1::2]:
        for i in range(5):
            a = math.radians(i * 72 + rnd.randint(0, 40))
            draw.ellipse((x + 22 * math.cos(a) - 14, y + 22 * math.sin(a) - 14,
                          x + 22 * math.cos(a) + 14, y + 22 * math.sin(a) + 14), outline=rgb(color), width=4)
    return img


def obj_sunglasses() -> Image.Image:
    img, draw = _canvas()
    px = 24
    rows = [
        "  XXXXXXXXXXXXXXXXXXXXXX  ",
        "  X......X....X......X    ",
        "  X......X....X......X    ",
        "   X....X      X....X     ",
        "    XXXX        XXXX      ",
    ]
    ox, oy = 0, 220
    for j, row in enumerate(rows):
        for i, ch in enumerate(row):
            if ch == "X":
                draw.rectangle((ox + i * px, oy + j * px, ox + (i + 1) * px, oy + (j + 1) * px), fill=rgb("#F2D23F"))
            elif ch == ".":
                draw.rectangle((ox + i * px, oy + j * px, ox + (i + 1) * px, oy + (j + 1) * px), fill=rgb("#1B1B22"))
    return img


def obj_star(color: str) -> Image.Image:
    img, draw = _canvas()
    c = OBJ_SIZE // 2
    pts = []
    for i in range(10):
        r = 250 if i % 2 == 0 else 110
        a = math.radians(-90 + i * 36)
        pts.append((c + r * math.cos(a), c + r * math.sin(a)))
    draw.polygon(pts, fill=rgb(color))
    return _outline(img)


def obj_peace(color: str) -> Image.Image:
    img, draw = _canvas()
    c, r = OBJ_SIZE // 2, 240
    draw.ellipse((c - r, c - r, c + r, c + r), outline=rgb(color), width=34)
    draw.line((c, c - r, c, c + r), fill=rgb(color), width=34)
    draw.line((c, c, c - r * 0.7, c + r * 0.7), fill=rgb(color), width=34)
    draw.line((c, c, c + r * 0.7, c + r * 0.7), fill=rgb(color), width=34)
    return img


def obj_bolt(color: str) -> Image.Image:
    img, draw = _canvas()
    draw.polygon([(340, 40), (150, 330), (290, 330), (230, 560), (450, 250), (310, 250)], fill=rgb(color))
    return _outline(img)


def obj_smiley(color: str) -> Image.Image:
    img, draw = _canvas()
    _smiley(draw, OBJ_SIZE // 2, OBJ_SIZE // 2, 230, rgb("#1B1B22"), width=16, fill=rgb(color))
    return img


def _autocrop(img: Image.Image, pad: float = 0.06) -> Image.Image:
    """Recadre sur le contenu visible et recentre dans un carre : chaque objet
    est ainsi centre et occupe la meme place dans sa vignette."""
    box = img.getchannel("A").getbbox()
    if not box:
        return img
    cropped = img.crop(box)
    side = int(max(cropped.size) * (1 + pad * 2))
    out = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    out.alpha_composite(cropped, ((side - cropped.width) // 2, (side - cropped.height) // 2))
    return out.resize((OBJ_SIZE, OBJ_SIZE), Image.LANCZOS)


def _outline(img: Image.Image, width: int = 10) -> Image.Image:
    alpha = img.getchannel("A").filter(ImageFilter.MaxFilter(width * 2 + 1))
    outline = Image.new("RGBA", img.size, (27, 27, 34, 255))
    outline.putalpha(alpha)
    outline.alpha_composite(img)
    return outline


OBJECTS = [
    ("sunglasses", obj_sunglasses, {"fr": "Lunettes pixel", "en": "Pixel shades", "es": "Gafas pixel"}),
    ("freedom-blue", lambda: obj_text("Freedom", "#4FC3F7", "#1D3FA3"), {"fr": "Freedom bleu", "en": "Blue Freedom", "es": "Freedom azul"}),
    ("freedom-purple", lambda: obj_text("Freedom", "#F3C9FF", "#7B2DA8"), {"fr": "Freedom violet", "en": "Purple Freedom", "es": "Freedom morado"}),
    ("freedom-green", lambda: obj_text("Freedom", "#B6F542", "#3E7A1F"), {"fr": "Freedom vert", "en": "Green Freedom", "es": "Freedom verde"}),
    ("flower-pink", lambda: obj_flower("#E86BB7", "#F5D24B"), {"fr": "Fleur rose", "en": "Pink flower", "es": "Flor rosa"}),
    ("flower-blue", lambda: obj_flower("#5FB3F5", "#F5D24B"), {"fr": "Fleur bleue", "en": "Blue flower", "es": "Flor azul"}),
    ("flower-orange", lambda: obj_flower("#F5A623", "#E8735A"), {"fr": "Fleur orange", "en": "Orange flower", "es": "Flor naranja"}),
    ("heart-green", lambda: obj_heart("#B6D33A"), {"fr": "Cœur vert", "en": "Green heart", "es": "Corazón verde"}),
    ("heart-orange", lambda: obj_heart("#F2B233"), {"fr": "Cœur orange", "en": "Orange heart", "es": "Corazón naranja"}),
    ("heart-pink", lambda: obj_heart("#F27AB3"), {"fr": "Cœur rose", "en": "Pink heart", "es": "Corazón rosa"}),
    ("paisley-blue", lambda: obj_paisley("#5FB3F5", "#F5D24B"), {"fr": "Paisley bleu", "en": "Blue paisley", "es": "Cachemir azul"}),
    ("paisley-purple", lambda: obj_paisley("#C79BF2", "#F27AB3"), {"fr": "Paisley violet", "en": "Purple paisley", "es": "Cachemir morado"}),
    ("branch-white", lambda: obj_branch("#FFFFFF"), {"fr": "Branche blanche", "en": "White branch", "es": "Rama blanca"}),
    ("branch-pink", lambda: obj_branch("#F27AB3"), {"fr": "Branche rose", "en": "Pink branch", "es": "Rama rosa"}),
    ("branch-black", lambda: obj_branch("#1B1B22"), {"fr": "Branche noire", "en": "Black branch", "es": "Rama negra"}),
    ("easy-retro", lambda: obj_text("EASY", "#E8735A", "#F9E9D2", face="party", size=190, tilt=0), {"fr": "EASY rétro", "en": "Retro EASY", "es": "EASY retro"}),
    ("star", lambda: obj_star("#F5D24B"), {"fr": "Étoile", "en": "Star", "es": "Estrella"}),
    ("peace", lambda: obj_peace("#FFFFFF"), {"fr": "Peace", "en": "Peace", "es": "Paz"}),
    ("bolt", lambda: obj_bolt("#FFE03D"), {"fr": "Éclair", "en": "Bolt", "es": "Rayo"}),
    ("smiley", lambda: obj_smiley("#FFE03D"), {"fr": "Smiley", "en": "Smiley", "es": "Smiley"}),
]


# --------------------------------------------------------------------------- main


def main() -> None:
    bg_dir, obj_dir, base_dir = MEDIA / "backgrounds", MEDIA / "objects", MEDIA / "base"
    for d in (bg_dir, obj_dir, base_dir):
        d.mkdir(parents=True, exist_ok=True)

    items = []
    for ident, make, label in BACKGROUNDS:
        make().save(bg_dir / f"{ident}.jpg", "JPEG", quality=88)
        items.append({"id": ident, "file": f"{ident}.jpg", "label": label})
    (bg_dir / "index.json").write_text(json.dumps({"items": items}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(items)} fonds -> {bg_dir}")

    items = []
    for ident, make, label in OBJECTS:
        _autocrop(make()).save(obj_dir / f"{ident}.png", "PNG")
        items.append({"id": ident, "file": f"{ident}.png", "label": label})
    (obj_dir / "index.json").write_text(json.dumps({"items": items}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(items)} objets -> {obj_dir}")

    # Geometrie de la planche de bord, partagee entre le canvas (Konva) et le
    # rendu serveur (Pillow). Unites : pixels du rendu final.
    shape = {
        "width": 3000,
        "height": 300,
        "cornerRadius": 95,
        "notch": {"width": 510, "height": 170, "radius": 34},
    }
    (base_dir / "shape.json").write_text(json.dumps(shape, indent=2), encoding="utf-8")
    print(f"masque -> {base_dir / 'shape.json'}")


if __name__ == "__main__":
    main()
