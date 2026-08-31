"""Deckygram logo generator.

Concept: a Steam Deck (front silhouette, bottom) launching a paper plane
(Telegram) out of its screen - "your screenshots fly from the Deck to
Telegram".  Telegram-blue badge, white shapes, rendered at 4x and
downscaled for clean edges.

Run (any Python with Pillow):  python make_logo.py
Writes logo.png (512x512) next to this script.
"""

import os

from PIL import Image, ImageDraw

S = 4
W = 512 * S

img = Image.new("RGBA", (W, W), (0, 0, 0, 0))


def px(*pts):
    return [(x * S, y * S) for x, y in pts]


# --- badge: rounded square, vertical Telegram-blue gradient ----------------
TOP = (42, 171, 238)      # #2AABEE
BOT = (30, 144, 205)
grad = Image.new("RGBA", (W, W))
gd = ImageDraw.Draw(grad)
for y in range(W):
    t = y / W
    c = tuple(int(TOP[i] + (BOT[i] - TOP[i]) * t) for i in range(3)) + (255,)
    gd.line([(0, y), (W, y)], fill=c)

mask = Image.new("L", (W, W), 0)
md = ImageDraw.Draw(mask)
md.rounded_rectangle([16 * S, 16 * S, (512 - 16) * S, (512 - 16) * S],
                     radius=100 * S, fill=255)
img.paste(grad, (0, 0), mask)
d = ImageDraw.Draw(img)

WHITE = (255, 255, 255, 255)
SCREEN = (23, 120, 176, 255)       # darker blue for the Deck screen
DETAIL = (170, 215, 245, 255)      # soft blue for grips/creases

# --- Steam Deck body (front view, bottom of the badge) ----------------------
# What makes it read as a DECK and not a generic handheld:
#   - wide, squared-off body (small corner radius, ~2.5:1)
#   - tall screen nearly touching top and bottom edges
#   - thumbsticks HIGH and INNER on both sides
#   - the signature SQUARE trackpads below each stick
#   - d-pad outer-left, ABXY outer-right, level with the sticks
d.rounded_rectangle(px((58, 296), (454, 452))[0] + px((58, 296), (454, 452))[1],
                    radius=30 * S, fill=WHITE)
# screen: big and tall, centered
d.rounded_rectangle(px((196, 308), (316, 440))[0] + px((196, 308), (316, 440))[1],
                    radius=8 * S, fill=SCREEN)
# thumbsticks (high, inner)
d.ellipse(px((143, 318), (179, 354))[0] + px((143, 318), (179, 354))[1],
          fill=DETAIL)
d.ellipse(px((333, 318), (369, 354))[0] + px((333, 318), (369, 354))[1],
          fill=DETAIL)
# square trackpads (below the sticks - the Deck's signature)
d.rounded_rectangle(px((126, 380), (172, 426))[0] + px((126, 380), (172, 426))[1],
                    radius=8 * S, fill=DETAIL)
d.rounded_rectangle(px((340, 380), (386, 426))[0] + px((340, 380), (386, 426))[1],
                    radius=8 * S, fill=DETAIL)
# d-pad (outer-left, level with sticks)
d.rounded_rectangle(px((84, 332), (124, 342))[0] + px((84, 332), (124, 342))[1],
                    radius=4 * S, fill=DETAIL)
d.rounded_rectangle(px((99, 317), (109, 357))[0] + px((99, 317), (109, 357))[1],
                    radius=4 * S, fill=DETAIL)
# ABXY (outer-right, level with sticks)
for cx, cy in ((408, 322), (422, 336), (408, 350), (394, 336)):
    d.ellipse(px((cx - 6, cy - 6), (cx + 6, cy + 6))[0]
              + px((cx - 6, cy - 6), (cx + 6, cy + 6))[1], fill=DETAIL)

# --- paper plane launching from the screen ---------------------------------
# small white plane, nose up-right, above the Deck
d.polygon(px((196, 210), (420, 96), (346, 292), (282, 232)), fill=WHITE)
d.polygon(px((282, 232), (287, 290), (322, 250)), fill=(222, 238, 250, 255))
d.line(px((420, 96), (282, 232)), fill=DETAIL, width=6 * S)

# --- launch trail: dots from the screen up to the plane's tail --------------
for cx, cy, r in ((242, 300, 8), (222, 272, 10), (206, 244, 12)):
    d.ellipse(px((cx - r, cy - r), (cx + r, cy + r))[0]
              + px((cx - r, cy - r), (cx + r, cy + r))[1],
              fill=(255, 255, 255, 170))

out = img.resize((512, 512), Image.LANCZOS)
out.save(os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo.png"))
print("logo.png written")
