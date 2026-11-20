#!/usr/bin/env python3
"""
generate.py -- draws "The World in One Day", a one-page broadsheet that sums
up the world news of Thursday 19 November 2026, and writes it to entry.png.

Everything on the page (masthead, feature art, medium art, the dotted world
map, the briefs) is drawn in code with Pillow; no photograph or external
asset is used.  The picture is rendered at 2048x2048 and downscaled to
1024x1024 with a Lanczos filter so the small type stays crisp.

The render is deterministic: no randomness, no clock, no network.  Running
this script twice produces a byte-identical entry.png.
"""

import hashlib
import math
import os

from PIL import Image, ImageDraw, ImageFont

# --------------------------------------------------------------------------
# Canvas constants.  Layout is planned in "page units" (the final 1024px
# grid) and rendered at SCALE x that, then downscaled.
# --------------------------------------------------------------------------
PAGE = 1024
SCALE = 2
MARGIN = 22
RIGHT = PAGE - MARGIN            # 1002
CW = PAGE - 2 * MARGIN           # 980, content width

CREAM = (246, 241, 229)
CREAM_DARK = (238, 230, 212)
INK = (28, 27, 25)
INK_SOFT = (74, 70, 62)
RED = (179, 52, 42)
RED_DARK = (146, 38, 30)
HAIR = (196, 188, 168)
WHITE = (252, 250, 244)

SERIF = "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"
SERIF_B = "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"
SANS = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
SANS_B = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
SANS_O = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"  # no Sans-Oblique on this system

_font_cache = {}


def F(path, size):
    """Font at `size` page units (scaled to render pixels), cached."""
    px = max(4, int(round(size * SCALE)))
    key = (path, px)
    if key not in _font_cache:
        _font_cache[key] = ImageFont.truetype(path, px)
    return _font_cache[key]


def _u(v):
    """Page units -> render pixels."""
    return v * SCALE


class CV:
    """A thin scaling wrapper over ImageDraw: all coordinates are given in
    page units, all font sizes go through F()."""

    def __init__(self, img):
        self.img = img
        self.d = ImageDraw.Draw(img)

    # -- measurements ------------------------------------------------------
    def tw(self, s, font):
        return self.d.textlength(s, font=font) / SCALE

    def wrap(self, s, font, maxw):
        """Greedy word wrap; returns a list of lines that fit maxw."""
        words = s.split()
        lines, cur = [], ""
        for w_ in words:
            trial = (cur + " " + w_).strip()
            if self.tw(trial, font) <= maxw or not cur:
                cur = trial
            else:
                lines.append(cur)
                cur = w_
        if cur:
            lines.append(cur)
        return lines

    # -- primitives --------------------------------------------------------
    def rect(self, x, y, w, h, fill=None, outline=None, width=1):
        self.d.rectangle([_u(x), _u(y), _u(x + w), _u(y + h)],
                         fill=fill, outline=outline,
                         width=max(1, int(round(width * SCALE))))

    def line(self, pts, fill=INK, width=1):
        self.d.line([(_u(x), _u(y)) for x, y in pts], fill=fill,
                    width=max(1, int(round(width * SCALE))))

    def hline(self, x0, x1, y, fill=INK, width=1):
        self.line([(x0, y), (x1, y)], fill=fill, width=width)

    def vline(self, x, y0, y1, fill=INK, width=1):
        self.line([(x, y0), (x, y1)], fill=fill, width=width)

    def ellipse(self, x, y, w, h, fill=None, outline=None, width=1):
        self.d.ellipse([_u(x), _u(y), _u(x + w), _u(y + h)],
                       fill=fill, outline=outline,
                       width=max(1, int(round(width * SCALE))))

    def poly(self, pts, fill=None, outline=None, width=1):
        self.d.polygon([(_u(x), _u(y)) for x, y in pts], fill=fill,
                       outline=outline,
                       width=max(1, int(round(width * SCALE))))

    def arc(self, x, y, w, h, a0, a1, fill=INK, width=1):
        self.d.arc([_u(x), _u(y), _u(x + w), _u(y + h)], a0, a1, fill=fill,
                   width=max(1, int(round(width * SCALE))))

    def text(self, x, y, s, font, fill=INK, anchor="la"):
        self.d.text((_u(x), _u(y)), s, font=font, fill=fill, anchor=anchor)

    def tracked(self, x, y, s, font, fill=INK, tracking=1.2, anchor_right=None):
        """Letter-spaced text, drawn glyph by glyph.  Returns end x."""
        widths = [self.tw(ch, font) for ch in s]
        total = sum(widths) + tracking * max(0, len(s) - 1)
        if anchor_right is not None:
            x = anchor_right - total
        cx = x
        for ch, wch in zip(s, widths):
            self.text(cx, y, ch, font, fill=fill)
            cx += wch + tracking
        return cx

    def tracked_width(self, s, font, tracking=1.2):
        return sum(self.tw(ch, font) for ch in s) + tracking * max(0, len(s) - 1)


def italic_line(img, x, y, s, font, fill):
    """Draw one line of fake-italic serif: render upright, shear, paste."""
    pad = 6
    meas = ImageDraw.Draw(img)
    wpx = int(meas.textlength(s, font=font)) + pad * 2 * SCALE
    hpx = int(font.size * 1.6) + pad * 2 * SCALE
    layer = Image.new("RGBA", (wpx, hpx), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    ld.text((pad * SCALE, pad * SCALE), s, font=font, fill=fill + (255,))
    shear = 0.22
    extra = int(shear * hpx) + 2
    layer = layer.transform((wpx + extra, hpx), Image.AFFINE,
                            (1, shear, -shear * hpx, 0, 1, 0),
                            resample=Image.BILINEAR)
    img.paste(layer, (int(_u(x)) - pad * SCALE, int(_u(y)) - pad * SCALE),
              layer)
    return meas.textlength(s, font=font) / SCALE


def number_circle(cv, x, y, d, n, fill=RED):
    cv.ellipse(x, y, d, d, fill=fill)
    f = F(SANS_B, d * 0.60)
    cv.text(x + d / 2, y + d / 2 + d * 0.03, str(n), f, fill=WHITE,
            anchor="mm")


def chip(cv, x_right, y, label, h=13):
    """Small outlined tag chip, right-aligned at x_right. Returns its width."""
    f = F(SANS_B, h * 0.56)
    w = cv.tw(label, f) + 9
    cv.rect(x_right - w, y, w, h, outline=INK_SOFT, width=0.8)
    cv.text(x_right - w / 2, y + h / 2 - h * 0.30, label, f, fill=INK_SOFT,
            anchor="ma")
    return w


def stamp(img, cx, cy, label, color=RED, size=13, angle=-11):
    """A rotated rubber-stamp label (outline box + bold text), pasted at
    page-unit centre (cx, cy)."""
    f = F(SANS_B, size)
    meas = ImageDraw.Draw(img)
    tw_ = meas.textlength(label, font=f)
    wpx = int(tw_ + 14 * SCALE)
    hpx = int(f.size * 1.9)
    layer = Image.new("RGBA", (wpx + 8, hpx + 8), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer)
    ld.rectangle([3, 3, wpx + 3, hpx + 3], outline=color + (255,),
                 width=max(2, int(1.4 * SCALE)))
    ld.text((wpx / 2 + 3, hpx / 2 + 4), label, font=f, fill=color + (255,),
            anchor="mm")
    layer = layer.rotate(angle, resample=Image.BILINEAR, expand=True)
    img.paste(layer, (int(_u(cx) - layer.width / 2),
                      int(_u(cy) - layer.height / 2)), layer)


# --------------------------------------------------------------------------
# The day's slate (all stories: Thursday 19 November 2026)
# --------------------------------------------------------------------------
TOTAL_STORIES = 40

REGIONS = [
    ("ASIA-PACIFIC", 9, (46, 95, 138)),
    ("EUROPE", 10, (62, 122, 78)),
    ("MIDDLE EAST", 5, (168, 80, 60)),
    ("AMERICAS", 4, (124, 106, 174)),
    ("AFRICA", 5, (138, 109, 59)),
    ("OCEANIA", 4, (79, 150, 168)),
    ("WORLDWIDE", 3, (74, 74, 72)),
]

UTC_ITEMS = [
    ("00:00", "AUCKLAND", "GTA VI unlocks"),
    ("04:42", "RIYADH", "air-raid sirens"),
    ("08:40", "SEOUL", "exam begins"),
    ("09:30", "JAKARTA", "law passed"),
    ("10:00", "THE HAGUE", "genocide ruling"),
    ("12:30", "SHENZHEN", "three leaders meet"),
    ("14:30", "NEW YORK", "Anthropic debut"),
]

NUMBERS = [
    ("3", "presidents at one table"),
    ("9–6", "World Court genocide vote"),
    ("$81.3bn", "Anthropic’s record IPO raise"),
    ("$120bn", "aid goal cut at COP31"),
    ("109–0", "Danish vote on Arctic pact"),
    ("4.9%", "Australian jobless rate"),
]


FEATURES = [
    {
        "n": 1, "kicker": "SHENZHEN · SUMMIT", "tag": "CONFIRMED",
        "banner": "FIRST US–CHINA–RUSSIA SUMMIT · APEC 2026",
        "art": "summit", "artfoot": None,
        "headline": "Trump, Xi and Putin hold first three-way summit",
        "dek": ("The US, Chinese and Russian leaders met for 90 minutes "
                "beside APEC in Shenzhen and issued a “Declaration toward "
                "Peace” on nuclear risk and UN reform. Kyiv was not in "
                "the room."),
        "source": "— Reuters · AP · Xinhua",
    },
    {
        "n": 2, "kicker": "THE HAGUE · JUSTICE", "tag": "CONFIRMED",
        "banner": "9–6 · GENOCIDE VERDICT",
        "art": "court", "artfoot": "WORLD COURT · THE HAGUE",
        "headline": "World Court: Myanmar committed genocide",
        "dek": ("By 9 votes to 6 the ICJ found Myanmar guilty of genocide "
                "against the Rohingya in 2017 and ordered reparations and "
                "safe returns. Some 730,000 people fled to Bangladesh."),
        "source": "— Al Jazeera · UN News",
    },
    {
        "n": 3, "kicker": "ANTALYA · CLIMATE", "tag": "CONFIRMED",
        "banner": "DRAFT DEAL · 19 NOV · AID GOAL CUT",
        "art": "cop", "artfoot": "COP31 · ANTALYA",
        "headline": "COP31 draft drops fossil fuels and $120bn aid goal",
        "dek": ("The slimmer draft text drops the fossil-fuel phase-out "
                "and carries no figure for adaptation aid. Negotiators "
                "published the revised text in Antalya; talks are due to "
                "end on Friday."),
        "source": "— Reuters · AFP",
    },
]


def _flag_us(cv, x, y, w, h):
    stripe = h / 7.0
    for i in range(7):
        cv.rect(x, y + i * stripe, w, stripe + 0.6,
                fill=(178, 34, 52) if i % 2 == 0 else (244, 242, 238))
    cv.rect(x, y, w * 0.44, stripe * 4, fill=(38, 48, 110))
    df = F(SANS_B, 3.4)
    for r in range(3):
        for c in range(4):
            cv.text(x + 3 + c * w * 0.105, y + 1.5 + r * stripe * 1.28,
                    "★", df, fill=WHITE)


def _flag_cn(cv, x, y, w, h):
    cv.rect(x, y, w, h, fill=(222, 41, 16))
    f1 = F(SANS_B, 9)
    cv.text(x + w * 0.10, y + h * 0.10, "★", f1, fill=(255, 222, 0))
    f2 = F(SANS_B, 4.6)
    for dx, dy in [(0.34, 0.10), (0.40, 0.26), (0.40, 0.44), (0.33, 0.58)]:
        cv.text(x + w * dx, y + h * dy, "★", f2, fill=(255, 222, 0))


def _flag_ru(cv, x, y, w, h):
    t = h / 3.0
    cv.rect(x, y, w, t + 0.5, fill=(244, 242, 238))
    cv.rect(x, y + t, w, t + 0.5, fill=(30, 60, 160))
    cv.rect(x, y + 2 * t, w, t + 0.5, fill=(204, 40, 40))


def art_summit(cv, x, y, w, h):
    """Three leaders at one long table, flags behind them (F1)."""
    cv.rect(x, y, w, h, fill=(30, 46, 78))
    cv.rect(x, y + h * 0.62, w, h * 0.38, fill=(24, 36, 62))
    fw, fh = w * 0.17, h * 0.34
    fy = y + h * 0.16
    xs = [x + w * 0.10, x + w * 0.415, x + w * 0.73]
    for fx, fn in zip(xs, (_flag_us, _flag_cn, _flag_ru)):
        cv.vline(fx - 2.5, fy - 4, y + h * 0.66, fill=(120, 128, 148), width=1.4)
        fn(cv, fx, fy, fw, fh)
        cv.rect(fx, fy, fw, fh, outline=(10, 14, 24), width=0.8)
    # table
    ty = y + h * 0.70
    cv.poly([(x + w * 0.05, ty), (x + w * 0.95, ty),
             (x + w * 0.99, y + h * 0.97), (x + w * 0.01, y + h * 0.97)],
            fill=(96, 62, 38))
    cv.hline(x + w * 0.05, x + w * 0.95, ty, fill=(140, 100, 62), width=1.6)
    # leaders
    skin = [(232, 183, 140), (238, 196, 156), (233, 186, 143)]
    hair = [(206, 172, 96), (30, 30, 32), (168, 160, 148)]
    ties = [(178, 34, 52), (150, 30, 30), (36, 52, 120)]
    names = ["TRUMP", "XI", "PUTIN"]
    nf = F(SANS_B, 7.2)
    for i, cxr in enumerate([0.185, 0.50, 0.815]):
        cx = x + w * cxr
        hy = y + h * 0.47
        # suit
        cv.poly([(cx - w * 0.085, ty + 2), (cx - w * 0.062, hy + 13),
                 (cx + w * 0.062, hy + 13), (cx + w * 0.085, ty + 2)],
                fill=(22, 24, 30))
        cv.poly([(cx - 6, hy + 13), (cx + 6, hy + 13), (cx, ty + 2)],
                fill=(240, 238, 232))
        cv.poly([(cx - 2.2, hy + 15), (cx + 2.2, hy + 15),
                 (cx + 1.2, ty - 4), (cx - 1.2, ty - 4)], fill=ties[i])
        # head + hair (filled half-disc)
        cv.ellipse(cx - 11.5, hy - 13, 23, 25, fill=skin[i])
        cv.d.pieslice([_u(cx - 11.5), _u(hy - 13), _u(cx + 11.5),
                       _u(hy + 12)], 180, 360, fill=hair[i])
        # name plate
        pw = cv.tw(names[i], nf) + 10
        cv.rect(cx - pw / 2, ty + h * 0.115, pw, 12.5, fill=(238, 230, 205))
        cv.text(cx, ty + h * 0.115 + 2.2, names[i], nf, fill=INK, anchor="ma")


def art_court(cv, x, y, w, h):
    """Courthouse with columns and a balance scale (F2)."""
    cv.rect(x, y, w, h, fill=(178, 203, 224))
    cv.rect(x, y + h * 0.80, w, h * 0.20, fill=(148, 168, 150))
    bx, bw = x + w * 0.07, w * 0.52
    by = y + h * 0.08
    # pediment + roof
    cv.poly([(bx - 6, by + 13), (bx + bw / 2, by - 6), (bx + bw + 6, by + 13)],
            fill=(146, 58, 46))
    cv.rect(bx - 6, by + 13, bw + 12, 4.4, fill=(120, 48, 38))
    cv.ellipse(bx + bw / 2 - 4, by, 8, 8, fill=(240, 234, 220),
               outline=(120, 48, 38), width=0.8)
    # columns
    col_y = by + 17.5
    col_h = h * 0.46
    for i in range(5):
        cx = bx + 8 + i * (bw - 16) / 4
        cv.rect(cx - 4.5, col_y, 9, col_h, fill=(243, 240, 232),
                outline=(150, 148, 140), width=0.7)
        cv.rect(cx - 6, col_y - 3, 12, 3.4, fill=(226, 220, 205))
        cv.rect(cx - 6, col_y + col_h, 12, 3.4, fill=(226, 220, 205))
    # steps
    sy = col_y + col_h + 3.5
    for i in range(2):
        cv.rect(bx - 4 - i * 3, sy + i * 4.2, bw + 8 + i * 6, 3.6,
                fill=(214, 208, 194), outline=(160, 156, 146), width=0.6)
    # balance scale
    sx = x + w * 0.80
    top = y + h * 0.20
    bot = y + h * 0.82
    cv.vline(sx, top, bot, fill=(60, 54, 44), width=2.6)
    cv.hline(sx - w * 0.155, sx + w * 0.155, top + 4, fill=(60, 54, 44),
             width=2.6)
    cv.ellipse(sx - 4, top - 6, 8, 8, fill=(198, 158, 44))
    for sgn, drop in [(-1, 7), (1, 1.5)]:
        px = sx + sgn * w * 0.155
        py = top + 4 + drop
        cv.line([(px, top + 4), (px - 11, py + 13)], fill=(60, 54, 44),
                width=1.1)
        cv.line([(px, top + 4), (px + 11, py + 13)], fill=(60, 54, 44),
                width=1.1)
        cv.arc(px - 13, py + 6, 26, 15, 0, 180, fill=(60, 54, 44), width=2)
        cv.hline(px - 13, px + 13, py + 13.5, fill=(60, 54, 44), width=1.6)
    cv.rect(sx - 13, bot - 2, 26, 4.5, fill=(60, 54, 44))


def art_cop(cv, x, y, w, h):
    """Globe + thermometer + draft document with a struck line (F3)."""
    cv.rect(x, y, w, h, fill=(38, 104, 96))
    cv.rect(x, y + h * 0.78, w, h * 0.22, fill=(30, 84, 78))
    # globe
    gx, gy, gr = x + w * 0.17, y + h * 0.52, h * 0.335
    cv.ellipse(gx - gr, gy - gr, 2 * gr, 2 * gr, fill=(58, 116, 165))
    land = (92, 158, 96)
    cv.poly([(gx - gr * 0.55, gy - gr * 0.62), (gx - gr * 0.18, gy - gr * 0.78),
             (gx - gr * 0.05, gy - gr * 0.45), (gx - gr * 0.28, gy - gr * 0.2),
             (gx - gr * 0.52, gy - gr * 0.3)], fill=land)
    cv.poly([(gx - gr * 0.30, gy + gr * 0.02), (gx - gr * 0.05, gy + gr * 0.05),
             (gx - gr * 0.12, gy + gr * 0.42), (gx - gr * 0.30, gy + gr * 0.55),
             (gx - gr * 0.42, gy + gr * 0.2)], fill=land)
    cv.poly([(gx + gr * 0.18, gy - gr * 0.55), (gx + gr * 0.62, gy - gr * 0.5),
             (gx + gr * 0.7, gy - gr * 0.15), (gx + gr * 0.35, gy - gr * 0.05),
             (gx + gr * 0.15, gy - gr * 0.28)], fill=land)
    cv.poly([(gx + gr * 0.3, gy + gr * 0.28), (gx + gr * 0.55, gy + gr * 0.3),
             (gx + gr * 0.45, gy + gr * 0.62), (gx + gr * 0.25, gy + gr * 0.5)],
            fill=land)
    cv.ellipse(gx - gr, gy - gr, 2 * gr, 2 * gr, outline=(24, 60, 90),
               width=1.2)
    # thermometer
    tx = x + w * 0.415
    tube_t, tube_b = y + h * 0.18, y + h * 0.72
    cv.rect(tx - 4.5, tube_t, 9, tube_b - tube_t, fill=(238, 240, 238),
            outline=(30, 50, 55), width=0.8)
    cv.rect(tx - 4.5, tube_t + (tube_b - tube_t) * 0.38, 9,
            (tube_b - tube_t) * 0.62, fill=RED)
    cv.ellipse(tx - 9.5, tube_b - 4, 19, 19, fill=RED, outline=(30, 50, 55),
               width=0.8)
    for i in range(4):
        tyy = tube_t + 4 + i * (tube_b - tube_t - 10) / 3
        cv.hline(tx + 6.5, tx + 11.5, tyy, fill=(230, 236, 234), width=1)
    # document
    dx, dy, dw, dh = x + w * 0.535, y + h * 0.10, w * 0.43, h * 0.76
    cv.rect(dx + 3, dy + 3, dw, dh, fill=(20, 60, 56))
    cv.rect(dx, dy, dw, dh, fill=(250, 248, 240), outline=(120, 118, 108),
            width=0.8)
    tf = F(SANS_B, 12.5)
    cv.text(dx + dw * 0.08, dy + dh * 0.11, "REVISED TEXT · 19 NOV",
            F(SANS_B, 7), fill=INK_SOFT)
    txx = dx + dw * 0.08
    tyy = dy + dh * 0.34
    cv.text(txx, tyy, "FOSSIL FUELS", tf, fill=INK)
    twd = cv.tw("FOSSIL FUELS", tf)
    cv.line([(txx - 2, tyy + 8.5), (txx + twd + 2, tyy + 5.5)], fill=RED,
            width=2.4)
    for i in range(2):
        gy = dy + dh * (0.60 + i * 0.15)
        cv.hline(dx + dw * 0.08, dx + dw * 0.86, gy, fill=(178, 174, 162),
                 width=1.6)
    cv.text(dx + dw * 0.08, dy + dh * 0.80, "$120BN ADAPTATION AID",
            F(SANS_B, 7.2), fill=INK_SOFT)


MEDIUMS = [
    {"n": 4, "kicker": "NEW YORK · MARKETS", "tag": "CONFIRMED",
     "label": "ANT · NASDAQ", "art": "chart",
     "headline": "Anthropic starts trading on Nasdaq",
     "brief": ("Its record $81.3bn share sale was priced at $83 on "
               "Wednesday; shares opened at $111.50, passing SpaceX’s "
               "$75bn record. — AP")},
    {"n": 5, "kicker": "WORLDWIDE · GAMES", "tag": "CONFIRMED",
     "label": "GTA VI", "art": "gta",
     "headline": "GTA VI goes on sale after 13 years",
     "brief": ("The midnight launch draws rave reviews; analysts estimate "
               "17.1m pre-orders worth about $1.65bn, on PS5 and Xbox "
               "only. — ABC")},
    {"n": 6, "kicker": "CRIMEA · WAR", "tag": "CONFIRMED",
     "label": "KERCH BRIDGE", "art": "bridge",
     "headline": "Ukraine hits Crimea bridge again",
     "brief": ("A third strike in a week halts trains to Russia over the "
               "Kerch Bridge. — Euronews")},
    {"n": 7, "kicker": "RIYADH · GULF", "tag": "CLAIM",
     "label": "OVER RIYADH", "art": "riyadh",
     "headline": "Saudis shoot down Houthi missiles",
     "brief": ("Debris fell on the capital; no casualties were reported, "
               "the Saudi-led coalition said. — Reuters")},
    {"n": 8, "kicker": "ODISHA · STORM", "tag": "FORECAST",
     "label": "CYCLONE AKVAN", "art": "cyclone",
     "headline": "Cyclone Akvan nears India’s coast",
     "brief": ("204,070 people are listed to evacuate and 11 districts "
               "are on red alert before Friday’s landfall near "
               "Gopalpur. — IMD")},
    {"n": 9, "kicker": "SEOUL · JUSTICE", "tag": "CONFIRMED",
     "label": "SEOUL", "art": "seoul",
     "headline": "Korea’s top court clears ex-PM Han",
     "brief": ("The Supreme Court overturns Han Duck-soo’s martial-law "
               "conviction and orders a retrial. — AP")},
    {"n": 10, "kicker": "GREENLAND · SECURITY", "tag": "CONFIRMED",
     "label": "GREENLAND · 109–0", "art": "greenland",
     "headline": "Denmark backs Arctic pact with US",
     "brief": ("Parliament approves the Greenland security deal 109–0, "
               "expanding the US presence under Danish sovereignty. — AP")},
    {"n": 11, "kicker": "CANBERRA · ECONOMY", "tag": "CONFIRMED",
     "label": "JOBLESS RATE", "art": "bars",
     "headline": "Australia’s jobless rate jumps to 4.9%",
     "brief": ("A five-year high: 753,700 people were unemployed in "
               "October and the dollar slid. — ABS")},
    {"n": 12, "kicker": "NAIROBI · SPORT", "tag": "CONFIRMED",
     "label": "DOPING · 3 YEARS", "art": "runner",
     "headline": "Marathon champion banned for doping",
     "brief": ("Kenya’s Peres Jepchirchir gets three years after "
               "admitting an EPO violation. — ABC")},
    {"n": 13, "kicker": "BOGOTÁ · LABOUR", "tag": "CONFIRMED",
     "label": "PARO NACIONAL", "art": "crowd",
     "headline": "Colombia’s unions hold national strike",
     "brief": ("Teachers and workers march in Bogotá, Medellín and Cali "
               "against the economic rescue bill. — Infobae")},
]


def _burst(cv, cx, cy, r, color=(250, 214, 90)):
    for a in range(0, 360, 45):
        rad = math.radians(a)
        cv.line([(cx, cy), (cx + r * math.cos(rad), cy + r * math.sin(rad))],
                fill=color, width=1.3)
    cv.ellipse(cx - 1.8, cy - 1.8, 3.6, 3.6, fill=(255, 240, 190))


def art_chart(cv, x, y, w, h):
    cv.rect(x, y, w, h, fill=(22, 62, 46))
    cv.text(x + 8, y + h * 0.16, "ANT", F(SANS_B, 15), fill=WHITE)
    pts = [(0.34, 0.78), (0.48, 0.62), (0.60, 0.68), (0.72, 0.44),
           (0.84, 0.50), (0.965, 0.20)]
    cv.line([(x + w * a, y + h * b) for a, b in pts], fill=(120, 230, 150),
            width=2)
    ex, ey = x + w * 0.965, y + h * 0.20
    cv.poly([(ex, ey), (ex - 7, ey + 1), (ex - 1, ey + 6)], fill=(120, 230, 150))
    for i, bh in enumerate([0.30, 0.42, 0.38, 0.55, 0.50, 0.72]):
        bx = x + w * (0.36 + i * 0.105)
        cv.rect(bx, y + h * (0.94 - bh * 0.5), w * 0.055, h * bh * 0.5,
                fill=(52, 110, 78))


def art_gta(cv, x, y, w, h):
    bands = [(88, 44, 108), (140, 52, 110), (196, 84, 92), (232, 128, 70),
             (246, 178, 92)]
    bh = h / len(bands)
    for i, c in enumerate(bands):
        cv.rect(x, y + i * bh, w, bh + 0.6, fill=c)
    cv.ellipse(x + w * 0.40, y + h * 0.30, w * 0.17, h * 0.52,
               fill=(250, 196, 96))
    cv.rect(x, y + h * 0.80, w, h * 0.20, fill=(30, 18, 40))
    # palm silhouettes
    for px, ph in [(0.16, 0.62), (0.30, 0.45)]:
        bx, by = x + w * px, y + h * 0.86
        cv.line([(bx, by), (bx + 2, by - h * ph)], fill=(24, 14, 34), width=2.2)
        tx, ty = bx + 2, by - h * ph
        for a in (-160, -115, -70, -25, 15):
            rad = math.radians(a)
            cv.line([(tx, ty), (tx + 11 * math.cos(rad), ty + 6 * math.sin(rad))],
                    fill=(24, 14, 34), width=1.6)
    cv.text(x + w * 0.97, y + h * 0.10, "VI", F(SERIF_B, 19), fill=WHITE,
            anchor="ra")


def art_bridge(cv, x, y, w, h):
    cv.rect(x, y, w, h * 0.58, fill=(126, 174, 214))
    cv.rect(x, y + h * 0.58, w, h * 0.42, fill=(56, 106, 160))
    dy = y + h * 0.52
    cv.hline(x, x + w, dy, fill=(40, 44, 52), width=2.2)
    for i in range(9):
        px = x + w * (0.06 + i * 0.11)
        cv.vline(px, dy - h * 0.16, dy, fill=(40, 44, 52), width=1)
    cv.arc(x + w * 0.08, dy - h * 0.30, w * 0.84, h * 0.34, 180, 360,
           fill=(40, 44, 52), width=1.4)
    _burst(cv, x + w * 0.52, dy - h * 0.10, 7, color=(255, 150, 50))
    for i in range(4):
        cv.hline(x + w * (0.08 + i * 0.22), x + w * (0.18 + i * 0.22),
                 y + h * (0.72 + (i % 2) * 0.12), fill=(170, 205, 230),
                 width=1)


def art_riyadh(cv, x, y, w, h):
    cv.rect(x, y, w, h, fill=(14, 20, 42))
    for i, (bw_, bh) in enumerate([(0.10, 0.42), (0.13, 0.60), (0.09, 0.36),
                                    (0.14, 0.52), (0.10, 0.44), (0.12, 0.58),
                                    (0.11, 0.40)]):
        bx = x + w * (0.03 + i * 0.135)
        cv.rect(bx, y + h * (1 - bh), w * bw_, h * bh, fill=(6, 8, 18))
        for wy in (0.18, 0.38):
            cv.rect(bx + w * bw_ * 0.3, y + h * (1 - bh + wy), 1.8, 1.8,
                    fill=(250, 214, 90))
    _burst(cv, x + w * 0.30, y + h * 0.26, 6.5)
    _burst(cv, x + w * 0.58, y + h * 0.16, 5)
    _burst(cv, x + w * 0.82, y + h * 0.32, 6)


def art_cyclone(cv, x, y, w, h):
    cv.rect(x, y, w, h, fill=(58, 88, 104))
    cx, cy = x + w * 0.60, y + h * 0.52
    for r, a0 in [(13, 20), (9.5, 140), (6, 260)]:
        cv.arc(cx - r, cy - r * 0.78, 2 * r, 2 * r * 0.78, a0, a0 + 235,
               fill=(235, 242, 244), width=2)
    cv.ellipse(cx - 2.4, cy - 2.4, 4.8, 4.8, fill=(235, 242, 244))
    cv.poly([(x, y + h), (x, y + h * 0.52), (x + w * 0.20, y + h * 0.40),
             (x + w * 0.30, y + h * 0.66), (x + w * 0.26, y + h)],
            fill=(206, 182, 138))
    cv.text(x + w * 0.055, y + h * 0.60, "ODISHA", F(SANS_B, 6),
            fill=(90, 74, 44))


def art_seoul(cv, x, y, w, h):
    cv.rect(x, y, w, h, fill=(233, 227, 209))
    bx, by, bw = x + w * 0.07, y + h * 0.14, w * 0.34
    cv.poly([(bx - 3, by + 8), (bx + bw / 2, by - 3), (bx + bw + 3, by + 8)],
            fill=(146, 58, 46))
    for i in range(3):
        cx = bx + 4 + i * (bw - 8) / 2
        cv.rect(cx - 2.4, by + 10, 4.8, h * 0.52, fill=(248, 246, 238),
                outline=(150, 148, 140), width=0.6)
    cv.rect(bx - 3, by + h * 0.66, bw + 6, 3, fill=(120, 116, 104))


def art_greenland(cv, x, y, w, h):
    cv.rect(x, y, w, h, fill=(203, 226, 238))
    gx, gy = x + w * 0.44, y + h * 0.50
    cv.poly([(gx - 16, gy + 8), (gx - 12, gy - 6), (gx - 4, gy - 13),
             (gx + 7, gy - 12), (gx + 14, gy - 5), (gx + 12, gy + 5),
             (gx + 4, gy + 13), (gx - 6, gy + 12)], fill=(248, 250, 252),
            outline=(150, 175, 195), width=0.8)
    # Danish flag
    fx, fy = x + w * 0.10, y + h * 0.16
    cv.vline(fx, fy, fy + h * 0.62, fill=(70, 70, 70), width=1.2)
    cv.rect(fx + 1, fy, 17, 11.5, fill=(198, 40, 48))
    cv.rect(fx + 6, fy, 3, 11.5, fill=WHITE)
    cv.rect(fx + 1, fy + 4.6, 17, 2.6, fill=WHITE)
    # US flag (simplified)
    fx2 = x + w * 0.80
    cv.vline(fx2, fy, fy + h * 0.62, fill=(70, 70, 70), width=1.2)
    _flag_us(cv, fx2 + 1, fy, 17, 11.5)


def art_bars(cv, x, y, w, h):
    cv.rect(x, y, w, h, fill=(240, 231, 217))
    base = y + h * 0.88
    cv.hline(x + w * 0.06, x + w * 0.96, base, fill=INK_SOFT, width=1)
    b1x, b2x, bw = x + w * 0.30, x + w * 0.58, w * 0.15
    cv.rect(b1x, base - h * 0.42, bw, h * 0.42, fill=(140, 136, 128))
    cv.rect(b2x, base - h * 0.52, bw, h * 0.52, fill=RED)
    cv.text(b1x + bw / 2, base - h * 0.42 - 8.5, "4.7%", F(SANS_B, 7.5),
            fill=INK_SOFT, anchor="ma")
    cv.text(b2x + bw / 2, base - h * 0.52 - 8.5, "4.9%", F(SANS_B, 7.5),
            fill=RED, anchor="ma")
    cv.text(x + w * 0.06, y + h * 0.10, "OCT", F(SANS_B, 6.4), fill=INK_SOFT)


def art_runner(cv, x, y, w, h):
    cv.rect(x, y, w, h, fill=(231, 222, 204))
    cv.hline(x, x + w, y + h * 0.86, fill=(170, 158, 128), width=1.6)
    cx, cy = x + w * 0.34, y + h * 0.30
    ink = (38, 36, 34)
    cv.ellipse(cx - 3.4, cy - 8, 6.8, 6.8, fill=ink)
    cv.line([(cx, cy), (cx + 5, cy + 9)], fill=ink, width=2.6)          # torso
    cv.line([(cx + 5, cy + 9), (cx + 13, cy + 12)], fill=ink, width=2.4)  # thigh
    cv.line([(cx + 13, cy + 12), (cx + 11, cy + 20)], fill=ink, width=2.4)  # shin
    cv.line([(cx + 5, cy + 9), (cx - 3, cy + 15)], fill=ink, width=2.4)  # thigh b
    cv.line([(cx - 3, cy + 15), (cx + 4, cy + 21)], fill=ink, width=2.4)  # shin b
    cv.line([(cx + 1, cy + 2), (cx + 9, cy + 7)], fill=ink, width=2.2)   # arm
    cv.line([(cx + 1, cy + 2), (cx - 6, cy + 8)], fill=ink, width=2.2)   # arm b


def art_crowd(cv, x, y, w, h):
    cv.rect(x, y, w, h, fill=(222, 231, 242))
    # banners on poles
    for bx, txt, col in [(0.10, "PARO", (198, 60, 50)), (0.55, "24H", (52, 84, 140))]:
        px = x + w * bx
        cv.vline(px, y + h * 0.18, y + h * 0.78, fill=(70, 66, 60), width=1.4)
        cv.rect(px, y + h * 0.14, w * 0.30, h * 0.30, fill=col)
        cv.text(px + w * 0.15, y + h * 0.20, txt, F(SANS_B, 7), fill=WHITE,
                anchor="ma")
    # crowd heads
    cols = [(198, 90, 60), (60, 90, 160), (90, 140, 90), (200, 160, 60),
            (150, 80, 140)]
    for row in range(2):
        for i in range(9):
            hx = x + w * (0.06 + i * 0.105) + (row * 4)
            hy = y + h * (0.66 + row * 0.17)
            cv.ellipse(hx - 3.4, hy - 3.4, 6.8, 6.8,
                       fill=cols[(i + row) % len(cols)])
            cv.rect(hx - 4.4, hy + 3.2, 8.8, 3.6,
                    fill=cols[(i + row + 2) % len(cols)])


ART_FNS = {
    "summit": art_summit, "court": art_court, "cop": art_cop,
    "chart": art_chart, "gta": art_gta, "bridge": art_bridge,
    "riyadh": art_riyadh, "cyclone": art_cyclone, "seoul": art_seoul,
    "greenland": art_greenland, "bars": art_bars, "runner": art_runner,
    "crowd": art_crowd,
}


BRIEFS = [
    (14, "KYIV", "Zelensky says there can be no talks about Ukraine without Ukraine at the table.", "Reuters"),
    (15, "SHENZHEN", "Xi urges a ban on all nuclear arms as the three leaders meet.", "Al Jazeera"),
    (16, "SHENZHEN", "Trump and Xi agree that oil must keep flowing through Hormuz.", "Reuters"),
    (17, "APEC", "Australia’s Albanese tells Putin to end the war in Ukraine now.", "ABC"),
    (18, "SEOUL", "551,864 candidates sit South Korea’s college entrance exam as flights pause for the listening test.", "Sedaily"),
    (19, "JAKARTA", "Indonesia passes an asset-seizure law after an 18-year wait.", "Kompas"),
    (20, "HORMUZ", "Iran says its mines have set five tankers ablaze in the strait.", "Al Jazeera"),
    (21, "KRASNODAR", "Kyiv says its drones hit two Russian oil refineries overnight.", "Euronews"),
    (22, "BRUSSELS", "The EU delays its methane rules by two years.", "Euronews"),
    (23, "BRUSSELS", "The European Commission confirms a cyberattack on its systems.", "Reuters"),
    (24, "LONDON", "An inquiry finds the superyacht Bayesian was vulnerable to the wind that sank her.", "RNZ"),
    (25, "PARIS", "France’s left splits over a pact with Mélenchon ahead of the run-off.", "Reuters"),
    (26, "DHAKA", "An Awami League shutdown closes parts of Bangladesh and police report two killed.", "AFP"),
    (27, "SANAA", "Houthi media report Saudi air strikes on Yemen’s capital.", "Reuters"),
    (28, "MOGADISHU", "Somalia orders the UAE ambassador to leave the country.", "Al Jazeera"),
    (29, "SUDAN", "A court sentences the absent RSF chief to death.", "AP"),
    (30, "PRETORIA", "South Africa’s central bank holds its rate at 7.25%.", "SABC"),
    (31, "CANARIES", "A record 11,000 migrants arrive in the Canaries in 15 days.", "Africanews"),
    (32, "FLORIDA", "Floods shut schools in Broward and Miami for a second day.", "CBS"),
    (33, "WELLINGTON", "A court rules that pay-equity cuts broke the rights law.", "RNZ"),
    (34, "TONGA", "A drought emergency takes effect across the islands.", "RNZ"),
    (35, "COOK ISLANDS", "Cyclone Xavier weakens to category 4.", "RNZ"),
    (36, "ROME", "Author Corrado Augias dies at 91.", "Euronews"),
    (37, "ZURICH", "Two rivals step up to challenge FIFA president Infantino.", "ABC"),
    (38, "SPACE", "Astronomers watch a red giant star eating a Sun-sized star.", "Nature"),
    (39, "TAIWAN", "TSMC tightens its curbs on AI chip sales to China.", "Reuters"),
    (40, "GAZA", "Israel says its tank raid past the truce line has ended.", "BBC"),
]

# Coarse continent outlines in (lon, lat) for the dotted map.
LAND = [
    [(-168, 65), (-155, 71), (-140, 70), (-130, 70), (-120, 72), (-110, 73),
     (-100, 73), (-95, 78), (-90, 75), (-85, 70), (-82, 72), (-78, 68),
     (-75, 65), (-70, 62), (-64, 60), (-60, 55), (-65, 50), (-70, 45),
     (-68, 44), (-74, 40), (-75, 36), (-79, 33), (-80, 31), (-81, 26),
     (-83, 28), (-86, 30), (-90, 29), (-94, 29), (-97, 26), (-97, 24),
     (-95, 19), (-92, 15), (-90, 14), (-87, 13), (-83, 9), (-79, 9),
     (-82, 8), (-85, 11), (-90, 13), (-95, 16), (-100, 17), (-105, 20),
     (-108, 23), (-112, 27), (-114, 30), (-117, 33), (-121, 35), (-123, 40),
     (-124, 46), (-128, 51), (-133, 56), (-140, 60), (-152, 60), (-160, 58),
     (-166, 60)],
    [(-46, 60), (-42, 61), (-38, 63), (-32, 64), (-30, 66), (-28, 68),
     (-24, 70), (-22, 72), (-24, 76), (-30, 79), (-38, 80), (-48, 79),
     (-55, 77), (-57, 74), (-56, 71), (-54, 68), (-53, 65), (-52, 62),
     (-50, 60)],
    [(-79, 9), (-77, 8), (-75, 10), (-72, 11), (-68, 11), (-64, 10),
     (-60, 8), (-55, 6), (-51, 4), (-50, 1), (-44, -2), (-38, -5),
     (-35, -8), (-37, -11), (-39, -14), (-39, -17), (-40, -21), (-46, -23),
     (-49, -28), (-52, -32), (-55, -34), (-57, -38), (-62, -39), (-62, -41),
     (-65, -44), (-65, -47), (-66, -50), (-68, -52), (-68, -55), (-71, -54),
     (-73, -51), (-74, -48), (-74, -44), (-73, -40), (-72, -34), (-70, -28),
     (-70, -22), (-70, -18), (-74, -15), (-77, -11), (-79, -7), (-80, -4),
     (-81, -1), (-80, 2), (-78, 5), (-77, 7)],
    [(-6, 35), (-2, 35), (3, 37), (9, 37), (10, 34), (11, 34), (19, 32),
     (25, 32), (30, 31), (32, 31), (34, 28), (35, 24), (37, 21), (38, 19),
     (39, 15), (41, 12), (44, 11), (48, 11), (51, 12), (50, 14), (46, 11),
     (43, 7), (42, 3), (41, -2), (40, -6), (40, -11), (39, -15), (37, -19),
     (36, -22), (35, -25), (33, -28), (30, -31), (27, -33), (22, -34),
     (19, -34), (17, -32), (16, -29), (15, -26), (14, -22), (13, -18),
     (13, -14), (12, -10), (13, -6), (12, -2), (9, 0), (9, 3), (6, 4),
     (1, 6), (-4, 5), (-8, 4), (-11, 7), (-13, 8), (-15, 11), (-17, 14),
     (-17, 19), (-16, 24), (-15, 28), (-12, 31), (-9, 32)],
    [(-9, 37), (-9, 43), (-2, 44), (0, 46), (-2, 48), (-5, 48), (-1, 49),
     (1, 51), (3, 52), (5, 53), (7, 54), (8, 55), (8, 57), (6, 58), (5, 60),
     (7, 62), (12, 62), (18, 64), (21, 65), (25, 66), (29, 68), (33, 69),
     (40, 68), (48, 68), (55, 69), (65, 70), (72, 72), (80, 73), (90, 74),
     (100, 76), (110, 74), (118, 73), (128, 72), (138, 72), (148, 71),
     (156, 70), (162, 68), (170, 67), (178, 66), (179, 64), (173, 63),
     (166, 61), (161, 59), (159, 55), (157, 51), (152, 48), (149, 45),
     (144, 44), (141, 41), (139, 38), (136, 35), (133, 34), (130, 33),
     (127, 35), (126, 38), (123, 39), (121, 37), (121, 33), (120, 30),
     (121, 27), (118, 25), (114, 22), (110, 20), (108, 16), (109, 12),
     (107, 9), (105, 6), (103, 5), (101, 7), (99, 9), (98, 13), (97, 16),
     (95, 16), (93, 18), (91, 22), (89, 22), (87, 21), (86, 20), (84, 19),
     (82, 16), (80, 14), (78, 9), (76, 10), (74, 13), (72, 18), (71, 20),
     (69, 22), (66, 25), (62, 25), (58, 25), (55, 25), (52, 26), (50, 28),
     (49, 30), (51, 27), (53, 25), (56, 25), (58, 23), (59, 22), (57, 19),
     (55, 17), (53, 15), (51, 14), (48, 14), (45, 12), (43, 13), (42, 16),
     (40, 20), (38, 24), (36, 28), (35, 30), (36, 33), (36, 36), (33, 36),
     (30, 36), (28, 37), (26, 38), (23, 36), (20, 36), (19, 38), (16, 38),
     (14, 40), (12, 42), (10, 44), (8, 44), (6, 43), (3, 43), (2, 41),
     (0, 39), (-2, 37), (-5, 36)],
    [(-5, 50), (-3, 51), (-1, 52), (0, 53), (-1, 55), (-2, 57), (-3, 58),
     (-5, 58), (-6, 57), (-5, 55), (-6, 53), (-5, 51)],
    [(-10, 52), (-8, 52), (-6, 53), (-6, 54), (-8, 55), (-10, 54)],
    [(-23, 64), (-19, 63), (-15, 63), (-13, 64), (-14, 66), (-19, 66),
     (-23, 65)],
    [(130, 31), (132, 33), (135, 34), (137, 35), (139, 36), (140, 38),
     (141, 40), (141, 43), (143, 44), (141, 45), (139, 42), (138, 39),
     (136, 36), (134, 34), (131, 33), (129, 32)],
    [(126, 35), (127, 35), (129, 36), (129, 38), (127, 39), (126, 38)],
    [(120, 22), (121, 22), (122, 24), (122, 25), (120, 25)],
    [(120, 12), (121, 14), (121, 16), (122, 18), (121, 17), (120, 15),
     (119, 13)],
    [(95, 5), (99, 3), (102, 1), (105, -2), (107, -4), (108, -6), (110, -7),
     (113, -7), (116, -8), (119, -8), (122, -9), (125, -9), (128, -8),
     (131, -4), (134, -3), (137, -2), (140, -2), (143, -3), (146, -5),
     (149, -7), (150, -9), (147, -9), (143, -8), (139, -7), (135, -5),
     (131, -3), (127, -1), (123, 0), (119, 0), (116, 2), (112, 1),
     (108, 2), (104, 3), (100, 5), (96, 6)],
    [(44, -13), (47, -13), (49, -14), (50, -16), (48, -19), (47, -22),
     (46, -24), (45, -25), (44, -23), (43, -20), (43, -17), (44, -14)],
    [(113, -22), (112, -26), (114, -30), (115, -33), (117, -35), (121, -34),
     (125, -33), (129, -32), (132, -32), (134, -33), (136, -35), (138, -36),
     (140, -38), (144, -38), (146, -39), (149, -38), (150, -37), (152, -34),
     (153, -31), (153, -28), (152, -25), (150, -22), (147, -19), (145, -16),
     (143, -14), (142, -11), (141, -13), (139, -17), (136, -15), (136, -12),
     (134, -11), (132, -11), (130, -13), (127, -14), (124, -16), (121, -18),
     (118, -20), (115, -21)],
    [(167, -45), (169, -44), (171, -43), (172, -42), (173, -41), (174, -40),
     (175, -38), (176, -37), (178, -37), (176, -38), (175, -40), (174, -41),
     (172, -43), (170, -44), (168, -46), (166, -46)],
    [(-85, 23), (-80, 23), (-76, 21), (-74, 20), (-77, 21), (-82, 22),
     (-85, 22)],
]

PINS = [
    (1, 114.0, 22.5), (2, 4.3, 52.0), (3, 30.7, 36.9), (4, -74.0, 40.7),
    (5, 174.8, -36.9), (6, 36.5, 45.4), (7, 46.7, 24.6), (8, 85.1, 20.3),
    (9, 127.0, 37.6), (10, -51.7, 64.2), (11, 149.1, -35.3),
    (12, 36.8, -1.3), (13, -74.1, 4.6),
]
PIN_NUDGE = {1: (2, 1), 3: (-5, 3), 6: (4, -3), 7: (3, 4), 8: (-3, 3),
             9: (4, -2)}


def _inside(lon, lat, poly):
    inside = False
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if ((yi > lat) != (yj > lat)) and \
                (lon < (xj - xi) * (lat - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def draw_map(cv, x, y, w, h):
    cv.rect(x, y, w, h, fill=(233, 236, 231), outline=HAIR, width=1)

    def proj(lon, lat):
        return (x + (lon + 168) / 352.0 * w, y + (84 - lat) / 134.0 * h)

    lat = 80.0
    while lat > -47:
        lon = -166.0
        while lon < 183:
            if any(_inside(lon, lat, p) for p in LAND):
                px, py = proj(lon, lat)
                cv.ellipse(px - 1.05, py - 1.05, 2.1, 2.1,
                           fill=(108, 128, 144))
            lon += 3.4
        lat -= 3.4
    nf = F(SANS_B, 6.6)
    for n, lon, la in PINS:
        px, py = proj(lon, la)
        dx, dy = PIN_NUDGE.get(n, (0, 0))
        px, py = px + dx, py + dy
        d = 12.5
        cv.ellipse(px - d / 2, py - d / 2, d, d, fill=RED, outline=WHITE,
                   width=1.1)
        cv.text(px, py + 0.4, str(n), nf, fill=WHITE, anchor="mm")


# --------------------------------------------------------------------------
# Rich-text helpers (mixed bold / regular spans with wrapping)
# --------------------------------------------------------------------------
def rich_wrap(cv, spans, maxw):
    """spans: [(text, font, fill)]. Returns lines of [(word, font, fill)]."""
    words = []
    for text, font, fill in spans:
        for w_ in text.split(" "):
            if w_:
                words.append((w_, font, fill))
    lines, cur, curw = [], [], 0.0
    for w_, font, fill in words:
        ww = cv.tw(w_, font)
        sp = cv.tw(" ", font)
        add = ww if not cur else ww + sp
        if cur and curw + add > maxw:
            lines.append(cur)
            cur, curw = [(w_, font, fill)], ww
        else:
            cur.append((w_, font, fill))
            curw += add
    if cur:
        lines.append(cur)
    return lines


def draw_rich(cv, x, y, lines, lh):
    for i, line in enumerate(lines):
        cx = x
        for w_, font, fill in line:
            cv.text(cx, y + i * lh, w_, font, fill=fill)
            cx += cv.tw(w_, font) + cv.tw(" ", font)


def brief_spans(n, place, sentence, source, size):
    return [
        (f"{n} ", F(SANS_B, size), RED),
        (f"{place} — ", F(SANS_B, size), INK),
        (sentence + " ", F(SANS, size), INK),
        (f"({source})", F(SANS_O, size), INK_SOFT),
    ]


# --------------------------------------------------------------------------
# Section renderers
# --------------------------------------------------------------------------
def draw_masthead(cv, img):
    cv.tracked(MARGIN, 13, "THE WORLD IN ONE DAY", F(SANS_B, 10), INK,
               tracking=2.2)
    cv.tracked(0, 13, "ONE PAGE · EVERY STORY DATED", F(SANS_B, 10), INK,
               tracking=2.2, anchor_right=RIGHT)
    cv.hline(MARGIN, RIGHT, 30, fill=INK, width=2.6)
    cv.hline(MARGIN, RIGHT, 34, fill=INK, width=0.8)
    cv.text(MARGIN, 40, "Thursday 19 November 2026", F(SERIF_B, 45), fill=INK)
    cv.text(RIGHT, 44, "40 STORIES", F(SERIF_B, 19), fill=INK, anchor="ra")
    cv.text(RIGHT, 68, "EVERY CONTINENT", F(SANS_B, 8.5), fill=INK_SOFT,
            anchor="ra")
    cv.text(RIGHT, 79, "ALL FROM THIS ONE DAY", F(SANS_B, 8.5),
            fill=INK_SOFT, anchor="ra")
    italic_line(img, MARGIN, 91,
                "Trump, Xi and Putin share one table · The World Court "
                "finds genocide in Myanmar · COP31’s draft drops fossil "
                "fuels", F(SERIF, 13.5), RED)
    cv.hline(MARGIN, RIGHT, 112, fill=INK, width=0.8)


def draw_region_bar(cv, y=115, h=18):
    total = sum(c for _, c, _ in REGIONS)
    x = MARGIN
    f = F(SANS_B, 8.8)
    for name, count, color in REGIONS:
        w = CW * count / total
        cv.rect(x, y, w, h, fill=color)
        label = f"{name} {count}"
        cv.text(x + w / 2, y + h / 2 - 4.6, label, f, fill=WHITE, anchor="ma")
        x += w


def draw_utc(cv, y=136):
    cv.text(MARGIN, y + 1, "THE DAY", F(SERIF_B, 12), fill=RED)
    cv.text(MARGIN, y + 15, "IN UTC", F(SERIF_B, 12), fill=RED)
    x0 = 104
    colw = (RIGHT - x0) / len(UTC_ITEMS)
    for i, (time, place, event) in enumerate(UTC_ITEMS):
        x = x0 + i * colw
        if i:
            cv.vline(x - 7, y + 2, y + 26, fill=HAIR, width=0.8)
        cv.text(x, y, time, F(SANS_B, 10.5), fill=INK)
        tw_ = cv.tw(time, F(SANS_B, 10.5))
        cv.text(x + tw_ + 5, y + 2.2, place, F(SANS_B, 8.3), fill=RED)
        cv.text(x, y + 15, event, F(SANS, 9.3), fill=INK_SOFT)
    cv.hline(MARGIN, RIGHT, y + 31, fill=HAIR, width=0.8)


def draw_numbers(cv, y=171):
    colw = CW / len(NUMBERS)
    for i, (num, label) in enumerate(NUMBERS):
        x = MARGIN + i * colw
        cv.text(x, y, num, F(SERIF_B, 23), fill=INK)
        cv.text(x, y + 27, label, F(SANS, 8.8), fill=INK_SOFT)
    cv.hline(MARGIN, RIGHT, y + 40, fill=INK, width=0.8)


def draw_feature(cv, img, f, x, y):
    w, art_h = 318, 88
    foot = 13 if f["artfoot"] else 0
    ART_FNS[f["art"]](cv, x, y + 17, w, art_h - 17 - foot)
    if f["art"] == "cop":
        scene_h = art_h - 30
        sdx = x + w * 0.535 + w * 0.43 * 0.94
        sdy = y + 17 + scene_h * 0.10 + scene_h * 0.76 * 0.92
        stamp(img, sdx, sdy, "CUT", size=10)
    if f["artfoot"]:
        cv.rect(x, y + art_h - 13, w, 13, fill=(24, 26, 30))
        cv.text(x + w / 2, y + art_h - 13 + 2.4, f["artfoot"],
                F(SANS_B, 7.3), fill=WHITE, anchor="ma")
    cv.rect(x, y, w, 17, fill=INK)
    cv.text(x + 7, y + 3.4, f["banner"], F(SANS_B, 8.8), fill=WHITE)
    cv.rect(x, y, w, art_h, outline=INK, width=1.2)
    ky = y + art_h + 5
    number_circle(cv, x, ky, 13.5, f["n"])
    cv.text(x + 19, ky + 1.2, f["kicker"], F(SANS_B, 10), fill=RED)
    chip(cv, x + w, ky + 0.25, f["tag"], h=13)
    hy = ky + 17
    hf = F(SERIF_B, 18.5)
    lines = cv.wrap(f["headline"], hf, w)
    for i, ln in enumerate(lines):
        cv.text(x, hy + i * 20.5, ln, hf, fill=INK)
    dy = hy + len(lines) * 20.5 + 4
    df = F(SANS, 10.6)
    dlines = cv.wrap(f["dek"], df, w)
    for i, ln in enumerate(dlines):
        cv.text(x, dy + i * 13, ln, df, fill=INK)
    sy = dy + len(dlines) * 13 + 3
    cv.text(x, sy, f["source"], F(SANS_O, 9.5), fill=RED_DARK)
    return sy + 12


def draw_medium(cv, img, m, x, ry):
    w, art_h = 188, 30
    ART_FNS[m["art"]](cv, x, ry, w, art_h)
    if m["art"] == "seoul":
        stamp(img, x + w * 0.74, ry + 15, "OVERTURNED", size=8.4)
    if m["art"] == "runner":
        stamp(img, x + w * 0.72, ry + 14.5, "BANNED", size=9)
    lf = F(SANS_B, 7.3)
    lw = cv.tw(m["label"], lf) + 8
    cv.rect(x, ry + art_h - 11, lw, 11, fill=(24, 26, 30))
    cv.text(x + 4, ry + art_h - 11 + 1.9, m["label"], lf, fill=WHITE)
    cv.rect(x, ry, w, art_h, outline=INK, width=1)
    ky = ry + art_h + 5
    number_circle(cv, x, ky, 11.5, m["n"])
    cv.text(x + 15.5, ky + 1, m["kicker"], F(SANS_B, 8.3), fill=RED)
    chip(cv, x + w, ky + 0.25, m["tag"], h=11)
    hy = ky + 15.5
    hf = F(SERIF_B, 12.6)
    lines = cv.wrap(m["headline"], hf, w)
    for i, ln in enumerate(lines):
        cv.text(x, hy + i * 14.2, ln, hf, fill=INK)
    by = hy + len(lines) * 14.2 + 3
    bf = F(SANS, 9.6)
    blines = cv.wrap(m["brief"], bf, w)
    for i, ln in enumerate(blines):
        cv.text(x, by + i * 10.4, ln, bf, fill=INK)


def draw_bottom(cv, img):
    hy = 708
    cv.text(MARGIN, hy, "WHERE IT HAPPENED", F(SERIF_B, 12.5), fill=INK)
    note_x = MARGIN + cv.tw("WHERE IT HAPPENED", F(SERIF_B, 12.5)) + 8
    cv.text(note_x, hy + 3, "positions approximate", F(SANS, 7.5),
            fill=INK_SOFT)
    cv.text(278, hy, "ALSO ON THURSDAY · 19 NOVEMBER 2026", F(SERIF_B, 12.5),
            fill=INK)
    cv.text(RIGHT, hy + 3.5, "place · what happened · source", F(SANS, 8.3),
            fill=INK_SOFT, anchor="ra")
    draw_map(cv, MARGIN, 730, 244, 148)
    # HOW SURE legend, under the map
    cv.text(MARGIN, 884, "HOW SURE ARE WE?", F(SANS_B, 9), fill=RED)
    legend = [("CONFIRMED", "— confirmed by named sources"),
              ("CLAIM", "— one side says so, unverified"),
              ("FORECAST", "— poll, draft or schedule")]
    for i, (word, rest) in enumerate(legend):
        yy = 898 + i * 11.5
        cv.text(MARGIN, yy, word, F(SANS_B, 8.6), fill=INK)
        cv.text(MARGIN + cv.tw(word, F(SANS_B, 8.6)) + 4, yy, rest,
                F(SANS, 8.6), fill=INK_SOFT)
    # Briefs: auto-fit the largest size whose two in-order columns fit.
    col_x = [278, 646]
    col_w = 352
    top, avail = 730, 218
    chosen = None
    for size in (9.2, 9.0, 8.8, 8.6, 8.4):
        lh = size * 1.10
        gap = 1.5
        wrapped = [(b, rich_wrap(cv, brief_spans(*b, size), col_w))
                   for b in BRIEFS]
        heights = [len(lines) * lh + gap for _, lines in wrapped]
        best = None
        for s in range(8, 20):
            m = max(sum(heights[:s]), sum(heights[s:]))
            if best is None or m < best[0]:
                best = (m, s)
        if best[0] <= avail:
            chosen = (wrapped[:best[1]], wrapped[best[1]:], lh, gap)
            break
    if chosen is None:
        chosen = (wrapped[:best[1]], wrapped[best[1]:], lh, gap)
    col1, col2, lh, gap = chosen
    for k, col in enumerate((col1, col2)):
        yy = top
        for (_, lines) in col:
            draw_rich(cv, col_x[k], yy, lines, lh)
            yy += len(lines) * lh + gap


def draw_date_check(cv):
    y = 954
    cv.rect(MARGIN, y, CW, 30, outline=RED, width=1.3)
    size = 9.2
    spans = [
        ("DATE CHECK ✓  ", F(SANS_B, size), RED),
        ("Every story on this page happened, or was first reported, on "
         "Thursday 19 November 2026. ", F(SANS, size), INK),
        ("LEFT OUT AS OTHER DAYS’ NEWS — ", F(SANS_B, size), RED),
        ("18 NOV: the EU’s €45bn Ukraine loan plan · Anthropic’s $83 "
         "pricing · Voyager 1’s light-day milestone · Nvidia’s results · "
         "Jeffries named for US speaker. 20 NOV: COP31’s scheduled close · "
         "Cyclone Akvan’s landfall.", F(SANS, size), INK),
    ]
    lines = rich_wrap(cv, spans, CW - 20)
    draw_rich(cv, MARGIN + 10, y + 5, lines, 11.3)


def draw_footer(cv):
    cv.text(MARGIN, 990,
            "Claims are attributed, not stated as fact · Pictures and map: "
            "original, drawn in code · Sources: Reuters, AP, AFP, BBC, "
            "Al Jazeera, UN News, Euronews, ABC, ABS, RNZ, Xinhua, "
            "Nature · 2026-11-19", F(SANS, 8.3), fill=INK_SOFT)


def main():
    img = Image.new("RGB", (PAGE * SCALE, PAGE * SCALE), CREAM)
    cv = CV(img)
    draw_masthead(cv, img)
    draw_region_bar(cv)
    draw_utc(cv)
    draw_numbers(cv)
    fx = [MARGIN, 353, 684]
    for f, x in zip(FEATURES, fx):
        draw_feature(cv, img, f, x, 215)
    cv.hline(MARGIN, RIGHT, 443, fill=HAIR, width=0.8)
    mx = [MARGIN + i * 198 for i in range(5)]
    for i, m in enumerate(MEDIUMS):
        draw_medium(cv, img, m, mx[i % 5], 449 if i < 5 else 573)
    cv.hline(MARGIN, RIGHT, 702, fill=HAIR, width=0.8)
    draw_bottom(cv, img)
    draw_date_check(cv)
    draw_footer(cv)
    final = img.resize((PAGE, PAGE), Image.LANCZOS)
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "entry.png")
    final.save(out, optimize=True)
    data = open(out, "rb").read()
    print(f"entry.png: {len(data)} bytes, "
          f"sha256 {hashlib.sha256(data).hexdigest()}")


if __name__ == "__main__":
    main()
