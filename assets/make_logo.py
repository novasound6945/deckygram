"""Deckygram logo generator.

Draws a rounded-square badge in Telegram blue with a white paper plane,
plus a small screenshot frame in the plane's wake - "your screenshots,
flying to Telegram".  Rendered at 4x and downscaled for clean edges.

Run (any Python with Pillow):  python make_logo.py
Writes logo.png (512x512) next to this script.
"""

import os

from PIL import Image, ImageDraw

S = 4                      # supersampling factor
W = 512 * S

img = Image.new("RGBA", (W, W), (0, 0, 0, 0))
d = ImageDraw.Draw(img)


def px(*pts):
    return [(x * S, y * S) for x, y in pts]


# --- badge: rounded square, vertical Telegram-blue gradient ----------------
TOP = (42, 171, 238)      # #2AABEE
BOT = (34, 158, 217)      # #229ED9
R = 100                    # corner radius (in 512 space)

grad = Image.new("RGBA", (W, W))
gd = ImageDraw.Draw(grad)
for y in range(W):
    t = y / W
    c = tuple(int(TOP[i] + (BOT[i] - TOP[i]) * t) for i in range(3)) + (255,)
    gd.line([(0, y), (W, y)], fill=c)

mask = Image.new("L", (W, W), 0)
md = ImageDraw.Draw(mask)
md.rounded_rectangle([16 * S, 16 * S, (512 - 16) * S, (512 - 16) * S],
                     radius=R * S, fill=255)
img.paste(grad, (0, 0), mask)
d = ImageDraw.Draw(img)

WHITE = (255, 255, 255, 255)
FAINT = (255, 255, 255, 150)

# --- screenshot frame flying off in the wake -------------------------------
# a small tilted photo card, lower-left, as if just launched
card = Image.new("RGBA", (W, W), (0, 0, 0, 0))
cd = ImageDraw.Draw(card)
cd.rounded_rectangle(px((96, 300), (196, 380))[0] + px((96, 300), (196, 380))[1],
                     radius=10 * S, fill=FAINT)
# tiny "mountain + sun" glyph to read as a photo
cd.ellipse(px((112, 312), (130, 330))[0] + px((112, 312), (130, 330))[1],
           fill=(42, 171, 238, 220))
cd.polygon(px((104, 372), (138, 336), (162, 360), (176, 346), (190, 372)),
           fill=(42, 171, 238, 220))
card = card.rotate(12, center=(146 * S, 340 * S), resample=Image.BICUBIC)
img.alpha_composite(card)
d = ImageDraw.Draw(img)

# --- motion dashes between card and plane ----------------------------------
for x0, x1, y in ((196, 226, 302), (216, 252, 268), (240, 282, 236)):
    d.line(px((x0, y), (x1, y - 14)), fill=FAINT, width=7 * S)

# --- paper plane ------------------------------------------------------------
# body
d.polygon(px((150, 258), (438, 120), (338, 396), (262, 306)), fill=WHITE)
# tail fold (slightly translucent to suggest the crease)
d.polygon(px((262, 306), (268, 380), (312, 330)), fill=(225, 240, 250, 255))
# crease line
d.line(px((438, 120), (262, 306)), fill=(180, 215, 240, 255), width=6 * S)

out = img.resize((512, 512), Image.LANCZOS)
out.save(os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo.png"))
print("logo.png written")
