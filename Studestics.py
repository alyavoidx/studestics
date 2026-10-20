import os
import sys
import sqlite3
import shutil
import threading
import subprocess
import re
import time
import math
import queue
import gc
from pathlib import Path
from datetime import datetime, date, timedelta

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import tkinter.font as tkfont

_native_messagebox = messagebox


class _ThemedMessageBox:
    """Stands in for tkinter.messagebox so every question and notice
    in the app uses the app's own dark dialog instead of the white
    Windows one. Falls back to the native boxes before the app exists."""

    app = None

    def _show(self, kind, title, message, **kwargs):

        if self.app is None:

            return getattr(_native_messagebox, {
                "ask": "askyesno",
                "info": "showinfo",
                "warning": "showwarning",
                "error": "showerror"
            }[kind])(title, message, **kwargs)

        return self.app._themed_message(
            kind, title, message, kwargs.get("parent")
        )

    def askyesno(self, title, message, **kwargs):
        return self._show("ask", title, message, **kwargs)

    def showinfo(self, title, message, **kwargs):
        return self._show("info", title, message, **kwargs)

    def showwarning(self, title, message, **kwargs):
        return self._show("warning", title, message, **kwargs)

    def showerror(self, title, message, **kwargs):
        return self._show("error", title, message, **kwargs)


messagebox = _ThemedMessageBox()

try:
    from PIL import Image, ImageDraw, ImageTk, ImageFilter, ImageEnhance, ImageFont
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    import pystray
except Exception:
    pystray = None


# ============================================================
# STUDestics CONFIG
# ============================================================

APP_NAME = "Studestics"

APP_DIR = Path.home() / ".studestics"
DB_PATH = APP_DIR / "studestics.db"
ATTACH_DIR = APP_DIR / "attachments"

APP_DIR.mkdir(parents=True, exist_ok=True)
ATTACH_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# COLORS (themes)
# ============================================================

THEMES = {
    "Purple": {
        "bg": "#090909", "sidebar": "#0D0D0D", "panel": "#111111",
        "panel2": "#171717", "border": "#252525", "text": "#FFFFFF",
        "muted": "#8F8F9F", "muted2": "#666672",
        "accent": "#7C3AED", "accent_hover": "#8B5CF6"
    },
    "Catppuccin": {
        "bg": "#11111B", "sidebar": "#181825", "panel": "#1E1E2E",
        "panel2": "#313244", "border": "#45475A", "text": "#CDD6F4",
        "muted": "#A6ADC8", "muted2": "#7F849C",
        "accent": "#9B72E0", "accent_hover": "#CBA6F7"
    },
    "Matcha": {
        "bg": "#0F130E", "sidebar": "#131811", "panel": "#171D15",
        "panel2": "#1F2820", "border": "#2E3B2B", "text": "#EEF3E6",
        "muted": "#9CAA92", "muted2": "#6E7C65",
        "accent": "#5E8F3E", "accent_hover": "#9BC276"
    },
    "Ocean": {
        "bg": "#0A1118", "sidebar": "#0D1620", "panel": "#101B27",
        "panel2": "#172633", "border": "#243749", "text": "#EAF2FA",
        "muted": "#8EA3B8", "muted2": "#61778C",
        "accent": "#2F6FEB", "accent_hover": "#60A5FA"
    },
    "Rose": {
        "bg": "#150D12", "sidebar": "#1A1016", "panel": "#20141B",
        "panel2": "#2B1A24", "border": "#3F2733", "text": "#FBEAF0",
        "muted": "#BC9BA9", "muted2": "#876272",
        "accent": "#C93B72", "accent_hover": "#F472A6"
    }
}


def _read_theme_name():
    """The saved theme, read straight from the settings table so the
    colours are known before any window exists."""

    try:

        connection = sqlite3.connect(DB_PATH)

        row = connection.execute(
            "SELECT value FROM settings WHERE key='theme'"
        ).fetchone()

        connection.close()

        if row and row[0] in THEMES:
            return row[0]

    except Exception:
        pass

    return "Purple"


def _theme_mix(a, b, t):

    ra = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    rb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]

    return "#%02X%02X%02X" % tuple(
        int(round(x + (y - x) * t)) for x, y in zip(ra, rb)
    )


def _theme_rgb(color):

    return tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))


THEME_NAME = _read_theme_name()

_THEME = THEMES[THEME_NAME]

BG = _THEME["bg"]
SIDEBAR = _THEME["sidebar"]
PANEL = _THEME["panel"]
PANEL_2 = _THEME["panel2"]
BORDER = _THEME["border"]

TEXT = _THEME["text"]
MUTED = _THEME["muted"]
MUTED_2 = _THEME["muted2"]

PURPLE = _THEME["accent"]
PURPLE_HOVER = _THEME["accent_hover"]
PURPLE_LIGHT = _theme_mix(PURPLE_HOVER, "#FFFFFF", 0.25)

GREEN = "#34D399"
RED = "#F87171"
YELLOW = "#FBBF24"
BLUE = "#60A5FA"

# Hover color for destructive buttons (Delete)
DANGER_HOVER = "#DC2626"

# Shades worked out from the theme, so every theme gets matching
# hover states, chips and "dim" cards.
HOVER_BG = _theme_mix(PANEL_2, TEXT, 0.07)
CHIP_BG = _theme_mix(PANEL_2, TEXT, 0.045)
TRACK = _theme_mix(PANEL_2, TEXT, 0.05)
SIDEBAR_HOVER = _theme_mix(SIDEBAR, TEXT, 0.05)
DEEP = _theme_mix(BG, "#000000", 0.4)
COMPLETED_BG = _theme_mix(BG, GREEN, 0.06)
NAV_TEXT = _theme_mix(TEXT, BG, 0.18)
NAV_ICON = _theme_mix(MUTED, TEXT, 0.35)
NAV_HOVER_ICON = _theme_mix(TEXT, BG, 0.08)

ACCENT_RGB = _theme_rgb(PURPLE_HOVER)
ACCENT_LIGHT_RGB = _theme_rgb(PURPLE_LIGHT)

# Neutral flat pills (Edit, Pause...) as RGB tuples.
NEUTRAL_FILL = _theme_rgb(_theme_mix(PANEL_2, TEXT, 0.06))
NEUTRAL_EDGE = _theme_rgb(_theme_mix(PANEL_2, TEXT, 0.17))
NEUTRAL_FILL_HOVER = _theme_rgb(_theme_mix(PANEL_2, TEXT, 0.12))
NEUTRAL_EDGE_HOVER = _theme_rgb(_theme_mix(PANEL_2, TEXT, 0.30))

# "gemini-flash-latest" is Google's own alias for "whatever the current
# Flash model is" — they hot-swap what it points to server-side whenever
# a new Flash version ships, so this line should never need editing again
# for a routine version bump. Pinned versions are still kept below as a
# fallback in case the alias itself ever has an issue, or Google is slow
# to update it right after a deprecation.
GEMINI_MODEL = "gemini-flash-latest"

# If the primary model is ever unavailable, the app tries these in order
# before giving up — so a single Google-side deprecation or alias hiccup
# doesn't silently kill the chat until someone edits source code.
# Free-quota trimming: how many tasks/goals go into each prompt, the
# reply length cap, and how many chat turns share one server-side
# conversation before it's started fresh (long chains re-send the whole
# history to Gemini on every turn, which burns quota).
AI_CONTEXT_ITEMS = 5
AI_MAX_OUTPUT_TOKENS = 400
AI_RESET_AFTER_TURNS = 8

GEMINI_MODEL_FALLBACKS = [
    "gemini-flash-latest",
    "gemini-3.8-flash",
    "gemini-3.5-flash",
]


# ============================================================
# HELPERS
# ============================================================

def now_string():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def format_date(value):
    if not value:
        return "No deadline"

    try:
        dt = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
        return dt.strftime("%d %b %Y • %I:%M %p")
    except Exception:
        return value


def priority_color(priority):
    if priority == "High":
        return RED
    if priority == "Medium":
        return YELLOW
    return GREEN


# Pomodoro: focus length is whatever the timer is set to; these are the
# break lengths and how many focus rounds make one set.
POMO_ROUNDS = 4
POMO_SHORT = 5 * 60
POMO_LONG = 15 * 60

# Distraction nudge: how often the front window is checked while a focus
# session runs, and the minimum gap between two nudges.
NUDGE_POLL_SECONDS = 3
NUDGE_COOLDOWN_SECONDS = 60

# Width of the options drawer that slides in on the Focus page.
FOCUS_DRAWER_WIDTH = 350
DEFAULT_NUDGE_WORDS = (
    "instagram, reels, tiktok, facebook, snapchat, netflix, twitch, shorts"
)


# One-click additions shown in the Nudge words dialog.
NUDGE_SUGGESTIONS = [
    "youtube", "instagram", "reels", "tiktok", "facebook",
    "snapchat", "netflix", "twitch", "shorts", "reddit",
    "twitter", "whatsapp", "discord", "pinterest",
    "prime video", "hotstar"
]


# Floating timer: the presets, their window sizes, the colour Windows is
# told to make see-through (so the shapes can be round), and the backdrop
# of the preview in Settings.
FLOAT_STYLES = [
    ("ring", "Ring"),
    ("ticks", "Ticks"),
    ("pill", "Pill"),
    ("bar", "Bar")
]

FLOAT_SIZES = {
    "ring": (160, 160),
    "ticks": (176, 176),
    "pill": (232, 72),
    "bar": (224, 92)
}

FLOAT_KEY = "#010203"
FLOAT_PREVIEW_BG = "#1E1E24"


def _hex_rgb(color):

    color = color.lstrip("#")

    return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))


def mix_color(a, b, t):
    """Blend hex colour a toward b by t (0..1)."""

    ra, rb = _hex_rgb(a), _hex_rgb(b)

    return "#%02x%02x%02x" % tuple(
        int(round(x + (y - x) * t)) for x, y in zip(ra, rb)
    )


def float_layout(style, zoom=1.0):
    """Where the time, status and round-dots go for a preset, scaled
    by `zoom`. Each is (x, y) or (x, y, size_in_pixels); dots is None
    for the wide presets (the caller puts them underneath)."""

    w, h = FLOAT_SIZES.get(style, FLOAT_SIZES["ring"])

    if style == "ring":

        raw = {
            "time": (w / 2, h / 2 - 6, 28),
            "status": (w / 2, h / 2 + 22, 11),
            "dots": (w / 2, h / 2 + 47)
        }

    elif style == "ticks":

        raw = {
            "time": (w / 2, h / 2 - 2, 26),
            "status": (w / 2, h / 2 + 22, 11),
            "dots": (w / 2, h / 2 + 45)
        }

    elif style == "pill":

        disc = 44

        cx = (h - disc) / 2 + disc / 2

        text_x = (cx + disc / 2 + 14 + w - 18) / 2

        raw = {
            "time": (text_x, h / 2 - 7, 28),
            "status": (text_x, h / 2 + 17, 11),
            "dots": None
        }

    else:

        raw = {
            "time": (w / 2, 42, 32),
            "status": (w / 2, 17, 11),
            "dots": None
        }

    out = {}

    for key in ("time", "status"):

        x, y, px = raw[key]

        out[key] = (x * zoom, y * zoom, max(8, int(round(px * zoom))))

    out["dots"] = (
        None
        if raw["dots"] is None
        else (raw["dots"][0] * zoom, raw["dots"][1] * zoom)
    )

    out["size"] = (int(round(w * zoom)), int(round(h * zoom)))

    return out


def render_float(
    style,
    fraction,
    color,
    bg,
    scale=4,
    zoom=1.0,
    card=True
):
    """Draw one clock preset (needs Pillow).

    `fraction` is the share of the phase still left (1 = full).
    `zoom` makes it bigger (the Focus page uses the same presets at
    about twice the size). `card=False` leaves out the round plate
    behind the ring and ticks.

    `bg` is the colour behind it. For the floating window pass None:
    the picture then has a see-through background and hard edges, so
    no dark halo shows when Windows cuts the background out.

    Returns (PIL image, layout); see float_layout. Drawn big and
    shrunk with LANCZOS, like every other round thing in the app.
    """

    w, h = FLOAT_SIZES.get(style, FLOAT_SIZES["ring"])

    fraction = max(0.0, min(1.0, float(fraction)))

    layout = float_layout(style, zoom)

    ow, oh = layout["size"]

    S = scale * zoom

    card_col, edge, track = PANEL, HOVER_BG, TRACK

    big = (int(round(w * S)), int(round(h * S)))

    if bg is None:
        img = Image.new("RGBA", big, (0, 0, 0, 0))
    else:
        img = Image.new("RGB", big, bg)

    d = ImageDraw.Draw(img)

    edge_w = max(1, int(round(S)))

    def cap(cx, cy, r, fill):
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=fill)

    if style in ("ring", "ticks"):

        if card:

            d.ellipse(
                [S, S, w * S - S - 1, h * S - S - 1],
                fill=card_col,
                outline=edge,
                width=edge_w
            )

        cx, cy = w * S / 2, h * S / 2

        if style == "ring":

            stroke = int(round(9 * S))
            pad = 13 * S

            box = [pad, pad, w * S - pad, h * S - pad]

            d.ellipse(box, outline=track, width=stroke)

            if fraction >= 0.999:

                d.ellipse(box, outline=color, width=stroke)

            elif fraction > 0:

                a0 = -90
                a1 = -90 + 360 * fraction

                d.arc(box, a0, a1, fill=color, width=stroke)

                radius = (w * S - 2 * pad) / 2 - stroke / 2

                for ang in (a0, a1):

                    cap(
                        cx + radius * math.cos(math.radians(ang)),
                        cy + radius * math.sin(math.radians(ang)),
                        stroke / 2,
                        color
                    )

        else:

            count = 60

            r0, r1 = 52 * S, 72 * S
            tick_w = 3.2 * S

            lit = int(math.ceil(fraction * count - 1e-9))

            tint = mix_color(color, "#FFFFFF", 0.5)

            for i in range(count):

                ang = math.radians(-90 + i * 360 / count)

                ux, uy = math.cos(ang), math.sin(ang)

                col = (
                    mix_color(color, tint, i / (count - 1))
                    if i < lit
                    else HOVER_BG
                )

                x0, y0 = cx + ux * r0, cy + uy * r0
                x1, y1 = cx + ux * r1, cy + uy * r1

                d.line([(x0, y0), (x1, y1)], fill=col, width=int(tick_w))

                cap(x0, y0, tick_w / 2, col)
                cap(x1, y1, tick_w / 2, col)

    elif style == "pill":

        d.rounded_rectangle(
            [S, S, w * S - S - 1, h * S - S - 1],
            radius=(h / 2) * S,
            fill=card_col,
            outline=edge,
            width=edge_w
        )

        disc = 44

        cx = (h - disc) / 2 + disc / 2
        cy = h / 2

        box = [
            (cx - disc / 2) * S, (cy - disc / 2) * S,
            (cx + disc / 2) * S, (cy + disc / 2) * S
        ]

        # The disc is a pie: what is left is coloured, what has gone
        # is dark.
        d.ellipse(box, fill=HOVER_BG)

        if fraction >= 0.999:

            d.ellipse(box, fill=color)

        elif fraction > 0:

            d.pieslice(box, -90, -90 + 360 * fraction, fill=color)

    else:

        d.rounded_rectangle(
            [S, S, w * S - S - 1, h * S - S - 1],
            radius=22 * S,
            fill=card_col,
            outline=edge,
            width=edge_w
        )

        x0, x1 = 24, w - 24
        y0, y1 = h - 28, h - 20

        d.rounded_rectangle(
            [x0 * S, y0 * S, x1 * S, y1 * S],
            radius=4 * S,
            fill=track
        )

        if fraction > 0:

            fx = x0 + max(8, (x1 - x0) * fraction)

            d.rounded_rectangle(
                [x0 * S, y0 * S, fx * S, y1 * S],
                radius=4 * S,
                fill=color
            )

    img = img.resize((ow, oh), Image.LANCZOS)

    if bg is None:

        # Hard edges: every pixel is either fully there or fully
        # gone, and the ones that stay keep their true colour.
        r, g, b, alpha = img.split()

        alpha = alpha.point(lambda v: 255 if v >= 110 else 0)

        img = Image.merge("RGBA", (r, g, b, alpha))

    return img, layout


NAV_ICONS = {
    "Dashboard": "grid",
    "Tasks": "check",
    "Goals": "target",
    "Notes": "note",
    "Focus Mode": "clock",
    "AI Chat": "chat",
    "Analytics": "bars",
    "Settings": "gear"
}


NAV_W = 230
NAV_H = 52
SIDEBAR_WIDTH = 250


def nav_icon_image(kind, color, size=26, filled=False):
    """Line icon, or its solid version when `filled` (the active
    page). Anti-aliased: drawn big, shrunk."""

    scale = 8

    big = size * scale

    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))

    d = ImageDraw.Draw(img)

    u = big / 24.0

    lw = max(1, int(round(2 * u)))

    gone = (0, 0, 0, 0)

    def box(x0, y0, x1, y1):
        return [x0 * u, y0 * u, x1 * u, y1 * u]

    if kind == "grid":

        for x0, y0 in ((3, 3), (13.5, 3), (3, 13.5), (13.5, 13.5)):

            d.rounded_rectangle(
                box(x0, y0, x0 + 7.5, y0 + 7.5),
                radius=2.2 * u,
                fill=color if filled else None,
                outline=color,
                width=lw
            )

    elif kind == "check":

        d.rounded_rectangle(
            box(4, 3, 20, 21),
            radius=3.5 * u,
            fill=color if filled else None,
            outline=color,
            width=lw
        )

        d.line(
            [(8 * u, 12.3 * u), (10.9 * u, 15.2 * u), (16 * u, 9 * u)],
            fill=gone if filled else color,
            width=int(round(2.2 * u)),
            joint="curve"
        )

    elif kind == "target":

        d.ellipse(box(3, 3, 21, 21), fill=color if filled else None,
                  outline=color, width=lw)

        d.ellipse(box(7.2, 7.2, 16.8, 16.8),
                  fill=gone if filled else None,
                  outline=gone if filled else color, width=lw)

        d.ellipse(box(10.4, 10.4, 13.6, 13.6), fill=color)

    elif kind == "clock":

        d.ellipse(box(3, 3, 21, 21), fill=color if filled else None,
                  outline=color, width=lw)

        d.line(
            [(12 * u, 7 * u), (12 * u, 12 * u), (15.6 * u, 14.2 * u)],
            fill=gone if filled else color,
            width=int(round(2 * u)),
            joint="curve"
        )

    elif kind == "chat":

        d.rounded_rectangle(
            box(3, 4, 21, 17),
            radius=4.5 * u,
            fill=color if filled else None,
            outline=color,
            width=lw
        )

        d.polygon(
            [(7 * u, 16 * u), (7 * u, 21 * u), (12.5 * u, 16 * u)],
            fill=color
        )

        for x in (8, 12, 16):

            d.ellipse(
                box(x - 1.15, 9.35, x + 1.15, 11.65),
                fill=gone if filled else color
            )

    elif kind == "note":

        d.rounded_rectangle(
            box(5, 3, 19, 21),
            radius=2.6 * u,
            fill=color if filled else None,
            outline=color,
            width=lw
        )

        for y in (8.5, 12.5, 16.5):

            d.line(
                [(8.4 * u, y * u), (15.6 * u, y * u)],
                fill=gone if filled else color,
                width=int(round(1.9 * u))
            )

    elif kind == "bars":

        for x0, y0, x1 in ((4, 12, 8), (10, 5, 14), (16, 9, 20)):

            d.rounded_rectangle(
                box(x0, y0, x1, 20),
                radius=1.6 * u,
                fill=color
            )

    else:

        # Gear: a disc, eight teeth, and a hole through the middle.
        c = big / 2
        body = 6.6 * u
        tooth = 3.4 * u
        tooth_w = 4.2 * u

        for i in range(8):

            ang = math.radians(i * 45)

            ux, uy = math.cos(ang), math.sin(ang)
            px, py = -uy, ux

            r0, r1 = body * 0.8, body + tooth

            d.polygon(
                [
                    (c + ux * r0 + px * tooth_w / 2,
                     c + uy * r0 + py * tooth_w / 2),
                    (c + ux * r1 + px * tooth_w * 0.38,
                     c + uy * r1 + py * tooth_w * 0.38),
                    (c + ux * r1 - px * tooth_w * 0.38,
                     c + uy * r1 - py * tooth_w * 0.38),
                    (c + ux * r0 - px * tooth_w / 2,
                     c + uy * r0 - py * tooth_w / 2)
                ],
                fill=color
            )

        d.ellipse([c - body, c - body, c + body, c + body], fill=color)

        hole = body * 0.42

        d.ellipse([c - hole, c - hole, c + hole, c + hole], fill=gone)

    return img.resize((size, size), Image.LANCZOS)


def mini_marker_image(kind, color, size=18):
    """Little marker for the sidebar lists: a ring with a dot in it
    for a task (an open item), a four-point sparkle for a goal."""

    scale = 8

    big = size * scale

    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))

    d = ImageDraw.Draw(img)

    u = big / 18.0

    if kind == "goal":

        c = 9 * u

        pts = []

        for i in range(8):

            ang = math.radians(-90 + i * 45)

            r = (7.6 if i % 2 == 0 else 2.6) * u

            pts.append((c + r * math.cos(ang), c + r * math.sin(ang)))

        d.polygon(pts, fill=color)

    else:

        d.ellipse(
            [2 * u, 2 * u, 16 * u, 16 * u],
            outline=color,
            width=int(round(1.8 * u))
        )

        d.ellipse([6.2 * u, 6.2 * u, 11.8 * u, 11.8 * u], fill=color)

    return img.resize((size, size), Image.LANCZOS)


class NavItem:
    """One row of the sidebar, Instagram-style: a big icon and label.
    The page you are on is bold with a solid icon; hovering gives a
    soft rounded highlight."""

    W, H = NAV_W, NAV_H

    def __init__(self, parent, name, command):

        self.name = name
        self.command = command
        self.active = False
        self.hover = False
        self._key = None

        self.canvas = tk.Canvas(
            parent,
            width=self.W,
            height=self.H,
            bg=SIDEBAR,
            highlightthickness=0,
            bd=0,
            cursor="hand2"
        )

        self.canvas.bind("<Enter>", lambda e: self._set_hover(True))
        self.canvas.bind("<Leave>", lambda e: self._set_hover(False))
        self.canvas.bind("<Button-1>", lambda e: self.command())

        self.paint()

    def pack(self, **kw):
        self.canvas.pack(**kw)

    def _set_hover(self, on):

        self.hover = on
        self.paint()

    def set_active(self, on):

        self.active = bool(on)
        self.paint()

    def paint(self):

        key = (self.active, self.hover)

        if key == self._key:
            return

        self._key = key

        if self.active:
            text, icon = TEXT, PURPLE_HOVER
        elif self.hover:
            text, icon = TEXT, NAV_HOVER_ICON
        else:
            text, icon = NAV_TEXT, NAV_ICON

        fill = PANEL_2 if self.hover else None

        c = self.canvas

        try:

            c.delete("all")

            if HAS_PIL:

                scale = 4

                w, h = self.W, self.H

                img = Image.new("RGB", (w * scale, h * scale), SIDEBAR)

                if fill:

                    ImageDraw.Draw(img).rounded_rectangle(
                        [0, 0, w * scale - 1, h * scale - 1],
                        radius=14 * scale,
                        fill=fill
                    )

                img = img.resize((w, h), Image.LANCZOS)

                glyph = nav_icon_image(
                    NAV_ICONS.get(self.name, "grid"),
                    icon,
                    26,
                    filled=self.active
                )

                img.paste(glyph, (18, (h - 26) // 2), glyph)

                self.photo = ImageTk.PhotoImage(img)

                c.create_image(0, 0, anchor="nw", image=self.photo)

            elif fill:

                c.create_rectangle(
                    0, 0, self.W, self.H,
                    fill=fill,
                    outline=""
                )

            c.create_text(
                62,
                self.H / 2,
                text=self.name,
                anchor="w",
                fill=text,
                font=("Segoe UI", 13, "bold" if self.active else "normal")
            )

        except Exception:
            pass


class CanvasText:
    """A piece of canvas text that answers to configure(text=, fg=)
    and cget('text'), so code written for a Label keeps working."""

    def __init__(self, canvas, item):

        self.canvas = canvas
        self.item = item

    def configure(self, **kw):

        opts = {}

        if "text" in kw:
            opts["text"] = kw["text"]

        if "fg" in kw:
            opts["fill"] = kw["fg"]

        if opts:
            self.canvas.itemconfigure(self.item, **opts)

    def cget(self, key):

        if key == "text":
            return self.canvas.itemcget(self.item, "text")

        return ""


class DeadlineState:
    """What the deadline picker has chosen. No Tk in here, so the
    rules (month steps, hour wrap, 12-hour clock) are easy to test."""

    DEFAULT_HOUR = 18

    def __init__(self, initial="", today=None):

        self.today = today or datetime.now().date()

        try:
            self.sel = datetime.strptime(initial, "%Y-%m-%d %H:%M:%S")
        except Exception:
            self.sel = None

        base = self.sel.date() if self.sel else self.today

        self.year, self.month = base.year, base.month

    def _ensure(self):

        if self.sel is None:

            self.sel = datetime.combine(
                self.today,
                datetime.min.time()
            ).replace(hour=self.DEFAULT_HOUR)

        return self.sel

    def set_date(self, day):

        keep = self.sel or self._ensure()

        self.sel = datetime.combine(day, keep.time())

        self.year, self.month = day.year, day.month

    def shift_month(self, step):

        index = self.year * 12 + (self.month - 1) + step

        self.year, self.month = divmod(index, 12)

        self.month += 1

    def bump_hour(self, step):

        cur = self._ensure()

        self.sel = cur.replace(hour=(cur.hour + step) % 24)

    def bump_minute(self, step):

        cur = self._ensure()

        self.sel = cur.replace(minute=(cur.minute + step) % 60)

    def toggle_ampm(self):

        cur = self._ensure()

        self.sel = cur.replace(hour=(cur.hour + 12) % 24)

    def clear(self):

        self.sel = None

    def value(self):

        return self.sel.strftime("%Y-%m-%d %H:%M:%S") if self.sel else ""

    def hour12(self):

        return (self.sel.hour % 12 or 12) if self.sel else 6

    def minute(self):

        return self.sel.minute if self.sel else 0

    def ampm(self):

        return ("AM" if self.sel.hour < 12 else "PM") if self.sel else "PM"

    def readout(self):

        if not self.sel:
            return "No deadline", ""

        return (
            self.sel.strftime("%a %d %b %Y"),
            f"{self.hour12()}:{self.minute():02d} {self.ampm()}"
        )

    def weeks(self):
        """Monday-first rows of day numbers (0 = not in this month)."""

        import calendar

        return calendar.Calendar(0).monthdayscalendar(
            self.year,
            self.month
        )


DUE_SOON_SECONDS = 24 * 3600      # "due soon" highlight
DUE_ALERT_SECONDS = 60 * 60       # one-time "due in an hour" alert


def deadline_dt(value):

    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


def _span_text(seconds):

    seconds = abs(seconds)

    if seconds < 90 * 60:
        return f"{max(1, int(round(seconds / 60)))} min"

    if seconds < 48 * 3600:
        return f"{int(round(seconds / 3600))}h"

    return f"{int(seconds // 86400)}d"


def due_info(deadline, now=None):
    """(state, label, colour) for a deadline string. state is
    'none', 'overdue', 'soon' (within a day) or 'ok'."""

    dt = deadline_dt(deadline)

    if dt is None:
        return "none", "", None

    secs = (dt - (now or datetime.now())).total_seconds()

    if secs < 0:

        label = (
            "Overdue"
            if -secs < 60
            else f"Overdue by {_span_text(secs)}"
        )

        return "overdue", label, RED

    if secs <= DUE_SOON_SECONDS:
        return "soon", f"Due in {_span_text(secs)}", YELLOW

    return "ok", "", None


def fmt_duration(seconds):
    """1500 -> '25m', 3900 -> '1h 05m', 0 -> '0m'."""

    seconds = max(0, int(seconds))

    if seconds == 0:
        return "0m"

    minutes = int(round(seconds / 60))

    if minutes < 1:
        return "<1m"

    hours, mins = divmod(minutes, 60)

    if hours:
        return f"{hours}h {mins:02d}m"

    return f"{mins}m"


def parse_words(text):
    """'Instagram, Reels ,,tiktok' -> ['instagram', 'reels', 'tiktok']."""

    return [
        w.strip().lower()
        for w in (text or "").split(",")
        if w.strip()
    ]


def foreground_window_title():
    """Title of the window currently in front (Windows only; '' on any
    other system or on error). Needs no extra install - plain ctypes."""

    if sys.platform != "win32":
        return ""

    try:

        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32

        user32.GetForegroundWindow.restype = wintypes.HWND
        user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        user32.GetWindowTextW.argtypes = [
            wintypes.HWND, wintypes.LPWSTR, ctypes.c_int
        ]

        hwnd = user32.GetForegroundWindow()

        if not hwnd:
            return ""

        length = user32.GetWindowTextLengthW(hwnd)

        if length <= 0:
            return ""

        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)

        return buffer.value

    except Exception:
        return ""


# ============================================================
# DATABASE
# ============================================================

class Database:

    def __init__(self):
        self.lock = threading.RLock()

        self.connection = sqlite3.connect(
            DB_PATH,
            check_same_thread=False
        )

        self.connection.row_factory = sqlite3.Row

        self.setup()

    def setup(self):

        with self.lock:

            self.connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS profile (
                    id INTEGER PRIMARY KEY CHECK(id = 1),
                    name TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                );

                CREATE TABLE IF NOT EXISTS goals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1,
                    description TEXT DEFAULT '',
                    image_path TEXT DEFAULT '',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    deadline TEXT DEFAULT '',
                    priority TEXT DEFAULT 'Medium',
                    status TEXT DEFAULT 'Pending',
                    image_path TEXT DEFAULT '',
                    created_at TEXT NOT NULL,
                    completed_at TEXT DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS focus_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id INTEGER,
                    task_title TEXT DEFAULT '',
                    planned_seconds INTEGER NOT NULL,
                    actual_seconds INTEGER NOT NULL,
                    completed INTEGER NOT NULL DEFAULT 0,
                    nudges INTEGER NOT NULL DEFAULT 0,
                    day TEXT NOT NULL,
                    ended_at TEXT NOT NULL
                );
                """
            )

            self.connection.commit()

            # Older databases predate per-task reminder times.
            columns = [
                row["name"] for row in
                self.connection.execute(
                    "PRAGMA table_info(tasks)"
                ).fetchall()
            ]

            if "remind_minutes" not in columns:

                self.connection.execute(
                    "ALTER TABLE tasks ADD COLUMN "
                    "remind_minutes INTEGER DEFAULT 0"
                )

                self.connection.commit()

            # Older databases predate goal descriptions and pictures.
            goal_columns = [
                row["name"] for row in
                self.connection.execute(
                    "PRAGMA table_info(goals)"
                ).fetchall()
            ]

            for column in ("description", "image_path"):

                if column not in goal_columns:

                    self.connection.execute(
                        f"ALTER TABLE goals ADD COLUMN "
                        f"{column} TEXT DEFAULT ''"
                    )

            self.connection.commit()

            self.clean_old_errors()

    def clean_old_errors(self):

        with self.lock:

            self.connection.execute(
                """
                DELETE FROM messages
                WHERE role = 'assistant'
                AND (
                    content LIKE '503:%'
                    OR content LIKE '429:%'
                    OR content LIKE 'Gemini error:%'
                    OR content LIKE 'Gemini timed out:%'
                )
                """
            )

            self.connection.commit()

    # --------------------------------------------------------
    # Settings
    # --------------------------------------------------------

    def get_setting(self, key, default=""):

        with self.lock:

            row = self.connection.execute(
                "SELECT value FROM settings WHERE key=?",
                (key,)
            ).fetchone()

        if row is None:
            return default

        return row["value"]

    def set_setting(self, key, value):

        with self.lock:

            self.connection.execute(
                """
                INSERT OR REPLACE INTO settings(key, value)
                VALUES (?, ?)
                """,
                (key, value)
            )

            self.connection.commit()

    # --------------------------------------------------------
    # Profile
    # --------------------------------------------------------

    def get_profile(self):

        with self.lock:

            return self.connection.execute(
                "SELECT * FROM profile WHERE id=1"
            ).fetchone()

    def save_profile(self, name):

        with self.lock:

            self.connection.execute(
                """
                INSERT OR REPLACE INTO profile
                (id, name, created_at)
                VALUES (1, ?, ?)
                """,
                (name, now_string())
            )

            self.connection.commit()

    def rename_profile(self, name):

        with self.lock:

            self.connection.execute(
                "UPDATE profile SET name=? WHERE id=1",
                (name,)
            )

            self.connection.commit()

    # --------------------------------------------------------
    # Tasks
    # --------------------------------------------------------

    def add_task(
        self,
        title,
        description,
        deadline,
        priority,
        image_path="",
        remind_minutes=0
    ):

        with self.lock:

            cursor = self.connection.execute(
                """
                INSERT INTO tasks(
                    title,
                    description,
                    deadline,
                    priority,
                    status,
                    image_path,
                    remind_minutes,
                    created_at
                )
                VALUES (?, ?, ?, ?, 'Pending', ?, ?, ?)
                """,
                (
                    title,
                    description,
                    deadline,
                    priority,
                    image_path,
                    int(remind_minutes or 0),
                    now_string()
                )
            )

            self.connection.commit()

            return cursor.lastrowid

    def get_task(self, task_id):

        with self.lock:

            return self.connection.execute(
                "SELECT * FROM tasks WHERE id=?",
                (task_id,)
            ).fetchone()

    def update_task(
        self,
        task_id,
        title,
        description,
        deadline,
        priority,
        image_path="",
        remind_minutes=0
    ):

        with self.lock:

            self.connection.execute(
                """
                UPDATE tasks
                SET
                    title=?,
                    description=?,
                    deadline=?,
                    priority=?,
                    image_path=?,
                    remind_minutes=?
                WHERE id=?
                """,
                (
                    title,
                    description,
                    deadline,
                    priority,
                    image_path,
                    int(remind_minutes or 0),
                    task_id
                )
            )

            self.connection.commit()

    def get_tasks(self, include_completed=True):

        query = """
            SELECT *
            FROM tasks
        """

        if not include_completed:
            query += " WHERE status != 'Completed' "

        query += """
            ORDER BY
            CASE WHEN deadline = '' THEN 1 ELSE 0 END,
            deadline ASC,
            id DESC
        """

        with self.lock:

            return self.connection.execute(
                query
            ).fetchall()

    def complete_task(self, task_id):

        with self.lock:

            self.connection.execute(
                """
                UPDATE tasks
                SET
                    status='Completed',
                    completed_at=?
                WHERE id=?
                """,
                (
                    now_string(),
                    task_id
                )
            )

            self.connection.commit()

    def reopen_task(self, task_id):

        with self.lock:

            self.connection.execute(
                """
                UPDATE tasks
                SET
                    status='Pending',
                    completed_at=''
                WHERE id=?
                """,
                (task_id,)
            )

            self.connection.commit()

    def delete_task(self, task_id, keep_image=False):

        with self.lock:

            row = self.connection.execute(
                """
                SELECT image_path
                FROM tasks
                WHERE id=?
                """,
                (task_id,)
            ).fetchone()

            self.connection.execute(
                "DELETE FROM tasks WHERE id=?",
                (task_id,)
            )

            self.connection.commit()

        if row and row["image_path"] and not keep_image:

            try:
                Path(
                    row["image_path"]
                ).unlink(
                    missing_ok=True
                )
            except Exception:
                pass

    # --------------------------------------------------------
    # Goals
    # --------------------------------------------------------

    def add_goal(self, title, description="", image_path=""):

        with self.lock:

            self.connection.execute(
                """
                INSERT INTO goals(
                    title,
                    active,
                    description,
                    image_path,
                    created_at
                )
                VALUES (?, 1, ?, ?, ?)
                """,
                (
                    title,
                    description,
                    image_path,
                    now_string()
                )
            )

            self.connection.commit()

    def get_goal(self, goal_id):

        with self.lock:

            return self.connection.execute(
                "SELECT * FROM goals WHERE id=?",
                (goal_id,)
            ).fetchone()

    def update_goal(self, goal_id, title, description, image_path):

        old = self.get_goal(goal_id)

        with self.lock:

            self.connection.execute(
                """
                UPDATE goals
                SET title=?, description=?, image_path=?
                WHERE id=?
                """,
                (title, description, image_path, goal_id)
            )

            self.connection.commit()

        # A replaced or removed picture shouldn't linger on disk.
        if (
            old is not None
            and old["image_path"]
            and old["image_path"] != image_path
        ):

            try:
                Path(old["image_path"]).unlink(missing_ok=True)
            except Exception:
                pass

    def get_goals(self, active_only=False):

        query = "SELECT * FROM goals"

        if active_only:
            query += " WHERE active=1"

        query += " ORDER BY id DESC"

        with self.lock:

            return self.connection.execute(
                query
            ).fetchall()

    def toggle_goal(self, goal_id):

        with self.lock:

            self.connection.execute(
                """
                UPDATE goals
                SET active =
                    CASE
                        WHEN active=1 THEN 0
                        ELSE 1
                    END
                WHERE id=?
                """,
                (goal_id,)
            )

            self.connection.commit()

    def delete_goal(self, goal_id):

        with self.lock:

            row = self.connection.execute(
                "SELECT image_path FROM goals WHERE id=?",
                (goal_id,)
            ).fetchone()

            self.connection.execute(
                "DELETE FROM goals WHERE id=?",
                (goal_id,)
            )

            self.connection.commit()

        if row and row["image_path"]:

            try:
                Path(row["image_path"]).unlink(missing_ok=True)
            except Exception:
                pass

    def delete_all_tasks(self):

        with self.lock:

            rows = self.connection.execute(
                "SELECT image_path FROM tasks"
            ).fetchall()

            self.connection.execute("DELETE FROM tasks")
            self.connection.commit()

        for row in rows:

            if row["image_path"]:

                try:
                    Path(row["image_path"]).unlink(missing_ok=True)
                except Exception:
                    pass

    def delete_all_goals(self):

        with self.lock:

            rows = self.connection.execute(
                "SELECT image_path FROM goals"
            ).fetchall()

            self.connection.execute("DELETE FROM goals")
            self.connection.commit()

        for row in rows:

            if row["image_path"]:

                try:
                    Path(row["image_path"]).unlink(missing_ok=True)
                except Exception:
                    pass

    def delete_all_user_data(self):
        """Tasks, goals, chat history, focus history and every
        setting except the Gemini API key. The profile name stays."""

        self.delete_all_tasks()
        self.delete_all_goals()

        with self.lock:

            self.connection.execute("DELETE FROM messages")
            self.connection.execute("DELETE FROM focus_sessions")
            self.connection.execute(
                "DELETE FROM settings WHERE key <> ?",
                ("gemini_api_key",)
            )
            self.connection.commit()

    # --------------------------------------------------------
    # Chat
    # --------------------------------------------------------

    def add_message(self, role, content):

        with self.lock:

            self.connection.execute(
                """
                INSERT INTO messages(
                    role,
                    content,
                    created_at
                )
                VALUES (?, ?, ?)
                """,
                (
                    role,
                    content,
                    now_string()
                )
            )

            self.connection.commit()

    def get_messages(self):

        with self.lock:

            return self.connection.execute(
                """
                SELECT *
                FROM messages
                ORDER BY id ASC
                """
            ).fetchall()

    def clear_messages(self):

        with self.lock:

            self.connection.execute(
                "DELETE FROM messages"
            )

            self.connection.commit()

    # --------------------------------------------------------
    # Statistics
    # --------------------------------------------------------

    def statistics(self):

        with self.lock:

            total = self.connection.execute(
                "SELECT COUNT(*) AS n FROM tasks"
            ).fetchone()["n"]

            completed = self.connection.execute(
                """
                SELECT COUNT(*) AS n
                FROM tasks
                WHERE status='Completed'
                """
            ).fetchone()["n"]

            pending = total - completed

            goals = self.connection.execute(
                """
                SELECT COUNT(*) AS n
                FROM goals
                WHERE active=1
                """
            ).fetchone()["n"]

        return (
            total,
            completed,
            pending,
            goals
        )

    # --------------------------------------------------------
    # Focus sessions
    # --------------------------------------------------------

    def add_focus_session(
        self,
        task_id,
        task_title,
        planned_seconds,
        actual_seconds,
        completed,
        nudges=0
    ):

        now = datetime.now()

        with self.lock:

            self.connection.execute(
                """
                INSERT INTO focus_sessions(
                    task_id,
                    task_title,
                    planned_seconds,
                    actual_seconds,
                    completed,
                    nudges,
                    day,
                    ended_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    task_title or "",
                    int(planned_seconds),
                    int(actual_seconds),
                    1 if completed else 0,
                    int(nudges),
                    now.strftime("%Y-%m-%d"),
                    now.strftime("%Y-%m-%d %H:%M:%S")
                )
            )

            self.connection.commit()

    def recent_focus_sessions(self, limit=5):

        with self.lock:

            return self.connection.execute(
                """
                SELECT *
                FROM focus_sessions
                ORDER BY id DESC
                LIMIT ?
                """,
                (int(limit),)
            ).fetchall()

    def focus_daily_seconds(self, days=7):
        """[(YYYY-MM-DD, seconds), ...] oldest first, ending today,
        with 0 for days that have no sessions."""

        from datetime import timedelta

        today = datetime.now().date()

        wanted = [
            (today - timedelta(days=offset)).strftime("%Y-%m-%d")
            for offset in range(days - 1, -1, -1)
        ]

        with self.lock:

            rows = self.connection.execute(
                """
                SELECT day, SUM(actual_seconds) AS total
                FROM focus_sessions
                WHERE day >= ?
                GROUP BY day
                """,
                (wanted[0],)
            ).fetchall()

        totals = {row["day"]: row["total"] or 0 for row in rows}

        return [(day, totals.get(day, 0)) for day in wanted]

    def focus_profile_stats(self):
        """All-time focus numbers for the Profile page."""

        with self.lock:

            row = self.connection.execute(
                """
                SELECT COUNT(*) AS sessions,
                       COALESCE(SUM(actual_seconds), 0) AS total,
                       COALESCE(MAX(actual_seconds), 0) AS longest,
                       COALESCE(SUM(completed), 0) AS finished,
                       COALESCE(SUM(nudges), 0) AS nudges,
                       COUNT(DISTINCT day) AS days
                FROM focus_sessions
                """
            ).fetchone()

        return dict(row)

    def focus_stats(self):
        """today / last-7-days seconds, day streak, finished sessions."""

        from datetime import timedelta

        today = datetime.now().date()

        with self.lock:

            day_rows = self.connection.execute(
                "SELECT DISTINCT day FROM focus_sessions"
            ).fetchall()

            done = self.connection.execute(
                """
                SELECT COUNT(*) AS n
                FROM focus_sessions
                WHERE completed=1
                """
            ).fetchone()["n"]

        days = {row["day"] for row in day_rows}

        daily = dict(self.focus_daily_seconds(7))

        today_key = today.strftime("%Y-%m-%d")

        # The streak survives until the end of today: if you haven't
        # focused yet today, it counts back from yesterday.
        cursor = today

        if today_key not in days:
            cursor = today - timedelta(days=1)

        streak = 0

        while cursor.strftime("%Y-%m-%d") in days:
            streak += 1
            cursor -= timedelta(days=1)

        return {
            "today": daily.get(today_key, 0),
            "week": sum(daily.values()),
            "streak": streak,
            "completed_sessions": done
        }

    def close(self):

        try:
            self.connection.close()
        except Exception:
            pass


# ============================================================
# ROUNDED BUTTON
# ============================================================

# ============================================================
# EMOJI (Tk can't draw colour or non-BMP emoji, so they are drawn
# as small images with Pillow and the real characters are kept in
# the text that is stored and sent)
# ============================================================

_EMOJI_RE = re.compile(
    "(?:[\U0001F1E6-\U0001F1FF]{2}"
    "|[\U00010000-\U0010FFFF][\uFE0F\U0001F3FB-\U0001F3FF]*"
    "(?:\u200D(?:[\U00010000-\U0010FFFF]|[\u2600-\u27BF\u2B50])"
    "[\uFE0F\U0001F3FB-\U0001F3FF]*)*"
    # symbols that are emoji when followed by the emoji marker
    "|[\u00A9\u00AE\u203C\u2049\u2122\u2139\u2194-\u21AA"
    "\u231A-\u23FF\u24C2\u25AA-\u25FE\u2600-\u27BF"
    "\u2934\u2935\u2B05-\u2B55\u3030\u303D\u3297\u3299]\uFE0F"
    # symbols that are always emoji
    "|[\u231A\u231B\u23E9-\u23F3\u23F8-\u23FA\u25FD\u25FE"
    "\u2614\u2615\u2648-\u2653\u267F\u2693\u26A1\u26AA\u26AB"
    "\u26BD\u26BE\u26C4\u26C5\u26CE\u26D4\u26EA\u26F2\u26F3"
    "\u26F5\u26FA\u26FD\u2705\u270A\u270B\u2728\u274C\u274E"
    "\u2753-\u2755\u2757\u2795-\u2797\u27B0\u27BF\u2B1B\u2B1C"
    "\u2B50\u2B55])"
)

EMOJI_CATEGORIES = [
    ("😀", "Smileys", "😀 😃 😄 😁 😆 😅 🤣 😂 🙂 🙃 😉 😊 😇 🥰 😍 🤩 😘 😗 😚 😙 😋 😛 😜 🤪 😝 🤑 🤗 🤭 🤫 🤔 🤐 🤨 😐 😑 😶 😏 😒 🙄 😬 🤥 😌 😔 😪 🤤 😴 😷 🤒 🤕 🤢 🤮 🤧 🥵 🥶 🥴 😵 🤯 🤠 🥳 😎 🤓 🧐"),
    ("😭", "Feelings", "😕 😟 🙁 😮 😯 😲 😳 🥺 😦 😧 😨 😰 😥 😢 😭 😱 😖 😣 😞 😓 😩 😫 🥱 😤 😡 😠 🤬 😈 👿 💀 💩 🤡 👹 👺 👻 👽 👾 🤖 😺 😸 😹 😻 😼 😽 🙀 😿 😾 🙈 🙉 🙊 💋 💌 💘 💝 💖 💗 💓 💞 💕 💔"),
    ("👋", "People", "👋 🤚 🖐️ ✋ 🖖 👌 🤏 ✌️ 🤞 🤟 🤘 🤙 👈 👉 👆 👇 ☝️ 👍 👎 ✊ 👊 🤛 🤜 👏 🙌 👐 🤲 🤝 🙏 ✍️ 💅 🤳 💪 🦵 🦶 👂 👃 🧠 🦷 🦴 👀 👅 👄 👶 🧒 👦 👧 🧑 👨 👩 🧓 👴 👵 🙋 🙇 🤦 🤷 💁 🙆 🙅 🧘 🏃"),
    ("🐶", "Animals", "🐶 🐱 🐭 🐹 🐰 🦊 🐻 🐼 🐨 🐯 🦁 🐮 🐷 🐸 🐵 🐔 🐧 🐦 🐤 🦆 🦉 🦇 🐺 🐗 🐴 🦄 🐝 🐛 🦋 🐌 🐞 🐜 🐢 🐍 🦎 🐙 🦑 🦀 🐠 🐟 🐬 🐳 🦈 🐊 🐘 🦒 🌵 🌲 🌳 🌴 🌱 🌿 🍀 🍁 🍂 🌸 🌹 🌻 🌼 🌷 🍄"),
    ("🍎", "Food", "🍎 🍐 🍊 🍋 🍌 🍉 🍇 🍓 🍒 🍑 🥭 🍍 🥥 🥝 🍅 🥑 🥦 🥕 🌽 🥔 🍞 🥐 🧀 🥚 🍳 🥞 🥓 🍗 🍔 🍟 🍕 🌭 🥪 🌮 🌯 🍝 🍜 🍲 🍣 🍱 🍦 🍩 🍪 🎂 🍰 🍫 🍬 🍿 ☕ 🍵 🥤 🍺 🍷 🥂 🍹 🍾 🧃 🥛 🍼 🍯 🥗 🍡"),
    ("⚽", "Activities", "⚽ 🏀 🏈 ⚾ 🎾 🏐 🏓 🎱 🥊 🎯 🎮 🎲 🧩 🎨 🎬 🎤 🎧 🎸 🎹 🥁 🏆 🥇 🥈 🥉 🏅 🎉 🎊 🎈 🎁 🏄 🚴 🏋️ 🧗 🎻 🎷 🎺 🎳 ♟️ 🎭 🎪 🏹 🛹 ⛷️ 🏂 🥋 🎣 🏊 🤸 🎰 🔮 🎠 🎡 🎢 🪁 🥏 🏸 🏒 🏑 🏏"),
    ("💡", "Objects", "💡 🔦 💻 🖥️ ⌨️ 🖱️ 📱 ☎️ 📷 📺 🔋 🔌 💾 💿 📧 ✉️ 📦 🔑 🔒 🔓 🔨 🔧 ⚙️ 🧲 💰 💳 💎 ⚖️ 🧰 🔔 🔕 📢 🔍 🔎 📁 📂 🗂️ 🗑️ 🧹 📚 📖 📝 ✏️ 🖊️ 📌 📎 📅 📆 ⏰ ⏳ ⌛ 📊 📈 📉 🎓 🏫 💼 🧪 🔬 🔭 📡 🧬 🪑 🛒"),
    ("❤️", "Symbols", "❤️ 🧡 💛 💚 💙 💜 🖤 🤍 🤎 💯 ✨ ⭐ 🌟 💫 ⚡ 🔥 💥 ✅ ❌ ❗ ❓ ⚠️ 🚫 ✔️ ➕ ➖ ➡️ ⬅️ ⬆️ ⬇️ 🔄 ♻️ 🌈 ☀️ 🌙 ☁️ ⛅ 🌧️ ❄️ 🌊 🚀 ✈️ 🚗 🚲 🏠 🌍 🗺️ 🧭 ⛰️ 🏖️ 🌋 ⛱️ 🎡 🕐 ♾️ ©️ ™️ 🆗 🆒 🆕 🔝 💤 🎵 🎶"),
]

_EMOJI_FONT_PATHS = (
    "C:/Windows/Fonts/seguiemj.ttf",
    "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",
    "/System/Library/Fonts/Apple Color Emoji.ttc"
)

_EMOJI_CACHE = {}


def emoji_segments(text):
    """[(piece, is_emoji), ...] for a string."""

    parts = []
    pos = 0

    for match in _EMOJI_RE.finditer(text):

        if match.start() > pos:
            parts.append((text[pos:match.start()], False))

        parts.append((match.group(), True))

        pos = match.end()

    if pos < len(text):
        parts.append((text[pos:], False))

    return parts


def has_emoji(text):

    return _EMOJI_RE.search(text) is not None


def emoji_image(cluster, size):
    """A PIL RGBA image of one emoji, `size` px square, or None if no
    emoji font can draw it."""

    key = (cluster, size)

    if key in _EMOJI_CACHE:
        return _EMOJI_CACHE[key]

    result = None

    if HAS_PIL:

        for path in _EMOJI_FONT_PATHS:

            try:

                font = ImageFont.truetype(path, 109)

                # Big canvas and a wide margin: some emoji glyphs reach
                # above or left of the text origin and were being cut.
                canvas = Image.new("RGBA", (500, 500), (0, 0, 0, 0))

                ImageDraw.Draw(canvas).text(
                    (150, 150),
                    cluster,
                    font=font,
                    embedded_color=True
                )

                box = canvas.getbbox()

                if not box:
                    continue

                glyph = canvas.crop(box)

                inner = max(1, size - 2)

                scale = min(inner / glyph.width, inner / glyph.height)

                glyph = glyph.resize(
                    (
                        max(1, int(glyph.width * scale)),
                        max(1, int(glyph.height * scale))
                    ),
                    Image.LANCZOS
                )

                tile = Image.new("RGBA", (size, size), (0, 0, 0, 0))

                tile.paste(
                    glyph,
                    ((size - glyph.width) // 2, (size - glyph.height) // 2)
                )

                result = tile

                break

            except Exception:

                continue

    _EMOJI_CACHE[key] = result

    return result


# ============================================================
# START WITH WINDOWS (per-user "Run" registry key, no admin needed)
# ============================================================

try:
    import winreg
except ImportError:
    winreg = None

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_RUN_NAME = "Studestics"


def startup_supported():

    return winreg is not None and sys.platform == "win32"


def startup_command():
    """What Windows should run at sign-in: the .exe when packaged,
    otherwise pythonw (no console window) with this script."""

    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --background'

    interpreter = Path(sys.executable)

    windowless = interpreter.with_name("pythonw.exe")

    if windowless.exists():
        interpreter = windowless

    return f'"{interpreter}" "{Path(__file__).resolve()}" --background'


def startup_enabled():

    if not startup_supported():
        return False

    try:

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_READ
        ) as key:

            winreg.QueryValueEx(key, _RUN_NAME)

        return True

    except OSError:

        return False


def set_startup(enabled):

    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE
    ) as key:

        if enabled:

            winreg.SetValueEx(
                key, _RUN_NAME, 0, winreg.REG_SZ, startup_command()
            )

        else:

            try:
                winreg.DeleteValue(key, _RUN_NAME)
            except FileNotFoundError:
                pass


def app_icon_image(size=256):
    """The app's icon: a purple rounded square with a white S. Used
    for the window, the taskbar and the tray."""

    big = size * 4

    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))

    draw = ImageDraw.Draw(img)

    draw.rounded_rectangle(
        [0, 0, big - 1, big - 1],
        radius=int(big * 0.24),
        fill=(124, 58, 237, 255)
    )

    font = None

    for name in (
        "segoeuib.ttf",
        "C:/Windows/Fonts/segoeuib.ttf",
        "arialbd.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    ):

        try:

            font = ImageFont.truetype(name, int(big * 0.62))

            break

        except Exception:

            continue

    if font is None:
        font = ImageFont.load_default()

    draw.text(
        (big / 2, big / 2 + big * 0.02),
        "S",
        font=font,
        fill=(255, 255, 255, 255),
        anchor="mm"
    )

    return img.resize((size, size), Image.LANCZOS)


class RoundedButton:
    """A canvas-based button: rounded corners (anti-aliased the same
    way as chat bubbles) and a glow ring on hover, instead of a flat
    square tk.Button.

    Exposes just enough of the real tk.Button API — .pack()/.grid()
    and .configure(text=..., state=...) — that it's a drop-in
    replacement anywhere make_button() was used, including the two
    places that toggle a button's text or disable it at runtime.
    """

    HEIGHT = 32

    def __init__(
        self,
        app,
        parent,
        text,
        command=None,
        width_chars=None,
        active_color=None,
        selected=False
    ):

        self.app = app
        self.text = text
        self.command = command
        self.width_chars = width_chars
        self.active_color = active_color or PURPLE_HOVER
        self.state = "normal"
        self.hovered = False
        self.selected = selected

        self.font = tkfont.Font(family="Segoe UI", size=10)

        try:
            parent_bg = parent.cget("bg")
        except Exception:
            parent_bg = BG

        self.canvas = tk.Canvas(
            parent,
            bg=parent_bg,
            highlightthickness=0,
            bd=0,
            cursor="hand2"
        )

        self.canvas.bind("<Enter>", self._on_enter)
        self.canvas.bind("<Leave>", self._on_leave)
        self.canvas.bind("<Button-1>", self._on_click)

        self._redraw()

    def _text_width(self):

        padding = 26

        width = self.font.measure(self.text) + padding

        if self.width_chars:

            char_width = (
                self.font.measure("0") * self.width_chars
                + padding
            )

            width = max(width, char_width)

        return width

    def _redraw(self):

        w = self._text_width()
        h = self.HEIGHT

        self.canvas.delete("all")

        self.canvas.configure(
            width=w,
            height=h
        )

        if self.state == "disabled":
            bg_color, fg_color = PANEL_2, MUTED_2
        elif self.selected or self.hovered:
            bg_color, fg_color = self.active_color, TEXT
        else:
            bg_color, fg_color = PANEL_2, TEXT

        self.app._draw_bubble_background(
            self.canvas, w, h, h // 2, bg_color
        )

        if getattr(self, "icon", None) is not None:

            self.canvas.create_image(w / 2, h / 2, image=self.icon)

        else:

            self.canvas.create_text(
                w / 2, h / 2,
                text=self.text,
                font=self.font,
                fill=fg_color
            )

    def _on_enter(self, event=None):

        if self.state != "disabled":
            self.hovered = True
            self._redraw()

    def _on_leave(self, event=None):

        self.hovered = False
        self._redraw()

    def _on_click(self, event=None):

        if self.state != "disabled" and self.command:
            self.command()

    def configure(self, **kwargs):

        if "text" in kwargs:
            self.text = kwargs["text"]

        if "state" in kwargs:
            self.state = kwargs["state"]

        if "selected" in kwargs:
            self.selected = kwargs["selected"]

        self._redraw()

    def cget(self, key):

        if key == "text":
            return self.text

        if key == "state":
            return self.state

        return None

    def pack(self, *args, **kwargs):
        self.canvas.pack(*args, **kwargs)

    def grid(self, *args, **kwargs):
        self.canvas.grid(*args, **kwargs)

    def destroy(self):
        self.canvas.destroy()


# ============================================================
# APPLICATION
# ============================================================

_PANEL_CORNERS = {}


def _panel_corner_images(radius, accent=None, fill=None, outside=None,
                         border=None):
    """The four anti-aliased rounded corners (radius x radius each)
    of a bordered card, as small Pillow images. Cached."""

    fill = fill or PANEL
    outside = outside or BG
    border = border or BORDER

    key = (radius, accent, fill, outside, border)

    if key in _PANEL_CORNERS:
        return _PANEL_CORNERS[key]

    from PIL import ImageChops

    sc = 8
    size = radius * 2

    img = Image.new("RGB", (size * sc, size * sc), outside)

    ImageDraw.Draw(img).rounded_rectangle(
        [0, 0, size * sc - 1, size * sc - 1],
        radius=radius * sc,
        fill=border
    )

    mask = Image.new("L", (size * sc, size * sc), 0)

    ImageDraw.Draw(mask).rounded_rectangle(
        [sc, sc, size * sc - 1 - sc, size * sc - 1 - sc],
        radius=(radius - 1) * sc,
        fill=255
    )

    img.paste(Image.new("RGB", img.size, fill), (0, 0), mask)

    if accent:

        strip = Image.new("L", img.size, 0)

        ImageDraw.Draw(strip).rectangle(
            [0, 0, 5 * sc, size * sc],
            fill=255
        )

        img.paste(
            Image.new("RGB", img.size, accent),
            (0, 0),
            ImageChops.multiply(strip, mask)
        )

    img = img.resize((size, size), Image.LANCZOS)

    r = radius

    _PANEL_CORNERS[key] = {
        "tl": img.crop((0, 0, r, r)),
        "tr": img.crop((r, 0, size, r)),
        "bl": img.crop((0, r, r, size)),
        "br": img.crop((r, r, size, size))
    }

    return _PANEL_CORNERS[key]


class StudesticsApp(tk.Tk):

    def __init__(self):

        # ----------------------------------------------------
        # IMPORTANT:
        # Do NOT initialize the database or Gemini here.
        # First create the Tk window.
        # ----------------------------------------------------

        super().__init__()

        messagebox.app = self

        self._set_app_icon()

        self.title(APP_NAME)

        self.geometry(
            "1220x760"
        )

        self.minsize(
            1050,
            680
        )

        self.configure(
            bg=BG
        )

        # ----------------------------------------------------
        # State
        # ----------------------------------------------------

        self.db = None

        self._emoji_photos = {}
        self._emoji_chars = {}
        self._emoji_popup = None

        self.current_page = "Dashboard"
        self.tasks_show_completed = False
        self.tasks_page = 0

        # Reminders / background
        self._reminder_last = {}
        self._reminder_popup = None
        self._tray_icon = None
        self._tray_queue = queue.Queue()
        self._quitting = False
        self._tray_hint_shown = False
        self._alarm_stop = None
        self._alarm_owner = None

        self.sidebar_buttons = {}
        self.sidebar_nav_accents = {}

        self.page = None

        self.initialized = False

        # Focus
        self.focus_duration = 25 * 60
        self.focus_seconds = 25 * 60
        self.focus_running = False
        self.focus_finished = False
        self.focus_job = None

        self.focus_timer_label = None
        self.focus_status_label = None
        self.focus_start_button = None
        self.focus_end_time = 0.0
        self.focus_task_id = None
        self.focus_task_label = None
        self.focus_ring_canvas = None
        self.focus_ring_size = 320
        self._ring_key = None
        self.focus_preset_buttons = {}
        self.focus_custom_button = None

        # Pomodoro + distraction nudge
        self.focus_phase = "focus"      # focus | short | long
        self.pomo_enabled = False
        self.pomo_done = 0              # focus rounds finished in this set
        self.focus_reset_button = None
        self.focus_pomo_button = None
        self.focus_nudge_button = None
        self.settings_nudge_button = None
        self.focus_drawer_note = None
        self._drawer = None

        # Floating timer
        self.float_on = True
        self.float_style = "ring"
        self.float_pos = None
        self._float_win = None
        self._float_canvas = None
        self._float_key = None
        self._float_size = None
        self._float_transparent = False
        self._float_user_hidden = False
        self.float_icon = None
        self._float_icon_hover = False
        self._float_tip = None
        self._clock = None
        self.float_style_buttons = {}
        self.float_preview_canvas = None
        self.focus_nudges = 0           # nudges during the current session
        self.nudge_on = True
        self.nudge_words = parse_words(DEFAULT_NUDGE_WORDS)
        self._nudge_last_poll = 0.0
        self._nudge_cooldown_until = 0.0
        self._nudge_popup = None
        self.auto_delete_overdue = True
        self._deadline_alerted = set()
        self._auto_skip = set()
        self._deadline_popup = None
        self._removed_popup = None
        self.settings_autodel_button = None
        self._dots_key = "unset"

        # AI
        self.chat_busy = False
        self.chat_typing_job = None
        self.typing_row = None
        self.typing_canvas = None
        self.typing_dot_ids = []
        self.typing_phase = 0.0
        self.gemini_previous_id = ""
        self.gemini_turns = 0
        self.stream_canvas = None

        self.chat_body = None
        self.chat_canvas = None
        self.chat_input = None
        self.chat_status = None
        self.chat_send_button = None

        # ----------------------------------------------------
        # Build shell immediately
        # ----------------------------------------------------

        self.build_shell()

        # ----------------------------------------------------
        # Start initialization AFTER window is ready
        # ----------------------------------------------------

        self.after(
            100,
            self.initialize_app
        )

        self.after(300, self._poll_tray)

        self.protocol(
            "WM_DELETE_WINDOW",
            self.close_app
        )

    # ========================================================
    # STARTUP
    # ========================================================

    def initialize_app(self):

        self.set_startup_status(
            "Loading your workspace..."
        )

        try:

            self.db = Database()

            self.set_startup_status(
                "Loading preferences..."
            )

            self.load_preferences()

            self.initialized = True

            self.set_startup_status(
                "Ready."
            )

            self.after(
                250,
                self.finish_startup
            )

        except Exception as exc:

            self.show_startup_error(
                exc
            )

    def finish_startup(self):

        if not self.initialized:
            return

        self.show_page(
            "Dashboard"
        )

        self.start_reminders()

        profile = self.db.get_profile()

        # Launched by Windows at sign-in: start quietly in the tray
        # (main() already kept the window hidden, so nothing flashes).
        if "--background" in sys.argv:

            if profile is not None and pystray is not None:

                self._tray_hint_shown = True
                self.hide_to_tray()

            else:

                # First run, or no tray available: show the window.
                self.deiconify()

        if profile is None:

            self.after(
                150,
                self.ask_name
            )

    def load_preferences(self):

        try:

            minutes = int(
                self.db.get_setting(
                    "focus_minutes",
                    "25"
                )
            )

            minutes = max(
                1,
                min(
                    240,
                    minutes
                )
            )

            total = minutes * 60

            saved_total = self.db.get_setting("focus_total_seconds", "")

            if saved_total:

                total = max(1, min(240 * 60, int(saved_total)))

            self.focus_duration = total

            self.focus_seconds = (
                self.focus_duration
            )

        except Exception:

            self.focus_duration = (
                25 * 60
            )

            self.focus_seconds = (
                25 * 60
            )

        self.gemini_previous_id = (
            self.db.get_setting(
                "gemini_previous_id",
                ""
            )
        )

        try:
            self.gemini_turns = int(
                self.db.get_setting("gemini_turns", "0")
            )
        except ValueError:
            self.gemini_turns = 0

        self.pomo_enabled = (
            self.db.get_setting("pomodoro", "0") == "1"
        )

        self.nudge_on = (
            self.db.get_setting("nudge_enabled", "1") == "1"
        )

        self.nudge_words = parse_words(
            self.db.get_setting("nudge_words", DEFAULT_NUDGE_WORDS)
        )

        self.auto_delete_overdue = (
            self.db.get_setting("auto_delete_overdue", "1") == "1"
        )

        # Never remembered: the floating clock starts off every time
        # the app opens, and is turned on for the current run only.
        self.float_on = False

        style = self.db.get_setting("float_style", "ring")

        self.float_style = style if style in FLOAT_SIZES else "ring"

        try:

            self.float_pos = (
                int(self.db.get_setting("float_x", "")),
                int(self.db.get_setting("float_y", ""))
            )

        except ValueError:

            self.float_pos = None

    def set_startup_status(self, text):

        if hasattr(
            self,
            "startup_status"
        ):

            self.startup_status.configure(
                text=text
            )

        self.update_idletasks()

    def show_startup_error(self, exc):

        self.startup_status.configure(
            text="Startup error"
        )

        self.startup_error.configure(
            text=str(exc)
        )

    # ========================================================
    # SHELL
    # ========================================================

    def build_shell(self):

        # ----------------------------------------------------
        # Sidebar
        # ----------------------------------------------------

        self.sidebar = tk.Frame(
            self,
            bg=SIDEBAR,
            width=SIDEBAR_WIDTH
        )

        self.sidebar.pack(
            side="left",
            fill="y"
        )

        self.sidebar.pack_propagate(
            False
        )

        # Logo

        logo = tk.Frame(
            self.sidebar,
            bg=SIDEBAR
        )

        logo.pack(
            fill="x",
            padx=20,
            pady=(24, 26)
        )

        logo_badge = tk.Canvas(
            logo,
            width=34,
            height=34,
            bg=SIDEBAR,
            highlightthickness=0,
            bd=0
        )

        logo_badge.pack(
            side="left"
        )

        self._draw_logo_badge(logo_badge, size=34)

        tk.Label(
            logo,
            text="Studestics",
            bg=SIDEBAR,
            fg=TEXT,
            font=("Segoe UI", 16, "bold")
        ).pack(
            side="left",
            padx=(10, 0)
        )

        # Navigation

        pages = [
            "Dashboard",
            "Tasks",
            "Goals",
            "Notes",
            "Focus Mode",
            "AI Chat",
            "Analytics",
            "Settings"
        ]

        for page_name in pages:

            item = NavItem(
                self.sidebar,
                page_name,
                lambda name=page_name: self.show_page(name)
            )

            if page_name == "Settings":

                # Pinned to the bottom, like Instagram's "More".
                self._settings_nav = item

            else:

                item.pack(
                    padx=10,
                    pady=3
                )

            self.sidebar_buttons[page_name] = item

        # Up next — a quick glance at top-priority tasks/goals, filled
        # in by refresh_sidebar_upnext() and kept current on every
        # show_page(). Packed right after the nav list (normal top-down
        # flow), not anchored to the bottom, so it sits directly under
        # Settings instead of pinned below the sign-in line.
        self.sidebar_upnext_frame = tk.Frame(
            self.sidebar,
            bg=SIDEBAR
        )

        self.sidebar_upnext_frame.pack(
            side="top",
            fill="x",
            padx=20,
            pady=(16, 0)
        )

        # Live timer card: only shows while a focus timer is active
        # and you are on another page.
        self.sidebar_timer = tk.Canvas(
            self.sidebar,
            width=NAV_W,
            height=62,
            bg=SIDEBAR,
            highlightthickness=0,
            bd=0,
            cursor="hand2"
        )

        self.sidebar_timer.bind(
            "<Button-1>",
            lambda e: self.show_page("Focus Mode")
        )

        self._sidebar_timer_key = None
        self._sidebar_timer_shown = False

        # User

        self.sidebar_chip = tk.Frame(
            self.sidebar,
            bg=SIDEBAR,
            cursor="hand2"
        )

        self.sidebar_chip.pack(
            side="bottom",
            fill="x",
            padx=10,
            pady=(6, 14)
        )

        self.sidebar_avatar = self._avatar_canvas(
            self.sidebar_chip,
            34,
            "?",
            SIDEBAR
        )

        self.sidebar_avatar.pack(
            side="left",
            padx=(10, 12),
            pady=8
        )

        chip_text = tk.Frame(self.sidebar_chip, bg=SIDEBAR)

        chip_text.pack(
            side="left",
            fill="x",
            expand=True
        )

        self.sidebar_user = tk.Label(
            chip_text,
            text="Starting...",
            bg=SIDEBAR,
            fg=TEXT,
            font=("Segoe UI", 10, "bold"),
            anchor="w"
        )

        self.sidebar_user.pack(
            fill="x"
        )

        self.sidebar_user_sub = tk.Label(
            chip_text,
            text="View profile",
            bg=SIDEBAR,
            fg=MUTED_2,
            font=("Segoe UI", 8),
            anchor="w"
        )

        self.sidebar_user_sub.pack(
            fill="x"
        )

        chip_widgets = (
            self.sidebar_chip,
            self.sidebar_avatar,
            chip_text,
            self.sidebar_user,
            self.sidebar_user_sub
        )

        def chip_color(color):

            for w in chip_widgets:

                try:
                    w.configure(bg=color)
                except Exception:
                    pass

        for w in chip_widgets:

            w.bind("<Enter>", lambda e: chip_color(PANEL_2))
            w.bind("<Leave>", lambda e: chip_color(SIDEBAR))
            w.bind("<Button-1>", lambda e: self.show_page("Profile"))

        self._settings_nav.pack(
            side="bottom",
            after=self.sidebar_chip,
            padx=10,
            pady=(0, 4)
        )

        # ----------------------------------------------------
        # Main
        # ----------------------------------------------------

        self.main = tk.Frame(
            self,
            bg=BG
        )

        self.main.pack(
            side="left",
            fill="both",
            expand=True
        )

        # ----------------------------------------------------
        # Startup screen
        # ----------------------------------------------------

        self.startup_screen = tk.Frame(
            self.main,
            bg=BG
        )

        self.startup_screen.pack(
            fill="both",
            expand=True
        )

        tk.Label(
            self.startup_screen,
            text="Studestics",
            bg=BG,
            fg=TEXT,
            font=("Segoe UI", 34, "bold")
        ).pack(
            pady=(220, 8)
        )

        tk.Label(
            self.startup_screen,
            text="Your study workspace",
            bg=BG,
            fg=MUTED,
            font=("Segoe UI", 11)
        ).pack()

        self.startup_status = tk.Label(
            self.startup_screen,
            text="Starting...",
            bg=BG,
            fg=MUTED,
            font=("Segoe UI", 9)
        )

        self.startup_status.pack(
            pady=20
        )

        self.startup_error = tk.Label(
            self.startup_screen,
            text="",
            bg=BG,
            fg=RED,
            font=("Segoe UI", 9),
            wraplength=650
        )

        self.startup_error.pack()

    # ========================================================
    # UI HELPERS
    # ========================================================

    def make_button(
        self,
        parent,
        text,
        command,
        width=None,
        active=PURPLE_HOVER
    ):

        return RoundedButton(
            self,
            parent,
            text,
            command,
            width_chars=width,
            active_color=active
        )

    def build_priority_picker(
        self,
        parent,
        initial="Medium",
        button_width=None
    ):
        """Three color-coded pill buttons (Low/Medium/High) instead of
        a native ttk.Combobox, which carries OS theming and looks
        visibly out of place against the rest of the app.

        Returns a dict with key "value" holding the current selection
        — read picker_state["value"] wherever you'd have called
        combobox.get().
        """

        picker_state = {"value": initial}
        buttons = {}

        row = tk.Frame(
            parent,
            bg=BG
        )

        options = [
            ("Low", GREEN),
            ("Medium", YELLOW),
            ("High", RED)
        ]

        def select(name):

            picker_state["value"] = name

            for option_name, button in buttons.items():

                button.configure(
                    selected=(option_name == name)
                )

        for name, color in options:

            button = RoundedButton(
                self,
                row,
                name,
                command=lambda n=name: select(n),
                width_chars=button_width,
                active_color=color,
                selected=(name == initial)
            )

            button.pack(
                side="left",
                padx=(0, 8)
            )

            buttons[name] = button

        return row, picker_state

    def _themed_message(self, kind, title, message, parent=None):
        """Dark, rounded-button replacement for the Windows message
        boxes. Returns True/False for questions, None for notices."""

        window = tk.Toplevel(parent or self)

        window.title(title)

        window.configure(bg=BG)

        window.resizable(False, False)

        try:
            window.transient(parent or self)
        except Exception:
            pass

        result = {"value": False}

        danger = kind == "ask" and title.split(" ")[0] in (
            "Delete", "Clear", "Remove"
        )

        accent = {
            "error": RED,
            "warning": YELLOW,
            "info": PURPLE_HOVER,
            "ask": RED if danger else PURPLE_HOVER
        }[kind]

        body = tk.Frame(window, bg=BG)

        body.pack(
            fill="both",
            expand=True,
            padx=28,
            pady=(26, 8)
        )

        tk.Frame(
            body,
            bg=accent,
            width=4
        ).pack(
            side="left",
            fill="y",
            padx=(0, 16)
        )

        text_box = tk.Frame(body, bg=BG)

        text_box.pack(
            side="left",
            fill="both",
            expand=True
        )

        tk.Label(
            text_box,
            text=title,
            bg=BG,
            fg=TEXT,
            font=("Segoe UI", 15, "bold"),
            anchor="w",
            justify="left"
        ).pack(
            anchor="w"
        )

        tk.Label(
            text_box,
            text=message,
            bg=BG,
            fg=MUTED,
            font=("Segoe UI", 10),
            wraplength=340,
            anchor="w",
            justify="left"
        ).pack(
            anchor="w",
            pady=(6, 0)
        )

        tk.Frame(
            window,
            bg=BORDER,
            height=1
        ).pack(
            fill="x",
            pady=(18, 0)
        )

        buttons = tk.Frame(window, bg=BG)

        buttons.pack(
            fill="x",
            padx=28,
            pady=16
        )

        def finish(value):

            result["value"] = value

            try:
                window.grab_release()
            except Exception:
                pass

            window.destroy()

        if kind == "ask":

            yes_text = {
                "Delete": "Delete",
                "Clear": "Clear",
                "Remove": "Remove"
            }.get(title.split(" ")[0], "Yes")

            confirm = self.make_button(
                buttons,
                yes_text,
                lambda: finish(True),
                width=9,
                active="#DC2626" if danger else PURPLE_HOVER
            )

            confirm.configure(selected=True)

            confirm.pack(side="right")

            self.make_button(
                buttons,
                "Cancel",
                lambda: finish(False),
                width=9
            ).pack(
                side="right",
                padx=(0, 10)
            )

        else:

            ok = self.make_button(
                buttons,
                "OK",
                lambda: finish(True),
                width=9
            )

            ok.configure(selected=True)

            ok.pack(side="right")

            window.bind("<Return>", lambda e: finish(True))

        window.bind("<Escape>", lambda e: finish(False))
        window.protocol("WM_DELETE_WINDOW", lambda: finish(False))

        window.update_idletasks()

        self.center_window(
            window,
            460,
            window.winfo_reqheight()
        )

        try:
            window.grab_set()
            window.focus_force()
        except Exception:
            pass

        self.wait_window(window)

        return result["value"] if kind == "ask" else None

    def center_window(
        self,
        window,
        width,
        height
    ):

        window.update_idletasks()

        screen_w = window.winfo_screenwidth()
        screen_h = window.winfo_screenheight()

        # If the requested size doesn't actually fit the screen, shrink
        # it — otherwise centering math alone can still leave buttons
        # at the bottom of the dialog pushed off-screen on a short
        # display, with no way to reach them.
        margin = 40

        width = min(width, max(200, screen_w - margin))
        height = min(height, max(200, screen_h - margin))

        x = max(0, (screen_w - width) // 2)
        y = max(0, (screen_h - height) // 2)

        window.geometry(
            f"{width}x{height}+{x}+{y}"
        )

    def make_entry(
        self,
        parent,
        textvariable=None,
        show=None
    ):

        return tk.Entry(
            parent,
            textvariable=textvariable,
            show=show,
            bg=PANEL_2,
            fg=TEXT,
            insertbackground=TEXT,
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground=BORDER,
            highlightcolor=PURPLE,
            font=("Segoe UI", 10)
        )

    def clear_page(self):

        # The startup screen ("Studestics / Your study workspace / Ready.")
        # is packed directly into self.main and is never referenced again
        # once a real page loads — without this it stays stacked above
        # every page for the rest of the app's life.
        if self.startup_screen is not None:

            try:
                self.startup_screen.destroy()
            except Exception:
                pass

            self.startup_screen = None

        if self.page:

            self.page.destroy()

        self.page = tk.Frame(
            self.main,
            bg=BG
        )

        self.page.pack(
            fill="both",
            expand=True,
            padx=34,
            pady=28
        )

    def page_header(
        self,
        title,
        subtitle=""
    ):

        header = tk.Frame(
            self.page,
            bg=BG
        )

        header.pack(
            fill="x",
            pady=(0, 24)
        )

        tk.Label(
            header,
            text=title,
            bg=BG,
            fg=TEXT,
            font=("Segoe UI", 25, "bold")
        ).pack(
            anchor="w"
        )

        if subtitle:

            tk.Label(
                header,
                text=subtitle,
                bg=BG,
                fg=MUTED,
                font=("Segoe UI", 10)
            ).pack(
                anchor="w",
                pady=(4, 0)
            )

    def section_title(
        self,
        parent,
        title,
        subtitle=""
    ):

        box = tk.Frame(
            parent,
            bg=parent.cget("bg")
        )

        box.pack(
            fill="x",
            padx=20,
            pady=(20, 12)
        )

        tk.Label(
            box,
            text=title,
            bg=parent.cget("bg"),
            fg=TEXT,
            font=("Segoe UI", 14, "bold")
        ).pack(
            anchor="w"
        )

        if subtitle:

            tk.Label(
                box,
                text=subtitle,
                bg=parent.cget("bg"),
                fg=MUTED,
                font=("Segoe UI", 9)
            ).pack(
                anchor="w",
                pady=(2, 0)
            )

    def empty_text(
        self,
        parent,
        text
    ):

        tk.Label(
            parent,
            text=text,
            bg=parent.cget("bg"),
            fg=MUTED_2,
            font=("Segoe UI", 10)
        ).pack(
            anchor="w",
            padx=20,
            pady=18
        )

    # ========================================================
    # PAGE SWITCHING
    # ========================================================

    def show_page(self, page_name):

        if not self.initialized:
            return

        self.current_page = page_name

        for name, item in self.sidebar_buttons.items():
            item.set_active(name == page_name)

        self._sidebar_timer_update()

        self.refresh_sidebar_upnext()

        self.clear_page()

        if page_name == "Dashboard":
            self.build_dashboard()

        elif page_name == "Tasks":
            self.build_tasks()

        elif page_name == "Goals":
            self.build_goals()

        elif page_name == "Notes":
            self.build_notes()

        elif page_name == "Focus Mode":
            self.build_focus()

        elif page_name == "AI Chat":
            self.build_chat()

        elif page_name == "Analytics":
            self.build_analytics()

        elif page_name == "Settings":
            self.build_settings()

        elif page_name == "Profile":
            self.build_profile()

        self._settle_panels()

        profile = self.db.get_profile()

        self._refresh_profile_chip()

    def _avatar_canvas(self, parent, size, letter, bg):
        """A round badge: the chosen photo, or the person's initial."""

        canvas = tk.Canvas(
            parent,
            width=size,
            height=size,
            bg=bg,
            highlightthickness=0,
            bd=0
        )

        self._avatar_paint(canvas, size, letter, bg)

        return canvas

    def _avatar_hover_edit(self, canvas, size):
        """Fade a dark veil and a pencil over the round photo while the
        pointer is on it, to say "click to change". Smooth in and out."""

        if not HAS_PIL:
            return

        hv = {
            "level": 0.0,
            "target": 0.0,
            "job": None,
            "last": 0.0,
            "frames": {}
        }

        canvas._hv = hv

        STEPS = 12
        DURATION = 0.18

        def frame(index):

            if index in hv["frames"]:
                return hv["frames"][index]

            level = index / STEPS

            sc = 4

            big = size * sc

            img = Image.new("RGBA", (big, big), (0, 0, 0, 0))

            veil = Image.new("RGBA", (big, big), (0, 0, 0, int(150 * level)))

            mask = Image.new("L", (big, big), 0)

            ImageDraw.Draw(mask).ellipse([0, 0, big - 1, big - 1], fill=255)

            img.paste(veil, (0, 0), mask)

            # pencil, drawn in a 24-unit box centred on the photo
            box = size * 0.42 * sc

            u = box / 24.0

            ox = (big - box) / 2
            oy = (big - box) / 2

            def pts(points):

                return [(ox + x * u, oy + y * u) for x, y in points]

            pen = Image.new("RGBA", (big, big), (0, 0, 0, 0))

            d = ImageDraw.Draw(pen)

            white = (255, 255, 255, int(255 * level))
            softer = (255, 255, 255, int(150 * level))

            d.polygon(pts([(6.2, 14.8), (15.2, 5.8), (18.2, 8.8), (9.2, 17.8)]), fill=white)
            d.polygon(pts([(6.2, 14.8), (9.2, 17.8), (4, 20)]), fill=white)
            d.polygon(pts([(15.9, 5.1), (17.4, 3.6), (20.4, 6.6), (18.9, 8.1)]), fill=softer)

            img = Image.alpha_composite(img, pen)

            photo = ImageTk.PhotoImage(
                img.resize((size, size), Image.LANCZOS)
            )

            hv["frames"][index] = photo

            return photo

        def draw():

            canvas.delete("hover")

            index = int(round(hv["level"] * STEPS))

            if index > 0:

                canvas.create_image(
                    0, 0,
                    anchor="nw",
                    image=frame(index),
                    tags="hover"
                )

        def tick():

            hv["job"] = None

            now = time.time()

            dt = now - hv["last"]

            hv["last"] = now

            step = dt / DURATION

            if hv["level"] < hv["target"]:
                hv["level"] = min(hv["target"], hv["level"] + step)

            elif hv["level"] > hv["target"]:
                hv["level"] = max(hv["target"], hv["level"] - step)

            try:

                draw()

                if hv["level"] != hv["target"]:
                    hv["job"] = canvas.after(16, tick)

            except Exception:
                pass

        def go(target):

            hv["target"] = target

            if hv["job"] is None:

                hv["last"] = time.time()

                hv["job"] = canvas.after(16, tick)

        canvas.bind("<Enter>", lambda e: go(1.0), add="+")
        canvas.bind("<Leave>", lambda e: go(0.0), add="+")

    def _avatar_paint(self, canvas, size, letter, bg, photo=None):

        canvas.delete("all")

        if hasattr(canvas, "_hv"):
            canvas._hv["level"] = 0.0

        # The sidebar is built before the database exists.
        photo_path = photo or (
            self.db.get_setting("profile_photo", "")
            if getattr(self, "db", None) is not None
            else ""
        )

        sc = 4

        circle = None

        if HAS_PIL:

            mask = Image.new("L", (size * sc, size * sc), 0)

            ImageDraw.Draw(mask).ellipse(
                [0, 0, size * sc - 1, size * sc - 1],
                fill=255
            )

            base = None

            if photo_path and Path(photo_path).exists():

                try:

                    pic = Image.open(photo_path).convert("RGB")

                    side = min(pic.size)

                    left = (pic.width - side) // 2
                    top = (pic.height - side) // 2

                    base = pic.crop(
                        (left, top, left + side, top + side)
                    ).resize(
                        (size * sc, size * sc),
                        Image.LANCZOS
                    )

                except Exception:

                    base = None

            if base is None:

                base = Image.new("RGB", (size * sc, size * sc), PURPLE)

            img = Image.new("RGB", (size * sc, size * sc), bg)

            img.paste(base, (0, 0), mask)

            circle = ImageTk.PhotoImage(
                img.resize((size, size), Image.LANCZOS)
            )

            canvas._photo = circle

            canvas.create_image(0, 0, anchor="nw", image=circle)

            has_photo = bool(
                photo_path and Path(photo_path).exists()
            )

        else:

            canvas.create_oval(
                0, 0, size - 1, size - 1,
                fill=PURPLE,
                outline=PURPLE
            )

            has_photo = False

        if not has_photo:

            canvas.create_text(
                size / 2,
                size / 2,
                text=letter,
                fill="#FFFFFF",
                font=("Segoe UI", -int(size * 0.46), "bold"),
                tags="letter"
            )

    def choose_profile_photo(self):

        path = filedialog.askopenfilename(
            title="Choose profile picture",
            filetypes=[
                ("Images", "*.png *.jpg *.jpeg *.webp *.gif"),
                ("All files", "*.*")
            ]
        )

        if not path:
            return

        try:

            destination = APP_DIR / (
                f"profile_{int(datetime.now().timestamp())}"
                + Path(path).suffix.lower()
            )

            shutil.copy2(path, destination)

            old = self.db.get_setting("profile_photo", "")

            self.db.set_setting("profile_photo", str(destination))

            if old and old != str(destination):

                try:
                    Path(old).unlink(missing_ok=True)
                except Exception:
                    pass

        except Exception as exc:

            messagebox.showerror("Profile", str(exc))

            return

        self._refresh_profile_chip()

        if self.current_page == "Profile":
            self.show_page("Profile")

    def _refresh_profile_chip(self):

        profile = self.db.get_profile()

        if not profile:
            return

        name = profile["name"]

        try:

            self.sidebar_user.configure(text=name)

            self._avatar_paint(
                self.sidebar_avatar,
                34,
                (name.strip()[:1] or "?").upper(),
                SIDEBAR
            )

        except Exception:
            pass

    def _profile_stat(self, parent, label, value, color=None, column=0):

        box = tk.Frame(parent, bg=PANEL)

        box.grid(row=0, column=column, sticky="nsew", padx=6)

        parent.grid_columnconfigure(column, weight=1, uniform="pstat")

        tk.Label(
            box,
            text=label,
            bg=PANEL,
            fg=MUTED_2,
            font=("Segoe UI", 9)
        ).pack(
            anchor="w"
        )

        tk.Label(
            box,
            text=value,
            bg=PANEL,
            fg=color or TEXT,
            font=("Segoe UI", 26, "bold")
        ).pack(
            anchor="w",
            pady=(2, 0)
        )

    def _profile_card(self, parent, title, stats, accent=None):
        """A rounded card: a small title and a row of big numbers."""

        outer, inner = self.rounded_panel(
            parent,
            radius=16,
            accent=accent,
            fit=True
        )

        tk.Label(
            inner,
            text=title,
            bg=PANEL,
            fg=TEXT,
            font=("Segoe UI", 12, "bold")
        ).pack(
            anchor="w",
            padx=20,
            pady=(18, 10)
        )

        row = tk.Frame(inner, bg=PANEL)

        row.pack(
            fill="x",
            padx=14,
            pady=(0, 20)
        )

        for column, (label, value, color) in enumerate(stats):
            self._profile_stat(row, label, value, color, column)

        return outer

    def build_profile(self):

        profile = self.db.get_profile()

        if not profile:
            return

        name = profile["name"]

        self.page_header(
            "Profile",
            "Your stats and focus activity."
        )

        total, completed, pending, goals = self.db.statistics()

        focus = self.db.focus_profile_stats()

        stats = self.db.focus_stats()

        streak = stats["streak"]

        # ---- header card: badge, name, joined, streak, big numbers ----
        head_outer, head = self.rounded_panel(
            self.page,
            radius=16,
            accent=PURPLE,
            fit=True
        )

        head_outer.pack(
            fill="x",
            pady=(0, 16)
        )

        row = tk.Frame(head, bg=PANEL)

        row.pack(
            fill="x",
            padx=24,
            pady=22
        )

        avatar_box = tk.Frame(row, bg=PANEL)

        avatar_box.pack(
            side="left",
            padx=(0, 22)
        )

        avatar = self._avatar_canvas(
            avatar_box,
            96,
            (name.strip()[:1] or "?").upper(),
            PANEL
        )

        avatar.pack()

        avatar.configure(cursor="hand2")

        self._avatar_hover_edit(avatar, 96)

        change = tk.Label(
            avatar_box,
            text="Change photo",
            bg=PANEL,
            fg=MUTED_2,
            font=("Segoe UI", 8),
            cursor="hand2"
        )

        change.pack(pady=(6, 0))

        for w in (avatar, change):

            w.bind("<Button-1>", lambda e: self.choose_profile_photo())

        change.bind("<Enter>", lambda e: change.configure(fg=TEXT))
        change.bind("<Leave>", lambda e: change.configure(fg=MUTED_2))

        who = tk.Frame(row, bg=PANEL)

        who.pack(
            side="left",
            anchor="n"
        )

        name_row = tk.Frame(who, bg=PANEL)

        name_row.pack(anchor="w")

        name_label = tk.Label(
            name_row,
            text=name,
            bg=PANEL,
            fg=TEXT,
            font=("Segoe UI", 22, "bold")
        )

        name_label.pack(side="left")

        try:

            joined = datetime.strptime(
                profile["created_at"],
                "%Y-%m-%d %H:%M:%S"
            ).strftime("%d %b %Y")

        except Exception:

            joined = ""

        if joined:

            tk.Label(
                who,
                text=f"Joined {joined}",
                bg=PANEL,
                fg=MUTED_2,
                font=("Segoe UI", 9)
            ).pack(
                anchor="w",
                pady=(2, 0)
            )

        tk.Label(
            who,
            text=f"Current streak {streak} day"
                 + ("" if streak == 1 else "s"),
            bg=PANEL,
            fg=YELLOW if streak else MUTED_2,
            font=("Segoe UI", 9)
        ).pack(
            anchor="w"
        )

        def start_rename(event=None):

            name_label.pack_forget()

            edit_button.pack_forget()

            entry = self.make_entry(name_row)

            entry.insert(0, name)

            entry.configure(width=16)

            entry.pack(
                side="left",
                ipady=6
            )

            def save(event=None):

                new_name = entry.get().strip()

                if new_name and new_name != name:

                    self.db.rename_profile(new_name)

                    self._refresh_profile_chip()

                self.show_page("Profile")

            entry.bind("<Return>", save)
            entry.bind("<Escape>", lambda e: self.show_page("Profile"))

            self.make_button(
                name_row,
                "Save",
                save,
                width=5
            ).pack(
                side="left",
                padx=(8, 0)
            )

            entry.focus_set()

        edit_button = tk.Label(
            name_row,
            text="\u270E",
            bg=PANEL,
            fg=MUTED_2,
            font=("Segoe UI Symbol", 12),
            cursor="hand2"
        )

        edit_button.pack(
            side="left",
            padx=(10, 0)
        )

        edit_button.bind("<Button-1>", start_rename)
        edit_button.bind("<Enter>", lambda e: edit_button.configure(fg=TEXT))
        edit_button.bind("<Leave>", lambda e: edit_button.configure(fg=MUTED_2))

        tk.Frame(
            row,
            bg=BORDER,
            width=1
        ).pack(
            side="left",
            fill="y",
            padx=26
        )

        big = tk.Frame(row, bg=PANEL)

        big.pack(
            side="left",
            fill="x",
            expand=True
        )

        for column, (label, value, color) in enumerate((
            ("tasks created", str(total), BLUE),
            ("tasks completed", str(completed), GREEN),
            ("time focused", fmt_duration(focus["total"]), PURPLE_HOVER)
        )):
            self._profile_stat(big, label, value, color, column)

        # ---- two stat cards ----
        cards = tk.Frame(self.page, bg=BG)

        cards.pack(
            fill="x",
            pady=(0, 16)
        )

        cards.grid_columnconfigure(0, weight=1, uniform="pc")
        cards.grid_columnconfigure(1, weight=1, uniform="pc")

        left = self._profile_card(
            cards,
            "Focus",
            (
                ("sessions", str(focus["sessions"]), TEXT),
                ("finished", str(focus["finished"]), GREEN),
                ("longest", fmt_duration(focus["longest"]), PURPLE_HOVER),
                ("alerts", str(focus["nudges"]), YELLOW)
            ),
            accent=PURPLE_HOVER
        )

        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        right = self._profile_card(
            cards,
            "Tasks and goals",
            (
                ("pending", str(pending), YELLOW),
                ("completed", str(completed), GREEN),
                ("active goals", str(goals), PURPLE_HOVER),
                ("focus days", str(focus["days"]), BLUE)
            ),
            accent=BLUE
        )

        right.grid(row=0, column=1, sticky="nsew", padx=(8, 0))

        # ---- last 7 days, same chart as Analytics, fills the rest ----
        week = self.db.focus_daily_seconds(7)

        chart_outer, chart_inner = self.rounded_panel(
            self.page,
            radius=16
        )

        chart_outer.pack(
            fill="both",
            expand=True
        )

        self.section_title(
            chart_inner,
            "Last 7 days",
            "Time focused per day  \u00b7  "
            + fmt_duration(sum(secs for _, secs in week))
            + " in total"
        )

        chart = tk.Canvas(
            chart_inner,
            width=10,
            height=10,
            bg=PANEL,
            highlightthickness=0,
            bd=0
        )

        chart.pack(
            fill="both",
            expand=True,
            padx=20,
            pady=(0, 18)
        )

        chart.bind(
            "<Configure>",
            lambda event: self._draw_week_chart(chart, week)
        )

    def _sidebar_due_tag(self, deadline):
        """('Overdue', colour) / ('Today', ...) / ('Fri', ...) / ('', ...)
        for a deadline string like '2026-10-08 13:22:00'."""

        try:

            day = datetime.strptime(str(deadline)[:10], "%Y-%m-%d").date()

        except Exception:

            return "", MUTED_2

        delta = (day - datetime.now().date()).days

        if delta < 0:
            return "Overdue", RED

        if delta == 0:
            return "Today", YELLOW

        if delta == 1:
            return "Tomorrow", MUTED

        if delta < 7:
            return day.strftime("%a"), MUTED

        return "", MUTED_2

    def _sidebar_mini_row(
        self,
        parent,
        dot_color,
        title,
        command=None,
        tag="",
        tag_color=None,
        icon="task"
    ):
        """One line under 'Top tasks' / 'Active goals': a dot, the
        title, and a small due label. Click to open its page."""

        row = tk.Frame(
            parent,
            bg=SIDEBAR,
            cursor="hand2" if command else ""
        )

        row.pack(
            fill="x",
            pady=3
        )

        if HAS_PIL:

            photo = ImageTk.PhotoImage(
                mini_marker_image(icon, dot_color, 18)
            )

            dot = tk.Label(row, image=photo, bg=SIDEBAR, bd=0)

            dot.marker_photo = photo

        else:

            dot = tk.Label(
                row,
                text="●",
                bg=SIDEBAR,
                fg=dot_color,
                font=("Segoe UI", 8)
            )

        dot.pack(
            side="left",
            anchor="n",
            padx=(8, 0),
            pady=(5, 0)
        )

        if len(title) > 22:
            title = title[:21] + "…"

        # Title on top, due label under it, so neither is squeezed.
        text_box = tk.Frame(
            row,
            bg=SIDEBAR
        )

        text_box.pack(
            side="left",
            fill="x",
            expand=True,
            padx=(10, 6),
            pady=(3, 4)
        )

        name = tk.Label(
            text_box,
            text=title,
            bg=SIDEBAR,
            fg=NAV_TEXT,
            font=("Segoe UI", 10),
            anchor="w"
        )

        name.pack(
            fill="x"
        )

        parts = [row, dot, text_box, name]

        if tag:

            note = tk.Label(
                text_box,
                text=tag,
                bg=SIDEBAR,
                fg=tag_color or MUTED_2,
                font=("Segoe UI", 8),
                anchor="w"
            )

            note.pack(
                fill="x"
            )

            parts.append(note)

        def paint(color):

            for part in parts:

                try:
                    part.configure(bg=color)
                except Exception:
                    pass

        if command:

            for part in parts:

                part.bind("<Enter>", lambda e: paint(SIDEBAR_HOVER))
                part.bind("<Leave>", lambda e: paint(SIDEBAR))
                part.bind("<Button-1>", lambda e: command())

    def _sidebar_timer_update(self):
        """Show, redraw or hide the little timer card in the sidebar."""

        card = getattr(self, "sidebar_timer", None)

        if card is None or self._quitting:
            return

        try:

            show = (
                self.initialized
                and self._float_active()
                and self.current_page != "Focus Mode"
            )

            if not show:

                if self._sidebar_timer_shown:

                    card.pack_forget()

                    self._sidebar_timer_shown = False
                    self._sidebar_timer_key = None

                return

            if not self._sidebar_timer_shown:

                card.pack(
                    side="top",
                    before=self.sidebar_upnext_frame,
                    padx=10,
                    pady=(12, 0)
                )

                self._sidebar_timer_shown = True

            fraction = self.focus_seconds / max(1, self._phase_total())

            time_text = self.focus_time_text()
            status = self._float_status()
            color = self._float_color()

            key = (time_text, status, color, int(fraction * 230))

            if key == self._sidebar_timer_key:
                return

            self._sidebar_timer_key = key

            card.delete("all")

            if HAS_PIL:

                scale = 4

                w, h = NAV_W, 62

                img = Image.new("RGB", (w * scale, h * scale), SIDEBAR)

                d = ImageDraw.Draw(img)

                d.rounded_rectangle(
                    [0, 0, w * scale - 1, h * scale - 1],
                    radius=14 * scale,
                    fill=PANEL_2,
                    outline=BORDER,
                    width=scale
                )

                x0, x1, y0, y1 = 16, w - 16, 46, 50

                d.rounded_rectangle(
                    [x0 * scale, y0 * scale, x1 * scale, y1 * scale],
                    radius=2 * scale,
                    fill=HOVER_BG
                )

                fx = x0 + max(4, (x1 - x0) * fraction)

                d.rounded_rectangle(
                    [x0 * scale, y0 * scale, fx * scale, y1 * scale],
                    radius=2 * scale,
                    fill=color
                )

                img = img.resize((w, h), Image.LANCZOS)

                self._sidebar_timer_photo = ImageTk.PhotoImage(img)

                card.create_image(
                    0, 0,
                    anchor="nw",
                    image=self._sidebar_timer_photo
                )

            card.create_text(
                16, 22,
                anchor="w",
                text=time_text,
                fill=TEXT,
                font=("Segoe UI", 15, "bold")
            )

            card.create_text(
                NAV_W - 16, 23,
                anchor="e",
                text=status,
                fill=MUTED,
                font=("Segoe UI", 9)
            )

        except Exception:
            pass

    def refresh_sidebar_upnext(self):

        if not hasattr(self, "sidebar_upnext_frame"):
            return

        if not self.db:
            return

        for widget in self.sidebar_upnext_frame.winfo_children():
            widget.destroy()

        priority_rank = {"High": 0, "Medium": 1, "Low": 2}

        tasks = self.db.get_tasks(False)

        # Highest priority first; within the same priority, nearest
        # deadline first (tasks with no deadline sort to the end of
        # their priority tier, not to the very end of the whole list).
        tasks_sorted = sorted(
            tasks,
            key=lambda t: (
                priority_rank.get(t["priority"], 1),
                t["deadline"] or "9999-12-31 23:59:59"
            )
        )

        top_tasks = tasks_sorted[:3]

        active_goals = self.db.get_goals(True)[:2]

        if not top_tasks and not active_goals:
            return

        separator = tk.Frame(
            self.sidebar_upnext_frame,
            bg=mix_color(PURPLE, SIDEBAR, 0.2),
            height=1
        )

        separator.pack(
            fill="x",
            pady=(0, 12)
        )

        if top_tasks:

            tk.Label(
                self.sidebar_upnext_frame,
                text="TOP TASKS",
                bg=SIDEBAR,
                fg=BLUE,
                font=("Segoe UI", 8, "bold")
            ).pack(
                anchor="w",
                pady=(0, 6)
            )

            for task in top_tasks:

                tag, tag_color = self._sidebar_due_tag(task["deadline"])

                self._sidebar_mini_row(
                    self.sidebar_upnext_frame,
                    priority_color(task["priority"]),
                    task["title"],
                    command=lambda: self.show_page("Tasks"),
                    tag=tag,
                    tag_color=tag_color
                )

        if active_goals:

            tk.Label(
                self.sidebar_upnext_frame,
                text="ACTIVE GOALS",
                bg=SIDEBAR,
                fg=PURPLE_HOVER,
                font=("Segoe UI", 8, "bold")
            ).pack(
                anchor="w",
                pady=(12 if top_tasks else 0, 6)
            )

            for goal in active_goals:

                self._sidebar_mini_row(
                    self.sidebar_upnext_frame,
                    PURPLE_HOVER,
                    goal["title"],
                    command=lambda: self.show_page("Goals"),
                    icon="goal"
                )

    # ========================================================
    # DASHBOARD
    # ========================================================

    def get_greeting(self):

        hour = datetime.now().hour

        if hour < 5:
            return "Good night"

        if hour < 12:
            return "Good morning"

        if hour < 17:
            return "Good afternoon"

        if hour < 21:
            return "Good evening"

        return "Good night"

    def build_dashboard(self):

        profile = self.db.get_profile()

        name = (
            profile["name"]
            if profile
            else "there"
        )

        self.page_header(
            f"{self.get_greeting()}, {name}.",
            "A quiet place to organize your study life."
        )

        quick_actions = tk.Frame(
            self.page,
            bg=BG
        )

        quick_actions.pack(
            fill="x",
            pady=(0, 20)
        )

        self.make_button(
            quick_actions,
            "+ New task",
            self.new_task_dialog
        ).pack(
            side="left"
        )

        self.make_button(
            quick_actions,
            "+ New goal",
            self.new_goal_dialog
        ).pack(
            side="left",
            padx=8
        )

        self.make_button(
            quick_actions,
            "▶  Start focus session",
            lambda: self.show_page("Focus Mode")
        ).pack(
            side="left"
        )

        total, completed, pending, goals = (
            self.db.statistics()
        )

        cards = tk.Frame(
            self.page,
            bg=BG
        )

        cards.pack(
            fill="x",
            pady=(0, 24)
        )

        self.stat_card(
            cards,
            "Tasks",
            total,
            BLUE
        )

        self.stat_card(
            cards,
            "Completed",
            completed,
            GREEN
        )

        self.stat_card(
            cards,
            "Pending",
            pending,
            YELLOW
        )

        self.stat_card(
            cards,
            "Active goals",
            goals,
            PURPLE_HOVER
        )

        columns = tk.Frame(
            self.page,
            bg=BG
        )

        columns.pack(
            fill="both",
            expand=True
        )

        left_outer, left = self.rounded_panel(columns, radius=16)

        left_outer.pack(
            side="left",
            fill="both",
            expand=True,
            padx=(0, 10)
        )

        right_outer, right = self.rounded_panel(columns, radius=16)

        right_outer.pack(
            side="left",
            fill="both",
            expand=True,
            padx=(10, 0)
        )

        self.section_title(
            left,
            "Upcoming tasks",
            "Your nearest deadlines"
        )

        tasks = self.db.get_tasks(
            False
        )[:7]

        if not tasks:

            self.dashboard_empty_state(
                left,
                "No pending tasks",
                "You're all caught up. Add one when something comes up.",
                "+ Add a task",
                self.new_task_dialog
            )

        for task in tasks:

            self.dashboard_task(
                left,
                task
            )

        self.section_title(
            right,
            "Active goals",
            "Keep the bigger picture visible"
        )

        active_goals = self.db.get_goals(
            True
        )[:7]

        if not active_goals:

            self.dashboard_empty_state(
                right,
                "No active goals yet",
                "Set one to keep the bigger picture in view.",
                "+ Add a goal",
                self.new_goal_dialog
            )

        for goal in active_goals:

            row = tk.Frame(
                right,
                bg=PANEL
            )

            row.pack(
                fill="x",
                padx=20,
                pady=7
            )

            tk.Label(
                row,
                text="●",
                bg=PANEL,
                fg=PURPLE_HOVER,
                font=("Segoe UI", 9)
            ).pack(
                side="left"
            )

            tk.Label(
                row,
                text=goal["title"],
                bg=PANEL,
                fg=TEXT,
                font=("Segoe UI", 10)
            ).pack(
                side="left",
                padx=10
            )

    def dashboard_empty_state(
        self,
        parent,
        title,
        subtitle,
        button_text,
        button_command
    ):

        wrap = tk.Frame(
            parent,
            bg=PANEL
        )

        wrap.pack(
            fill="both",
            expand=True
        )

        center = tk.Frame(
            wrap,
            bg=PANEL
        )

        center.pack(
            expand=True
        )

        tk.Label(
            center,
            text=title,
            bg=PANEL,
            fg=MUTED,
            font=("Segoe UI", 11, "bold")
        ).pack()

        tk.Label(
            center,
            text=subtitle,
            bg=PANEL,
            fg=MUTED_2,
            font=("Segoe UI", 9),
            wraplength=240,
            justify="center"
        ).pack(
            pady=(4, 14)
        )

        self.make_button(
            center,
            button_text,
            button_command
        ).pack()

    def _settle_panels(self):
        """Lay out and paint every rounded card right after a page is
        built, before the screen repaints, so they never show up in an
        unrounded or half-sized state first."""

        pending = getattr(self, "_panel_layouts", [])

        self._panel_layouts = []

        if not pending:
            return

        try:

            for _ in range(3):

                self.update_idletasks()

                for fn in pending:

                    try:
                        fn()
                    except Exception:
                        pass

            self.update_idletasks()

        except Exception:
            pass

    def rounded_panel(self, parent, radius=14, accent=None, fit=False):
        """A card with anti-aliased rounded corners. Returns
        (outer, inner): place/pack/grid `outer`, put content in
        `inner`. fit=True makes the card as tall as its content."""

        if not HAS_PIL:

            outer = tk.Frame(
                parent,
                bg=PANEL,
                highlightthickness=1,
                highlightbackground=BORDER
            )

            if accent:

                tk.Frame(
                    outer,
                    bg=accent,
                    width=4
                ).pack(
                    side="left",
                    fill="y"
                )

            inner = tk.Frame(outer, bg=PANEL)

            inner.pack(
                side="left",
                fill="both",
                expand=True
            )

            return outer, inner

        from PIL import ImageChops

        outer = tk.Canvas(
            parent,
            bg=BG,
            width=10,
            height=100 if fit else 10,
            highlightthickness=0,
            bd=0
        )

        inner = tk.Frame(outer, bg=PANEL)

        inset = int(radius * 0.3) + 2

        state = {"key": None}

        def draw(w, h):

            r = radius

            if h < 2 * r + 2 or w < 2 * r + 2:
                return

            corners = _panel_corner_images(r, accent)

            if not hasattr(outer, "_corner_photos"):
                outer._corner_photos = {}

            photos = outer._corner_photos

            for name, pil in corners.items():

                if name not in photos:
                    photos[name] = ImageTk.PhotoImage(pil)

            outer.delete("bg")

            def rect(x0, y0, x1, y1, color):

                if x1 > x0 and y1 > y0:

                    outer.create_rectangle(
                        x0, y0, x1, y1,
                        fill=color,
                        width=0,
                        tags="bg"
                    )

            # body, then the 1px border along each straight edge
            rect(r, 0, w - r, h, PANEL)
            rect(0, r, w, h - r, PANEL)

            rect(r, 0, w - r, 1, BORDER)
            rect(r, h - 1, w - r, h, BORDER)
            rect(w - 1, r, w, h - r, BORDER)
            rect(0, r, 1, h - r, BORDER)

            if accent:
                rect(1, r, 5, h - r, accent)

            for name, x, y in (
                ("tl", 0, 0),
                ("tr", w - r, 0),
                ("bl", 0, h - r),
                ("br", w - r, h - r)
            ):

                outer.create_image(
                    x, y,
                    anchor="nw",
                    image=photos[name],
                    tags="bg"
                )

            outer.tag_lower("bg")

        def layout(event=None):

            w, h = outer.winfo_width(), outer.winfo_height()

            if w < 20 or h < 20:
                return

            if state["key"] != (w, h):

                state["key"] = (w, h)

                draw(w, h)

            if fit:

                inner.place(
                    x=inset,
                    y=inset,
                    width=w - 2 * inset
                )

                need = inner.winfo_reqheight() + 2 * inset

                if int(outer.cget("height")) != need:
                    outer.configure(height=need)

            else:

                inner.place(
                    x=inset,
                    y=inset,
                    width=w - 2 * inset,
                    height=h - 2 * inset
                )

        def inner_resized(event=None):

            if not fit:
                return

            need = inner.winfo_reqheight() + 2 * inset

            if int(outer.cget("height")) != need:
                outer.configure(height=need)

        outer.bind("<Configure>", layout)
        inner.bind("<Configure>", inner_resized)

        if not hasattr(self, "_panel_layouts"):
            self._panel_layouts = []

        self._panel_layouts.append(layout)

        return outer, inner

    def stat_card(
        self,
        parent,
        title,
        value,
        color
    ):

        card, body = self.rounded_panel(
            parent,
            radius=14,
            accent=color,
            fit=True
        )

        card.pack(
            side="left",
            fill="x",
            expand=True,
            padx=5
        )

        tk.Label(
            body,
            text=title,
            bg=PANEL,
            fg=MUTED,
            font=("Segoe UI", 9)
        ).pack(
            anchor="w",
            padx=18,
            pady=(15, 2)
        )

        tk.Label(
            body,
            text=str(value),
            bg=PANEL,
            fg=color,
            font=("Segoe UI", 25, "bold")
        ).pack(
            anchor="w",
            padx=18,
            pady=(0, 15)
        )

    def dashboard_task(
        self,
        parent,
        task
    ):

        row = tk.Frame(
            parent,
            bg=PANEL
        )

        row.pack(
            fill="x",
            padx=20,
            pady=6
        )

        tk.Label(
            row,
            text="●",
            bg=PANEL,
            fg=priority_color(
                task["priority"]
            ),
            font=("Segoe UI", 8)
        ).pack(
            side="left"
        )

        info = tk.Frame(
            row,
            bg=PANEL
        )

        info.pack(
            side="left",
            fill="x",
            expand=True,
            padx=10
        )

        tk.Label(
            info,
            text=task["title"],
            bg=PANEL,
            fg=TEXT,
            font=("Segoe UI", 10, "bold"),
            anchor="w"
        ).pack(
            fill="x"
        )

        tk.Label(
            info,
            text=format_date(
                task["deadline"]
            ),
            bg=PANEL,
            fg=MUTED,
            font=("Segoe UI", 8),
            anchor="w"
        ).pack(
            fill="x"
        )

        self.make_button(
            row,
            "Done",
            lambda tid=task["id"]:
                self.complete_and_refresh(tid),
            width=6
        ).pack(
            side="right"
        )

    # ========================================================
    # TASKS
    # ========================================================

    def build_tasks(self):

        self.page_header(
            "Tasks",
            "Assignments, deadlines and reference material."
        )

        toolbar = tk.Frame(
            self.page,
            bg=BG
        )

        toolbar.pack(
            fill="x",
            pady=(0, 16)
        )

        self.make_button(
            toolbar,
            "+ New task",
            self.new_task_dialog
        ).pack(
            side="left"
        )

        self.make_button(
            toolbar,
            "Refresh",
            lambda:
                self.show_page("Tasks"),
            width=9
        ).pack(
            side="left",
            padx=8
        )

        def toggle_completed():
            self.tasks_show_completed = not self.tasks_show_completed
            self.tasks_page = 0
            self.show_page("Tasks")

        self.make_button(
            toolbar,
            "Hide completed" if self.tasks_show_completed else "Show completed",
            toggle_completed,
            width=14
        ).pack(
            side="left"
        )

        outer = tk.Frame(
            self.page,
            bg=PANEL,
            highlightthickness=1,
            highlightbackground=BORDER
        )

        outer.pack(
            fill="both",
            expand=True
        )

        # The pager row always reserves its height, so the arrows
        # appearing later never shifts the cards around.
        pager = tk.Frame(
            outer,
            bg=PANEL,
            height=52
        )

        pager.pack(
            side="bottom",
            fill="x"
        )

        pager.pack_propagate(False)

        pager_inner = tk.Frame(
            pager,
            bg=PANEL
        )

        pager_inner.pack(
            expand=True
        )

        area = tk.Frame(
            outer,
            bg=PANEL
        )

        area.pack(
            fill="both",
            expand=True
        )

        # Size comes purely from the space available, never from the
        # cards inside it — otherwise the row count could feed back
        # into the size it was computed from.
        area.pack_propagate(False)

        holder = tk.Frame(
            area,
            bg=PANEL
        )

        holder.pack(
            fill="both",
            expand=True,
            padx=10,
            pady=8
        )

        columns = 3

        # Equal-width columns -> equal gaps between them, and the
        # cards stretch to fill the whole width.
        for column in range(columns):

            holder.grid_columnconfigure(
                column,
                weight=1,
                uniform="taskcol"
            )

        tasks = self.db.get_tasks(
            self.tasks_show_completed
        )

        max_rows = 4
        min_card_height = 130
        max_card_height = 190
        cell_padding = 16

        view = {"rows": None, "card_h": min_card_height, "area_h": 0, "job": None}

        def go_page(delta):

            self.tasks_page += delta
            render()

        def render():

            rows = view["rows"] or 1
            page_size = columns * rows

            pages = max(1, math.ceil(len(tasks) / page_size))

            self.tasks_page = max(
                0,
                min(self.tasks_page, pages - 1)
            )

            for widget in holder.winfo_children():
                widget.destroy()

            if not tasks:

                tk.Label(
                    holder,
                    text=(
                        "No completed tasks yet."
                        if self.tasks_show_completed
                        else "No pending tasks. Nice."
                    ),
                    bg=PANEL,
                    fg=MUTED_2,
                    font=("Segoe UI", 10)
                ).grid(
                    row=0,
                    column=0,
                    columnspan=columns,
                    sticky="w",
                    padx=12,
                    pady=12
                )

            start = self.tasks_page * page_size

            for index, task in enumerate(
                tasks[start:start + page_size]
            ):

                row, column = divmod(index, columns)

                cell = tk.Frame(
                    holder,
                    bg=PANEL
                )

                cell.grid(
                    row=row,
                    column=column,
                    sticky="new",
                    padx=8,
                    pady=8
                )

                self.task_card(
                    cell,
                    task,
                    view["card_h"]
                )

            for widget in pager_inner.winfo_children():
                widget.destroy()

            # Arrows only exist once tasks actually overflow a page.
            if pages > 1:

                def arrow(text, delta, enabled):

                    button = self.make_button(
                        pager_inner,
                        text,
                        lambda: go_page(delta),
                        width=3
                    )

                    if enabled:

                        button.pack(
                            side="left",
                            padx=8
                        )

                    else:

                        # Keep the page label from jumping around
                        # when an arrow isn't available.
                        spacer_width = int(button.canvas.cget("width"))

                        button.destroy()

                        tk.Frame(
                            pager_inner,
                            bg=PANEL,
                            width=spacer_width,
                            height=1
                        ).pack(
                            side="left",
                            padx=8
                        )

                arrow("‹", -1, self.tasks_page > 0)

                tk.Label(
                    pager_inner,
                    text=f"Page {self.tasks_page + 1} of {pages}",
                    bg=PANEL,
                    fg=MUTED,
                    font=("Segoe UI", 9)
                ).pack(
                    side="left",
                    padx=10
                )

                arrow("›", 1, self.tasks_page < pages - 1)

        def apply_layout():

            view["job"] = None

            try:

                if not area.winfo_exists():
                    return

            except Exception:
                return

            usable = view["area_h"] - cell_padding

            rows = max(
                1,
                min(
                    max_rows,
                    usable // (min_card_height + cell_padding)
                )
            )

            # Whatever height is left over after fitting whole rows is
            # shared out between the cards, so the page fills top to
            # bottom instead of leaving a blank strip under the last row.
            card_h = max(
                min_card_height,
                min(
                    max_card_height,
                    usable // rows - cell_padding
                )
            )

            if rows != view["rows"] or card_h != view["card_h"]:

                view["rows"] = rows
                view["card_h"] = card_h
                render()

        def on_area_resize(event):

            view["area_h"] = event.height

            if view["rows"] is None:

                apply_layout()

            else:

                # Dragging the window edge fires this on every pixel;
                # wait for it to settle before rebuilding the cards.
                if view["job"] is not None:

                    try:
                        area.after_cancel(view["job"])
                    except Exception:
                        pass

                view["job"] = area.after(120, apply_layout)

        area.bind(
            "<Configure>",
            on_area_resize
        )

    def task_card(
        self,
        parent,
        task,
        card_height=130
    ):

        if not HAS_PIL:
            self._task_card_plain(parent, task)
            return

        source_image = None

        if task["image_path"]:

            try:

                if Path(task["image_path"]).exists():

                    source_image = Image.open(
                        task["image_path"]
                    ).convert("RGB")

            except Exception:
                source_image = None

        self._task_card_canvas(parent, task, source_image, card_height)

    def _task_card_plain(
        self,
        parent,
        task
    ):

        bg = (
            COMPLETED_BG
            if task["status"] == "Completed"
            else PANEL_2
        )

        due_state, due_text, due_color = (
            ("none", "", None)
            if task["status"] == "Completed"
            else due_info(task["deadline"])
        )

        marked = due_state in ("overdue", "soon")

        card = tk.Frame(
            parent,
            bg=bg,
            highlightthickness=2 if marked else 1,
            highlightbackground=due_color if marked else BORDER
        )

        card.pack(
            fill="x",
            padx=18,
            pady=8
        )

        info = tk.Frame(
            card,
            bg=bg
        )

        info.pack(
            side="left",
            fill="both",
            expand=True,
            padx=16,
            pady=14
        )

        title = task["title"]

        if task["status"] == "Completed":
            title = "✓ " + title

        tk.Label(
            info,
            text=title,
            bg=bg,
            fg=(
                GREEN
                if task["status"] == "Completed"
                else TEXT
            ),
            font=("Segoe UI", 11, "bold"),
            anchor="w"
        ).pack(
            fill="x"
        )

        if task["description"]:

            tk.Label(
                info,
                text=task["description"],
                bg=bg,
                fg=MUTED,
                font=("Segoe UI", 9),
                wraplength=650,
                justify="left",
                anchor="w"
            ).pack(
                fill="x",
                pady=(4, 0)
            )

        meta = (
            f"{format_date(task['deadline'])}"
            f" • {task['priority']}"
        )

        if task["image_path"]:
            meta += "  •  reference attached"

        meta_row = tk.Frame(
            info,
            bg=bg
        )

        meta_row.pack(
            anchor="w",
            pady=(7, 0)
        )

        tk.Label(
            meta_row,
            text=meta,
            bg=bg,
            fg=priority_color(
                task["priority"]
            ),
            font=("Segoe UI", 8)
        ).pack(
            side="left"
        )

        if due_text:

            tk.Label(
                meta_row,
                text="  \u2022  " + due_text,
                bg=bg,
                fg=due_color,
                font=("Segoe UI", 8, "bold")
            ).pack(
                side="left"
            )

        actions = tk.Frame(
            card,
            bg=bg
        )

        actions.pack(
            side="right",
            padx=12
        )

        if task["status"] == "Completed":

            self.make_button(
                actions,
                "Reopen",
                lambda tid=task["id"]:
                    self.reopen_and_refresh(tid),
                width=8
            ).pack(
                pady=4
            )

        else:

            self.make_button(
                actions,
                "Complete",
                lambda tid=task["id"]:
                    self.complete_and_refresh(tid),
                width=8
            ).pack(
                pady=4
            )

        self.make_button(
            actions,
            "Edit",
            lambda tid=task["id"]:
                self.edit_task_dialog(tid),
            width=8
        ).pack(
            pady=4
        )

        self.make_button(
            actions,
            "Delete",
            lambda tid=task["id"]:
                self.delete_task_confirm(tid),
            width=8,
            active=DANGER_HOVER
        ).pack(
            pady=4
        )

        if task["image_path"]:

            self.make_button(
                actions,
                "Open image",
                lambda p=task["image_path"]:
                    self.open_file(p),
                width=8
            ).pack(
                pady=4
            )

    def _paste_flat(self, img, box, kind, hovered):
        """A solid pill for cards without a photo, in the app's own
        style: purple for the main action, dark grey for Edit, a
        red-tinted one for Delete."""

        x1, y1, x2, y2 = box
        w, h = x2 - x1, y2 - y1

        if w < 4 or h < 4:
            return

        look = {
            "primary": (ACCENT_RGB, ACCENT_RGB,
                        ACCENT_LIGHT_RGB, ACCENT_LIGHT_RGB),
            "neutral": (NEUTRAL_FILL, NEUTRAL_EDGE,
                        NEUTRAL_FILL_HOVER, NEUTRAL_EDGE_HOVER),
            "danger": ((42, 22, 24), (112, 42, 46),
                       (220, 38, 38), (220, 38, 38))
        }[kind]

        fill = look[2] if hovered else look[0]
        edge = look[3] if hovered else look[1]

        scale = 4

        big = Image.new("RGB", (w * scale, h * scale), edge)

        d = ImageDraw.Draw(big)

        inset = max(1, int(1.2 * scale))

        d.rounded_rectangle(
            [inset, inset, w * scale - 1 - inset, h * scale - 1 - inset],
            radius=h * scale // 2,
            fill=fill
        )

        pill = big.resize((w, h), Image.LANCZOS)

        mask_big = Image.new("L", (w * scale, h * scale), 0)

        ImageDraw.Draw(mask_big).rounded_rectangle(
            [0, 0, w * scale - 1, h * scale - 1],
            radius=h * scale // 2,
            fill=255
        )

        img.paste(pill, (x1, y1), mask_big.resize((w, h), Image.LANCZOS))

    def _paste_glass(
        self,
        img,
        box,
        accent,
        hovered
    ):
        """Draws a frosted-glass pill straight into `img` (in place):
        the photo behind it is blurred and lightly tinted, with a bright
        rim and a soft sheen along the top edge. Real Tk widgets can
        never be transparent, so the "buttons" are painted into the card
        image itself and hit-tested by hand."""

        x1, y1, x2, y2 = box
        w, h = x2 - x1, y2 - y1

        if w < 4 or h < 4:
            return

        scale = 4

        region = img.crop(box).convert("RGB")

        frosted = region.filter(ImageFilter.GaussianBlur(3))
        # Dimmed enough that white labels stay readable on light photos.
        frosted = ImageEnhance.Brightness(frosted).enhance(
            0.75 if hovered else 0.68
        )

        if hovered:
            tint, amount = accent, 0.55
        else:
            tint, amount = (255, 255, 255), 0.08

        frosted = Image.blend(
            frosted,
            Image.new("RGB", (w, h), tint),
            amount
        )

        sheen = Image.new("L", (1, h))

        for y in range(h):
            sheen.putpixel(
                (0, y),
                int(80 * max(0.0, 1 - y / (h * 0.55)))
            )

        sheen = sheen.resize((w, h))

        frosted = Image.composite(
            Image.new("RGB", (w, h), (255, 255, 255)),
            frosted,
            sheen
        )

        big_mask = Image.new("L", (w * scale, h * scale), 0)

        ImageDraw.Draw(big_mask).rounded_rectangle(
            [0, 0, w * scale - 1, h * scale - 1],
            radius=h * scale // 2,
            fill=255
        )

        mask = big_mask.resize((w, h), Image.LANCZOS)

        img.paste(frosted, (x1, y1), mask)

        ring_big = Image.new("L", (w * scale, h * scale), 0)

        ImageDraw.Draw(ring_big).rounded_rectangle(
            [0, 0, w * scale - 1, h * scale - 1],
            radius=h * scale // 2,
            outline=255,
            width=int(1.5 * scale)
        )

        ring = ring_big.resize((w, h), Image.LANCZOS)
        ring = ring.point(
            lambda v: int(v * (0.9 if hovered else 0.5))
        )

        img.paste(
            Image.new("RGB", (w, h), (255, 255, 255)),
            (x1, y1),
            ring
        )

    def _task_card_canvas(
        self,
        parent,
        task,
        source_image=None,
        card_height=130
    ):
        """One card design for every task: same size, same rounded
        corners, same frosted-glass buttons. With an attached photo the
        photo is the background (cover-fit, dimmed so the text stays
        readable); without one it's a solid dark card. Responsive:
        redraws at the new width on resize."""

        radius = 14
        is_completed = task["status"] == "Completed"
        task_id = task["id"]
        has_photo = source_image is not None

        due_state, due_text, due_color = (
            ("none", "", None)
            if is_completed
            else due_info(task["deadline"])
        )

        card_color = COMPLETED_BG if is_completed else PANEL_2

        canvas = tk.Canvas(
            parent,
            height=card_height,
            bg=PANEL,
            highlightthickness=0,
            bd=0,
            cursor="arrow"
        )

        canvas.pack(
            fill="x"
        )

        if is_completed:

            first_action = {
                "label": "Reopen",
                "command": lambda: self.reopen_and_refresh(task_id),
                "accent": ACCENT_RGB,
                "kind": "neutral"
            }

        else:

            first_action = {
                "label": "Complete",
                "command": lambda: self.complete_and_refresh(task_id),
                "accent": ACCENT_RGB,
                "kind": "primary"
            }

        actions = [
            first_action,
            {
                "label": "Edit",
                "command": lambda: self.edit_task_dialog(task_id),
                "accent": (96, 165, 250),
                "kind": "neutral"
            },
            {
                "label": "Delete",
                "command": lambda: self.delete_task_confirm(task_id),
                "accent": (220, 38, 38),
                "kind": "danger"
            }
        ]

        label_font = tkfont.Font(family="Segoe UI", size=10)
        title_font = tkfont.Font(family="Segoe UI", size=12, weight="bold")
        small_font = tkfont.Font(family="Segoe UI", size=9)

        pill_w = max(
            max(label_font.measure(a["label"]) for a in actions) + 44,
            108
        )
        pill_h = 34
        pill_gap = 8
        pill_margin = 16

        state = {"width": -1, "base": None, "hover": None}

        def fit(text, font, max_width):

            if font.measure(text) <= max_width:
                return text

            while text and font.measure(text + "…") > max_width:
                text = text[:-1]

            return text.rstrip() + "…"

        def pill_rects(width):

            total = (
                pill_h * len(actions)
                + pill_gap * (len(actions) - 1)
            )

            top = (card_height - total) // 2
            x2 = width - pill_margin
            x1 = x2 - pill_w

            return [
                (
                    x1,
                    top + i * (pill_h + pill_gap),
                    x2,
                    top + i * (pill_h + pill_gap) + pill_h
                )
                for i in range(len(actions))
            ]

        def pill_at(x, y):

            if state["base"] is None:
                return None

            for i, (x1, y1, x2, y2) in enumerate(
                pill_rects(state["width"])
            ):

                if x1 <= x <= x2 and y1 <= y <= y2:
                    return i

            return None

        def draw_composite():

            base = state["base"]

            if base is None:
                return

            width = state["width"]
            rects = pill_rects(width)

            img = base.copy()

            for i, rect in enumerate(rects):

                if rect[0] < 0:
                    continue

                if has_photo:

                    self._paste_glass(
                        img,
                        rect,
                        actions[i]["accent"],
                        state["hover"] == i
                    )

                else:

                    self._paste_flat(
                        img,
                        rect,
                        actions[i]["kind"],
                        state["hover"] == i
                    )

            photo = ImageTk.PhotoImage(img)
            canvas.card_photo = photo

            canvas.delete("card_bg", "card_text")

            canvas.create_image(
                0, 0, anchor="nw", image=photo, tags="card_bg"
            )

            # Keep long text from running underneath the buttons.
            max_text_w = max(
                60,
                width - pill_w - pill_margin - 18 - 24
            )

            title = task["title"]

            if is_completed:
                title = "✓ " + title

            canvas.create_text(
                18, 20,
                anchor="nw",
                text=fit(title, title_font, max_text_w),
                font=title_font,
                fill=GREEN if is_completed else "#FFFFFF",
                tags="card_text"
            )

            # Photo cards skip the description — it would sit on top
            # of the busy part of the picture.
            if not has_photo and task["description"]:

                description = " ".join(task["description"].split())

                canvas.create_text(
                    18, 50,
                    anchor="nw",
                    text=fit(description, small_font, max_text_w),
                    font=small_font,
                    fill=MUTED,
                    tags="card_text"
                )

            meta = (
                f"{format_date(task['deadline'])}"
                f"  •  {task['priority']}"
            )

            canvas.create_text(
                18, card_height - 20,
                anchor="sw",
                text=meta,
                font=small_font,
                fill=(
                    "#FFFFFF"
                    if has_photo
                    else priority_color(task["priority"])
                ),
                tags="card_text"
            )

            if due_text:

                canvas.create_text(
                    18 + small_font.measure(meta), card_height - 20,
                    anchor="sw",
                    text="  \u2022  " + due_text,
                    font=small_font,
                    fill=due_color,
                    tags="card_text"
                )

                # Coloured edge: red = overdue, amber = due soon.
                canvas.create_rectangle(
                    0, 16, 4, card_height - 16,
                    fill=due_color,
                    outline="",
                    tags="card_text"
                )

            for i, (x1, y1, x2, y2) in enumerate(rects):

                if has_photo:

                    # A soft dark shadow keeps white labels legible
                    # on light photos without dimming the glass.
                    canvas.create_text(
                        (x1 + x2) / 2 + 1,
                        (y1 + y2) / 2 + 1,
                        text=actions[i]["label"],
                        font=label_font,
                        fill="#000000",
                        tags="card_text"
                    )

                canvas.create_text(
                    (x1 + x2) / 2,
                    (y1 + y2) / 2,
                    text=actions[i]["label"],
                    font=label_font,
                    fill=(
                        "#F87171"
                        if (
                            not has_photo
                            and actions[i]["kind"] == "danger"
                            and state["hover"] != i
                        )
                        else "#FFFFFF"
                    ),
                    tags="card_text"
                )

        def render(event=None):

            width = canvas.winfo_width()

            if width < 40 or width == state["width"]:
                return

            state["width"] = width

            if has_photo:

                src_w, src_h = source_image.size
                target_ratio = width / card_height
                src_ratio = src_w / src_h

                if src_ratio > target_ratio:

                    new_w = max(1, int(src_h * target_ratio))
                    offset = max(0, (src_w - new_w) // 2)
                    box = (offset, 0, offset + new_w, src_h)

                else:

                    new_h = max(1, int(src_w / target_ratio))
                    offset = max(0, (src_h - new_h) // 2)
                    box = (0, offset, src_w, offset + new_h)

                try:

                    cropped = source_image.crop(box).resize(
                        (width, card_height), Image.LANCZOS
                    )

                except Exception:
                    return

                # Dark gradient, stronger toward the bottom where the
                # text sits, so the photo stays visible up top but the
                # text is readable whatever is underneath it.
                gradient = Image.new("L", (1, card_height))

                for y in range(card_height):

                    frac = y / max(1, card_height - 1)

                    gradient.putpixel(
                        (0, y),
                        int(40 + frac * 150)
                    )

                gradient = gradient.resize((width, card_height))

                black = Image.new(
                    "RGB", (width, card_height), (0, 0, 0)
                )

                composited = Image.composite(black, cropped, gradient)

            else:

                composited = Image.new(
                    "RGB", (width, card_height), card_color
                )

                # A faint lift along the top edge, like the glass
                # buttons' sheen, so a solid card isn't completely flat.
                lift = Image.new("L", (1, card_height))

                for y in range(card_height):

                    lift.putpixel(
                        (0, y),
                        int(14 * max(0.0, 1 - y / card_height))
                    )

                lift = lift.resize((width, card_height))

                composited = Image.composite(
                    Image.new(
                        "RGB", (width, card_height), (255, 255, 255)
                    ),
                    composited,
                    lift
                )

            mask = Image.new("L", (width, card_height), 0)

            ImageDraw.Draw(mask).rounded_rectangle(
                [0, 0, width - 1, card_height - 1],
                radius=radius,
                fill=255
            )

            # Corners show the surrounding panel color, so they blend
            # in instead of leaving a visible dark square.
            base = Image.new("RGBA", (width, card_height), PANEL)
            base.paste(composited, (0, 0), mask)

            state["base"] = base

            draw_composite()

        def on_motion(event):

            hovered = pill_at(event.x, event.y)

            if hovered != state["hover"]:

                state["hover"] = hovered
                draw_composite()

        def on_leave(event):

            if state["hover"] is not None:

                state["hover"] = None
                draw_composite()

        def on_click(event):

            hit = pill_at(event.x, event.y)

            if hit is not None:
                actions[hit]["command"]()

        canvas.bind("<Configure>", render)
        canvas.bind("<Motion>", on_motion)
        canvas.bind("<Leave>", on_leave)
        canvas.bind("<Button-1>", on_click)

    def edit_task_dialog(self, task_id):

        task = self.db.get_task(task_id)

        if task is not None:
            self.new_task_dialog(task)

    def new_task_dialog(self, task=None):
        """Create a task, or edit one when `task` (a row) is given."""

        editing = task is not None

        window = tk.Toplevel(
            self
        )

        window.title(
            "Edit task" if editing else "New task"
        )

        self.center_window(window, 700, 880)

        window.configure(
            bg=BG
        )

        window.transient(
            self
        )

        window.grab_set()

        tk.Label(
            window,
            text="Edit task" if editing else "Create task",
            bg=BG,
            fg=TEXT,
            font=("Segoe UI", 19, "bold")
        ).pack(
            anchor="w",
            padx=28,
            pady=(25, 20)
        )

        # Buttons are pinned to the bottom FIRST, before the scrollable
        # form area claims the remaining space — this guarantees they
        # stay visible and reachable no matter how tall the form ends
        # up being or how short the screen is.
        buttons = tk.Frame(
            window,
            bg=BG
        )

        buttons.pack(
            side="bottom",
            fill="x",
            padx=28,
            pady=(14, 22)
        )

        # A thin line above the buttons, so they read as the footer
        # of the dialog and not as part of the form.
        tk.Frame(
            window,
            bg=BORDER,
            height=1
        ).pack(
            side="bottom",
            fill="x"
        )

        save_ref = {}

        save_button = self.make_button(
            buttons,
            "Save changes" if editing else "Create task",
            lambda: save_ref["fn"](),
            width=13
        )

        save_button.configure(selected=True)

        save_button.pack(
            side="right"
        )

        self.make_button(
            buttons,
            "Cancel",
            window.destroy,
            width=9
        ).pack(
            side="right",
            padx=(0, 10)
        )

        form_outer = tk.Frame(
            window,
            bg=BG
        )

        form_outer.pack(
            fill="both",
            expand=True,
            padx=28
        )

        form_canvas = tk.Canvas(
            form_outer,
            bg=BG,
            highlightthickness=0
        )

        form = tk.Frame(
            form_canvas,
            bg=BG
        )

        form.bind(
            "<Configure>",
            lambda event:
                form_canvas.configure(
                    scrollregion=form_canvas.bbox("all")
                )
        )

        form_window = form_canvas.create_window(
            (0, 0),
            window=form,
            anchor="nw"
        )

        form_canvas.bind(
            "<Configure>",
            lambda event:
                form_canvas.itemconfigure(
                    form_window,
                    width=event.width
                )
        )

        form_canvas.pack(
            side="left",
            fill="both",
            expand=True
        )

        # No visible scrollbar — the form fits at normal sizes. The
        # mouse wheel still scrolls it on a very short screen.
        self._bind_mousewheel(form_canvas)

        tk.Label(
            form,
            text="Title",
            bg=BG,
            fg=MUTED
        ).pack(
            anchor="w"
        )

        title = self.make_entry(
            form
        )

        title.pack(
            fill="x",
            ipady=8,
            pady=(5, 12)
        )

        if editing:
            title.insert(0, task["title"])

        tk.Label(
            form,
            text="Description",
            bg=BG,
            fg=MUTED
        ).pack(
            anchor="w"
        )

        description = tk.Text(
            form,
            height=3,
            bg=PANEL_2,
            fg=TEXT,
            insertbackground=TEXT,
            relief="flat",
            font=("Segoe UI", 10)
        )

        description.pack(
            fill="x",
            pady=(5, 12)
        )

        if editing:
            description.insert("1.0", task["description"] or "")

        tk.Label(
            form,
            text="Deadline",
            bg=BG,
            fg=MUTED
        ).pack(
            anchor="w"
        )

        deadline_picker = self.build_deadline_picker(
            form,
            (
                task["deadline"]
                if editing
                else (
                    datetime.now() + timedelta(days=1)
                ).replace(
                    hour=DeadlineState.DEFAULT_HOUR,
                    minute=0,
                    second=0
                ).strftime("%Y-%m-%d %H:%M:%S")
            )
        )

        deadline_picker["frame"].pack(
            fill="x",
            pady=(6, 14)
        )

        tk.Label(
            form,
            text="Priority",
            bg=BG,
            fg=MUTED
        ).pack(
            anchor="w"
        )

        priority_row, priority_state = self.build_priority_picker(
            form,
            initial=task["priority"] if editing else "Medium",
            button_width=8
        )

        priority_row.pack(
            fill="x",
            pady=(5, 12)
        )

        # --- Custom reminder time: a toggle that slides the field open ---
        reveal = tk.Frame(
            form,
            bg=BG,
            height=1
        )

        reveal.pack(
            fill="x"
        )

        # The reveal frame is clipped to its (animated) height, so the
        # content inside appears to slide out as it grows.
        reveal.pack_propagate(False)

        reveal_inner = tk.Frame(
            reveal,
            bg=BG
        )

        reveal_inner.pack(
            fill="x",
            anchor="n"
        )

        tk.Label(
            reveal_inner,
            text="Remind me every  (minutes)",
            bg=BG,
            fg=MUTED
        ).pack(
            anchor="w",
            pady=(2, 0)
        )

        remind_entry = self.make_entry(
            reveal_inner
        )

        remind_entry.pack(
            fill="x",
            ipady=8,
            pady=(5, 4)
        )

        tk.Label(
            reveal_inner,
            text=(
                "Overrides the default — Low "
                f"{self._fmt_minutes(self.reminder_default('Low'))}"
                " · Medium "
                f"{self._fmt_minutes(self.reminder_default('Medium'))}"
                " · High "
                f"{self._fmt_minutes(self.reminder_default('High'))}"
            ),
            bg=BG,
            fg=MUTED_2,
            font=("Segoe UI", 8)
        ).pack(
            anchor="w",
            pady=(0, 12)
        )

        custom_state = {"on": False}
        reveal_anim = {"job": None, "height": 1}

        def animate_reveal(target, duration=260, steps=16):

            if reveal_anim["job"] is not None:

                try:
                    window.after_cancel(reveal_anim["job"])
                except Exception:
                    pass

                reveal_anim["job"] = None

            start = reveal_anim["height"]
            delta = target - start

            if delta == 0:
                return

            frame = {"i": 0}

            def step():

                frame["i"] += 1

                t = frame["i"] / steps

                # Ease-out cubic: moves fast at first, then settles.
                eased = 1 - (1 - t) ** 3

                height = max(1, int(round(start + delta * eased)))
                reveal_anim["height"] = height

                try:
                    reveal.configure(height=height)
                except Exception:
                    # Dialog was closed mid-animation.
                    reveal_anim["job"] = None
                    return

                if frame["i"] < steps:

                    reveal_anim["job"] = window.after(
                        max(1, duration // steps),
                        step
                    )

                else:

                    reveal_anim["job"] = None

            step()

        def toggle_custom():

            custom_state["on"] = not custom_state["on"]

            custom_button.configure(selected=custom_state["on"])

            if custom_state["on"]:

                form.update_idletasks()

                animate_reveal(reveal_inner.winfo_reqheight())

                window.after(280, remind_entry.focus_set)

            else:

                animate_reveal(1)

        custom_button = RoundedButton(
            self,
            priority_row,
            "Custom",
            command=toggle_custom,
            width_chars=8,
            active_color=PURPLE_HOVER
        )

        custom_button.pack(
            side="left",
            padx=(14, 0)
        )

        if editing and int(task["remind_minutes"] or 0) > 0:

            remind_entry.insert(0, str(int(task["remind_minutes"])))

            window.after(150, toggle_custom)

        selected_path = tk.StringVar()
        selected_name = tk.StringVar(value="No image attached")

        def show_name(*_):

            path = selected_path.get()

            if not path:
                selected_name.set("No image attached")
                return

            # Stored as "<timestamp>_<original name>" — show only the
            # original name, trimmed to fit.
            name = re.sub(r"^\d+_", "", Path(path).name)

            if len(name) > 34:
                name = name[:33] + "…"

            selected_name.set(name)

        selected_path.trace_add("write", show_name)

        if editing and task["image_path"]:
            selected_path.set(task["image_path"])

        tk.Label(
            form,
            text="Reference image  (optional)",
            bg=BG,
            fg=MUTED
        ).pack(
            anchor="w"
        )

        attachment_row = tk.Frame(
            form,
            bg=BG
        )

        attachment_row.pack(
            fill="x",
            pady=(5, 12)
        )

        self.make_button(
            attachment_row,
            "Attach image",
            lambda:
                self.select_attachment(
                    selected_path
                )
        ).pack(
            side="left"
        )

        tk.Label(
            attachment_row,
            textvariable=selected_name,
            bg=BG,
            fg=MUTED_2,
            font=("Segoe UI", 9)
        ).pack(
            side="left",
            padx=12
        )

        def save():

            task_title = (
                title.get().strip()
            )

            if not task_title:

                messagebox.showwarning(
                    "Task",
                    "Enter a task title.",
                    parent=window
                )

                return

            task_description = (
                description
                .get("1.0", "end-1c")
                .strip()
            )

            remind_text = (
                remind_entry.get().strip()
                if custom_state["on"]
                else ""
            )
            remind_minutes = 0

            if remind_text:

                try:
                    remind_minutes = int(remind_text)
                except ValueError:
                    remind_minutes = 0

                if remind_minutes < 1:

                    messagebox.showwarning(
                        "Task",
                        "Reminder time must be a whole number "
                        "of minutes (1 or more).",
                        parent=window
                    )

                    return

            if editing:

                self.db.update_task(
                    task["id"],
                    task_title,
                    task_description,
                    deadline_picker["get"](),
                    priority_state["value"],
                    selected_path.get(),
                    remind_minutes
                )

            else:

                self.db.add_task(
                    task_title,
                    task_description,
                    deadline_picker["get"](),
                    priority_state["value"],
                    selected_path.get(),
                    remind_minutes
                )

            window.destroy()

            self.show_page(
                self.current_page
            )

        save_ref["fn"] = save

        title.focus_set()

    def build_deadline_picker(self, parent, initial):
        """Month calendar + quick buttons + a 12-hour time stepper,
        drawn in the app's own style. Returns {"frame", "get"}; get()
        gives 'YYYY-MM-DD HH:MM:SS', or '' for no deadline."""

        state = DeadlineState(initial)

        frame = tk.Frame(parent, bg=BG)

        CW, CELL, ROW, TOP, HEAD = 252, 36, 31, 54, 34

        CH = TOP + ROW * 6 + 6

        cal = tk.Canvas(
            frame,
            width=CW,
            height=CH,
            bg=PANEL_2,
            highlightthickness=1,
            highlightbackground=BORDER,
            bd=0
        )

        cal.pack(side="left", anchor="n")

        side_area = tk.Frame(frame, bg=BG)

        side_area.pack(
            side="left", anchor="n", padx=(20, 0), fill="both", expand=True
        )

        # The date, quick buttons and time sit in the horizontal middle
        # of the space beside the calendar.
        side = tk.Frame(side_area, bg=BG)

        side.place(relx=0.5, y=0, anchor="n")

        pics = {}

        if HAS_PIL:

            for kind in ("fill", "ring"):

                big = 30 * 6

                img = Image.new("RGBA", (big, big), (0, 0, 0, 0))

                d = ImageDraw.Draw(img)

                if kind == "fill":
                    d.ellipse([0, 0, big - 1, big - 1], fill=PURPLE_HOVER)
                else:
                    d.ellipse(
                        [3, 3, big - 4, big - 4],
                        outline=PURPLE_HOVER,
                        width=9
                    )

                pics[kind] = ImageTk.PhotoImage(
                    img.resize((30, 30), Image.LANCZOS)
                )

        import calendar as _calendar

        day_label = tk.Label(
            side,
            text="",
            bg=BG,
            fg=TEXT,
            font=("Segoe UI", 13, "bold"),
            anchor="w"
        )

        day_label.pack(anchor="center")

        time_label = tk.Label(
            side,
            text="",
            bg=BG,
            fg=MUTED,
            font=("Segoe UI", 10),
            anchor="w"
        )

        time_label.pack(anchor="center", pady=(0, 12))

        hour_text = tk.StringVar()
        minute_text = tk.StringVar()

        def redraw():

            cal.delete("all")

            cal.create_text(
                CW / 2, HEAD / 2 + 2,
                text=f"{_calendar.month_name[state.month]} {state.year}",
                fill=TEXT,
                font=("Segoe UI", 11, "bold")
            )

            cal.create_text(
                22, HEAD / 2 + 1,
                text="\u2039",
                fill=MUTED,
                font=("Segoe UI", 18)
            )

            cal.create_text(
                CW - 22, HEAD / 2 + 1,
                text="\u203a",
                fill=MUTED,
                font=("Segoe UI", 18)
            )

            for i, letter in enumerate("MTWTFSS"):

                cal.create_text(
                    i * CELL + CELL / 2, 44,
                    text=letter,
                    fill=MUTED_2,
                    font=("Segoe UI", 8, "bold")
                )

            chosen = state.sel.date() if state.sel else None

            for r, week in enumerate(state.weeks()):

                for c, number in enumerate(week):

                    if not number:
                        continue

                    day = date(state.year, state.month, number)

                    cx = c * CELL + CELL / 2
                    cy = TOP + r * ROW + ROW / 2

                    if day == chosen:

                        if "fill" in pics:
                            cal.create_image(cx, cy, image=pics["fill"])

                        color, weight = "#FFFFFF", "bold"

                    elif day == state.today:

                        if "ring" in pics:
                            cal.create_image(cx, cy, image=pics["ring"])

                        color, weight = PURPLE_HOVER, "bold"

                    else:

                        color = TEXT if day >= state.today else MUTED_2
                        weight = "normal"

                    cal.create_text(
                        cx, cy,
                        text=str(number),
                        fill=color,
                        font=("Segoe UI", 10, weight)
                    )

            line1, line2 = state.readout()

            day_label.configure(text=line1)
            time_label.configure(text=line2)

            hour_text.set(f"{state.hour12():02d}")
            minute_text.set(f"{state.minute():02d}")

            try:

                ampm_button.configure(text=state.ampm())

            except Exception:
                pass

        def on_click(event):

            if event.y < HEAD:

                if event.x < 50:
                    state.shift_month(-1)
                elif event.x > CW - 50:
                    state.shift_month(1)

                redraw()

                return

            r = (event.y - TOP) // ROW
            c = event.x // CELL

            weeks = state.weeks()

            if 0 <= r < len(weeks) and 0 <= c < 7 and weeks[r][c]:

                state.set_date(
                    date(state.year, state.month, weeks[r][c])
                )

                redraw()

        cal.bind("<Button-1>", on_click)

        def quick(days):

            def go():

                state.set_date(state.today + timedelta(days=days))

                redraw()

            return go

        def clear():

            state.clear()

            redraw()

        chips = tk.Frame(side, bg=BG)

        chips.pack(fill="x")

        row1 = tk.Frame(chips, bg=BG)

        row1.pack(anchor="center")

        self.make_button(row1, "Today", quick(0), width=9).pack(side="left")

        self.make_button(
            row1, "Tomorrow", quick(1), width=9
        ).pack(side="left", padx=(8, 0))

        row2 = tk.Frame(chips, bg=BG)

        row2.pack(anchor="center", pady=(8, 0))

        self.make_button(
            row2, "Next week", quick(7), width=9
        ).pack(side="left")

        self.make_button(
            row2, "No deadline", clear, width=9
        ).pack(side="left", padx=(8, 0))

        tk.Label(
            side,
            text="Time",
            bg=BG,
            fg=MUTED
        ).pack(anchor="center", pady=(16, 6))

        def stepper(parent, text_var, down, up):

            box = tk.Frame(parent, bg=BG)

            self.make_button(
                box, "\u2212", lambda: (down(), redraw()), width=2
            ).pack(side="left")

            tk.Label(
                box,
                textvariable=text_var,
                bg=BG,
                fg=TEXT,
                width=3,
                font=("Segoe UI", 12, "bold")
            ).pack(side="left")

            self.make_button(
                box, "+", lambda: (up(), redraw()), width=2
            ).pack(side="left")

            return box

        time_row = tk.Frame(side, bg=BG)

        time_row.pack(anchor="w")

        stepper(
            time_row,
            hour_text,
            lambda: state.bump_hour(-1),
            lambda: state.bump_hour(1)
        ).pack(side="left")

        tk.Label(
            time_row,
            text=":",
            bg=BG,
            fg=MUTED,
            font=("Segoe UI", 13, "bold")
        ).pack(side="left", padx=4)

        stepper(
            time_row,
            minute_text,
            lambda: state.bump_minute(-5),
            lambda: state.bump_minute(5)
        ).pack(side="left")

        ampm_button = self.make_button(
            time_row,
            state.ampm(),
            lambda: (state.toggle_ampm(), redraw()),
            width=4
        )

        ampm_button.pack(side="left", padx=(10, 0))

        redraw()

        return {"frame": frame, "get": state.value}

    def select_attachment(
        self,
        variable
    ):

        path = filedialog.askopenfilename(
            title="Choose reference image",
            filetypes=[
                (
                    "Images",
                    "*.png *.jpg *.jpeg *.webp *.gif"
                ),
                (
                    "All files",
                    "*.*"
                )
            ]
        )

        if not path:
            return

        source = Path(
            path
        )

        safe_name = re.sub(
            r"[^A-Za-z0-9._-]",
            "_",
            source.name
        )

        destination = (
            ATTACH_DIR /
            f"{int(datetime.now().timestamp())}_{safe_name}"
        )

        try:

            shutil.copy2(
                source,
                destination
            )

            variable.set(
                str(destination)
            )

        except Exception as exc:

            messagebox.showerror(
                "Attachment",
                str(exc),
                parent=self
            )

    def complete_and_refresh(
        self,
        task_id
    ):

        self.db.complete_task(
            task_id
        )

        self.show_page(
            self.current_page
        )

    def reopen_and_refresh(
        self,
        task_id
    ):

        self.db.reopen_task(
            task_id
        )

        self.show_page(
            self.current_page
        )

    def delete_task_confirm(
        self,
        task_id
    ):

        if messagebox.askyesno(
            "Delete task",
            "Delete this task?",
            parent=self
        ):

            self.db.delete_task(
                task_id
            )

            self.show_page(
                "Tasks"
            )

    def open_file(
        self,
        path
    ):

        if not Path(path).exists():

            messagebox.showerror(
                "File",
                "The file no longer exists."
            )

            return

        try:

            os.startfile(
                path
            )

        except Exception:

            try:

                subprocess.Popen(
                    ["xdg-open", path]
                )

            except Exception as exc:

                messagebox.showerror(
                    "File",
                    str(exc)
                )

    # ========================================================
    # GOALS
    # ========================================================

    def build_goals(self):

        self.page_header(
            "Goals",
            "Keep your long-term direction visible."
        )

        self.make_button(
            self.page,
            "+ New goal",
            self.new_goal_dialog
        ).pack(
            anchor="w",
            pady=(0, 16)
        )

        self._build_paged_grid(
            self.db.get_goals(False),
            self._goal_card_canvas,
            "No goals yet.",
            "goals_page"
        )

    def _build_paged_grid(
        self,
        items,
        card_fn,
        empty_message,
        page_attr
    ):
        """Same 3-column, fill-the-page, arrows-only-on-overflow layout
        the Tasks page uses. card_fn(cell, item, card_height) draws one
        card; page_attr names the attribute remembering the page."""

        outer = tk.Frame(
            self.page,
            bg=PANEL,
            highlightthickness=1,
            highlightbackground=BORDER
        )

        outer.pack(fill="both", expand=True)

        pager = tk.Frame(outer, bg=PANEL, height=52)
        pager.pack(side="bottom", fill="x")
        pager.pack_propagate(False)

        pager_inner = tk.Frame(pager, bg=PANEL)
        pager_inner.pack(expand=True)

        area = tk.Frame(outer, bg=PANEL)
        area.pack(fill="both", expand=True)
        area.pack_propagate(False)

        holder = tk.Frame(area, bg=PANEL)
        holder.pack(fill="both", expand=True, padx=10, pady=8)

        columns = 3

        for column in range(columns):

            holder.grid_columnconfigure(
                column,
                weight=1,
                uniform="gridcol"
            )

        max_rows = 4
        min_card_height = 130
        max_card_height = 190
        cell_padding = 16

        view = {
            "rows": None,
            "card_h": min_card_height,
            "area_h": 0,
            "job": None
        }

        def go_page(delta):

            setattr(self, page_attr, getattr(self, page_attr, 0) + delta)
            render()

        def render():

            page_size = columns * (view["rows"] or 1)
            pages = max(1, math.ceil(len(items) / page_size))

            page = max(0, min(getattr(self, page_attr, 0), pages - 1))
            setattr(self, page_attr, page)

            for widget in holder.winfo_children():
                widget.destroy()

            if not items:

                tk.Label(
                    holder,
                    text=empty_message,
                    bg=PANEL,
                    fg=MUTED_2,
                    font=("Segoe UI", 10)
                ).grid(
                    row=0,
                    column=0,
                    columnspan=columns,
                    sticky="w",
                    padx=12,
                    pady=12
                )

            start = page * page_size

            for index, item in enumerate(items[start:start + page_size]):

                row, column = divmod(index, columns)

                cell = tk.Frame(holder, bg=PANEL)

                cell.grid(
                    row=row,
                    column=column,
                    sticky="new",
                    padx=8,
                    pady=8
                )

                card_fn(cell, item, view["card_h"])

            for widget in pager_inner.winfo_children():
                widget.destroy()

            if pages > 1:

                def arrow(text, delta, enabled):

                    button = self.make_button(
                        pager_inner,
                        text,
                        lambda: go_page(delta),
                        width=3
                    )

                    if enabled:

                        button.pack(side="left", padx=8)

                    else:

                        spacer_width = int(button.canvas.cget("width"))
                        button.destroy()

                        tk.Frame(
                            pager_inner,
                            bg=PANEL,
                            width=spacer_width,
                            height=1
                        ).pack(side="left", padx=8)

                arrow("‹", -1, page > 0)

                tk.Label(
                    pager_inner,
                    text=f"Page {page + 1} of {pages}",
                    bg=PANEL,
                    fg=MUTED,
                    font=("Segoe UI", 9)
                ).pack(side="left", padx=10)

                arrow("›", 1, page < pages - 1)

        def apply_layout():

            view["job"] = None

            try:

                if not area.winfo_exists():
                    return

            except Exception:
                return

            usable = view["area_h"] - cell_padding

            rows = max(
                1,
                min(
                    max_rows,
                    usable // (min_card_height + cell_padding)
                )
            )

            card_h = max(
                min_card_height,
                min(
                    max_card_height,
                    usable // rows - cell_padding
                )
            )

            if rows != view["rows"] or card_h != view["card_h"]:

                view["rows"] = rows
                view["card_h"] = card_h
                render()

        def on_area_resize(event):

            view["area_h"] = event.height

            if view["rows"] is None:

                apply_layout()

            else:

                if view["job"] is not None:

                    try:
                        area.after_cancel(view["job"])
                    except Exception:
                        pass

                view["job"] = area.after(120, apply_layout)

        area.bind("<Configure>", on_area_resize)

    def _goal_image(self, goal):
        """The goal's picture as an RGB image, or None."""

        if not HAS_PIL:
            return None

        try:

            path = goal["image_path"]

            if path and Path(path).exists():
                return Image.open(path).convert("RGB")

        except Exception:
            pass

        return None

    def _goal_card_plain(
        self,
        parent,
        goal
    ):
        """Fallback if Pillow isn't installed."""

        card = tk.Frame(
            parent,
            bg=PANEL_2,
            highlightthickness=1,
            highlightbackground=BORDER
        )

        card.pack(fill="x")

        tk.Label(
            card,
            text=goal["title"],
            bg=PANEL_2,
            fg=TEXT if goal["active"] else MUTED,
            font=("Segoe UI", 11, "bold")
        ).pack(anchor="w", padx=14, pady=(12, 2))

        tk.Label(
            card,
            text="Active" if goal["active"] else "Paused",
            bg=PANEL_2,
            fg=PURPLE_HOVER if goal["active"] else MUTED_2,
            font=("Segoe UI", 8)
        ).pack(anchor="w", padx=14)

        row = tk.Frame(card, bg=PANEL_2)
        row.pack(anchor="e", padx=12, pady=10)

        self.make_button(
            row,
            "Pause" if goal["active"] else "Resume",
            lambda gid=goal["id"]: self.toggle_goal_refresh(gid),
            width=8
        ).pack(side="left", padx=4)

        self.make_button(
            row,
            "Edit",
            lambda gid=goal["id"]: self.edit_goal_dialog(gid),
            width=8
        ).pack(side="left", padx=4)

        self.make_button(
            row,
            "Delete",
            lambda gid=goal["id"]: self.delete_goal_confirm(gid),
            width=8,
            active=DANGER_HOVER
        ).pack(side="left", padx=4)

    def _goal_card_canvas(
        self,
        parent,
        goal,
        card_height=130
    ):
        """Goal card in the same design as the task cards: rounded,
        solid dark (darker still when paused) with flat buttons, or the
        goal's picture as the background with frosted-glass buttons."""

        if not HAS_PIL:
            self._goal_card_plain(parent, goal)
            return

        radius = 14
        goal_id = goal["id"]
        active = bool(goal["active"])
        card_color = PANEL_2 if active else DEEP
        source_image = self._goal_image(goal)
        has_photo = source_image is not None

        canvas = tk.Canvas(
            parent,
            height=card_height,
            bg=PANEL,
            highlightthickness=0,
            bd=0,
            cursor="arrow"
        )

        canvas.pack(fill="x")

        actions = [
            {
                "label": "Pause" if active else "Resume",
                "command": lambda: self.toggle_goal_refresh(goal_id),
                "accent": ACCENT_RGB,
                "kind": "neutral" if active else "primary"
            },
            {
                "label": "Edit",
                "command": lambda: self.edit_goal_dialog(goal_id),
                "accent": (96, 165, 250),
                "kind": "neutral"
            },
            {
                "label": "Delete",
                "command": lambda: self.delete_goal_confirm(goal_id),
                "accent": (220, 38, 38),
                "kind": "danger"
            }
        ]

        label_font = tkfont.Font(family="Segoe UI", size=10)
        title_font = tkfont.Font(family="Segoe UI", size=12, weight="bold")
        small_font = tkfont.Font(family="Segoe UI", size=9)

        pill_w = max(
            max(label_font.measure(a["label"]) for a in actions) + 44,
            108
        )
        pill_h = 34
        pill_gap = 8
        pill_margin = 16

        state = {"width": -1, "base": None, "hover": None}

        def fit(text, font, max_width):

            if font.measure(text) <= max_width:
                return text

            while text and font.measure(text + "…") > max_width:
                text = text[:-1]

            return text.rstrip() + "…"

        def pill_rects(width):

            total = (
                pill_h * len(actions)
                + pill_gap * (len(actions) - 1)
            )

            top = (card_height - total) // 2
            x2 = width - pill_margin
            x1 = x2 - pill_w

            return [
                (
                    x1,
                    top + i * (pill_h + pill_gap),
                    x2,
                    top + i * (pill_h + pill_gap) + pill_h
                )
                for i in range(len(actions))
            ]

        def pill_at(x, y):

            if state["base"] is None:
                return None

            for i, (x1, y1, x2, y2) in enumerate(
                pill_rects(state["width"])
            ):

                if x1 <= x <= x2 and y1 <= y <= y2:
                    return i

            return None

        def draw_composite():

            base = state["base"]

            if base is None:
                return

            width = state["width"]
            rects = pill_rects(width)

            img = base.copy()

            for i, rect in enumerate(rects):

                if rect[0] < 0:
                    continue

                if has_photo:

                    self._paste_glass(
                        img,
                        rect,
                        actions[i]["accent"],
                        state["hover"] == i
                    )

                else:

                    self._paste_flat(
                        img,
                        rect,
                        actions[i]["kind"],
                        state["hover"] == i
                    )

            photo = ImageTk.PhotoImage(img)
            canvas.card_photo = photo

            canvas.delete("card_bg", "card_text")

            canvas.create_image(
                0, 0, anchor="nw", image=photo, tags="card_bg"
            )

            max_text_w = max(
                60,
                width - pill_w - pill_margin - 18 - 24
            )

            canvas.create_text(
                18, 20,
                anchor="nw",
                text=fit(goal["title"], title_font, max_text_w),
                font=title_font,
                fill=(
                    "#FFFFFF" if has_photo
                    else (TEXT if active else MUTED)
                ),
                tags="card_text"
            )

            # Photo cards skip the description, like task cards do.
            if not has_photo and goal["description"]:

                description = " ".join(goal["description"].split())

                canvas.create_text(
                    18, 50,
                    anchor="nw",
                    text=fit(description, small_font, max_text_w),
                    font=small_font,
                    fill=MUTED,
                    tags="card_text"
                )

            canvas.create_text(
                18, card_height - 20,
                anchor="sw",
                text=("●  Active" if active else "●  Paused"),
                font=small_font,
                fill=(
                    "#FFFFFF" if has_photo
                    else (PURPLE_HOVER if active else MUTED_2)
                ),
                tags="card_text"
            )

            for i, (x1, y1, x2, y2) in enumerate(rects):

                if has_photo:

                    # A soft dark shadow keeps white labels legible
                    # on light photos without dimming the glass.
                    canvas.create_text(
                        (x1 + x2) / 2 + 1,
                        (y1 + y2) / 2 + 1,
                        text=actions[i]["label"],
                        font=label_font,
                        fill="#000000",
                        tags="card_text"
                    )

                canvas.create_text(
                    (x1 + x2) / 2,
                    (y1 + y2) / 2,
                    text=actions[i]["label"],
                    font=label_font,
                    fill=(
                        "#F87171"
                        if (
                            not has_photo
                            and actions[i]["kind"] == "danger"
                            and state["hover"] != i
                        )
                        else "#FFFFFF"
                    ),
                    tags="card_text"
                )

        def render(event=None):

            width = canvas.winfo_width()

            if width < 40 or width == state["width"]:
                return

            state["width"] = width

            if has_photo:

                src_w, src_h = source_image.size
                target_ratio = width / card_height
                src_ratio = src_w / src_h

                if src_ratio > target_ratio:

                    new_w = max(1, int(src_h * target_ratio))
                    offset = max(0, (src_w - new_w) // 2)
                    box = (offset, 0, offset + new_w, src_h)

                else:

                    new_h = max(1, int(src_w / target_ratio))
                    offset = max(0, (src_h - new_h) // 2)
                    box = (0, offset, src_w, offset + new_h)

                try:

                    cropped = source_image.crop(box).resize(
                        (width, card_height), Image.LANCZOS
                    )

                except Exception:
                    return

                # Darker toward the bottom so the text stays readable;
                # a little darker overall when the goal is paused.
                extra = 0 if active else 45
                gradient = Image.new("L", (1, card_height))

                for y in range(card_height):

                    frac = y / max(1, card_height - 1)

                    gradient.putpixel(
                        (0, y),
                        min(235, int(40 + frac * 150) + extra)
                    )

                gradient = gradient.resize((width, card_height))

                black = Image.new(
                    "RGB", (width, card_height), (0, 0, 0)
                )

                composited = Image.composite(black, cropped, gradient)

            else:

                composited = Image.new(
                    "RGB", (width, card_height), card_color
                )

                lift = Image.new("L", (1, card_height))

                for y in range(card_height):

                    lift.putpixel(
                        (0, y),
                        int(14 * max(0.0, 1 - y / card_height))
                    )

                lift = lift.resize((width, card_height))

                composited = Image.composite(
                    Image.new("RGB", (width, card_height), (255, 255, 255)),
                    composited,
                    lift
                )

            mask = Image.new("L", (width, card_height), 0)

            ImageDraw.Draw(mask).rounded_rectangle(
                [0, 0, width - 1, card_height - 1],
                radius=radius,
                fill=255
            )

            base = Image.new("RGBA", (width, card_height), PANEL)
            base.paste(composited, (0, 0), mask)

            state["base"] = base

            draw_composite()

        def on_motion(event):

            hovered = pill_at(event.x, event.y)

            if hovered != state["hover"]:

                state["hover"] = hovered
                draw_composite()

        def on_leave(event):

            if state["hover"] is not None:

                state["hover"] = None
                draw_composite()

        def on_click(event):

            hit = pill_at(event.x, event.y)

            if hit is not None:
                actions[hit]["command"]()

        canvas.bind("<Configure>", render)
        canvas.bind("<Motion>", on_motion)
        canvas.bind("<Leave>", on_leave)
        canvas.bind("<Button-1>", on_click)

    def edit_goal_dialog(self, goal_id):

        goal = self.db.get_goal(goal_id)

        if goal is not None:
            self.new_goal_dialog(goal)

    def new_goal_dialog(self, goal=None):
        """Create a goal, or edit one when `goal` (a row) is given."""

        editing = goal is not None

        window = tk.Toplevel(self)

        window.title("Edit goal" if editing else "New goal")

        self.center_window(window, 560, 500)

        window.configure(bg=BG)

        window.transient(self)

        window.grab_set()

        tk.Label(
            window,
            text="Edit goal" if editing else "Create goal",
            bg=BG,
            fg=TEXT,
            font=("Segoe UI", 19, "bold")
        ).pack(
            anchor="w",
            padx=28,
            pady=(25, 18)
        )

        # Footer first, so it stays pinned at the bottom.
        buttons = tk.Frame(window, bg=BG)

        buttons.pack(
            side="bottom",
            fill="x",
            padx=28,
            pady=(14, 22)
        )

        tk.Frame(
            window,
            bg=BORDER,
            height=1
        ).pack(
            side="bottom",
            fill="x"
        )

        save_ref = {}

        save_button = self.make_button(
            buttons,
            "Save changes" if editing else "Create goal",
            lambda: save_ref["fn"](),
            width=13
        )

        save_button.configure(selected=True)
        save_button.pack(side="right")

        self.make_button(
            buttons,
            "Cancel",
            window.destroy,
            width=9
        ).pack(
            side="right",
            padx=(0, 10)
        )

        form = tk.Frame(window, bg=BG)

        form.pack(
            fill="both",
            expand=True,
            padx=28
        )

        tk.Label(
            form,
            text="Title",
            bg=BG,
            fg=MUTED
        ).pack(anchor="w")

        entry = self.make_entry(form)

        entry.pack(
            fill="x",
            ipady=8,
            pady=(5, 12)
        )

        if editing:
            entry.insert(0, goal["title"])

        tk.Label(
            form,
            text="Description  (optional)",
            bg=BG,
            fg=MUTED
        ).pack(anchor="w")

        description = tk.Text(
            form,
            height=4,
            bg=PANEL_2,
            fg=TEXT,
            insertbackground=TEXT,
            relief="flat",
            font=("Segoe UI", 10)
        )

        description.pack(
            fill="x",
            pady=(5, 12)
        )

        if editing:
            description.insert("1.0", goal["description"] or "")

        selected_path = tk.StringVar(value="")
        selected_name = tk.StringVar(value="No image selected")

        def show_name(*args):

            path = selected_path.get()

            if not path:
                selected_name.set("No image selected")
                return

            name = re.sub(r"^\d+_", "", Path(path).name)

            if len(name) > 34:
                name = name[:33] + "…"

            selected_name.set(name)

        selected_path.trace_add("write", show_name)

        if editing and goal["image_path"]:
            selected_path.set(goal["image_path"])

        tk.Label(
            form,
            text="Image  (optional)",
            bg=BG,
            fg=MUTED
        ).pack(anchor="w")

        attachment_row = tk.Frame(form, bg=BG)

        attachment_row.pack(
            fill="x",
            pady=(5, 12)
        )

        self.make_button(
            attachment_row,
            "Attach image",
            lambda: self.select_attachment(selected_path)
        ).pack(side="left")

        self.make_button(
            attachment_row,
            "Remove",
            lambda: selected_path.set(""),
            width=9
        ).pack(side="left", padx=(8, 0))

        tk.Label(
            attachment_row,
            textvariable=selected_name,
            bg=BG,
            fg=MUTED_2,
            font=("Segoe UI", 9)
        ).pack(
            side="left",
            padx=12
        )

        def save():

            value = entry.get().strip()

            if not value:

                messagebox.showwarning(
                    "Goal",
                    "Enter a goal title.",
                    parent=window
                )

                return

            text = description.get("1.0", "end-1c").strip()

            if editing:

                self.db.update_goal(
                    goal["id"],
                    value,
                    text,
                    selected_path.get()
                )

            else:

                self.db.add_goal(
                    value,
                    text,
                    selected_path.get()
                )

            window.destroy()

            self.show_page(self.current_page)

        save_ref["fn"] = save

        entry.focus_set()

    def toggle_goal_refresh(
        self,
        goal_id
    ):

        self.db.toggle_goal(
            goal_id
        )

        self.show_page(
            "Goals"
        )

    def delete_goal_confirm(
        self,
        goal_id
    ):

        if messagebox.askyesno(
            "Delete goal",
            "Delete this goal?",
            parent=self
        ):

            self.db.delete_goal(
                goal_id
            )

            self.show_page(
                "Goals"
            )

    # ========================================================
    # NOTES (a plain text editor)
    # ========================================================

    def build_notes(self):

        self.page_header(
            "Notes",
            "A simple text editor. Write here, or open and edit .txt files."
        )

        db = self.db

        # What's on screen survives page switches and restarts: the text
        # is kept as a draft, plus which file (if any) it belongs to.
        if not hasattr(self, "_note_text"):

            self._note_text = db.get_setting("notes_draft", "")
            self._note_path = db.get_setting("notes_file", "")
            self._note_dirty = db.get_setting("notes_dirty", "0") == "1"

        bar = tk.Frame(self.page, bg=BG)

        bar.pack(fill="x", pady=(0, 12))

        name_var = tk.StringVar()
        state_var = tk.StringVar()
        status_var = tk.StringVar()

        shell = tk.Frame(
            self.page,
            bg=PANEL_2,
            highlightthickness=1,
            highlightbackground=BORDER
        )

        status = tk.Frame(self.page, bg=BG)

        status.pack(side="bottom", fill="x", pady=(8, 0))

        shell.pack(fill="both", expand=True)

        editor = tk.Text(
            shell,
            bg=PANEL_2,
            fg=TEXT,
            insertbackground=TEXT,
            selectbackground=PURPLE,
            selectforeground="#FFFFFF",
            relief="flat",
            bd=0,
            highlightthickness=0,
            wrap="word",
            undo=True,
            autoseparators=True,
            maxundo=-1,
            font=("Consolas", 12),
            padx=18,
            pady=14,
            spacing1=2,
            spacing3=2,
            tabs=("1c",)
        )

        editor.pack(fill="both", expand=True)

        editor.insert("1.0", self._note_text)
        editor.edit_reset()
        editor.edit_modified(False)

        tk.Label(
            status,
            textvariable=status_var,
            bg=BG,
            fg=MUTED_2,
            font=("Segoe UI", 9)
        ).pack(side="left")

        def file_label():

            path = self._note_path

            name_var.set(Path(path).name if path else "Untitled")

            state_var.set(
                "●  Unsaved changes" if self._note_dirty else "Saved"
            )

            state_label.configure(
                fg=YELLOW if self._note_dirty else MUTED_2
            )

        def update_status(event=None):

            try:

                line, col = editor.index("insert").split(".")

                words = len(editor.get("1.0", "end-1c").split())

                status_var.set(
                    f"Ln {line}, Col {int(col) + 1}   •   "
                    f"{words} word{'s' if words != 1 else ''}"
                )

            except Exception:
                pass

        draft_job = {"id": None}

        def store_draft():

            draft_job["id"] = None

            try:

                db.set_setting("notes_draft", self._note_text)
                db.set_setting("notes_file", self._note_path)
                db.set_setting(
                    "notes_dirty", "1" if self._note_dirty else "0"
                )

            except Exception:
                pass

        def on_modified(event=None):

            if not editor.edit_modified():
                return

            editor.edit_modified(False)

            self._note_text = editor.get("1.0", "end-1c")
            self._note_dirty = True

            file_label()
            update_status()

            if draft_job["id"] is not None:

                try:
                    editor.after_cancel(draft_job["id"])
                except Exception:
                    pass

            draft_job["id"] = editor.after(600, store_draft)

        def on_destroy(event=None):

            if event is not None and event.widget is not editor:
                return

            if draft_job["id"] is not None:
                store_draft()

        def confirm_discard():

            if not self._note_dirty:
                return True

            return messagebox.askyesno(
                "Unsaved changes",
                "This note has changes that aren't saved to a file. "
                "Continue and discard them?",
                parent=self
            )

        def set_content(text, path, dirty):

            editor.delete("1.0", "end")
            editor.insert("1.0", text)
            editor.edit_reset()
            editor.edit_modified(False)
            editor.mark_set("insert", "1.0")
            editor.see("1.0")

            self._note_text = text
            self._note_path = path
            self._note_dirty = dirty

            store_draft()
            file_label()
            update_status()

        def write_to(path):

            try:

                with open(path, "w", encoding="utf-8", newline="") as handle:
                    handle.write(editor.get("1.0", "end-1c"))

            except Exception as exc:

                messagebox.showerror(
                    "Save failed",
                    str(exc),
                    parent=self
                )

                return False

            self._note_text = editor.get("1.0", "end-1c")
            self._note_path = path
            self._note_dirty = False

            store_draft()
            file_label()

            return True

        def save_as(event=None):

            start = Path(self._note_path) if self._note_path else None

            options = {}

            if start is not None:
                options["initialdir"] = str(start.parent)

            path = filedialog.asksaveasfilename(
                title="Save as",
                defaultextension=".txt",
                initialfile=start.name if start else "note.txt",
                filetypes=[
                    ("Text files", "*.txt"),
                    ("Markdown", "*.md"),
                    ("All files", "*.*")
                ],
                **options
            )

            if path:
                write_to(path)

            return "break"

        def save(event=None):

            if self._note_path:
                write_to(self._note_path)
            else:
                save_as()

            return "break"

        def open_file(event=None):

            if not confirm_discard():
                return "break"

            path = filedialog.askopenfilename(
                title="Open a text file",
                filetypes=[
                    ("Text files", "*.txt *.md *.log *.csv *.json"),
                    ("All files", "*.*")
                ]
            )

            if not path:
                return "break"

            text = None

            for encoding in ("utf-8-sig", "utf-16", "cp1252"):

                try:

                    with open(path, "r", encoding=encoding) as handle:
                        text = handle.read()

                    break

                except Exception:
                    continue

            if text is None:

                messagebox.showerror(
                    "Open failed",
                    "That file couldn't be read as text.",
                    parent=self
                )

                return "break"

            set_content(text.replace("\r\n", "\n"), path, False)

            return "break"

        def new_note(event=None):

            if confirm_discard():
                set_content("", "", False)

            return "break"

        self.make_button(bar, "New", new_note, width=7).pack(side="left")

        self.make_button(
            bar, "Open", open_file, width=7
        ).pack(side="left", padx=8)

        save_button = self.make_button(bar, "Save", save, width=7)

        save_button.configure(selected=True)
        save_button.pack(side="left")

        self.make_button(
            bar, "Save as", save_as, width=9
        ).pack(side="left", padx=8)

        state_label = tk.Label(
            bar,
            textvariable=state_var,
            bg=BG,
            fg=MUTED_2,
            font=("Segoe UI", 9)
        )

        state_label.pack(side="right")

        tk.Label(
            bar,
            textvariable=name_var,
            bg=BG,
            fg=TEXT,
            font=("Segoe UI", 10, "bold")
        ).pack(side="right", padx=(0, 12))

        editor.bind("<<Modified>>", on_modified)
        editor.bind("<KeyRelease>", update_status)
        editor.bind("<ButtonRelease-1>", update_status)
        editor.bind("<Control-s>", save)
        editor.bind("<Control-S>", save_as)
        editor.bind("<Control-o>", open_file)
        editor.bind("<Control-n>", new_note)
        editor.bind("<Destroy>", on_destroy)

        # Tab inserts a real tab; Ctrl+A selects everything.
        editor.bind(
            "<Control-a>",
            lambda e: (editor.tag_add("sel", "1.0", "end-1c"), "break")[1]
        )

        file_label()
        update_status()

        editor.focus_set()
        editor.mark_set("insert", "end-1c")

    # ========================================================
    # FOCUS MODE
    # ========================================================

    def build_focus(self):

        self.page_header(
            "Focus Mode",
            "Pick a task, set a timer, and stay on it."
        )

        panel = tk.Frame(
            self.page,
            bg=PANEL,
            highlightthickness=1,
            highlightbackground=BORDER
        )

        panel.pack(
            fill="both",
            expand=True
        )

        content = tk.Frame(
            panel,
            bg=PANEL
        )

        content.pack(
            pady=(34, 0)
        )

        # ---- the clock: same presets as the floating one ----
        geom = self._clock_geom()

        self._clock = geom
        self._ring_key = None
        self._dots_key = "unset"

        ring = tk.Canvas(
            content,
            width=geom["cw"],
            height=geom["ch"],
            bg=PANEL,
            highlightthickness=0,
            bd=0
        )

        ring.pack()

        self.focus_ring_canvas = ring

        lay = geom["layout"]

        tx, ty, tpx = lay["time"]
        sx, sy, spx = lay["status"]

        self.focus_timer_label = CanvasText(
            ring,
            ring.create_text(
                tx, ty,
                text=self.focus_time_text(),
                fill=TEXT,
                font=("Segoe UI", -tpx, "bold")
            )
        )

        self.focus_status_label = CanvasText(
            ring,
            ring.create_text(
                sx, sy,
                text="Ready",
                fill=MUTED,
                font=("Segoe UI", -spx)
            )
        )

        # ---- which task ----
        task_row = tk.Frame(
            content,
            bg=PANEL
        )

        task_row.pack(
            pady=(26, 0)
        )

        task = self._focus_task()

        if task is None:

            self.make_button(
                task_row,
                "Choose a task",
                self.choose_focus_task,
                width=14
            ).pack(
                side="left"
            )

        else:

            title = task["title"]

            if len(title) > 26:
                title = title[:25] + "…"

            self.make_button(
                task_row,
                f"Focusing on: {title}",
                self.choose_focus_task
            ).pack(
                side="left"
            )

            self.make_button(
                task_row,
                "Clear",
                self.clear_focus_task,
                width=6
            ).pack(
                side="left",
                padx=(8, 0)
            )

        # ---- length: presets + a Custom pill that slides open ----
        presets = tk.Frame(
            content,
            bg=PANEL
        )

        presets.pack(
            pady=(22, 0)
        )

        self.focus_preset_buttons = {}

        for minutes in (15, 25, 45, 60, 90):

            button = self.make_button(
                presets,
                f"{minutes}m",
                lambda m=minutes: self.set_focus_minutes(m),
                width=5
            )

            button.pack(
                side="left",
                padx=4
            )

            self.focus_preset_buttons[minutes] = button

        reveal, reveal_inner, set_open = self._make_reveal(
            content,
            PANEL
        )

        custom_state = {"open": False}

        def toggle_custom():

            custom_state["open"] = not custom_state["open"]

            set_open(custom_state["open"])

            if custom_state["open"]:

                self.after(
                    280,
                    self.custom_focus_entry.focus_set
                )

        self.focus_custom_button = self.make_button(
            presets,
            "Custom",
            toggle_custom,
            width=7
        )

        self.focus_custom_button.pack(
            side="left",
            padx=4
        )

        reveal.pack(
            fill="x",
            pady=(10, 0)
        )

        custom_row = tk.Frame(
            reveal_inner,
            bg=PANEL
        )

        custom_row.pack(
            pady=(2, 4)
        )

        self.custom_focus_entry = self.make_entry(
            custom_row
        )

        self.custom_focus_entry.configure(width=5, justify="center")

        self.custom_focus_entry.insert(
            0,
            str(self.focus_duration // 60)
        )

        self.custom_focus_entry.pack(
            side="left",
            ipady=7
        )

        tk.Label(
            custom_row,
            text="min",
            bg=PANEL,
            fg=MUTED_2,
            font=("Segoe UI", 9)
        ).pack(
            side="left",
            padx=(6, 12)
        )

        self.custom_focus_sec_entry = self.make_entry(
            custom_row
        )

        self.custom_focus_sec_entry.configure(width=5, justify="center")

        self.custom_focus_sec_entry.insert(
            0,
            str(self.focus_duration % 60)
        )

        self.custom_focus_sec_entry.pack(
            side="left",
            ipady=7
        )

        tk.Label(
            custom_row,
            text="sec",
            bg=PANEL,
            fg=MUTED_2,
            font=("Segoe UI", 9)
        ).pack(
            side="left",
            padx=(6, 12)
        )

        self.make_button(
            custom_row,
            "Set",
            self.apply_custom_focus,
            width=6
        ).pack(
            side="left"
        )

        # ---- start / reset ----
        controls = tk.Frame(
            content,
            bg=PANEL
        )

        controls.pack(
            pady=(22, 34)
        )

        self.focus_start_button = self.make_button(
            controls,
            "Start",
            self.toggle_focus,
            width=12
        )

        # Solid purple: the one primary action on the page.
        self.focus_start_button.configure(selected=True)

        self.focus_start_button.pack(
            side="left",
            padx=5
        )

        self.focus_reset_button = self.make_button(
            controls,
            "Reset",
            self.reset_focus_or_skip,
            width=12
        )

        self.focus_reset_button.pack(
            side="left",
            padx=5
        )

        self._build_focus_drawer(panel)
        self._build_float_toggle(panel)

        self._refresh_focus_presets()
        self.update_focus_ui()

    def _make_reveal(self, parent, bg):
        """A frame that slides open/shut with an ease-out animation.
        Returns (reveal, inner, set_open): pack `reveal` yourself, put
        content in `inner`, call set_open(True/False)."""

        reveal = tk.Frame(parent, bg=bg, height=1)
        reveal.pack_propagate(False)

        inner = tk.Frame(reveal, bg=bg)
        inner.pack(anchor="n")

        anim = {"job": None, "height": 1}

        def animate_to(target, duration=260, steps=16):

            if anim["job"] is not None:

                try:
                    reveal.after_cancel(anim["job"])
                except Exception:
                    pass

                anim["job"] = None

            start = anim["height"]
            delta = target - start

            if delta == 0:
                return

            frame = {"i": 0}

            def step():

                frame["i"] += 1

                t = frame["i"] / steps
                eased = 1 - (1 - t) ** 3

                height = max(1, int(round(start + delta * eased)))
                anim["height"] = height

                try:
                    reveal.configure(height=height)
                except Exception:
                    anim["job"] = None
                    return

                if frame["i"] < steps:

                    anim["job"] = reveal.after(
                        max(1, duration // steps),
                        step
                    )

                else:

                    anim["job"] = None

            step()

        def set_open(opened):

            if opened:

                reveal.update_idletasks()
                animate_to(inner.winfo_reqheight())

            else:

                animate_to(1)

        return reveal, inner, set_open

    def _refresh_focus_presets(self):

        try:

            minutes_now, seconds_now = divmod(self.focus_duration, 60)

            for minutes, button in self.focus_preset_buttons.items():
                button.configure(
                    selected=(minutes == minutes_now and not seconds_now)
                )

            if self.focus_custom_button is not None:

                self.focus_custom_button.configure(
                    selected=(
                        seconds_now != 0
                        or minutes_now not in self.focus_preset_buttons
                    )
                )

            self.custom_focus_entry.delete(0, "end")
            self.custom_focus_entry.insert(0, str(minutes_now))

            self.custom_focus_sec_entry.delete(0, "end")
            self.custom_focus_sec_entry.insert(0, str(seconds_now))

        except Exception:
            pass

    CLOCK_ZOOM = {
        "ring": 2.0,
        "ticks": 1.8,
        "pill": 1.9,
        "bar": 1.8
    }

    def _clock_geom(self):
        """Size of the Focus-page clock for the chosen preset."""

        style = (
            self.float_style
            if self.float_style in FLOAT_SIZES
            else "ring"
        )

        zoom = self.CLOCK_ZOOM.get(style, 2.0)

        lay = float_layout(style, zoom)

        w, h = lay["size"]

        # The wide presets have no room inside for the round dots, so
        # they get a strip underneath.
        extra = 32 if lay["dots"] is None else 0

        return {
            "style": style,
            "zoom": zoom,
            "layout": lay,
            "w": w,
            "h": h,
            "cw": w,
            "ch": h + extra,
            "dots": lay["dots"] or (w / 2, h + 16),
            "card": style in ("pill", "bar")
        }

    def focus_draw_ring(self):
        """The clock: empties clockwise as the session runs, green
        when it's complete. Anti-aliased via Pillow."""

        canvas = self.focus_ring_canvas

        if canvas is None:
            return

        geom = self._clock

        if geom is None:
            return

        if self.focus_finished:
            fraction = 1.0
        else:
            fraction = self.focus_seconds / max(1, self._phase_total())

        key = (
            round(fraction, 3),
            self.focus_finished,
            self.focus_phase
        )

        # Redraw only when it would actually look different.
        if key == self._ring_key:
            return

        self._ring_key = key

        if self.focus_finished:
            color = GREEN
        elif self.focus_phase != "focus":
            color = BLUE
        else:
            color = PURPLE_HOVER

        canvas.delete("ring")

        w, h = geom["w"], geom["h"]

        if not HAS_PIL:

            size = min(w, h)

            x0 = w / 2 - size / 2 + 14
            y0 = h / 2 - size / 2 + 14
            x1 = w / 2 + size / 2 - 14
            y1 = h / 2 + size / 2 - 14

            canvas.create_oval(
                x0, y0, x1, y1,
                outline=BORDER,
                width=10,
                tags="ring"
            )

            if fraction > 0:

                canvas.create_arc(
                    x0, y0, x1, y1,
                    start=90,
                    extent=-min(359.9, 360 * fraction),
                    style="arc",
                    outline=color,
                    width=10,
                    tags="ring"
                )

            canvas.tag_lower("ring")

            return

        img, _ = render_float(
            geom["style"],
            fraction,
            color,
            PANEL,
            zoom=geom["zoom"],
            card=geom["card"]
        )

        photo = ImageTk.PhotoImage(img)
        canvas.ring_photo = photo

        canvas.create_image(
            w / 2,
            h / 2,
            image=photo,
            tags="ring"
        )

        canvas.tag_lower("ring")

    def focus_time_text(self):

        minutes, seconds = divmod(
            max(
                0,
                self.focus_seconds
            ),
            60
        )

        return (
            f"{minutes:02d}:{seconds:02d}"
        )

    def set_focus_minutes(
        self,
        minutes
    ):

        self.set_focus_total(minutes * 60)

    def _focus_len_text(self):
        """'25 minutes' or '1 minute 30 seconds'."""

        minutes, seconds = divmod(self.focus_duration, 60)

        parts = []

        if minutes:
            parts.append(f"{minutes} minute" + ("" if minutes == 1 else "s"))

        if seconds:
            parts.append(f"{seconds} second" + ("" if seconds == 1 else "s"))

        return " ".join(parts) or "0 seconds"

    def set_focus_total(
        self,
        total
    ):
        """Set the timer length in seconds (minutes + seconds from
        the Custom box, or a whole number of minutes from a preset)."""

        if self.focus_running:
            return

        minutes = total // 60

        self.focus_duration = total

        self.focus_seconds = (
            self.focus_duration
        )

        self.focus_finished = False
        self.focus_phase = "focus"

        self.db.set_setting(
            "focus_minutes",
            str(max(1, minutes))
        )

        self.db.set_setting(
            "focus_total_seconds",
            str(total)
        )

        self.update_focus_ui()
        self._refresh_focus_presets()

    def apply_custom_focus(self):

        try:

            minutes = int(
                self.custom_focus_entry.get().strip() or "0"
            )

            seconds = int(
                self.custom_focus_sec_entry.get().strip() or "0"
            )

        except ValueError:

            messagebox.showwarning(
                "Focus",
                "Enter whole numbers."
            )

            return

        if not 0 <= seconds <= 59:

            messagebox.showwarning(
                "Focus",
                "Seconds go from 0 to 59."
            )

            return

        total = minutes * 60 + seconds

        if not 1 <= total <= 240 * 60:

            messagebox.showwarning(
                "Focus",
                "Choose between 1 second and 240 minutes."
            )

            return

        self.set_focus_total(
            total
        )

    def toggle_focus(self):

        if self.focus_finished:

            self.reset_focus()

        self._cancel_focus_job()

        self.focus_running = (
            not self.focus_running
        )

        if self.focus_running:

            self.focus_finished = False

            # Count toward a fixed end time instead of subtracting a
            # second per tick, so sleep/lag can't make it drift.
            self.focus_end_time = time.time() + self.focus_seconds

            # The popup can start the next phase while you are on
            # another page, when these widgets no longer exist.
            try:

                self.focus_start_button.configure(
                    text="Pause"
                )

            except Exception:
                pass

            self.focus_tick()

        else:

            try:

                self.focus_start_button.configure(
                    text="Resume"
                )

                self.focus_status_label.configure(
                    text="Paused",
                    fg=MUTED
                )

            except Exception:
                pass

            self._float_update()
            self._sidebar_timer_update()

    def reset_focus(self):

        # Stopping a focus session early still counts what you did.
        self._log_partial_focus()

        self.focus_running = False
        self.focus_finished = False
        self.focus_nudges = 0

        if self.focus_job:

            try:
                self.after_cancel(
                    self.focus_job
                )
            except Exception:
                pass

            self.focus_job = None

        self.focus_seconds = self._phase_total()

        self.update_focus_ui()

    def _cancel_focus_job(self):

        if self.focus_job:

            try:
                self.after_cancel(self.focus_job)
            except Exception:
                pass

            self.focus_job = None

    def focus_tick(self):

        if not self.focus_running:
            return

        self.focus_seconds = max(
            0,
            math.ceil(self.focus_end_time - time.time())
        )

        if self.focus_seconds <= 0:

            self.focus_running = False
            self.focus_job = None

            self._focus_phase_finished()

            return

        self._maybe_nudge()

        self.update_focus_ui()

        self.focus_job = self.after(
            250,
            self.focus_tick
        )

    # --------------------------------------------------------
    # Focusing on a task
    # --------------------------------------------------------

    def _focus_task(self):
        """The chosen task if it still exists and isn't done yet."""

        if self.focus_task_id is None:
            return None

        for task in self.db.get_tasks(False):

            if task["id"] == self.focus_task_id:
                return task

        self.focus_task_id = None

        return None

    def focus_task_text(self):

        task = self._focus_task()

        if task is None:
            return "No task selected"

        title = task["title"]

        if len(title) > 40:
            title = title[:39] + "…"

        return f"Focusing on: {title}"

    def clear_focus_task(self):

        self.focus_task_id = None
        self.show_page("Focus Mode")

    def choose_focus_task(self):

        rank = {"High": 0, "Medium": 1, "Low": 2}

        tasks = sorted(
            self.db.get_tasks(False),
            key=lambda t: rank.get(t["priority"], 1)
        )

        shown = tasks[:8]
        extra = len(tasks) - len(shown)

        win = tk.Toplevel(self)

        win.title("Choose a task")
        win.configure(bg=BG)
        win.transient(self)
        win.grab_set()

        self.center_window(
            win,
            480,
            190 + 46 * max(1, len(shown)) + (24 if extra else 0)
        )

        tk.Label(
            win,
            text="Focus on which task?",
            bg=BG,
            fg=TEXT,
            font=("Segoe UI", 18, "bold")
        ).pack(
            anchor="w",
            padx=28,
            pady=(24, 14)
        )

        bar = tk.Frame(win, bg=BG)

        bar.pack(
            side="bottom",
            fill="x",
            padx=28,
            pady=20
        )

        self.make_button(
            bar,
            "Cancel",
            win.destroy,
            width=9
        ).pack(
            side="right"
        )

        def pick(task_id):

            self.focus_task_id = task_id
            win.destroy()
            self.show_page("Focus Mode")

        if not shown:

            tk.Label(
                win,
                text="No pending tasks — add one first.",
                bg=BG,
                fg=MUTED_2,
                font=("Segoe UI", 10)
            ).pack(
                anchor="w",
                padx=28
            )

        for task in shown:

            row = tk.Frame(win, bg=PANEL_2)

            row.pack(
                fill="x",
                padx=28,
                pady=3
            )

            tk.Label(
                row,
                text="●",
                bg=PANEL_2,
                fg=priority_color(task["priority"]),
                font=("Segoe UI", 8)
            ).pack(
                side="left",
                padx=(12, 6),
                pady=10
            )

            title = task["title"]

            if len(title) > 32:
                title = title[:31] + "…"

            tk.Label(
                row,
                text=title,
                bg=PANEL_2,
                fg=TEXT,
                font=("Segoe UI", 10, "bold"),
                anchor="w"
            ).pack(
                side="left",
                fill="x",
                expand=True
            )

            self.make_button(
                row,
                "Select",
                lambda tid=task["id"]: pick(tid),
                width=7
            ).pack(
                side="right",
                padx=8,
                pady=6
            )

        if extra:

            tk.Label(
                win,
                text=f"+ {extra} more (complete some to see them)",
                bg=BG,
                fg=MUTED_2,
                font=("Segoe UI", 9)
            ).pack(
                anchor="w",
                padx=30,
                pady=(4, 0)
            )

    # --------------------------------------------------------
    # Phases, Pomodoro and session history
    # --------------------------------------------------------

    def _phase_total(self):
        """Length in seconds of the current phase."""

        if self.focus_phase == "short":
            return POMO_SHORT

        if self.focus_phase == "long":
            return POMO_LONG

        return self.focus_duration

    def _log_focus(self, completed, actual_seconds):

        try:

            task = self._focus_task()

            self.db.add_focus_session(
                task["id"] if task is not None else None,
                task["title"] if task is not None else "",
                self.focus_duration,
                actual_seconds,
                completed,
                self.focus_nudges
            )

        except Exception:
            pass

        self.focus_nudges = 0

    def _log_partial_focus(self):
        """Called when a focus phase is reset before it finished."""

        if self.focus_phase != "focus" or self.focus_finished:
            return

        elapsed = self.focus_duration - self.focus_seconds

        # Ignore accidental starts.
        if elapsed >= 60:
            self._log_focus(False, elapsed)

    def _focus_phase_finished(self):
        """The countdown hit zero: log it and decide what comes next."""

        finished = self.focus_phase

        if finished == "focus":
            self._log_focus(True, self.focus_duration)

        if not self.pomo_enabled:

            self.focus_finished = True

            # No-op safely if you switched pages mid-session.
            self.update_focus_ui()

            self.focus_session_complete()

            return

        if finished == "focus":

            self.pomo_done += 1

            next_phase = (
                "long" if self.pomo_done >= POMO_ROUNDS else "short"
            )

        else:

            if finished == "long":
                self.pomo_done = 0

            next_phase = "focus"

        self.focus_phase = next_phase
        self.focus_seconds = self._phase_total()
        self.focus_nudges = 0

        self.update_focus_ui()

        self.pomodoro_popup(finished, next_phase)

    def skip_break(self):

        self._cancel_focus_job()

        self.focus_running = False
        self.focus_finished = False
        self.focus_phase = "focus"
        self.focus_seconds = self.focus_duration
        self.focus_nudges = 0

        # Skipping the long break starts a fresh set of rounds.
        if self.pomo_done >= POMO_ROUNDS:
            self.pomo_done = 0

        self._ring_key = None

        self.update_focus_ui()

    def reset_focus_or_skip(self):

        if self.pomo_enabled and self.focus_phase != "focus":
            self.skip_break()
        else:
            self.reset_focus()

    # --------------------------------------------------------
    # Options drawer (gear icon, slides in from the left)
    # --------------------------------------------------------

    def _gear_image(self, size, color):
        """Anti-aliased gear icon: drawn big, shrunk with LANCZOS."""

        scale = 6
        big = size * scale

        img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        c = big / 2
        body = big * 0.29
        tooth = big * 0.15
        tooth_w = big * 0.17

        for i in range(8):

            angle = math.radians(i * 45)

            ux, uy = math.cos(angle), math.sin(angle)
            px, py = -uy, ux

            r0 = body * 0.8
            r1 = body + tooth

            draw.polygon(
                [
                    (c + ux * r0 + px * tooth_w / 2,
                     c + uy * r0 + py * tooth_w / 2),
                    (c + ux * r1 + px * tooth_w * 0.38,
                     c + uy * r1 + py * tooth_w * 0.38),
                    (c + ux * r1 - px * tooth_w * 0.38,
                     c + uy * r1 - py * tooth_w * 0.38),
                    (c + ux * r0 - px * tooth_w / 2,
                     c + uy * r0 - py * tooth_w / 2)
                ],
                fill=color
            )

        draw.ellipse(
            [c - body, c - body, c + body, c + body],
            fill=color
        )

        hole = body * 0.42

        # Plain Draw() on RGBA overwrites pixels, so this punches a
        # transparent hole through the middle.
        draw.ellipse(
            [c - hole, c - hole, c + hole, c + hole],
            fill=(0, 0, 0, 0)
        )

        return img.resize((size, size), Image.LANCZOS)

    def _arrow_image(self, width, height, color, fill):
        """The '>' handle on the drawer's left wall: a tab with
        rounded right corners and a chevron pointing at the wall the
        drawer slides back into. Anti-aliased via LANCZOS."""

        scale = 6

        img = Image.new(
            "RGBA",
            (width * scale, height * scale),
            (0, 0, 0, 0)
        )

        draw = ImageDraw.Draw(img)

        radius = width * scale * 0.5

        # Starts left of the image so only the right corners round.
        draw.rounded_rectangle(
            [-radius, 0, width * scale - 1, height * scale - 1],
            radius=radius,
            fill=fill
        )

        cx = width * scale * 0.46
        cy = height * scale * 0.5
        arm_x = width * scale * 0.13
        arm_y = height * scale * 0.13

        points = [
            (cx - arm_x, cy - arm_y),
            (cx + arm_x, cy),
            (cx - arm_x, cy + arm_y)
        ]

        draw.line(
            points,
            fill=color,
            width=int(scale * 2.2),
            joint="curve"
        )

        for x, y in (points[0], points[2]):

            r = scale * 1.1

            draw.ellipse([x - r, y - r, x + r, y + r], fill=color)

        return img.resize((width, height), Image.LANCZOS)

    def _paint_gear(self):

        state = self._drawer

        if not state:
            return

        gear = state["gear"]

        color = TEXT if state["hover"] else MUTED

        if color == state.get("paint_key"):
            return

        state["paint_key"] = color

        try:

            gear.delete("all")

            if HAS_PIL:

                photo = ImageTk.PhotoImage(
                    self._gear_image(26, color)
                )

                gear.gear_photo = photo

                gear.create_image(19, 19, image=photo)

            else:

                gear.create_text(
                    19, 19,
                    text="≡",
                    fill=color,
                    font=("Segoe UI", 16)
                )

        except Exception:
            pass

    def _paint_arrow(self):

        state = self._drawer

        if not state:
            return

        arrow = state["arrow"]

        hover = state["arrow_hover"]

        key = hover

        if key == state.get("arrow_key"):
            return

        state["arrow_key"] = key

        color = TEXT if hover else MUTED
        fill = HOVER_BG if hover else PANEL_2

        try:

            arrow.delete("all")

            if HAS_PIL:

                photo = ImageTk.PhotoImage(
                    self._arrow_image(24, 64, color, fill)
                )

                arrow.arrow_photo = photo

                arrow.create_image(0, 0, anchor="nw", image=photo)

            else:

                arrow.create_text(
                    12, 32,
                    text="›",
                    fill=color,
                    font=("Segoe UI", 20)
                )

        except Exception:
            pass

    def _show_gear(self):

        state = self._drawer

        if not state:
            return

        try:

            state["gear"].place(relx=1.0, x=-52, y=14)

        except Exception:
            pass

        self._paint_gear()

    def toggle_focus_drawer(self):

        state = self._drawer

        if not state:
            return

        state["open"] = not state["open"]

        if state["open"]:

            # The gear steps aside; the '>' handle on the drawer's
            # wall takes over as the way back.
            try:
                state["gear"].place_forget()
            except Exception:
                pass

            self._refresh_drawer_words()

        self._slide_drawer(
            state["shown"] if state["open"] else state["hidden"]
        )

    def _slide_drawer(self, target, duration=280, steps=16):
        """Ease-out slide of the drawer to x=target (an offset from
        the panel's right edge). Safe to call again mid-slide: it
        carries on from where it is."""

        state = self._drawer

        if not state:
            return

        frame = state["frame"]

        if state["job"] is not None:

            try:
                frame.after_cancel(state["job"])
            except Exception:
                pass

            state["job"] = None

        start = state["x"]
        delta = target - start

        if delta == 0:
            return

        counter = {"i": 0}

        def step():

            counter["i"] += 1

            t = counter["i"] / steps
            eased = 1 - (1 - t) ** 3

            x = int(round(start + delta * eased))

            state["x"] = x

            try:
                frame.place_configure(x=x)
            except Exception:
                # Page was rebuilt while sliding.
                state["job"] = None
                return

            if counter["i"] < steps:

                state["job"] = frame.after(
                    max(1, duration // steps),
                    step
                )

            else:

                state["job"] = None

                # Fully back in the wall: the gear returns.
                if not state["open"]:
                    self._show_gear()

        step()

    def _static_pill(self, parent, text):
        """A pill that only displays text: no hover glow, no click."""

        button = self.make_button(parent, text, None)

        try:

            for event in ("<Enter>", "<Leave>", "<Button-1>"):
                button.canvas.unbind(event)

            button.canvas.configure(cursor="arrow")

        except Exception:
            pass

        return button

    def _refresh_drawer_words(self):
        """The words currently being watched, listed at the bottom of
        the drawer. Rebuilt whenever the words or the on/off change."""

        state = self._drawer

        if not state or not state.get("words_box"):
            return

        box = state["words_box"]

        try:

            for child in box.winfo_children():
                child.destroy()

            tk.Label(
                box,
                text="Words being watched",
                bg=SIDEBAR,
                fg=TEXT,
                font=("Segoe UI", 11, "bold")
            ).pack(
                anchor="w"
            )

            words = list(self.nudge_words)

            if not self.nudge_on:

                hint = "Distraction alerts are off, so these are ignored."

            elif not words:

                hint = "No words yet. Press Edit above to add some."

            else:

                hint = "Click Edit above to add or remove words."

            tk.Label(
                box,
                text=hint,
                bg=SIDEBAR,
                fg=YELLOW if not self.nudge_on else MUTED_2,
                font=("Segoe UI", 9),
                wraplength=FOCUS_DRAWER_WIDTH - 60,
                justify="left"
            ).pack(
                anchor="w",
                pady=(2, 8)
            )

            limit = 18

            shown = words[:limit]

            font = tkfont.Font(family="Segoe UI", size=10)

            row = None
            used = 0

            for word in shown:

                # Same padding RoundedButton adds, plus the gap.
                needed = font.measure(word) + 26 + 8

                if row is None or used + needed > FOCUS_DRAWER_WIDTH - 64:

                    row = tk.Frame(
                        box,
                        bg=SIDEBAR
                    )

                    row.pack(
                        anchor="w",
                        pady=3
                    )

                    used = 0

                self._static_pill(row, word).pack(
                    side="left",
                    padx=(0, 8)
                )

                used += needed

            if len(words) > limit:

                tk.Label(
                    box,
                    text=f"+ {len(words) - limit} more",
                    bg=SIDEBAR,
                    fg=MUTED_2,
                    font=("Segoe UI", 9)
                ).pack(
                    anchor="w",
                    pady=(2, 0)
                )

        except Exception:
            pass

    def _build_focus_drawer(self, panel):
        """Gear icon at the top-right of the Focus panel. Clicking it
        slides an options drawer in from the right wall; the gear
        steps aside and a '>' handle on the drawer's left wall slides
        it back."""

        width = FOCUS_DRAWER_WIDTH

        # x is an offset from the panel's right edge: +2 = just
        # outside the wall, -width = fully showing.
        hidden = 2
        shown = -width

        drawer = tk.Frame(
            panel,
            bg=SIDEBAR,
            highlightthickness=1,
            highlightbackground=BORDER
        )

        drawer.place(
            relx=1.0,
            x=hidden,
            y=0,
            width=width,
            relheight=1
        )

        self._drawer = {
            "frame": drawer,
            "x": hidden,
            "hidden": hidden,
            "shown": shown,
            "job": None,
            "open": False,
            "hover": False,
            "arrow_hover": False,
            "words_box": None
        }

        # Content starts right of the '>' handle on the left wall.
        left = 38

        tk.Label(
            drawer,
            text="Focus options",
            bg=SIDEBAR,
            fg=TEXT,
            font=("Segoe UI", 14, "bold")
        ).pack(
            anchor="w",
            padx=(left, 20),
            pady=(22, 0)
        )

        tk.Label(
            drawer,
            text="Change how the timer works.",
            bg=SIDEBAR,
            fg=MUTED,
            font=("Segoe UI", 9)
        ).pack(
            anchor="w",
            padx=(left, 20),
            pady=(2, 8)
        )

        def option(title, explain, make_control):

            box = tk.Frame(
                drawer,
                bg=SIDEBAR
            )

            box.pack(
                fill="x",
                padx=(left, 22),
                pady=(18, 0)
            )

            top = tk.Frame(
                box,
                bg=SIDEBAR
            )

            top.pack(
                fill="x"
            )

            tk.Label(
                top,
                text=title,
                bg=SIDEBAR,
                fg=TEXT,
                font=("Segoe UI", 11, "bold")
            ).pack(
                side="left"
            )

            make_control(top).pack(
                side="right"
            )

            tk.Label(
                box,
                text=explain,
                bg=SIDEBAR,
                fg=MUTED,
                font=("Segoe UI", 9),
                wraplength=width - left - 28,
                justify="left"
            ).pack(
                anchor="w",
                pady=(6, 0)
            )

        def pomodoro_control(parent):

            self.focus_pomo_button = self.make_button(
                parent,
                "On" if self.pomo_enabled else "Off",
                self.toggle_pomodoro,
                width=6
            )

            self.focus_pomo_button.configure(
                selected=self.pomo_enabled
            )

            return self.focus_pomo_button

        def alerts_control(parent):

            self.focus_nudge_button = self.make_button(
                parent,
                "On" if self.nudge_on else "Off",
                self.toggle_nudge,
                width=6
            )

            self.focus_nudge_button.configure(
                selected=self.nudge_on
            )

            return self.focus_nudge_button

        option(
            "Pomodoro mode",
            f"Study in rounds. Each round lasts as long as the timer "
            f"you picked, then you get a {POMO_SHORT // 60}-minute "
            f"break. After {POMO_ROUNDS} rounds you get a longer "
            f"{POMO_LONG // 60}-minute break. The dots inside the "
            f"circle show which round you are on.",
            pomodoro_control
        )

        option(
            "Distraction alerts",
            "While the timer is running, if you switch to a "
            "distracting site or app (like Instagram), a popup "
            "reminds you what you are working on.",
            alerts_control
        )

        option(
            "Distraction words",
            "The words that count as a distraction. Studestics "
            "looks for them in the title of the window you are "
            "using, such as a browser tab.",
            lambda parent: self.make_button(
                parent,
                "Edit",
                self.edit_nudge_words,
                width=6
            )
        )

        self.focus_drawer_note = tk.Label(
            drawer,
            text="",
            bg=SIDEBAR,
            fg=YELLOW,
            font=("Segoe UI", 9),
            wraplength=width - left - 28,
            justify="left"
        )

        self.focus_drawer_note.pack(
            anchor="w",
            padx=(left, 22),
            pady=(14, 0)
        )

        # The words in use, down in the empty space at the bottom.
        words_box = tk.Frame(
            drawer,
            bg=SIDEBAR
        )

        words_box.pack(
            side="bottom",
            fill="x",
            padx=(left, 22),
            pady=(0, 24)
        )

        self._drawer["words_box"] = words_box

        self._refresh_drawer_words()

        # '>' handle on the drawer's left wall, centred vertically.
        arrow = tk.Canvas(
            drawer,
            width=24,
            height=64,
            bg=SIDEBAR,
            highlightthickness=0,
            bd=0,
            cursor="hand2"
        )

        arrow.place(
            x=1,
            rely=0.5,
            y=-32
        )

        self._drawer["arrow"] = arrow

        def arrow_hover(on):

            self._drawer["arrow_hover"] = on
            self._paint_arrow()

        arrow.bind("<Enter>", lambda e: arrow_hover(True))
        arrow.bind("<Leave>", lambda e: arrow_hover(False))
        arrow.bind("<Button-1>", lambda e: self.toggle_focus_drawer())

        self._paint_arrow()

        # Gear: top-right corner of the panel, shown only while the
        # drawer is closed.
        gear = tk.Canvas(
            panel,
            width=38,
            height=38,
            bg=PANEL,
            highlightthickness=0,
            bd=0,
            cursor="hand2"
        )

        self._drawer["gear"] = gear

        def hover(on):

            self._drawer["hover"] = on
            self._paint_gear()

        gear.bind("<Enter>", lambda e: hover(True))
        gear.bind("<Leave>", lambda e: hover(False))
        gear.bind("<Button-1>", lambda e: self.toggle_focus_drawer())

        self._show_gear()

    # --------------------------------------------------------
    # Floating timer (a small always-on-top clock)
    # --------------------------------------------------------

    def _float_status(self):

        if not self.focus_running:
            return "Paused"

        return {
            "focus": "Focusing",
            "short": "Short break",
            "long": "Long break"
        }.get(self.focus_phase, "Focusing")

    def _float_color(self):

        return PURPLE_HOVER if self.focus_phase == "focus" else BLUE

    def _float_active(self):
        """A timer is running, or paused part-way through."""

        if self.focus_finished:
            return False

        return (
            self.focus_running
            or self.focus_seconds < self._phase_total()
        )

    def _float_draw(
        self,
        canvas,
        style,
        fraction,
        color,
        bg,
        time_text,
        status_text,
        center
    ):
        """Paint one preset onto a canvas. Used by the floating window
        and by the preview in Settings, so they always match."""

        canvas.delete("all")

        w, h = FLOAT_SIZES.get(style, FLOAT_SIZES["ring"])

        if HAS_PIL:

            image, layout = render_float(
                style,
                fraction,
                color,
                None if bg == FLOAT_KEY else bg
            )

            photo = ImageTk.PhotoImage(image)

            canvas.float_photo = photo

            canvas.create_image(
                center[0],
                center[1],
                image=photo
            )

            ox = center[0] - w / 2
            oy = center[1] - h / 2

            tx, ty, tpx = layout["time"]
            sx, sy, spx = layout["status"]

            # Negative sizes are pixels, so the text matches the
            # pixel-drawn shape at any display scaling.
            canvas.create_text(
                ox + tx,
                oy + ty,
                text=time_text,
                fill=TEXT,
                font=("Segoe UI", -tpx, "bold")
            )

            canvas.create_text(
                ox + sx,
                oy + sy,
                text=status_text,
                fill=MUTED,
                font=("Segoe UI", -spx)
            )

        else:

            x0 = center[0] - w / 2
            y0 = center[1] - h / 2

            canvas.create_rectangle(
                x0, y0, x0 + w, y0 + h,
                fill=PANEL,
                outline=BORDER
            )

            canvas.create_text(
                center[0],
                center[1] - 6,
                text=time_text,
                fill=TEXT,
                font=("Segoe UI", -26, "bold")
            )

            canvas.create_text(
                center[0],
                center[1] + 20,
                text=status_text,
                fill=MUTED,
                font=("Segoe UI", -11)
            )

    def _float_close(self):

        if self._float_win is not None:

            try:
                self._float_win.destroy()
            except Exception:
                pass

        self._float_win = None
        self._float_canvas = None
        self._float_key = None
        self._float_size = None

    def _float_create(self, size):

        w, h = size

        win = tk.Toplevel(self)

        win.overrideredirect(True)
        win.attributes("-topmost", True)

        transparent = False

        try:

            # Windows only: this colour becomes see-through, which is
            # what lets the ring and the pill have round edges.
            win.configure(bg=FLOAT_KEY)
            win.attributes("-transparentcolor", FLOAT_KEY)

            transparent = True

        except Exception:

            win.configure(bg=PANEL)

        self._float_transparent = transparent

        canvas = tk.Canvas(
            win,
            width=w,
            height=h,
            bg=FLOAT_KEY if transparent else PANEL,
            highlightthickness=0,
            bd=0,
            cursor="fleur"
        )

        canvas.pack(
            fill="both",
            expand=True
        )

        screen_w = win.winfo_screenwidth()
        screen_h = win.winfo_screenheight()

        pos = self.float_pos

        # Remembered spot, unless it is off-screen now (monitor
        # unplugged, resolution changed): then bottom-right.
        if (
            pos is None
            or not (0 <= pos[0] <= screen_w - w)
            or not (0 <= pos[1] <= screen_h - h)
        ):

            pos = (screen_w - w - 28, screen_h - h - 72)

        win.geometry(f"{w}x{h}+{int(pos[0])}+{int(pos[1])}")

        drag = {}

        def press(event):

            drag["dx"] = event.x_root - win.winfo_x()
            drag["dy"] = event.y_root - win.winfo_y()
            drag["x0"] = event.x_root
            drag["y0"] = event.y_root
            drag["moved"] = False

        def move(event):

            if "dx" in drag:

                if (
                    abs(event.x_root - drag["x0"]) > 3
                    or abs(event.y_root - drag["y0"]) > 3
                ):
                    drag["moved"] = True

                win.geometry(
                    f"+{event.x_root - drag['dx']}"
                    f"+{event.y_root - drag['dy']}"
                )

        def release(event):

            if "dx" not in drag:
                return

            moved = drag.get("moved", False)

            drag.clear()

            if not moved:

                # A plain click: pause, or resume.
                self.toggle_focus()

                return

            self.float_pos = (win.winfo_x(), win.winfo_y())

            self.db.set_setting("float_x", str(self.float_pos[0]))
            self.db.set_setting("float_y", str(self.float_pos[1]))

        canvas.bind("<ButtonPress-1>", press)
        canvas.bind("<B1-Motion>", move)
        canvas.bind("<ButtonRelease-1>", release)

        self._float_win = win
        self._float_canvas = canvas
        self._float_size = size
        self._float_key = None

    def _float_update(self):
        """Show, redraw or close the floating timer to match the
        focus timer. Cheap: it only redraws when something changed."""

        if self._quitting or not self.initialized:
            return

        try:

            active = self._float_active()

            if not active:
                self._float_user_hidden = False

            if not (
                self.float_on
                and active
                and not self._float_user_hidden
            ):

                self._float_close()

                return

            style = self.float_style

            size = FLOAT_SIZES.get(style, FLOAT_SIZES["ring"])

            if self._float_win is None:
                self._float_create(size)

            fraction = (
                self.focus_seconds / max(1, self._phase_total())
            )

            time_text = self.focus_time_text()
            status = self._float_status()
            color = self._float_color()

            key = (style, time_text, status, color, int(fraction * 240))

            if key == self._float_key:
                return

            self._float_key = key

            w, h = size

            # Style changed while it was showing: resize in place.
            if self._float_size != size:

                self._float_win.geometry(
                    f"{w}x{h}+{self._float_win.winfo_x()}"
                    f"+{self._float_win.winfo_y()}"
                )

                self._float_size = size

            self._float_draw(
                self._float_canvas,
                style,
                fraction,
                color,
                FLOAT_KEY if self._float_transparent else PANEL,
                time_text,
                status,
                (w / 2, h / 2)
            )

        except Exception:
            pass

    def toggle_float(self):

        self.float_on = not self.float_on

        self._float_user_hidden = False

        self._refresh_float_controls()

        self._float_update()

        try:
            self._tray_icon.update_menu()
        except Exception:
            pass

    def _float_icon_image(self, size, color, on):
        """Little 'window floating over a screen' icon; crossed out
        when the floating clock is off."""

        scale = 8

        big = size * scale

        img = Image.new("RGBA", (big, big), (0, 0, 0, 0))

        d = ImageDraw.Draw(img)

        u = big / 26.0

        d.rounded_rectangle(
            [2 * u, 4 * u, 24 * u, 20 * u],
            radius=3.5 * u,
            outline=color,
            width=max(1, int(round(1.9 * u)))
        )

        d.rounded_rectangle(
            [12.5 * u, 11 * u, 21.5 * u, 17 * u],
            radius=2 * u,
            fill=color
        )

        if not on:

            # Slash with a thin gap on each side so it reads as
            # "off" and not as part of the screen.
            d.line(
                [(3.5 * u, 23 * u), (22.5 * u, 2.5 * u)],
                fill=(0, 0, 0, 0),
                width=int(round(5.2 * u))
            )

            d.line(
                [(3.5 * u, 23 * u), (22.5 * u, 2.5 * u)],
                fill=color,
                width=int(round(2 * u))
            )

        return img.resize((size, size), Image.LANCZOS)

    def _paint_float_icon(self):

        icon = self.float_icon

        if icon is None:
            return

        if self.float_on:
            color = PURPLE_HOVER if not self._float_icon_hover else PURPLE_LIGHT
        else:
            color = TEXT if self._float_icon_hover else MUTED

        try:

            icon.delete("all")

            if HAS_PIL:

                photo = ImageTk.PhotoImage(
                    self._float_icon_image(26, color, self.float_on)
                )

                icon.icon_photo = photo

                icon.create_image(19, 19, image=photo)

            else:

                icon.create_text(
                    19, 19,
                    text="▭" if self.float_on else "▫",
                    fill=color,
                    font=("Segoe UI", 16)
                )

        except Exception:
            pass

    def _float_tip_show(self, on):

        tip = self._float_tip

        if tip is None:
            return

        try:

            if on:

                tip.configure(
                    text=(
                        "Floating clock: On  (click to turn off)"
                        if self.float_on
                        else "Floating clock: Off  (click to turn on)"
                    )
                )

                tip.place(x=58, y=22)

                tk.Misc.tkraise(tip)

            else:

                tip.place_forget()

        except Exception:
            pass

    def _build_float_toggle(self, panel):
        """Icon at the top-left of the Focus panel: turns the
        floating clock on or off."""

        icon = tk.Canvas(
            panel,
            width=38,
            height=38,
            bg=PANEL,
            highlightthickness=0,
            bd=0,
            cursor="hand2"
        )

        icon.place(x=14, y=14)

        self.float_icon = icon
        self._float_icon_hover = False

        self._float_tip = tk.Label(
            panel,
            text="",
            bg=SIDEBAR,
            fg=TEXT,
            font=("Segoe UI", 9),
            padx=10,
            pady=5,
            highlightthickness=1,
            highlightbackground=BORDER
        )

        def hover(on):

            self._float_icon_hover = on

            self._paint_float_icon()

            self._float_tip_show(on)

        def click(event=None):

            self.toggle_float()

            self._float_tip_show(True)

        icon.bind("<Enter>", lambda e: hover(True))
        icon.bind("<Leave>", lambda e: hover(False))
        icon.bind("<Button-1>", click)

        self._paint_float_icon()

    def choose_float_style(self, name):

        if name not in FLOAT_SIZES:
            return

        self.float_style = name

        self.db.set_setting("float_style", name)

        self._refresh_float_controls()
        self._float_preview_refresh()

        self._float_update()

    def _refresh_float_controls(self):

        self._paint_float_icon()

        for key, button in self.float_style_buttons.items():

            try:

                button.configure(selected=(key == self.float_style))

            except Exception:
                pass

    def _float_preview_refresh(self):
        """The sample in Settings: the chosen preset, part-way
        through a session."""

        canvas = self.float_preview_canvas

        if canvas is None:
            return

        try:

            self._float_draw(
                canvas,
                self.float_style,
                0.62,
                PURPLE_HOVER,
                FLOAT_PREVIEW_BG,
                "15:28",
                "Focusing",
                (160, 108)
            )

            canvas.create_text(
                14,
                12,
                anchor="nw",
                text="Preview",
                fill=MUTED_2,
                font=("Segoe UI", -11)
            )

            self._round_preview_corners(canvas)

        except Exception:
            pass

    def _round_preview_corners(self, canvas, radius=14):
        """Round the sample's corners: a 1px border along the edges
        and four anti-aliased corner pieces on top."""

        if not HAS_PIL:
            return

        w = int(canvas.cget("width"))
        h = int(canvas.cget("height"))

        corners = _panel_corner_images(
            radius,
            fill=FLOAT_PREVIEW_BG,
            outside=PANEL,
            border=BORDER
        )

        photos = getattr(canvas, "_corner_photos", None)

        if photos is None:

            photos = {
                name: ImageTk.PhotoImage(pil)
                for name, pil in corners.items()
            }

            canvas._corner_photos = photos

        for x0, y0, x1, y1 in (
            (radius, 0, w - radius, 1),
            (radius, h - 1, w - radius, h),
            (0, radius, 1, h - radius),
            (w - 1, radius, w, h - radius)
        ):

            canvas.create_rectangle(
                x0, y0, x1, y1,
                fill=BORDER,
                width=0
            )

        for name, x, y in (
            ("tl", 0, 0),
            ("tr", w - radius, 0),
            ("bl", 0, h - radius),
            ("br", w - radius, h - radius)
        ):

            canvas.create_image(
                x, y,
                anchor="nw",
                image=photos[name]
            )

    def _refresh_pomo_button(self):

        try:

            self.focus_pomo_button.configure(
                text="On" if self.pomo_enabled else "Off",
                selected=self.pomo_enabled
            )

        except Exception:
            pass

    def _drawer_note(self, text):
        """Short message at the bottom of the drawer, gone after a
        few seconds."""

        try:

            self.focus_drawer_note.configure(text=text)

            def clear():

                try:

                    if self.focus_drawer_note.cget("text") == text:
                        self.focus_drawer_note.configure(text="")

                except Exception:
                    pass

            self.after(3500, clear)

        except Exception:
            pass

    def toggle_pomodoro(self):

        if self.focus_running:

            self._drawer_note(
                "Pause or reset the timer first, then switch Pomodoro."
            )

            return

        self.pomo_enabled = not self.pomo_enabled

        self.db.set_setting(
            "pomodoro",
            "1" if self.pomo_enabled else "0"
        )

        self.focus_phase = "focus"
        self.focus_finished = False
        self.pomo_done = 0
        self.focus_nudges = 0
        self.focus_seconds = self.focus_duration

        self._ring_key = None

        self._refresh_pomo_button()

        self.update_focus_ui()

    def focus_draw_dots(self):
        """Round dots inside the ring: one per focus round in a set.
        Filled = done, outlined = the round you are on."""

        canvas = self.focus_ring_canvas

        if canvas is None:
            return

        if self.pomo_enabled:

            key = (
                self.pomo_done,
                self.focus_phase,
                self.pomo_enabled
            )

        else:

            key = None

        if key == self._dots_key:
            return

        self._dots_key = key

        canvas.delete("dots")

        if key is None:
            return

        geom = self._clock

        if geom is None:
            return

        dots_x, dots_y = geom["dots"]

        diameter = 12
        gap = 10

        width = POMO_ROUNDS * diameter + (POMO_ROUNDS - 1) * gap
        height = diameter + 8

        current = (
            self.pomo_done
            if self.focus_phase == "focus"
            else -1
        )

        if not HAS_PIL:

            left = dots_x - width / 2
            top = dots_y - diameter / 2

            for i in range(POMO_ROUNDS):

                x = left + i * (diameter + gap)

                filled = i < self.pomo_done

                canvas.create_oval(
                    x, top, x + diameter, top + diameter,
                    fill=PURPLE_HOVER if filled else PANEL,
                    outline=PURPLE_HOVER if (filled or i == current)
                    else BORDER,
                    width=2,
                    tags="dots"
                )

            return

        scale = 4

        img = Image.new(
            "RGBA",
            ((width + 8) * scale, height * scale),
            (0, 0, 0, 0)
        )

        draw = ImageDraw.Draw(img)

        for i in range(POMO_ROUNDS):

            x = 4 + i * (diameter + gap)
            y = 4

            box = [
                x * scale,
                y * scale,
                (x + diameter) * scale,
                (y + diameter) * scale
            ]

            if i < self.pomo_done:

                draw.ellipse(box, fill=PURPLE_HOVER)

            elif i == current:

                draw.ellipse(
                    box,
                    fill=CHIP_BG,
                    outline=PURPLE_HOVER,
                    width=2 * scale
                )

            else:

                draw.ellipse(box, fill=HOVER_BG)

        img = img.resize(
            (width + 8, height),
            Image.LANCZOS
        )

        photo = ImageTk.PhotoImage(img)
        canvas.dots_photo = photo

        canvas.create_image(
            dots_x,
            dots_y,
            image=photo,
            tags="dots"
        )

    def pomodoro_popup(self, finished, next_phase):
        """Always-on-top popup between Pomodoro phases."""

        task = self._focus_task()

        win = tk.Toplevel(self)

        win.configure(bg=BG)
        win.attributes("-topmost", True)

        # A full focus round rings until you answer; the end of a
        # break is a single, gentler beep.
        self._attach_alarm(win, finished == "focus")

        self.center_window(win, 560, 230)

        if finished == "focus":

            if next_phase == "long":
                heading = "Set complete"
            else:
                heading = f"Round {self.pomo_done} done"

            win.title(heading)

            if next_phase == "long":

                summary = (
                    f"{POMO_ROUNDS} rounds finished. "
                    f"Take a {POMO_LONG // 60}-minute break."
                )

            else:

                summary = (
                    f"{self._focus_len_text()} focused. "
                    f"Take a {POMO_SHORT // 60}-minute break."
                )

            if task is not None:

                title = task["title"]

                if len(title) > 30:
                    title = title[:29] + "…"

                summary += f' You were working on "{title}".'

        else:

            heading = "Break's over"

            win.title(heading)

            summary = (
                f"Ready for round {self.pomo_done + 1} "
                f"of {POMO_ROUNDS}?"
            )

        tk.Label(
            win,
            text=heading,
            bg=BG,
            fg=TEXT,
            font=("Segoe UI", 18, "bold")
        ).pack(
            anchor="w",
            padx=28,
            pady=(28, 4)
        )

        tk.Label(
            win,
            text=summary,
            bg=BG,
            fg=MUTED,
            font=("Segoe UI", 10),
            wraplength=500,
            justify="left"
        ).pack(
            anchor="w",
            padx=28
        )

        bar = tk.Frame(win, bg=BG)

        bar.pack(
            side="bottom",
            fill="x",
            padx=28,
            pady=22
        )

        def start_next():

            win.destroy()

            if not self.focus_running:
                self.toggle_focus()

        def skip():

            win.destroy()
            self.skip_break()

        primary = self.make_button(
            bar,
            "Start break" if finished == "focus" else "Start focus",
            start_next,
            width=12
        )

        primary.configure(selected=True)

        primary.pack(
            side="right"
        )

        if finished == "focus":

            self.make_button(
                bar,
                "Skip break",
                skip,
                width=10
            ).pack(
                side="right",
                padx=8
            )

            if task is not None:

                def mark_done():

                    self.db.complete_task(task["id"])
                    self.focus_task_id = None
                    win.destroy()
                    self.show_page(self.current_page)

                self.make_button(
                    bar,
                    "Mark task done",
                    mark_done,
                    width=14
                ).pack(
                    side="left"
                )

        else:

            self.make_button(
                bar,
                "Dismiss",
                win.destroy,
                width=9
            ).pack(
                side="right",
                padx=8
            )

    # --------------------------------------------------------
    # Distraction nudge
    # --------------------------------------------------------

    def toggle_nudge(self):

        self.nudge_on = not self.nudge_on

        self.db.set_setting(
            "nudge_enabled",
            "1" if self.nudge_on else "0"
        )

        self._refresh_nudge_buttons()
        self._refresh_drawer_words()

    def _refresh_nudge_buttons(self):
        """Keep the Focus-page pill and the Settings button in step.
        Either may belong to a page that no longer exists."""

        try:

            self.focus_nudge_button.configure(
                text="On" if self.nudge_on else "Off",
                selected=self.nudge_on
            )

        except Exception:
            pass

        try:

            self.settings_nudge_button.configure(
                text="On" if self.nudge_on else "Off",
                selected=self.nudge_on
            )

        except Exception:
            pass

    def _maybe_nudge(self):
        """Called from the focus tick. Every few seconds, look at the
        window in front and nudge if it looks like a distraction."""

        if not self.nudge_on or self.focus_phase != "focus":
            return

        now = time.time()

        if now - self._nudge_last_poll < NUDGE_POLL_SECONDS:
            return

        self._nudge_last_poll = now

        if now < self._nudge_cooldown_until:
            return

        if self._nudge_popup is not None:

            try:

                if self._nudge_popup.winfo_exists():
                    return

            except Exception:
                pass

            self._nudge_popup = None

        title = foreground_window_title().lower()

        # Never nudge about Studestics itself.
        if not title or APP_NAME.lower() in title:
            return

        for word in self.nudge_words:

            if word and word in title:

                self._nudge_cooldown_until = (
                    now + NUDGE_COOLDOWN_SECONDS
                )

                self.focus_nudges += 1

                self.show_nudge(word)

                return

    def _nudge_beep(self):
        """One short beep that doesn't touch any other alarm."""

        def worker():

            try:

                import winsound

                winsound.Beep(900, 140)

            except Exception:
                pass

        threading.Thread(target=worker, daemon=True).start()

    def show_nudge(self, word):

        task = self._focus_task()

        win = tk.Toplevel(self)
        self._nudge_popup = win

        win.title("Back to focus")
        win.configure(bg=BG)
        win.attributes("-topmost", True)

        self.center_window(win, 460, 230)

        self._nudge_beep()

        tk.Label(
            win,
            text="Back to it",
            bg=BG,
            fg=TEXT,
            font=("Segoe UI", 18, "bold")
        ).pack(
            anchor="w",
            padx=28,
            pady=(28, 4)
        )

        lines = (
            f"That looks like {word.title()}, and your focus timer "
            f"is still running ({self.focus_time_text()} left)."
        )

        if task is not None:

            title = task["title"]

            if len(title) > 36:
                title = title[:35] + "…"

            lines += f'\n\nStill on: "{title}"'

        tk.Label(
            win,
            text=lines,
            bg=BG,
            fg=MUTED,
            font=("Segoe UI", 10),
            wraplength=400,
            justify="left"
        ).pack(
            anchor="w",
            padx=28
        )

        bar = tk.Frame(win, bg=BG)

        bar.pack(
            side="bottom",
            fill="x",
            padx=28,
            pady=22
        )

        primary = self.make_button(
            bar,
            "Back to focus",
            win.destroy,
            width=13
        )

        primary.configure(selected=True)

        primary.pack(
            side="right"
        )

        self.make_button(
            bar,
            "Open app",
            lambda: (self.restore_window(), win.destroy()),
            width=9
        ).pack(
            side="right",
            padx=8
        )

        # Don't nag: it goes away on its own if ignored.
        def auto_close():

            try:

                if win.winfo_exists():
                    win.destroy()

            except Exception:
                pass

        win.after(20000, auto_close)

    def edit_nudge_words(self):
        """Add and remove nudge words one at a time. Edits stay in a
        local list until Save, so Cancel throws them away."""

        win = tk.Toplevel(self)

        win.title("Distraction words")
        win.configure(bg=BG)
        win.transient(self)
        win.grab_set()

        self.center_window(win, 580, 520)

        words = list(self.nudge_words)

        tk.Label(
            win,
            text="Distraction words",
            bg=BG,
            fg=TEXT,
            font=("Segoe UI", 18, "bold")
        ).pack(
            anchor="w",
            padx=28,
            pady=(24, 4)
        )

        tk.Label(
            win,
            text=(
                "While the focus timer is running, if the window in "
                "front has one of these words in its title (like a "
                "website name in your browser tab), Studestics pops up "
                "a reminder of what you are working on. Click a word "
                "to remove it."
            ),
            bg=BG,
            fg=MUTED,
            font=("Segoe UI", 9),
            wraplength=520,
            justify="left"
        ).pack(
            anchor="w",
            padx=28,
            pady=(0, 14)
        )

        chips = tk.Frame(
            win,
            bg=BG
        )

        chips.pack(
            fill="x",
            anchor="n",
            padx=28
        )

        note = tk.Label(
            win,
            text="",
            bg=BG,
            fg=MUTED_2,
            font=("Segoe UI", 9)
        )

        note.pack(
            anchor="w",
            padx=28,
            pady=(4, 0)
        )

        sugg_label = tk.Label(
            win,
            text="",
            bg=BG,
            fg=MUTED,
            font=("Segoe UI", 9, "bold")
        )

        sugg_label.pack(
            anchor="w",
            padx=28,
            pady=(14, 2)
        )

        sugg = tk.Frame(
            win,
            bg=BG
        )

        sugg.pack(
            fill="x",
            anchor="n",
            padx=28
        )

        bar = tk.Frame(win, bg=BG)

        # Packed *before* the word lists so they keep their space on a
        # short window; the lists give way, never the buttons.
        bar.pack(
            side="bottom",
            fill="x",
            padx=28,
            pady=20,
            before=chips
        )

        add_row = tk.Frame(win, bg=BG)

        add_row.pack(
            side="bottom",
            fill="x",
            padx=28,
            pady=(0, 6),
            before=chips
        )

        chip_font = tkfont.Font(family="Segoe UI", size=10)

        def flow(frame, items):
            """Lay buttons out left to right, wrapping to a new row."""

            row = None
            used = 0

            for label, command, active in items:

                # Same padding RoundedButton adds, plus the gap.
                needed = chip_font.measure(label) + 26 + 8

                if row is None or used + needed > 520:

                    row = tk.Frame(
                        frame,
                        bg=BG
                    )

                    row.pack(
                        anchor="w",
                        pady=3
                    )

                    used = 0

                self.make_button(
                    row,
                    label,
                    command,
                    active=active
                ).pack(
                    side="left",
                    padx=(0, 8)
                )

                used += needed

        def render():

            for child in chips.winfo_children():
                child.destroy()

            for child in sugg.winfo_children():
                child.destroy()

            flow(
                chips,
                [
                    (f"{w}  ×", lambda w=w: remove(w), DANGER_HOVER)
                    for w in words
                ]
            )

            note.configure(
                text=(
                    ""
                    if words
                    else "No words yet, so you won't get any distraction alerts."
                )
            )

            # Eight at a time keeps the dialog compact; adding one
            # slides the next suggestion in.
            available = [
                w for w in NUDGE_SUGGESTIONS if w not in words
            ][:8]

            sugg_label.configure(
                text="Quick add" if available else ""
            )

            flow(
                sugg,
                [
                    (f"+ {w}", lambda w=w: add_word(w), PURPLE_HOVER)
                    for w in available
                ]
            )

        def remove(word):

            if word in words:
                words.remove(word)

            render()

        def add_word(word):

            if word not in words:
                words.append(word)

            render()

        var = tk.StringVar()

        entry = self.make_entry(
            add_row,
            textvariable=var
        )

        entry.pack(
            side="left",
            fill="x",
            expand=True,
            ipady=8
        )

        def add(event=None):

            # Commas work too, so "reddit, whatsapp" adds both.
            for word in parse_words(var.get()):

                if word not in words:
                    words.append(word)

            var.set("")

            render()

            entry.focus_set()

        entry.bind("<Return>", add)

        self.make_button(
            add_row,
            "Add",
            add,
            width=8
        ).pack(
            side="left",
            padx=(8, 0)
        )

        def reset_defaults():

            words[:] = parse_words(DEFAULT_NUDGE_WORDS)

            render()

        def save():

            self.nudge_words = list(words)

            self.db.set_setting(
                "nudge_words",
                ", ".join(words)
            )

            self._refresh_drawer_words()

            win.destroy()

        save_button = self.make_button(
            bar,
            "Save",
            save,
            width=9
        )

        save_button.configure(selected=True)

        save_button.pack(
            side="right"
        )

        self.make_button(
            bar,
            "Cancel",
            win.destroy,
            width=9
        ).pack(
            side="right",
            padx=8
        )

        self.make_button(
            bar,
            "Reset to defaults",
            reset_defaults,
            width=15
        ).pack(
            side="left"
        )

        render()

        entry.focus_set()

    def focus_session_complete(self):
        """Alarm + always-on-top popup when a focus session ends."""

        task = self._focus_task()

        win = tk.Toplevel(self)

        win.title("Focus session complete")

        self._attach_alarm(win, True)
        win.configure(bg=BG)
        win.attributes("-topmost", True)

        self.center_window(win, 460, 220)

        tk.Label(
            win,
            text="Focus session complete",
            bg=BG,
            fg=TEXT,
            font=("Segoe UI", 18, "bold")
        ).pack(
            anchor="w",
            padx=28,
            pady=(28, 4)
        )

        summary = f"{self._focus_len_text()} done."

        if task is not None:

            title = task["title"]

            if len(title) > 30:
                title = title[:29] + "…"

            summary += f' You were working on "{title}".'

        tk.Label(
            win,
            text=summary,
            bg=BG,
            fg=MUTED,
            font=("Segoe UI", 10),
            wraplength=400,
            justify="left"
        ).pack(
            anchor="w",
            padx=28
        )

        bar = tk.Frame(win, bg=BG)

        bar.pack(
            side="bottom",
            fill="x",
            padx=28,
            pady=22
        )

        self.make_button(
            bar,
            "Dismiss",
            win.destroy,
            width=9
        ).pack(
            side="right"
        )

        if task is not None:

            def mark_done():

                self.db.complete_task(task["id"])
                self.focus_task_id = None
                win.destroy()
                self.show_page(self.current_page)

            self.make_button(
                bar,
                "Mark task done",
                mark_done,
                width=14
            ).pack(
                side="right",
                padx=8
            )

        else:

            self.make_button(
                bar,
                "Open app",
                lambda: (self.restore_window(), win.destroy()),
                width=9
            ).pack(
                side="right",
                padx=8
            )

    def update_focus_ui(self):

        try:

            self.focus_timer_label.configure(
                text=self.focus_time_text()
            )

        except Exception:
            pass

        try:

            if self.focus_finished:

                self.focus_status_label.configure(
                    text="Session complete ✓",
                    fg=GREEN
                )

            else:

                running_text, ready_text = {
                    "focus": ("Focusing", "Ready"),
                    "short": ("Short break", "Break ready"),
                    "long": ("Long break", "Break ready")
                }.get(self.focus_phase, ("Focusing", "Ready"))

                self.focus_status_label.configure(
                    text=(
                        running_text
                        if self.focus_running
                        else ready_text
                    ),
                    fg=MUTED
                )

        except Exception:
            pass

        try:

            wanted = "Pause" if self.focus_running else "Start"

            # Re-rendering the button every tick is wasteful.
            if self.focus_start_button.cget("text") != wanted:

                self.focus_start_button.configure(
                    text=wanted
                )

        except Exception:
            pass

        try:
            self.focus_draw_ring()
        except Exception:
            pass

        try:
            self.focus_draw_dots()
        except Exception:
            pass

        try:

            wanted = (
                "Skip break"
                if self.pomo_enabled and self.focus_phase != "focus"
                else "Reset"
            )

            if self.focus_reset_button.cget("text") != wanted:

                self.focus_reset_button.configure(
                    text=wanted
                )

        except Exception:
            pass

        self._float_update()
        self._sidebar_timer_update()

    # ========================================================
    # AI CHAT
    # ========================================================

    def build_chat(self):

        self.page_header(
            "AI Chat",
            "Your study assistant, powered by Gemini."
        )

        outer = tk.Frame(
            self.page,
            bg=PANEL,
            highlightthickness=1,
            highlightbackground=BORDER
        )

        outer.pack(
            fill="both",
            expand=True
        )

        header = tk.Frame(
            outer,
            bg=PANEL
        )

        header.pack(
            fill="x",
            padx=18,
            pady=(15, 10)
        )

        tk.Label(
            header,
            text="Studestics AI",
            bg=PANEL,
            fg=TEXT,
            font=("Segoe UI", 12, "bold")
        ).pack(
            side="left"
        )

        self.chat_status = tk.Label(
            header,
            text="Ready",
            bg=PANEL,
            fg=MUTED,
            font=("Segoe UI", 8)
        )

        self.chat_status.pack(
            side="left",
            padx=10
        )

        self.make_button(
            header,
            "Clear Chat",
            self.clear_chat,
            width=10
        ).pack(
            side="right"
        )

        # Chat area

        chat_area = tk.Frame(
            outer,
            bg=PANEL
        )

        chat_area.pack(
            fill="both",
            expand=True
        )

        self.chat_canvas = tk.Canvas(
            chat_area,
            bg=PANEL,
            highlightthickness=0
        )

        self.chat_body = tk.Frame(
            self.chat_canvas,
            bg=PANEL
        )

        self.chat_body.bind(
            "<Configure>",
            lambda event:
                self.chat_canvas.configure(
                    scrollregion=self.chat_canvas.bbox("all")
                )
        )

        self.chat_canvas_window = self.chat_canvas.create_window(
            (0, 0),
            window=self.chat_body,
            anchor="nw"
        )

        self.chat_canvas.bind(
            "<Configure>",
            lambda event:
                self.chat_canvas.itemconfigure(
                    self.chat_canvas_window,
                    width=event.width
                )
        )

        self.chat_canvas.pack(
            side="left",
            fill="both",
            expand=True
        )

        self._bind_mousewheel(self.chat_canvas)

        messages = self.db.get_messages()

        if not messages:

            self.add_chat_bubble(
                "assistant",
                "Hey! I'm Studestics AI.\n\n"
                "Ask me about your studies, "
                "planning, assignments or goals."
            )

        else:

            for message in messages:

                self.add_chat_bubble(
                    message["role"],
                    message["content"]
                )

        # Input

        input_area = tk.Frame(
            outer,
            bg=PANEL
        )

        input_area.pack(
            fill="x",
            padx=15,
            pady=15
        )

        self.chat_input = tk.Text(
            input_area,
            height=1,
            bg=PANEL_2,
            fg=MUTED_2,
            insertbackground=TEXT,
            selectbackground=PURPLE_HOVER,
            selectforeground=TEXT,
            inactiveselectbackground=PURPLE_HOVER,
            relief="flat",
            bd=0,
            font=("Segoe UI", 10),
            wrap="word",
            highlightthickness=1,
            highlightbackground=BORDER,
            highlightcolor=PURPLE,
            padx=12,
            pady=9,
            undo=True,
            autoseparators=True,
            maxundo=-1
        )

        self.chat_input.pack(
            side="left",
            fill="both",
            expand=True
        )

        self.chat_placeholder_active = False

        self.show_chat_placeholder()

        self.chat_input.bind(
            "<Key>",
            self.on_chat_key_press
        )

        self.chat_input.bind(
            "<FocusOut>",
            self.restore_chat_placeholder_if_empty
        )

        self.chat_input.bind(
            "<<Modified>>",
            self.on_chat_input_changed
        )

        self.chat_input.bind(
            "<Return>",
            self.chat_enter
        )

        self.chat_input.bind(
            "<Shift-Return>",
            self.chat_shift_enter
        )

        self._bind_text_shortcuts(self.chat_input)

        self.chat_send_button = self.make_button(
            input_area,
            "Send",
            self.send_chat,
            width=9
        )

        self.chat_send_button.pack(
            side="right",
            padx=(10, 0),
            fill="y"
        )

        if HAS_PIL:

            self.chat_emoji_button = self.make_button(
                input_area,
                "",
                self.open_emoji_picker,
                width=6
            )

            smile = emoji_image("😊", 24)

            if smile is not None:

                self.chat_emoji_button.icon = ImageTk.PhotoImage(smile)

                self.chat_emoji_button._redraw()

            self.chat_emoji_button.pack(
                side="right",
                padx=(10, 0),
                fill="y"
            )

        self.chat_input.focus_set()

        self.after(
            50,
            self.scroll_chat
        )

        if self.chat_busy:

            self.start_typing_animation()

    def _rounded_rect(
        self,
        canvas,
        x1, y1, x2, y2,
        r,
        **kwargs
    ):

        points = [
            x1 + r, y1,
            x2 - r, y1,
            x2, y1,
            x2, y1 + r,
            x2, y2 - r,
            x2, y2,
            x2 - r, y2,
            x1 + r, y2,
            x1, y2,
            x1, y2 - r,
            x1, y1 + r,
            x1, y1,
        ]

        return canvas.create_polygon(
            points,
            smooth=True,
            **kwargs
        )

    def _draw_bubble_background(
        self,
        canvas,
        width,
        height,
        radius,
        color
    ):
        """Draws the bubble's rounded-rect background.

        Plain Tkinter Canvas polygons have no anti-aliasing, so rounded
        corners look visibly jagged/"pixelated" — this renders the
        shape at 4x resolution with Pillow and downsamples it, which
        gives genuinely smooth edges. Falls back to a plain polygon if
        Pillow isn't installed.
        """

        if HAS_PIL and width > 2 and height > 2:

            scale = 4
            big_w, big_h = int(width * scale), int(height * scale)

            img = Image.new("RGBA", (big_w, big_h), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)

            draw.rounded_rectangle(
                [0, 0, big_w - 1, big_h - 1],
                radius=int(radius * scale),
                fill=color
            )

            img = img.resize((width, height), Image.LANCZOS)

            photo = ImageTk.PhotoImage(img)

            # Keep a reference on the canvas itself — otherwise Python's
            # garbage collector drops the image and the bubble goes
            # blank the moment this function returns.
            canvas.bubble_photo = photo

            canvas.create_image(0, 0, anchor="nw", image=photo)

        else:

            self._rounded_rect(
                canvas,
                1, 1, width - 1, height - 1,
                radius,
                fill=color,
                outline=""
            )

    def _draw_logo_badge(
        self,
        canvas,
        size=40
    ):
        """The app's logo mark: an anti-aliased rounded square instead
        of the plain flat-cornered square it was before."""

        if HAS_PIL and size > 2:

            scale = 4
            big = size * scale

            img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)

            draw.rounded_rectangle(
                [0, 0, big - 1, big - 1],
                radius=int(big * 0.28),
                fill=PURPLE
            )

            img = img.resize((size, size), Image.LANCZOS)

            photo = ImageTk.PhotoImage(img)

            canvas.logo_photo = photo

            canvas.create_image(0, 0, anchor="nw", image=photo)

        else:

            canvas.create_rectangle(
                0, 0, size, size,
                fill=PURPLE,
                outline=""
            )

        badge_font = tkfont.Font(
            family="Segoe UI",
            size=int(size * 0.42),
            weight="bold"
        )

        # Tk centers text using the font's full ascent+descent box, but
        # a bare capital letter has no descender ink — that empty
        # descent space pulls the glyph's visual position down/off-
        # center. Shift it up using the font's own reported descent so
        # this adapts correctly to whatever font actually gets used.
        descent = badge_font.metrics("descent")

        canvas.create_text(
            size / 2, (size / 2) - (descent / 2),
            text="S",
            font=badge_font,
            fill="#FFFFFF"
        )

    def _draw_avatar(
        self,
        canvas,
        size=28
    ):
        """Draws the Studestics AI avatar: a purple circle with a
        4-point sparkle icon — anti-aliased via Pillow when available,
        so it doesn't get the jagged edges plain canvas circles have.
        """

        def sparkle_points(cx, cy, s):

            return [
                cx, cy - s,
                cx + s * 0.32, cy - s * 0.32,
                cx + s, cy,
                cx + s * 0.32, cy + s * 0.32,
                cx, cy + s,
                cx - s * 0.32, cy + s * 0.32,
                cx - s, cy,
                cx - s * 0.32, cy - s * 0.32,
            ]

        if HAS_PIL and size > 2:

            scale = 4
            big = size * scale

            img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)

            draw.ellipse(
                [0, 0, big - 1, big - 1],
                fill=PURPLE_HOVER
            )

            cx = cy = big / 2
            s = big * 0.28

            draw.polygon(
                sparkle_points(cx, cy, s),
                fill="#FFFFFF"
            )

            img = img.resize((size, size), Image.LANCZOS)

            photo = ImageTk.PhotoImage(img)

            # Keep a reference or the image gets garbage-collected and
            # the avatar goes blank.
            canvas.avatar_photo = photo

            canvas.create_image(0, 0, anchor="nw", image=photo)

        else:

            canvas.create_oval(
                1, 1, size - 1, size - 1,
                fill=PURPLE_HOVER,
                outline=""
            )

            cx = cy = size / 2
            s = size * 0.28

            canvas.create_polygon(
                sparkle_points(cx, cy, s),
                fill="#FFFFFF",
                outline=""
            )

    def _tokenize_bold(self, text):
        """Split a line into (word, is_bold) tokens based on **spans**."""

        tokens = []
        pos = 0

        for match in re.finditer(r"\*\*(.+?)\*\*", text):

            if match.start() > pos:

                for word in text[pos:match.start()].split():
                    tokens.append((word, False))

            for word in match.group(1).split():
                tokens.append((word, True))

            pos = match.end()

        if pos < len(text):

            for word in text[pos:].split():
                tokens.append((word, False))

        return tokens

    def _word_width(self, word, font_obj):
        """Width of a word, with each emoji counted as a square."""

        if not has_emoji(word):
            return font_obj.measure(word)

        box = font_obj.metrics("linespace")

        width = 0

        for piece, is_emoji in emoji_segments(word):

            width += (
                box + 2 if is_emoji else font_obj.measure(piece)
            )

        return width

    def _wrap_tokens(
        self,
        tokens,
        regular_font,
        bold_font,
        max_width
    ):

        if not tokens:
            return [[]]

        space_w = regular_font.measure(" ")
        lines = []
        current = []
        current_width = 0

        for word, is_bold in tokens:

            font_obj = bold_font if is_bold else regular_font
            word_w = self._word_width(word, font_obj)
            add_w = word_w + (space_w if current else 0)

            if current and current_width + add_w > max_width:

                lines.append(current)
                current = [(word, is_bold)]
                current_width = word_w

            else:

                current.append((word, is_bold))
                current_width += add_w

        if current:
            lines.append(current)

        return lines

    def _layout_markdown_lite(
        self,
        content,
        regular_font,
        bold_font,
        max_text_width
    ):
        """Turn Gemini's lightly-markdown'd text into wrapped render lines.

        Handles **bold** spans (including mixed bold/regular on one line,
        e.g. "**Label:** value") and "* "/"- "/"1. " list markers (turned
        into a bullet + indent). Returns a list of (tokens, indent) where
        tokens is a list of (word, is_bold) pairs for one visual line.
        """

        list_marker = re.compile(r"^(\d+\.|\*|-)\s+")

        render_lines = []

        for raw_line in content.split("\n"):

            stripped = raw_line.strip()

            if stripped == "":
                render_lines.append(([], 0))
                continue

            indent = 0
            prefix = []

            if list_marker.match(stripped):

                stripped = list_marker.sub("", stripped, count=1)
                indent = 14
                prefix = [("•", False)]

            tokens = prefix + self._tokenize_bold(stripped)

            wrapped = self._wrap_tokens(
                tokens,
                regular_font,
                bold_font,
                max_text_width - indent
            )

            for line_tokens in wrapped:
                render_lines.append((line_tokens, indent))

        return render_lines or [([], 0)]

    def _draw_bubble(
        self,
        canvas,
        content,
        bg_color,
        fg_color
    ):

        regular_font = tkfont.Font(family="Segoe UI", size=10)
        bold_font = tkfont.Font(family="Segoe UI", size=10, weight="bold")

        pad_x, pad_y, line_gap = 16, 12, 5
        max_text_width = 440

        render_lines = self._layout_markdown_lite(
            content,
            regular_font,
            bold_font,
            max_text_width
        )

        line_height = regular_font.metrics("linespace") + line_gap
        space_w = regular_font.measure(" ")

        def line_width(tokens, indent):

            width = indent
            first = True

            for word, is_bold in tokens:

                font_obj = bold_font if is_bold else regular_font

                width += self._word_width(word, font_obj) + (
                    0 if first else space_w
                )

                first = False

            return width

        content_width = max(
            (
                line_width(tokens, indent)
                for tokens, indent in render_lines
            ),
            default=40
        )

        canvas_w = min(max_text_width, content_width) + pad_x * 2
        canvas_h = (
            len(render_lines) * line_height
            + pad_y * 2
            - line_gap
        )

        canvas.delete("all")

        canvas.configure(
            width=canvas_w,
            height=canvas_h,
            bg=PANEL,
            highlightthickness=0,
            bd=0
        )

        self._rounded_rect(
            canvas,
            1, 1, canvas_w - 1, canvas_h - 1,
            16,
            fill=bg_color,
            outline=""
        )

        y = pad_y

        words = []

        for line_no, (tokens, indent) in enumerate(render_lines):

            x = pad_x + indent
            first = True

            for word, is_bold in tokens:

                font_obj = bold_font if is_bold else regular_font

                if not first:
                    x += space_w

                if has_emoji(word):

                    self._draw_emoji_word(
                        canvas, word, x, y, font_obj, fg_color
                    )

                else:

                    canvas.create_text(
                        x,
                        y,
                        text=word,
                        anchor="nw",
                        font=font_obj,
                        fill=fg_color,
                        tags="word"
                    )

                word_w = self._word_width(word, font_obj)

                words.append({
                    "x": x,
                    "y": y,
                    "w": word_w,
                    "h": line_height - line_gap,
                    "text": word,
                    "line": line_no
                })

                x += word_w
                first = False

            y += line_height

        self._bubble_selectable(canvas, words, space_w)

    def _draw_emoji_word(self, canvas, word, x, y, font_obj, fg_color):
        """A word containing emoji: text pieces as text, emoji as
        small images."""

        box = font_obj.metrics("linespace")

        if not hasattr(canvas, "_emoji_photos"):
            canvas._emoji_photos = []

        for piece, is_emoji in emoji_segments(word):

            if is_emoji:

                pil = emoji_image(piece, box)

                if pil is not None:

                    photo = ImageTk.PhotoImage(pil)

                    canvas._emoji_photos.append(photo)

                    canvas.create_image(
                        x, y,
                        anchor="nw",
                        image=photo,
                        tags="word"
                    )

                else:

                    canvas.create_text(
                        x, y,
                        text="\u25AF",
                        anchor="nw",
                        font=font_obj,
                        fill=fg_color,
                        tags="word"
                    )

                x += box + 2

            else:

                canvas.create_text(
                    x,
                    y,
                    text=piece,
                    anchor="nw",
                    font=font_obj,
                    fill=fg_color,
                    tags="word"
                )

                x += font_obj.measure(piece)

    def _bubble_selectable(self, canvas, words, space_w):
        """Drag to select text in a chat bubble, double-click for a
        word, Ctrl+C to copy. The bubble is drawn word by word on a
        canvas, so selection is done here by hand."""

        canvas._words = words
        canvas._sel = None

        if getattr(canvas, "_sel_bound", False):
            return

        canvas._sel_bound = True

        try:
            canvas.configure(cursor="xterm")
        except Exception:
            pass

        drag = {"a": None, "moved": False}

        def hit(x, y):

            best = None
            best_score = None

            for index, w in enumerate(canvas._words):

                dy = 0

                if y < w["y"]:
                    dy = w["y"] - y

                elif y > w["y"] + w["h"] + 5:
                    dy = y - (w["y"] + w["h"] + 5)

                dx = 0

                if x < w["x"]:
                    dx = w["x"] - x

                elif x > w["x"] + w["w"]:
                    dx = x - (w["x"] + w["w"])

                score = dy * 1000 + dx

                if best_score is None or score < best_score:

                    best_score = score
                    best = index

            return best

        def paint():

            canvas.delete("sel")

            if canvas._sel is None:
                return

            lo, hi = sorted(canvas._sel)

            for index in range(lo, hi + 1):

                w = canvas._words[index]

                x2 = w["x"] + w["w"]

                if index < hi:

                    nxt = canvas._words[index + 1]

                    if nxt["line"] == w["line"]:
                        x2 = nxt["x"]

                canvas.create_rectangle(
                    w["x"] - 1,
                    w["y"] - 1,
                    x2,
                    w["y"] + w["h"] + 2,
                    fill="#2F6FEB",
                    outline="",
                    tags="sel"
                )

            try:
                canvas.tag_lower("sel", "word")
            except Exception:
                pass

        def selected_text():

            if canvas._sel is None:
                return ""

            lo, hi = sorted(canvas._sel)

            out = ""

            last_line = None

            for index in range(lo, hi + 1):

                w = canvas._words[index]

                if last_line is not None:

                    out += "\n" * (w["line"] - last_line) if (
                        w["line"] != last_line
                    ) else " "

                out += w["text"]

                last_line = w["line"]

            return out

        def clear_others():

            other = getattr(self, "_selected_bubble", None)

            if other is not None and other is not canvas:

                try:

                    other._sel = None
                    other.delete("sel")

                except Exception:
                    pass

            self._selected_bubble = canvas

        def press(event):

            canvas.focus_set()

            clear_others()

            index = hit(event.x, event.y)

            drag["a"] = index
            drag["moved"] = False

            canvas._sel = None

            paint()

        def motion(event):

            if drag["a"] is None:
                return

            index = hit(event.x, event.y)

            if index is None:
                return

            if index != drag["a"]:
                drag["moved"] = True

            if drag["moved"]:

                canvas._sel = (drag["a"], index)

                paint()

        def double(event):

            index = hit(event.x, event.y)

            if index is None:
                return

            canvas._sel = (index, index)

            paint()

        def copy(event=None):

            text = selected_text()

            if not text:
                return "break"

            try:

                self.clipboard_clear()
                self.clipboard_append(text)

            except Exception:
                pass

            return "break"

        canvas.bind("<Button-1>", press)
        canvas.bind("<B1-Motion>", motion)
        canvas.bind("<Double-Button-1>", double)
        canvas.bind("<Control-c>", copy)
        canvas.bind("<Control-C>", copy)

    def create_bubble_canvas(
        self,
        parent,
        content,
        bg_color,
        fg_color
    ):

        canvas = tk.Canvas(
            parent,
            bg=PANEL,
            highlightthickness=0,
            bd=0
        )

        self._draw_bubble(
            canvas,
            content,
            bg_color,
            fg_color
        )

        return canvas

    def add_chat_bubble(
        self,
        role,
        content
    ):

        if not self.chat_body:
            return None

        is_user = role == "user"
        bg_color = PURPLE if is_user else PANEL_2
        fg_color = TEXT

        row = tk.Frame(
            self.chat_body,
            bg=PANEL
        )

        row.pack(
            fill="x",
            padx=12,
            pady=5
        )

        holder = tk.Frame(
            row,
            bg=PANEL
        )

        if is_user:

            holder.pack(
                side="right",
                padx=(80, 0)
            )

        else:

            avatar = tk.Canvas(
                row,
                width=28,
                height=28,
                bg=PANEL,
                highlightthickness=0
            )

            avatar.pack(
                side="left",
                anchor="s",
                padx=(0, 8)
            )

            self._draw_avatar(avatar, size=28)

            holder.pack(
                side="left",
                padx=(0, 80)
            )

        canvas = self.create_bubble_canvas(
            holder,
            content,
            bg_color,
            fg_color
        )

        canvas.pack()

        return canvas

    def _bind_mousewheel(self, canvas):

        def on_enter(event):
            canvas.bind_all(
                "<MouseWheel>",
                lambda e: canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
            )
            canvas.bind_all("<Button-4>", lambda e: canvas.yview_scroll(-1, "units"))
            canvas.bind_all("<Button-5>", lambda e: canvas.yview_scroll(1, "units"))

        def on_leave(event):
            canvas.unbind_all("<MouseWheel>")
            canvas.unbind_all("<Button-4>")
            canvas.unbind_all("<Button-5>")

        canvas.bind("<Enter>", on_enter)
        canvas.bind("<Leave>", on_leave)

    def scroll_chat(self):

        try:

            # Packing a new bubble doesn't resize chat_body synchronously —
            # Tk defers that to the next idle cycle, and the scrollregion
            # only gets recalculated when chat_body's <Configure> event
            # fires after that. Scrolling immediately after adding a
            # message was therefore scrolling against the OLD (too short)
            # scrollregion, landing just short of the real bottom.
            self.chat_body.update_idletasks()

            self.chat_canvas.configure(
                scrollregion=self.chat_canvas.bbox("all")
            )

            self.chat_canvas.yview_moveto(1.0)

        except Exception:
            pass

    # --------------------------------------------------------
    # Thinking dots
    # --------------------------------------------------------

    def create_typing_bubble(self):

        if not self.chat_body:
            return

        row = tk.Frame(
            self.chat_body,
            bg=PANEL
        )

        row.pack(
            fill="x",
            padx=12,
            pady=5
        )

        avatar = tk.Canvas(
            row,
            width=28,
            height=28,
            bg=PANEL,
            highlightthickness=0
        )

        avatar.pack(
            side="left",
            anchor="s",
            padx=(0, 8)
        )

        self._draw_avatar(avatar, size=28)

        holder = tk.Frame(
            row,
            bg=PANEL
        )

        holder.pack(
            side="left",
            padx=(0, 80)
        )

        dots_w, dots_h = 56, 34

        canvas = tk.Canvas(
            holder,
            width=dots_w,
            height=dots_h,
            bg=PANEL,
            highlightthickness=0,
            bd=0
        )

        canvas.pack()

        self._draw_bubble_background(
            canvas,
            dots_w,
            dots_h,
            16,
            PANEL_2
        )

        dot_ids = []

        for _ in range(3):

            dot_ids.append(
                canvas.create_oval(
                    0, 0, 0, 0,
                    fill=MUTED,
                    outline=""
                )
            )

        self.typing_row = row
        self.typing_canvas = canvas
        self.typing_dot_ids = dot_ids
        self.typing_phase = 0.0

        self._render_typing_dots()

    def _render_typing_dots(self):

        if not self.typing_canvas or not self.typing_dot_ids:
            return

        base_y = 17
        spacing = 13
        start_x = 15
        radius = 3

        for i, dot_id in enumerate(self.typing_dot_ids):

            phase = self.typing_phase - (i * 0.7)
            wave = max(0.0, math.sin(phase))
            offset = wave * 5

            cx = start_x + i * spacing
            cy = base_y - offset

            try:

                self.typing_canvas.coords(
                    dot_id,
                    cx - radius, cy - radius,
                    cx + radius, cy + radius
                )

            except Exception:
                pass

    def remove_typing_bubble(self):

        if self.typing_row:

            try:
                self.typing_row.destroy()
            except Exception:
                pass

        self.typing_row = None
        self.typing_canvas = None
        self.typing_dot_ids = []

        if self.chat_typing_job:

            try:

                self.after_cancel(
                    self.chat_typing_job
                )

            except Exception:
                pass

            self.chat_typing_job = None

    def start_typing_animation(self):

        if not self.chat_busy:
            return

        if not self.typing_canvas:

            self.create_typing_bubble()

            self.scroll_chat()

        self.typing_phase += 0.5

        self._render_typing_dots()

        self.chat_typing_job = self.after(
            90,
            self.start_typing_animation
        )

    # --------------------------------------------------------
    # Standard text-editing shortcuts
    # --------------------------------------------------------

    def _bind_text_shortcuts(self, text_widget):
        """Ctrl+X/C/V already work — Tk binds cut/copy/paste to those
        keys on every platform out of the box. What Tk does NOT do by
        default is what Windows/Mac users actually expect from the rest:
        it uses old Emacs-style bindings instead, where Ctrl+A jumps to
        the start of the line (not select-all), Ctrl+Z does nothing
        unless undo=True is set, and Ctrl+Y means "paste" (not redo).
        This overrides those with the familiar behavior.
        """

        def undo(event):
            try:
                text_widget.edit_undo()
            except tk.TclError:
                pass
            return "break"

        def redo(event):
            try:
                text_widget.edit_redo()
            except tk.TclError:
                pass
            return "break"

        def select_all(event):
            text_widget.tag_add("sel", "1.0", "end-1c")
            text_widget.mark_set("insert", "end-1c")
            return "break"

        def delete_word_backward(event):
            text_widget.delete("insert -1c wordstart", "insert")
            return "break"

        def delete_word_forward(event):
            text_widget.delete("insert", "insert wordend")
            return "break"

        def delete_selection_then_backspace(event):
            sel_range = text_widget.tag_ranges("sel")
            if sel_range:
                text_widget.delete(sel_range[0], sel_range[1])
                return "break"
            return None

        def delete_selection_then_delete(event):
            sel_range = text_widget.tag_ranges("sel")
            if sel_range:
                text_widget.delete(sel_range[0], sel_range[1])
                return "break"
            return None

        text_widget.bind("<BackSpace>", delete_selection_then_backspace)
        text_widget.bind("<Delete>", delete_selection_then_delete)

        text_widget.bind("<Control-z>", undo)
        text_widget.bind("<Control-Z>", redo)          # Ctrl+Shift+Z
        text_widget.bind("<Control-Shift-Z>", redo)
        text_widget.bind("<Control-y>", redo)          # common Windows redo shortcut
        text_widget.bind("<Control-a>", select_all)
        text_widget.bind("<Control-BackSpace>", delete_word_backward)
        text_widget.bind("<Control-Delete>", delete_word_forward)

    # --------------------------------------------------------
    # Chat input placeholder + autosize
    # --------------------------------------------------------

    CHAT_PLACEHOLDER_TEXT = "Message Studestics AI..."

    CHAT_PLACEHOLDER_IGNORE_KEYS = {
        "Shift_L", "Shift_R", "Control_L", "Control_R",
        "Alt_L", "Alt_R", "Caps_Lock", "Tab", "Escape",
        "Left", "Right", "Up", "Down", "Home", "End",
        "Prior", "Next"
    }

    def show_chat_placeholder(self):

        self.chat_input.delete("1.0", "end")
        self.chat_input.insert("1.0", self.CHAT_PLACEHOLDER_TEXT)
        self.chat_input.mark_set("insert", "1.0")
        self.chat_input.configure(fg=MUTED_2, height=1)
        self.chat_placeholder_active = True
        self.chat_input.edit_modified(False)
        self.chat_input.edit_reset()

    def clear_chat_placeholder(self):

        if self.chat_placeholder_active:

            self.chat_input.delete("1.0", "end")
            self.chat_input.configure(fg=TEXT)
            self.chat_placeholder_active = False
            self.chat_input.edit_reset()

    def restore_chat_placeholder_if_empty(self, event=None):

        if self.chat_input.get("1.0", "end-1c") == "":
            self.show_chat_placeholder()

    _REGULAR_TYPING_EXCLUDE = {"Return", "Tab", "BackSpace", "Delete"}

    def on_chat_key_press(self, event):

        control_held = bool(event.state & 0x4)

        if (
            self.chat_placeholder_active
            and not control_held
            and event.keysym not in self.CHAT_PLACEHOLDER_IGNORE_KEYS
        ):
            self.clear_chat_placeholder()

        # Tk's Text widget does NOT replace a selection when you type
        # over it — the old selected text just stays there, highlighted,
        # next to whatever you typed. This is what caused the stuck
        # blue highlight. Every modern text box replaces the selection,
        # so we do it explicitly here.
        if (
            event.char
            and event.keysym not in self._REGULAR_TYPING_EXCLUDE
            and not control_held
        ):

            sel_range = self.chat_input.tag_ranges("sel")

            if sel_range:
                self.chat_input.delete(sel_range[0], sel_range[1])

    def autosize_chat_input(self):

        self.chat_input.edit_modified(False)

        if self.chat_placeholder_active:
            return

        display_lines = int(
            self.chat_input.index("end-1c").split(".")[0]
        )

        new_height = min(
            max(display_lines, 1),
            6
        )

        if int(self.chat_input.cget("height")) != new_height:

            self.chat_input.configure(
                height=new_height
            )

    def on_chat_input_changed(self, event=None):

        self.autosize_chat_input()

        try:
            self._convert_typed_emoji()
        except Exception:
            pass

    def get_chat_input_text(self):
        """Safe read of the chat box — returns '' while the placeholder
        is showing, so it can never be sent as a real message."""

        if self.chat_placeholder_active:
            return ""

        return self._chat_input_string().strip()

    def _chat_input_pieces(self):
        """The message box as [(text, is_emoji)], reading embedded
        emoji images back into their real characters."""

        pieces = []

        try:

            items = self.chat_input.dump(
                "1.0", "end-1c", text=True, image=True
            )

        except Exception:

            items = [("text", self.chat_input.get("1.0", "end-1c"), "1.0")]

        for kind, value, _index in items:

            if kind == "text":

                try:
                    value = value.encode(
                        "utf-16", "surrogatepass"
                    ).decode("utf-16", "replace")
                except Exception:
                    pass

                pieces.append((value, False))

            elif kind == "image":

                char = self._emoji_chars.get(value, "")

                if char:
                    pieces.append((char, True))

        return pieces

    def _chat_input_string(self):

        return "".join(text for text, _ in self._chat_input_pieces())

    def _put_emoji_image(self, char):

        pil = emoji_image(char, 20)

        if pil is None:

            self.chat_input.insert("insert", char)

            return

        photo = ImageTk.PhotoImage(pil)

        name = self.chat_input.image_create(
            "insert",
            image=photo,
            padx=1
        )

        self._emoji_photos[name] = photo
        self._emoji_chars[name] = char

    def insert_emoji(self, char):

        if self.chat_placeholder_active:
            self.clear_chat_placeholder()

        self._put_emoji_image(char)

        self.chat_input.focus_set()

        self.autosize_chat_input()

    def _convert_typed_emoji(self):
        """Emoji typed or pasted (Win + .) arrive as characters Tk
        can't draw; swap them for images."""

        if self.chat_placeholder_active:
            return

        pieces = self._chat_input_pieces()

        if not any(
            has_emoji(text) or any(0xD800 <= ord(c) <= 0xDFFF for c in text)
            for text, is_emoji in pieces
            if not is_emoji
        ):
            return

        self.chat_input.delete("1.0", "end")

        for text, is_emoji in pieces:

            if is_emoji:

                self._put_emoji_image(text)

                continue

            for part, part_is_emoji in emoji_segments(text):

                if part_is_emoji:
                    self._put_emoji_image(part)
                elif part:
                    self.chat_input.insert("insert", part)

        self.chat_input.mark_set("insert", "end-1c")

    def open_emoji_picker(self):

        old = getattr(self, "_emoji_popup", None)

        if old is not None:

            try:
                old.destroy()
            except Exception:
                pass

            self._emoji_popup = None

            return

        popup = tk.Toplevel(self)

        popup.overrideredirect(True)

        popup.configure(bg=BORDER)

        self._emoji_popup = popup

        body = tk.Frame(popup, bg=PANEL_2)

        body.pack(padx=1, pady=1)

        tabs = tk.Frame(body, bg=PANEL_2)

        tabs.pack(fill="x", padx=8, pady=(8, 2))

        for column in range(4):
            tabs.grid_columnconfigure(column, weight=1, uniform="emoji_tab")

        grid = tk.Frame(body, bg=PANEL_2)

        grid.pack(padx=8, pady=(4, 8))

        title = tk.Label(
            body,
            text="",
            bg=PANEL_2,
            fg=MUTED,
            font=("Segoe UI", 9),
            anchor="w"
        )

        title.pack(fill="x", padx=12, pady=(0, 0))

        def close(event=None):

            try:
                popup.destroy()
            except Exception:
                pass

            self._emoji_popup = None

        def pick(char):

            close()

            self.insert_emoji(char)

        cols = 8
        cell_px = 40

        state = {"tab": 0}

        tab_canvases = []

        def show(tab_index):

            state["tab"] = tab_index

            for index, tab in enumerate(tab_canvases):

                chosen = index == tab_index

                tab.configure(
                    bg=PURPLE if chosen else CHIP_BG,
                    fg="#FFFFFF" if chosen else MUTED
                )

            for child in grid.winfo_children():
                child.destroy()

            _icon, name, chars = EMOJI_CATEGORIES[tab_index]

            title.configure(text="")

            for index, char in enumerate(chars.split()):

                pil = emoji_image(char, 28)

                cell = tk.Canvas(
                    grid,
                    width=cell_px,
                    height=cell_px,
                    bg=PANEL_2,
                    highlightthickness=0,
                    bd=0,
                    cursor="hand2"
                )

                cell.grid(
                    row=index // cols,
                    column=index % cols,
                    padx=1,
                    pady=1
                )

                if pil is not None:

                    cell._photo = ImageTk.PhotoImage(pil)

                    cell.create_image(
                        cell_px // 2, cell_px // 2, image=cell._photo
                    )

                else:

                    cell.create_text(
                        cell_px // 2, cell_px // 2,
                        text=char[0] if ord(char[0]) < 0x10000 else "\u25AF",
                        fill=TEXT,
                        font=("Segoe UI", 14)
                    )

                cell.bind(
                    "<Enter>", lambda e, c=cell: c.configure(bg=HOVER_BG)
                )
                cell.bind(
                    "<Leave>", lambda e, c=cell: c.configure(bg=PANEL_2)
                )
                cell.bind("<Button-1>", lambda e, ch=char: pick(ch))

            popup.update_idletasks()

            place()

        def place():

            button = self.chat_emoji_button.canvas

            x = (
                button.winfo_rootx()
                + button.winfo_width()
                - popup.winfo_reqwidth()
            )

            y = (
                button.winfo_rooty()
                - popup.winfo_reqheight()
                - 8
            )

            popup.geometry(f"+{max(0, x)}+{max(0, y)}")

        for index, (icon, name, chars) in enumerate(EMOJI_CATEGORIES):

            tab = tk.Label(
                tabs,
                text=name,
                bg=PANEL_2,
                fg=MUTED,
                font=("Segoe UI", 9),
                cursor="hand2",
                pady=5
            )

            tab.grid(
                row=index // 4,
                column=index % 4,
                sticky="ew",
                padx=2,
                pady=2
            )

            tab_canvases.append(tab)

            tab.bind("<Button-1>", lambda e, i=index: show(i))

        show(0)

        popup.bind("<Escape>", close)
        popup.bind("<FocusOut>", close)

        popup.focus_force()

    # --------------------------------------------------------
    # Keyboard
    # --------------------------------------------------------

    def chat_enter(
        self,
        event
    ):

        self.send_chat()

        return "break"

    def chat_shift_enter(
        self,
        event
    ):

        self.clear_chat_placeholder()

        self.chat_input.insert(
            "insert",
            "\n"
        )

        self.on_chat_input_changed()

        return "break"

    # --------------------------------------------------------
    # AI
    # --------------------------------------------------------

    def get_gemini_key(self):

        return self.db.get_setting(
            "gemini_api_key",
            ""
        ).strip()

    def get_gemini_model(self):

        model = self.db.get_setting(
            "gemini_model",
            GEMINI_MODEL
        ).strip()

        return model or GEMINI_MODEL

    def _gemini_model_candidates(self):
        """The configured model first, then the built-in fallback list —
        deduplicated, order preserved."""

        primary = self.get_gemini_model()

        candidates = [primary]

        for model_name in GEMINI_MODEL_FALLBACKS:

            if model_name not in candidates:
                candidates.append(model_name)

        return candidates

    def _notify_model_fallback(self, model_name):
        """Called when the primary model failed and a fallback worked —
        remembers it (done by the caller) and gives a quiet UI signal
        instead of failing silently or crashing."""

        try:

            self.chat_status.configure(
                text=f"Switched to {model_name}",
                fg=YELLOW
            )

        except Exception:
            pass

    def get_ai_context(self):

        tasks = self.db.get_tasks(
            False
        )[:AI_CONTEXT_ITEMS]

        goals = self.db.get_goals(
            True
        )[:AI_CONTEXT_ITEMS]

        task_lines = []

        for task in tasks:

            task_lines.append(
                f"- {task['title']} | "
                f"{task['priority']} | "
                f"{task['deadline'] or 'no deadline'}"
            )

        goal_lines = []

        for goal in goals:

            goal_lines.append(
                f"- {goal['title']}"
            )

        return (
            "STUDENT CONTEXT\n\n"
            "Pending tasks:\n"
            + (
                "\n".join(task_lines)
                if task_lines
                else "- none"
            )
            + "\n\n"
            "Active goals:\n"
            + (
                "\n".join(goal_lines)
                if goal_lines
                else "- none"
            )
        )

    def send_chat(self):

        if self.chat_busy:
            return

        if not self.get_gemini_key():

            messagebox.showwarning(
                "Gemini",
                "Add your Gemini API key in Settings first.",
                parent=self
            )

            return

        text = self.get_chat_input_text()

        if not text:
            return

        self.chat_input.delete(
            "1.0",
            "end"
        )

        self.show_chat_placeholder()

        self.db.add_message(
            "user",
            text
        )

        self.add_chat_bubble(
            "user",
            text
        )

        self.scroll_chat()

        self.chat_busy = True

        self.chat_status.configure(
            text="Thinking…",
            fg=MUTED
        )

        self.chat_send_button.configure(
            state="disabled"
        )

        self.start_typing_animation()

        threading.Thread(
            target=self.ai_worker,
            args=(text,),
            daemon=True
        ).start()

    def ai_worker(
        self,
        user_text
    ):

        try:

            # Lazy import.
            # Gemini is NOT imported during startup.
            from google import genai

            api_key = self.get_gemini_key()

            if not api_key:

                raise RuntimeError(
                    "Gemini API key is missing."
                )

            client = genai.Client(
                api_key=api_key,
                http_options={
                    "timeout": 30000
                }
            )

            prompt = (
                self.get_ai_context()
                + "\n\n"
                + "STUDENT MESSAGE:\n"
                + user_text
            )

            base_kwargs = {
                "input": prompt,
                "stream": True,
                "generation_config": {
                    "thinking_level": "low",
                    # Keeps replies snappy and on-topic for a chat
                    # sidebar instead of long essays.
                    "max_output_tokens": AI_MAX_OUTPUT_TOKENS
                },
                "system_instruction": (
                    "You are Studestics AI, "
                    "a friendly study and productivity "
                    "assistant. "
                    "Be helpful, practical, concise "
                    "and encouraging. "
                    "Help the student understand topics, "
                    "plan work, organize tasks and study. "
                    "Do not use emoji — the display "
                    "environment cannot render most of them."
                )
            }

            # Start a fresh server-side conversation every N turns so
            # the re-sent history can't grow without bound. The chat
            # shown on screen is untouched.
            if (
                self.gemini_previous_id
                and self.gemini_turns >= AI_RESET_AFTER_TURNS
            ):

                self.gemini_previous_id = ""
                self.gemini_turns = 0

                self.db.set_setting("gemini_previous_id", "")
                self.db.set_setting("gemini_turns", "0")

            candidate_models = self._gemini_model_candidates()

            stream = None
            used_model = None
            last_error = None

            for model_name in candidate_models:

                kwargs = dict(base_kwargs)
                kwargs["model"] = model_name

                if self.gemini_previous_id:

                    kwargs[
                        "previous_interaction_id"
                    ] = self.gemini_previous_id

                try:

                    stream = (
                        client.interactions.create(
                            **kwargs
                        )
                    )

                    used_model = model_name

                    break

                except Exception as first_error:

                    error_text = str(
                        first_error
                    ).lower()

                    # Specific signal: this particular conversation ID
                    # is stale/gone, not the model itself.
                    stale_conversation = (
                        self.gemini_previous_id
                        and "previous_interaction_id" in error_text
                    )

                    if stale_conversation:

                        self.gemini_previous_id = ""
                        self.gemini_turns = 0

                        self.db.set_setting(
                            "gemini_previous_id",
                            ""
                        )

                        kwargs.pop(
                            "previous_interaction_id",
                            None
                        )

                        try:

                            stream = (
                                client.interactions.create(
                                    **kwargs
                                )
                            )

                            used_model = model_name

                            break

                        except Exception as second_error:

                            last_error = second_error
                            second_text = str(second_error).lower()

                            model_missing = (
                                "not_found" in second_text
                                or "404" in second_text
                                or "not found" in second_text
                            )

                            if model_missing:
                                continue

                            raise

                    # Generic "not found" with no mention of the
                    # conversation ID almost certainly means the MODEL
                    # itself is gone — try the next candidate. Anything
                    # else (bad key, rate limit, timeout) won't be fixed
                    # by trying a different model, so it's raised
                    # immediately instead of wasting three slow calls.
                    model_missing = (
                        "not_found" in error_text
                        or "404" in error_text
                        or "not found" in error_text
                    )

                    if model_missing:
                        last_error = first_error
                        continue

                    raise

            if stream is None:

                raise last_error or RuntimeError(
                    "None of the configured Gemini models are available."
                )

            if used_model and used_model != self.get_gemini_model():

                # A fallback model worked — remember it so future
                # messages don't have to rediscover this every time.
                self.db.set_setting(
                    "gemini_model",
                    used_model
                )

                self.after(
                    0,
                    lambda m=used_model:
                        self._notify_model_fallback(m)
                )

            full_text = ""
            interaction_id = None
            bubble_started = False
            last_update = 0.0
            min_interval = 0.05  # throttle UI updates to ~20/sec

            for event in stream:

                event_type = getattr(
                    event,
                    "event_type",
                    ""
                )

                if event_type == "step.delta":

                    delta = getattr(
                        event,
                        "delta",
                        None
                    )

                    if delta and getattr(
                        delta,
                        "type",
                        ""
                    ) == "text":

                        full_text += getattr(
                            delta,
                            "text",
                            ""
                        )

                        if not bubble_started:

                            bubble_started = True

                            self.after(
                                0,
                                self.ai_stream_started
                            )

                        now = time.time()

                        if now - last_update >= min_interval:

                            last_update = now

                            self.after(
                                0,
                                lambda t=full_text:
                                    self.ai_stream_update(t)
                            )

                elif event_type in (
                    "interaction.created",
                    "interaction.completed"
                ):

                    interaction = getattr(
                        event,
                        "interaction",
                        None
                    )

                    candidate_id = getattr(
                        interaction,
                        "id",
                        None
                    ) if interaction else None

                    if candidate_id:

                        interaction_id = candidate_id

                elif event_type == "error":

                    error_obj = getattr(
                        event,
                        "error",
                        None
                    )

                    error_message = getattr(
                        error_obj,
                        "message",
                        "Gemini stream error."
                    ) if error_obj else "Gemini stream error."

                    raise RuntimeError(
                        error_message
                    )

            # Always push the final, complete text — the throttle above
            # may have skipped the very last delta or two.
            if bubble_started:

                self.after(
                    0,
                    lambda t=full_text:
                        self.ai_stream_update(t)
                )

            if not full_text:

                raise RuntimeError(
                    "Gemini returned an empty response."
                )

            if interaction_id:

                self.gemini_previous_id = (
                    interaction_id
                )

                self.db.set_setting(
                    "gemini_previous_id",
                    interaction_id
                )

                self.gemini_turns += 1

                self.db.set_setting(
                    "gemini_turns",
                    str(self.gemini_turns)
                )

            self.db.add_message(
                "assistant",
                full_text.strip()
            )

            self.after(
                0,
                lambda result=full_text.strip():
                    self.ai_stream_finished(
                        result,
                        None
                    )
            )

        except Exception as exc:

            self.after(
                0,
                lambda error=str(exc):
                    self.ai_stream_finished(
                        None,
                        error
                    )
            )

    def ai_stream_started(self):

        self.remove_typing_bubble()

        self.stream_canvas = self.add_chat_bubble(
            "assistant",
            ""
        )

        self.scroll_chat()

    def ai_stream_update(self, text):

        if self.stream_canvas is None:
            return

        try:

            self._draw_bubble(
                self.stream_canvas,
                text,
                PANEL_2,
                TEXT
            )

            self.scroll_chat()

        except Exception:
            pass

    def ai_stream_finished(
        self,
        answer,
        error
    ):

        self.chat_busy = False

        self.remove_typing_bubble()

        try:

            self.chat_send_button.configure(
                state="normal"
            )

        except Exception:
            pass

        if error:

            error_lower = (
                error.lower()
            )

            if (
                "503" in error_lower
                or
                "service_unavailable"
                in error_lower
                or
                "temporarily overloaded"
                in error_lower
            ):

                message = (
                    "Gemini is temporarily overloaded "
                    "right now. Try again in a moment."
                )

            elif (
                "429" in error_lower
                or
                "rate_limit" in error_lower
                or
                "quota" in error_lower
            ):

                message = (
                    "Gemini's free tier only allows a few requests "
                    "per minute/day — you've hit that limit. Wait a "
                    "bit and try again, or see the note in Settings "
                    "about staying inside the free tier."
                )

            elif (
                "timeout" in error_lower
                or
                "deadline" in error_lower
            ):

                message = (
                    "Gemini took too long to respond. "
                    "Try sending the message again."
                )

            elif (
                "api key" in error_lower
                or
                "401" in error_lower
                or
                "403" in error_lower
            ):

                message = (
                    "Your Gemini API key needs to be "
                    "checked in Settings."
                )

            elif (
                "not_found" in error_lower
                or
                "404" in error_lower
                or
                "not found" in error_lower
            ):

                tried = ", ".join(self._gemini_model_candidates())

                message = (
                    f"None of the Gemini models Studestics knows "
                    f"about are available right now (tried: {tried}). "
                    "Check the current model list at ai.google.dev, "
                    "then set the right one under Settings → Gemini "
                    "Model."
                )

            elif (
                "no module named" in error_lower
                and "google" in error_lower
            ):

                message = (
                    "The Gemini SDK isn't installed. "
                    "Run: pip install google-genai"
                )

            else:

                message = (
                    "Gemini error:\n"
                    + error
                )

            self.chat_status.configure(
                text="Error",
                fg=RED
            )

            if self.stream_canvas is not None:

                # Some text already streamed in before the failure —
                # keep it, and add a short note instead of hiding it.
                self.add_chat_bubble(
                    "assistant",
                    f"(Interrupted) {message}"
                )

            else:

                self.add_chat_bubble(
                    "assistant",
                    message
                )

        else:

            self.chat_status.configure(
                text="Ready",
                fg=GREEN
            )

            # The bubble already shows the final text from the last
            # ai_stream_update call — nothing more to render.

        self.stream_canvas = None

        self.scroll_chat()

    def clear_chat(self):

        if self.chat_busy:

            messagebox.showinfo(
                "AI Chat",
                "Wait for Gemini to finish first."
            )

            return

        if messagebox.askyesno(
            "Clear chat",
            "Clear the saved AI conversation?",
            parent=self
        ):

            self.db.clear_messages()

            self.gemini_previous_id = ""
            self.gemini_turns = 0

            self.db.set_setting(
                "gemini_previous_id",
                ""
            )

            self.db.set_setting(
                "gemini_turns",
                "0"
            )

            self.show_page(
                "AI Chat"
            )

    # ========================================================
    # ANALYTICS
    # ========================================================

    def build_analytics(self):

        self.page_header(
            "Analytics",
            "Your focus time and task progress."
        )

        total, completed, pending, goals = (
            self.db.statistics()
        )

        stats = self.db.focus_stats()

        cards = tk.Frame(
            self.page,
            bg=BG
        )

        cards.pack(
            fill="x",
            pady=(0, 24)
        )

        streak = stats["streak"]

        self.stat_card(
            cards,
            "Focus today",
            fmt_duration(stats["today"]),
            PURPLE_HOVER
        )

        self.stat_card(
            cards,
            "Last 7 days",
            fmt_duration(stats["week"]),
            BLUE
        )

        self.stat_card(
            cards,
            "Focus streak",
            f"{streak} day" + ("" if streak == 1 else "s"),
            YELLOW
        )

        self.stat_card(
            cards,
            "Tasks done",
            f"{completed} / {total}",
            GREEN
        )

        columns = tk.Frame(
            self.page,
            bg=BG
        )

        columns.pack(
            fill="both",
            expand=True
        )

        columns.grid_rowconfigure(0, weight=1)
        columns.grid_columnconfigure(0, weight=1, uniform="an")
        columns.grid_columnconfigure(1, weight=1, uniform="an")

        left_outer, left = self.rounded_panel(columns, radius=16)

        left_outer.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=(5, 10)
        )

        right_outer, right = self.rounded_panel(columns, radius=16)

        right_outer.grid(
            row=0,
            column=1,
            sticky="nsew",
            padx=(10, 5)
        )

        self.section_title(
            left,
            "Last 7 days",
            "Time focused per day  \u00b7  "
            + fmt_duration(
                sum(
                    secs for _, secs in
                    self.db.focus_daily_seconds(7)
                )
            )
            + " in total"
        )

        chart = tk.Canvas(
            left,
            width=10,
            height=10,
            bg=PANEL,
            highlightthickness=0,
            bd=0
        )

        chart.pack(
            fill="both",
            expand=True,
            padx=20,
            pady=(0, 18)
        )

        week = self.db.focus_daily_seconds(7)

        chart.bind(
            "<Configure>",
            lambda event: self._draw_week_chart(chart, week)
        )

        self.section_title(
            right,
            "Recent sessions",
            "Your latest focus sessions"
        )

        sessions = self.db.recent_focus_sessions(5)

        if not sessions:

            self.empty_text(
                right,
                "No focus sessions yet. Finish one in "
                "Focus Mode and it shows up here."
            )

        for session in sessions:

            self._analytics_session_row(
                right,
                session
            )

    def _analytics_session_row(self, parent, session):

        row = tk.Frame(
            parent,
            bg=PANEL
        )

        if parent.winfo_children()[-1:] and len(
            parent.winfo_children()
        ) > 2:

            tk.Frame(
                parent,
                bg=BORDER,
                height=1
            ).pack(
                fill="x",
                padx=20
            )

        row.pack(
            fill="x",
            padx=20,
            pady=11
        )

        title = session["task_title"]

        if not title or title == "No task selected":
            title = "Free focus"

        if len(title) > 28:
            title = title[:27] + "…"

        left = tk.Frame(
            row,
            bg=PANEL
        )

        left.pack(
            side="left",
            fill="x",
            expand=True
        )

        tk.Label(
            left,
            text=title,
            bg=PANEL,
            fg=TEXT if session["task_title"] else MUTED,
            font=("Segoe UI", 10, "bold"),
            anchor="w"
        ).pack(
            anchor="w"
        )

        try:

            when = datetime.strptime(
                session["ended_at"],
                "%Y-%m-%d %H:%M:%S"
            ).strftime("%a %d %b • %I:%M %p")

        except Exception:

            when = session["ended_at"]

        detail = when

        nudges = session["nudges"] or 0

        if nudges:
            detail += (
                f" • {nudges} distraction alert"
                + ("" if nudges == 1 else "s")
            )

        tk.Label(
            left,
            text=detail,
            bg=PANEL,
            fg=MUTED_2,
            font=("Segoe UI", 8),
            anchor="w"
        ).pack(
            anchor="w"
        )

        right = tk.Frame(
            row,
            bg=PANEL
        )

        right.pack(
            side="right"
        )

        tk.Label(
            right,
            text=fmt_duration(session["actual_seconds"]),
            bg=PANEL,
            fg=TEXT,
            font=("Segoe UI", 10, "bold"),
            anchor="e"
        ).pack(
            anchor="e"
        )

        finished = bool(session["completed"])

        tk.Label(
            right,
            text="✓ Finished" if finished else "Stopped early",
            bg=PANEL,
            fg=GREEN if finished else MUTED_2,
            font=("Segoe UI", 8),
            anchor="e"
        ).pack(
            anchor="e"
        )

    def _draw_week_chart(self, canvas, data):
        """Bar chart that fills whatever space it is given and redraws
        when the window is resized. Bars are anti-aliased via Pillow."""

        try:

            width = canvas.winfo_width()
            height = canvas.winfo_height()

            if width < 80 or height < 80:
                return

            key = (width, height)

            if getattr(canvas, "_chart_key", None) == key:
                return

            canvas._chart_key = key

            canvas.delete("all")

            label_h = 24
            top_pad = 22

            plot_h = height - label_h - top_pad

            count = len(data)

            slot = width / count
            bar_w = min(46, slot * 0.5)

            # At least a 30-minute scale, so one short session doesn't
            # fill the whole chart.
            biggest = max([secs for _, secs in data] + [30 * 60])

            bars = []

            for index, (day, secs) in enumerate(data):

                bar_h = (
                    max(6, plot_h * secs / biggest)
                    if secs > 0
                    else 4
                )

                x0 = index * slot + (slot - bar_w) / 2
                y1 = top_pad + plot_h
                y0 = y1 - bar_h

                is_today = index == count - 1

                if secs <= 0:
                    color = BORDER
                elif is_today:
                    color = PURPLE_HOVER
                else:
                    color = PURPLE

                bars.append((x0, y0, x0 + bar_w, y1, color))

            base_y = top_pad + plot_h

            for frac in (0, 0.5, 1.0):

                gy = base_y - plot_h * frac

                canvas.create_line(
                    0, gy, width, gy,
                    fill=mix_color(BORDER, PANEL, 0.35 if frac else 0.0),
                    dash=(2, 4) if frac else ()
                )

            if HAS_PIL:

                scale = 3

                img = Image.new(
                    "RGBA",
                    (width * scale, height * scale),
                    (0, 0, 0, 0)
                )

                draw = ImageDraw.Draw(img)

                for x0, y0, x1, y1, color in bars:

                    draw.rounded_rectangle(
                        [
                            x0 * scale, y0 * scale,
                            x1 * scale, y1 * scale
                        ],
                        radius=min(8, bar_w / 2) * scale,
                        fill=color
                    )

                img = img.resize(
                    (width, height),
                    Image.LANCZOS
                )

                photo = ImageTk.PhotoImage(img)
                canvas.chart_photo = photo

                canvas.create_image(
                    0,
                    0,
                    anchor="nw",
                    image=photo
                )

            else:

                for x0, y0, x1, y1, color in bars:

                    canvas.create_rectangle(
                        x0, y0, x1, y1,
                        fill=color,
                        outline=color
                    )

            for index, (day, secs) in enumerate(data):

                x0, y0, x1, y1, color = bars[index]

                center = (x0 + x1) / 2

                if index == count - 1:

                    label = "Today"

                else:

                    try:

                        label = datetime.strptime(
                            day,
                            "%Y-%m-%d"
                        ).strftime("%a")

                    except Exception:

                        label = day

                canvas.create_text(
                    center,
                    height - label_h / 2 + 2,
                    text=label,
                    fill=TEXT if index == count - 1 else MUTED,
                    font=("Segoe UI", 9)
                )

                if secs > 0:

                    canvas.create_text(
                        center,
                        y0 - 10,
                        text=fmt_duration(secs),
                        fill=MUTED,
                        font=("Segoe UI", 8)
                    )

        except Exception:
            pass

    # ========================================================
    # SETTINGS
    # ========================================================

    def build_settings(self):
        """Settings has grown past one screen, so the cards live in a
        scrolling frame (mouse wheel; no scrollbar, like the dialogs)."""

        self.page_header(
            "Settings",
            "Local preferences and Gemini connection."
        )

        real_page = self.page

        scroller = tk.Canvas(
            real_page,
            bg=BG,
            highlightthickness=0,
            bd=0,
            yscrollincrement=40
        )

        scroller.pack(
            fill="both",
            expand=True
        )

        inner = tk.Frame(
            scroller,
            bg=BG
        )

        inner_id = scroller.create_window(
            (0, 0),
            window=inner,
            anchor="nw"
        )

        inner.bind(
            "<Configure>",
            lambda e: scroller.configure(
                scrollregion=scroller.bbox("all")
            )
        )

        scroller.bind(
            "<Configure>",
            lambda e: scroller.itemconfigure(inner_id, width=e.width)
        )

        def on_wheel(event):

            try:

                if (
                    not scroller.winfo_exists()
                    or self.current_page != "Settings"
                ):
                    return

                first, last = scroller.yview()

                # Nothing to scroll when everything already fits.
                if first <= 0.0 and last >= 1.0:
                    return

                scroller.yview_scroll(
                    int(-1 * (event.delta / 120)),
                    "units"
                )

            except Exception:
                pass

        scroller.bind_all("<MouseWheel>", on_wheel)

        # The cards are built into the scrolling frame; clear_page()
        # must still find the real page afterwards, whatever happens.
        self.page = inner

        try:

            self._build_settings_cards()

        finally:

            self.page = real_page

        tk.Frame(
            inner,
            bg=BG,
            height=24
        ).pack()

    def _build_settings_cards(self):

        panel_outer, panel = self.rounded_panel(
            self.page,
            radius=16,
            fit=True
        )

        panel_outer.pack(
            fill="x",
            pady=(0, 15)
        )

        self.section_title(
            panel,
            "Gemini API",
            "Your API key stays in the local Studestics database."
        )

        row = tk.Frame(
            panel,
            bg=PANEL
        )

        row.pack(
            fill="x",
            padx=25,
            pady=(0, 8)
        )

        self.api_key_var = tk.StringVar(
            value=self.get_gemini_key()
        )

        key_entry = self.make_entry(
            row,
            self.api_key_var,
            show="•"
        )

        key_entry.pack(
            side="left",
            fill="x",
            expand=True,
            ipady=9
        )

        self.make_button(
            row,
            "Save",
            self.save_api_key,
            width=9
        ).pack(
            side="left",
            padx=8
        )

        self.make_button(
            row,
            "Test Gemini",
            self.test_gemini,
            width=11
        ).pack(
            side="left"
        )

        model_row = tk.Frame(
            panel,
            bg=PANEL
        )

        model_row.pack(
            fill="x",
            padx=25,
            pady=(4, 8)
        )

        tk.Label(
            model_row,
            text="Model",
            bg=PANEL,
            fg=MUTED,
            font=("Segoe UI", 8)
        ).pack(
            anchor="w",
            pady=(0, 3)
        )

        model_entry_row = tk.Frame(
            model_row,
            bg=PANEL
        )

        model_entry_row.pack(
            fill="x"
        )

        self.gemini_model_var = tk.StringVar(
            value=self.get_gemini_model()
        )

        model_entry = self.make_entry(
            model_entry_row,
            self.gemini_model_var
        )

        model_entry.pack(
            side="left",
            fill="x",
            expand=True,
            ipady=9
        )

        self.make_button(
            model_entry_row,
            "Save",
            self.save_gemini_model,
            width=9
        ).pack(
            side="left",
            padx=8
        )

        tk.Label(
            panel,
            text=(
                "If Gemini ever renames or retires a model, put the "
                "new name here — no code changes needed. Flash-Lite "
                "models get a much bigger free-tier daily allowance "
                "than regular Flash (often 500+ requests/day vs ~20), "
                "if Gemini chat is burning through your free quota "
                "too fast — try 'gemini-flash-lite-latest'. Current "
                "models: ai.google.dev/gemini-api/docs/models"
            ),
            bg=PANEL,
            fg=MUTED_2,
            font=("Segoe UI", 8),
            wraplength=650,
            justify="left"
        ).pack(
            anchor="w",
            padx=25,
            pady=(0, 4)
        )

        self.settings_status = tk.Label(
            panel,
            text="",
            bg=PANEL,
            fg=MUTED,
            font=("Segoe UI", 8)
        )

        self.settings_status.pack(
            anchor="w",
            padx=25,
            pady=(0, 20)
        )

        focus_panel_outer, focus_panel = self.rounded_panel(
            self.page,
            radius=16,
            fit=True
        )

        focus_panel_outer.pack(
            fill="x"
        )

        self.section_title(
            focus_panel,
            "Focus defaults",
            "Default timer length and distraction alerts."
        )

        focus_row = tk.Frame(
            focus_panel,
            bg=PANEL
        )

        focus_row.pack(
            fill="x",
            padx=25,
            pady=(0, 12)
        )

        tk.Label(
            focus_row,
            text="Minutes",
            bg=PANEL,
            fg=MUTED
        ).pack(
            side="left"
        )

        self.focus_setting_entry = self.make_entry(
            focus_row
        )

        self.focus_setting_entry.insert(
            0,
            str(
                self.focus_duration // 60
            )
        )

        self.focus_setting_entry.pack(
            side="left",
            padx=10,
            ipady=8
        )

        self.make_button(
            focus_row,
            "Save",
            self.save_focus_default,
            width=8
        ).pack(
            side="left"
        )

        nudge_row = tk.Frame(
            focus_panel,
            bg=PANEL
        )

        nudge_row.pack(
            fill="x",
            padx=25,
            pady=(0, 22)
        )

        tk.Label(
            nudge_row,
            text="Distraction alerts",
            bg=PANEL,
            fg=MUTED
        ).pack(
            side="left"
        )

        self.settings_nudge_button = self.make_button(
            nudge_row,
            "On",
            self.toggle_nudge,
            width=6
        )

        self.settings_nudge_button.pack(
            side="left",
            padx=10
        )

        self.make_button(
            nudge_row,
            "Edit words",
            self.edit_nudge_words,
            width=10
        ).pack(
            side="left"
        )

        tk.Label(
            nudge_row,
            text="Pops up a reminder if you switch to a distracting "
                 "site or app while the timer runs.",
            bg=PANEL,
            fg=MUTED_2,
            font=("Segoe UI", 8)
        ).pack(
            side="left",
            padx=12
        )

        self._refresh_nudge_buttons()

        float_panel_outer, float_panel = self.rounded_panel(
            self.page,
            radius=16,
            fit=True
        )

        float_panel_outer.pack(
            fill="x",
            pady=(15, 0)
        )

        self.section_title(
            float_panel,
            "Clock style",
            "How the timer looks on the Focus page and in the small "
            "clock that floats over your windows."
        )

        float_body = tk.Frame(
            float_panel,
            bg=PANEL
        )

        float_body.pack(
            fill="x",
            padx=25,
            pady=(0, 22)
        )

        float_left = tk.Frame(
            float_body,
            bg=PANEL
        )

        float_left.pack(
            side="left",
            anchor="n"
        )

        tk.Label(
            float_left,
            text="Style",
            bg=PANEL,
            fg=MUTED
        ).pack(
            anchor="w",
            pady=(0, 6)
        )

        style_row = tk.Frame(
            float_left,
            bg=PANEL
        )

        style_row.pack(
            anchor="w"
        )

        self.float_style_buttons = {}

        for key, label in FLOAT_STYLES:

            button = self.make_button(
                style_row,
                label,
                lambda k=key: self.choose_float_style(k),
                width=7
            )

            button.pack(
                side="left",
                padx=(0, 8)
            )

            self.float_style_buttons[key] = button

        tk.Label(
            float_left,
            text="Turn the floating clock on or off with the icon at "
                 "the top left of Focus Mode.\n"
                 "Click it to pause or resume the timer. Drag it to move it.",
            bg=PANEL,
            fg=MUTED_2,
            font=("Segoe UI", 8),
            justify="left"
        ).pack(
            anchor="w",
            pady=(16, 0)
        )

        self.float_preview_canvas = tk.Canvas(
            float_body,
            width=320,
            height=216,
            bg=FLOAT_PREVIEW_BG,
            highlightthickness=0,
            bd=0
        )

        self.float_preview_canvas.pack(
            side="right"
        )

        self._refresh_float_controls()
        self._float_preview_refresh()

        rem_panel_outer, rem_panel = self.rounded_panel(
            self.page,
            radius=16,
            fit=True
        )

        rem_panel_outer.pack(
            fill="x",
            pady=(15, 0)
        )

        self.section_title(
            rem_panel,
            "Reminders",
            "How often Studestics reminds you about unfinished "
            "tasks, in minutes."
        )

        rem_row = tk.Frame(
            rem_panel,
            bg=PANEL
        )

        rem_row.pack(
            fill="x",
            padx=25,
            pady=(0, 6)
        )

        self.reminder_vars = {}

        for label, priority in (
            ("Low", "Low"),
            ("Medium", "Medium"),
            ("High", "High")
        ):

            tk.Label(
                rem_row,
                text=label,
                bg=PANEL,
                fg=MUTED
            ).pack(
                side="left",
                padx=(0, 6)
            )

            var = tk.StringVar(
                value=str(self.reminder_default(priority))
            )

            self.reminder_vars[priority] = var

            entry = self.make_entry(
                rem_row,
                var
            )

            entry.configure(width=6, justify="center")

            entry.pack(
                side="left",
                padx=(0, 18),
                ipady=8
            )

        self.make_button(
            rem_row,
            "Save",
            self.save_reminder_settings,
            width=8
        ).pack(
            side="left"
        )

        self.make_button(
            rem_row,
            "Test alarm",
            self.test_reminder,
            width=10
        ).pack(
            side="left",
            padx=8
        )

        auto_row = tk.Frame(
            rem_panel,
            bg=PANEL
        )

        auto_row.pack(
            fill="x",
            padx=25,
            pady=(10, 2)
        )

        tk.Label(
            auto_row,
            text="Remove overdue tasks automatically",
            bg=PANEL,
            fg=MUTED
        ).pack(
            side="left"
        )

        self.settings_autodel_button = self.make_button(
            auto_row,
            "On" if self.auto_delete_overdue else "Off",
            self.toggle_auto_delete,
            width=6
        )

        self.settings_autodel_button.configure(
            selected=self.auto_delete_overdue
        )

        self.settings_autodel_button.pack(
            side="left",
            padx=10
        )

        tk.Label(
            rem_panel,
            text="On: a task is deleted when its deadline passes, and "
                 "an Undo popup tells you. Off: it stays, and you get "
                 "one alert when it runs out. Completed tasks are "
                 "never removed.",
            bg=PANEL,
            fg=MUTED_2,
            font=("Segoe UI", 8),
            wraplength=650,
            justify="left"
        ).pack(
            anchor="w",
            padx=25,
            pady=(0, 10)
        )

        note = (
            "A task can also get its own custom time when you "
            "create it."
        )

        if pystray is None:

            note += (
                "  To keep reminders running after you close the "
                "window, run: pip install pystray"
            )

        tk.Label(
            rem_panel,
            text=note,
            bg=PANEL,
            fg=MUTED_2,
            font=("Segoe UI", 8),
            wraplength=650,
            justify="left"
        ).pack(
            anchor="w",
            padx=25,
            pady=(0, 18)
        )

        data_panel = self._build_data_card()

        dev_panel = self._build_dev_card()

        startup_panel = (
            self._build_startup_card() if startup_supported() else None
        )

        appearance_panel = self._build_appearance_card()

        # Group the cards under headings, in this order.
        order = [
            (self._settings_heading(
                "Appearance",
                "Colours and theme."
            ), None),
            (appearance_panel, (0, 15)),
            (self._settings_heading(
                "General",
                "The AI connection and reminders."
            ), None),
            (panel_outer, (0, 15)),
            (rem_panel_outer, (0, 15)),
            *(
                [(startup_panel, (0, 15))]
                if startup_panel is not None
                else []
            ),
            (self._settings_heading(
                "Focus Mode",
                "Timer length, distraction alerts and the clock."
            ), None),
            (focus_panel_outer, (0, 15)),
            (float_panel_outer, (0, 15)),
            (self._settings_heading(
                "Data",
                "Clear out what you've stored in Studestics."
            ), None),
            (data_panel, (0, 15)),
            (self._settings_heading(
                "Developer",
                "Tools for checking how things look."
            ), None),
            (dev_panel, (0, 15))
        ]

        for widget in (
            panel_outer, rem_panel_outer, focus_panel_outer,
            float_panel_outer, data_panel, dev_panel, startup_panel,
            appearance_panel
        ):

            if widget is None:
                continue

            widget.pack_forget()

        for widget, gap in order:

            if gap is None:

                widget.pack(fill="x", pady=(14, 10))

            else:

                widget.pack(fill="x", pady=gap)

    def _settings_heading(self, title, subtitle):

        box = tk.Frame(self.page, bg=BG)

        top = tk.Frame(box, bg=BG)

        top.pack(fill="x")

        tk.Label(
            top,
            text=title.upper(),
            bg=BG,
            fg=PURPLE_HOVER,
            font=("Segoe UI", 11, "bold")
        ).pack(
            side="left"
        )

        tk.Frame(
            top,
            bg=mix_color(PURPLE, BG, 0.55),
            height=1
        ).pack(
            side="left",
            fill="x",
            expand=True,
            padx=(14, 0),
            pady=(3, 0)
        )

        tk.Label(
            box,
            text=subtitle,
            bg=BG,
            fg=MUTED,
            font=("Segoe UI", 9)
        ).pack(
            anchor="w",
            pady=(3, 0)
        )

        return box

    def _build_data_card(self):

        outer, card = self.rounded_panel(
            self.page,
            radius=16,
            fit=True
        )

        rows = (
            (
                "Delete all tasks",
                "Removes every task, pending and completed, and "
                "their pictures.",
                "Delete tasks",
                self.delete_all_tasks_confirm
            ),
            (
                "Delete all goals",
                "Removes every goal.",
                "Delete goals",
                self.delete_all_goals_confirm
            ),
            (
                "Delete user data",
                "Removes tasks, goals, AI chat, focus history and "
                "all settings. Your Gemini API key and name stay.",
                "Delete everything",
                self.delete_user_data_confirm
            )
        )

        for index, (title, text, button, command) in enumerate(rows):

            if index:

                tk.Frame(
                    card,
                    bg=BORDER,
                    height=1
                ).pack(
                    fill="x",
                    padx=25
                )

            row = tk.Frame(card, bg=PANEL)

            row.pack(
                fill="x",
                padx=25,
                pady=16
            )

            left = tk.Frame(row, bg=PANEL)

            left.pack(
                side="left",
                fill="x",
                expand=True
            )

            tk.Label(
                left,
                text=title,
                bg=PANEL,
                fg=TEXT,
                font=("Segoe UI", 11, "bold")
            ).pack(
                anchor="w"
            )

            tk.Label(
                left,
                text=text,
                bg=PANEL,
                fg=MUTED_2,
                font=("Segoe UI", 9),
                wraplength=560,
                justify="left"
            ).pack(
                anchor="w",
                pady=(2, 0)
            )

            self.make_button(
                row,
                button,
                command,
                width=16,
                active="#DC2626"
            ).pack(
                side="right"
            )

        return outer

    def _build_appearance_card(self):
        """Theme picker: a tile per theme with a tiny preview of it.
        The colours are read at start-up, so a change needs a restart."""

        outer, card = self.rounded_panel(
            self.page,
            radius=16,
            fit=True
        )

        tk.Label(
            card,
            text="Theme",
            bg=PANEL,
            fg=TEXT,
            font=("Segoe UI", 11, "bold")
        ).pack(anchor="w", padx=25, pady=(18, 2))

        tk.Label(
            card,
            text="Pick the colours for the whole app.",
            bg=PANEL,
            fg=MUTED_2,
            font=("Segoe UI", 9)
        ).pack(anchor="w", padx=25)

        tiles = tk.Frame(card, bg=PANEL)

        tiles.pack(fill="x", padx=21, pady=(14, 6))

        saved = self.db.get_setting("theme", "") or THEME_NAME

        if saved not in THEMES:
            saved = THEME_NAME

        hint_var = tk.StringVar(value="")

        canvases = {}

        def draw(name, canvas, selected):

            t = THEMES[name]

            canvas.delete("all")

            w, h = 126, 78

            canvas.create_rectangle(
                1, 1, w - 1, h - 1,
                fill=t["bg"],
                outline=t["accent_hover"] if selected else t["border"],
                width=3 if selected else 1
            )

            canvas.create_rectangle(
                4, 4, 28, h - 4,
                fill=t["sidebar"],
                outline=""
            )

            for i in range(3):

                canvas.create_rectangle(
                    8, 12 + i * 14, 24, 20 + i * 14,
                    fill=t["accent_hover"] if i == 0 else t["border"],
                    outline=""
                )

            canvas.create_rectangle(
                36, 10, w - 10, 34,
                fill=t["panel2"],
                outline=""
            )

            canvas.create_rectangle(
                44, 17, 78, 21,
                fill=t["text"],
                outline=""
            )

            canvas.create_rectangle(
                44, 25, 64, 28,
                fill=t["muted"],
                outline=""
            )

            canvas.create_rectangle(
                36, 42, w - 10, 66,
                fill=t["panel2"],
                outline=""
            )

            canvas.create_rectangle(
                w - 52, 49, w - 18, 59,
                fill=t["accent"],
                outline=""
            )

        def choose(name):

            self.db.set_setting("theme", name)

            for other, canvas in canvases.items():
                draw(other, canvas, other == name)

            if name == THEME_NAME:

                hint_var.set("")
                restart_row.pack_forget()

            else:

                hint_var.set(
                    f"{name} will be used after a restart."
                )

                restart_row.pack(
                    fill="x", padx=25, pady=(4, 16)
                )

        for index, name in enumerate(THEMES):

            cell = tk.Frame(tiles, bg=PANEL)

            cell.pack(side="left", padx=4)

            canvas = tk.Canvas(
                cell,
                width=126,
                height=78,
                bg=PANEL,
                highlightthickness=0,
                bd=0,
                cursor="hand2"
            )

            canvas.pack()

            canvases[name] = canvas

            draw(name, canvas, name == saved)

            canvas.bind("<Button-1>", lambda e, n=name: choose(n))

            label = tk.Label(
                cell,
                text=name,
                bg=PANEL,
                fg=TEXT,
                font=("Segoe UI", 9),
                cursor="hand2"
            )

            label.pack(pady=(4, 0))

            label.bind("<Button-1>", lambda e, n=name: choose(n))

        restart_row = tk.Frame(card, bg=PANEL)

        tk.Label(
            restart_row,
            textvariable=hint_var,
            bg=PANEL,
            fg=YELLOW,
            font=("Segoe UI", 9)
        ).pack(side="left")

        self.make_button(
            restart_row,
            "Restart now",
            self.restart_app,
            width=13
        ).pack(side="right")

        if saved != THEME_NAME:

            hint_var.set(f"{saved} will be used after a restart.")

            restart_row.pack(fill="x", padx=25, pady=(4, 16))

        else:

            tk.Frame(card, bg=PANEL, height=12).pack()

        return outer

    def restart_app(self):
        """Start a fresh copy, then close this one. The new copy waits
        a moment for this one's single-instance lock to be released."""

        try:

            # Clean environment: a one-file .exe must unpack itself
            # fresh, not reuse the folder of the copy that is closing.
            env = {
                key: value for key, value in os.environ.items()
                if not key.startswith("_PYI")
                and key != "_MEIPASS2"
            }

            env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"

            if getattr(sys, "frozen", False):

                command = [sys.executable]

            else:

                interpreter = Path(sys.executable)

                windowless = interpreter.with_name("pythonw.exe")

                if windowless.exists():
                    interpreter = windowless

                command = [str(interpreter), str(Path(__file__).resolve())]

            command.append("--restarted")

            flags = 0

            if sys.platform == "win32":

                flags = (
                    0x00000008     # DETACHED_PROCESS: no console at all
                    | 0x00000200   # CREATE_NEW_PROCESS_GROUP
                )

            # The new copy waits for this one's single-instance lock,
            # so it can't be mistaken for a second copy.
            subprocess.Popen(
                command,
                env=env,
                close_fds=True,
                creationflags=flags
            )

        except Exception as exc:

            messagebox.showerror(
                "Restart",
                f"Couldn't restart automatically: {exc}\n\n"
                "Close and reopen Studestics to apply the theme.",
                parent=self
            )

            return

        self.quit_app()

    def _build_startup_card(self):

        outer, card = self.rounded_panel(
            self.page,
            radius=16,
            fit=True
        )

        row = tk.Frame(card, bg=PANEL)

        row.pack(
            fill="x",
            padx=25,
            pady=18
        )

        left = tk.Frame(row, bg=PANEL)

        left.pack(
            side="left",
            fill="x",
            expand=True
        )

        tk.Label(
            left,
            text="Start with Windows",
            bg=PANEL,
            fg=TEXT,
            font=("Segoe UI", 11, "bold")
        ).pack(
            anchor="w"
        )

        tk.Label(
            left,
            text="Opens Studestics quietly in the tray when you sign in, "
                 "so reminders keep working.",
            bg=PANEL,
            fg=MUTED_2,
            font=("Segoe UI", 9),
            wraplength=560,
            justify="left"
        ).pack(
            anchor="w",
            pady=(2, 0)
        )

        enabled = startup_enabled()

        self.settings_startup_button = self.make_button(
            row,
            "On" if enabled else "Off",
            self.toggle_startup,
            width=8
        )

        self.settings_startup_button.configure(selected=enabled)

        self.settings_startup_button.pack(
            side="right"
        )

        return outer

    def toggle_startup(self):

        target = not startup_enabled()

        try:

            set_startup(target)

        except Exception as exc:

            messagebox.showerror(
                "Start with Windows",
                f"Couldn't change this: {exc}",
                parent=self
            )

            return

        try:

            self.settings_startup_button.configure(
                text="On" if target else "Off",
                selected=target
            )

        except Exception:
            pass

    def _build_dev_card(self):

        outer, card = self.rounded_panel(
            self.page,
            radius=16,
            fit=True
        )

        row = tk.Frame(card, bg=PANEL)

        row.pack(
            fill="x",
            padx=25,
            pady=16
        )

        left = tk.Frame(row, bg=PANEL)

        left.pack(
            side="left",
            fill="x",
            expand=True
        )

        tk.Label(
            left,
            text="Welcome page",
            bg=PANEL,
            fg=TEXT,
            font=("Segoe UI", 11, "bold")
        ).pack(
            anchor="w"
        )

        tk.Label(
            left,
            text="Shows the first-launch welcome page and tour. "
                 "Nothing is saved or changed.",
            bg=PANEL,
            fg=MUTED_2,
            font=("Segoe UI", 9),
            wraplength=560,
            justify="left"
        ).pack(
            anchor="w",
            pady=(2, 0)
        )

        self.make_button(
            row,
            "Preview",
            lambda: self.ask_name(preview=True),
            width=16
        ).pack(
            side="right"
        )

        return outer

    def delete_all_tasks_confirm(self):

        if messagebox.askyesno(
            "Delete all tasks",
            "Delete every task? This can't be undone.",
            icon="warning",
            parent=self
        ):

            self.db.delete_all_tasks()

            messagebox.showinfo(
                "Delete all tasks",
                "All tasks were deleted.",
                parent=self
            )

            self.show_page("Settings")

    def delete_all_goals_confirm(self):

        if messagebox.askyesno(
            "Delete all goals",
            "Delete every goal? This can't be undone.",
            icon="warning",
            parent=self
        ):

            self.db.delete_all_goals()

            messagebox.showinfo(
                "Delete all goals",
                "All goals were deleted.",
                parent=self
            )

            self.show_page("Settings")

    def delete_user_data_confirm(self):

        if not messagebox.askyesno(
            "Delete user data",
            "Delete your tasks, goals, AI chat, focus history and all "
            "settings?\n\nYour Gemini API key and name are kept. "
            "This can't be undone.",
            icon="warning",
            parent=self
        ):
            return

        self.db.delete_all_user_data()

        # Forget the editor's in-memory text too.
        for attr in ("_note_text", "_note_path", "_note_dirty"):

            if hasattr(self, attr):
                delattr(self, attr)

        self.auto_delete_overdue = True

        messagebox.showinfo(
            "Delete user data",
            "Done. Restart Studestics to apply the default settings.",
            parent=self
        )

        self.show_page("Settings")

    def save_api_key(self):

        value = (
            self.api_key_var
            .get()
            .strip()
        )

        self.db.set_setting(
            "gemini_api_key",
            value
        )

        self.settings_status.configure(
            text="API key saved.",
            fg=GREEN
        )

    def save_gemini_model(self):

        value = (
            self.gemini_model_var
            .get()
            .strip()
        )

        if not value:
            value = GEMINI_MODEL

        self.db.set_setting(
            "gemini_model",
            value
        )

        self.gemini_model_var.set(value)

        self.settings_status.configure(
            text=f"Model set to {value}.",
            fg=GREEN
        )

    def test_gemini(self):

        key = (
            self.api_key_var
            .get()
            .strip()
        )

        if not key:

            self.settings_status.configure(
                text="Enter an API key first.",
                fg=RED
            )

            return

        self.db.set_setting(
            "gemini_api_key",
            key
        )

        self.settings_status.configure(
            text="Testing Gemini…",
            fg=MUTED
        )

        threading.Thread(
            target=self.gemini_test_worker,
            daemon=True
        ).start()

    def gemini_test_worker(self):

        try:

            from google import genai

            client = genai.Client(
                api_key=self.get_gemini_key(),
                http_options={
                    "timeout": 30000
                }
            )

            interaction = (
                client.interactions.create(
                    model=self.get_gemini_model(),
                    input=(
                        "Reply with exactly: "
                        "Studestics connection OK"
                    ),
                    generation_config={
                        "thinking_level": "low"
                    }
                )
            )

            answer = getattr(
                interaction,
                "output_text",
                ""
            )

            self.after(
                0,
                lambda:
                    self.settings_status.configure(
                        text=(
                            "Gemini connection works ✓"
                            if answer
                            else "Gemini returned no text."
                        ),
                        fg=GREEN if answer else RED
                    )
            )

        except Exception as exc:

            self.after(
                0,
                lambda error=str(exc):
                    self.settings_status.configure(
                        text=f"Gemini test failed: {error}",
                        fg=RED
                    )
            )

    def save_focus_default(self):

        try:

            minutes = int(
                self.focus_setting_entry.get()
            )

        except ValueError:

            self.settings_status.configure(
                text="Enter a whole number.",
                fg=RED
            )

            return

        if not 1 <= minutes <= 240:

            self.settings_status.configure(
                text="Choose 1–240 minutes.",
                fg=RED
            )

            return

        self.db.set_setting(
            "focus_minutes",
            str(minutes)
        )

        self.db.set_setting(
            "focus_total_seconds",
            str(minutes * 60)
        )

        if not self.focus_running:

            self.focus_duration = (
                minutes * 60
            )

            self.focus_seconds = (
                self.focus_duration
            )

            self.update_focus_ui()

        self.settings_status.configure(
            text="Focus default saved.",
            fg=GREEN
        )

    # ========================================================
    # FIRST LAUNCH NAME
    # ========================================================

    def ask_name(self, preview=False):
        """First launch: a full-window welcome page (name and optional
        photo), then a short three-step tour. preview=True is the
        Settings > Developer button: nothing is saved or changed."""

        overlay = tk.Frame(self, bg=BG)

        overlay.place(x=0, y=0, relwidth=1, relheight=1)

        overlay.lift()

        column = tk.Frame(overlay, bg=BG)

        column.place(relx=0.5, rely=0.46, anchor="center")

        state = {"step": 0, "busy": False}

        TOUR = (
            (
                "check",
                BLUE,
                "Plan your tasks",
                "Add tasks with a deadline, a priority and a reminder. "
                "Overdue and due-soon ones stand out so nothing slips."
            ),
            (
                "clock",
                PURPLE_HOVER,
                "Stay on one thing",
                "Pick a task in Focus Mode, start the timer and keep "
                "going. A small floating clock can follow you around."
            ),
            (
                "note",
                YELLOW,
                "Jot things down",
                "Notes is a simple text editor. Write quick notes, or "
                "open a .txt file, edit it and save it back. Your draft "
                "is kept even if you close the app."
            ),
            (
                "chat",
                GREEN,
                "Ask for help",
                "Chat with Gemini about your plans and deadlines. It "
                "needs a free API key. The next page shows how to get one."
            ),
            (
                "gear",
                PURPLE_HOVER,
                "Add your Gemini key",
                "",
                {
                    "steps": (
                        "Open Google AI Studio and sign in with Google.",
                        "Choose Create API key and copy it.",
                        "In Studestics open Settings, then Gemini API.",
                        "Paste the key, press Save, then Test Gemini."
                    ),
                    "link": (
                        "Open Google AI Studio",
                        "https://aistudio.google.com/apikey"
                    )
                }
            )
        )

        def clear():

            for child in column.winfo_children():
                child.destroy()

        def finish_now():

            try:
                overlay.destroy()
            except Exception:
                pass

            self._refresh_profile_chip()

            self.show_page("Settings" if preview else "Dashboard")

        # ---- slide + fade between steps ----
        def collect(widget, found):

            for child in widget.winfo_children():

                if isinstance(child, tk.Label):

                    try:
                        found.append((child, child.cget("fg")))
                    except Exception:
                        pass

                collect(child, found)

        def run(duration, frame, done):

            start = time.time()

            def tick():

                t = min(1.0, (time.time() - start) / duration)

                try:
                    frame(t)
                except Exception:
                    pass

                if t < 1.0:
                    self.after(16, tick)
                else:
                    done()

            tick()

        def place_at(dx):

            column.place(
                relx=0.5,
                rely=0.46,
                anchor="center",
                x=int(dx)
            )

        def tint(items, amount):

            for widget, fg in items:

                try:
                    widget.configure(fg=mix_color(BG, fg, amount))
                except Exception:
                    pass

        def reveal():

            items = []

            collect(column, items)

            state["busy"] = True

            def frame(t):

                e = 1 - (1 - t) ** 3

                place_at((1 - e) * 44)

                tint(items, e)

            def done():

                state["busy"] = False

                place_at(0)

            frame(0.0)

            run(0.4, frame, done)

        def leave(then):

            items = []

            collect(column, items)

            def frame(t):

                e = t * t

                place_at(-e * 44)

                tint(items, 1 - e)

            run(0.2, frame, then)

        def swap(action):

            if state["busy"]:
                return

            state["busy"] = True

            leave(action)

        def finish():

            swap(finish_now)

        def dots(active):

            row = tk.Frame(column, bg=BG)

            row.pack(pady=(26, 0))

            for index in range(len(TOUR)):

                tk.Frame(
                    row,
                    bg=PURPLE_HOVER if index == active else BORDER,
                    width=22 if index == active else 8,
                    height=8
                ).pack(
                    side="left",
                    padx=4
                )

        def show_tour(index):

            clear()

            kind, color, title, text, *more = TOUR[index]

            extra = more[0] if more else {}

            if HAS_PIL:

                holder = tk.Canvas(
                    column,
                    width=88,
                    height=88,
                    bg=BG,
                    highlightthickness=0,
                    bd=0
                )

                holder.pack(pady=(0, 18))

                glyph = nav_icon_image(kind, color, 56, filled=True)

                holder._photo = ImageTk.PhotoImage(glyph)

                holder.create_oval(
                    0, 0, 87, 87,
                    fill=PANEL,
                    outline=BORDER
                )

                holder.create_image(44, 44, image=holder._photo)

            tk.Label(
                column,
                text=title,
                bg=BG,
                fg=TEXT,
                font=("Segoe UI", 24, "bold")
            ).pack()

            if text:

                tk.Label(
                    column,
                    text=text,
                    bg=BG,
                    fg=MUTED,
                    font=("Segoe UI", 11),
                    wraplength=420,
                    justify="center"
                ).pack(
                    pady=(10, 0)
                )

            if extra.get("steps"):

                steps = tk.Frame(column, bg=BG)

                steps.pack(pady=(14, 0))

                for number, line in enumerate(extra["steps"], 1):

                    row = tk.Frame(steps, bg=BG)

                    row.pack(anchor="w", pady=3)

                    tk.Label(
                        row,
                        text=str(number),
                        bg=PURPLE,
                        fg="#FFFFFF",
                        width=2,
                        font=("Segoe UI", 9, "bold")
                    ).pack(side="left", padx=(0, 10))

                    tk.Label(
                        row,
                        text=line,
                        bg=BG,
                        fg=TEXT,
                        font=("Segoe UI", 10),
                        wraplength=380,
                        justify="left"
                    ).pack(side="left")

            if extra.get("link"):

                label, url = extra["link"]

                def open_link(address=url):

                    try:

                        import webbrowser

                        webbrowser.open(address)

                    except Exception:
                        pass

                self.make_button(
                    column,
                    label,
                    open_link,
                    width=22
                ).pack(pady=(14, 0))

            dots(index)

            buttons = tk.Frame(column, bg=BG)

            buttons.pack(pady=(26, 0))

            last = index == len(TOUR) - 1

            if not last:

                self.make_button(
                    buttons,
                    "Skip",
                    finish,
                    width=8
                ).pack(
                    side="left",
                    padx=(0, 10)
                )

            go = self.make_button(
                buttons,
                "Get started" if last else "Next",
                finish if last else (
                    lambda: swap(lambda: show_tour(index + 1))
                ),
                width=12
            )

            go.configure(selected=True)

            go.pack(side="left")

            reveal()

        def show_welcome():

            clear()

            badge = tk.Canvas(
                column,
                width=64,
                height=64,
                bg=BG,
                highlightthickness=0,
                bd=0
            )

            badge.pack(pady=(0, 18))

            self._draw_logo_badge(badge, size=64)

            tk.Label(
                column,
                text="Welcome to Studestics",
                bg=BG,
                fg=TEXT,
                font=("Segoe UI", 28, "bold")
            ).pack()

            tk.Label(
                column,
                text="A quiet place to organize your study life.",
                bg=BG,
                fg=MUTED,
                font=("Segoe UI", 12)
            ).pack(
                pady=(6, 24)
            )

            avatar = self._avatar_canvas(column, 92, "?", BG)

            avatar.pack()

            avatar.configure(cursor="hand2")

            self._avatar_hover_edit(avatar, 92)

            add_photo = tk.Label(
                column,
                text="Add a photo (optional)",
                bg=BG,
                fg=MUTED_2,
                font=("Segoe UI", 9),
                cursor="hand2"
            )

            add_photo.pack(pady=(6, 18))

            tk.Label(
                column,
                text="What should Studestics call you?",
                bg=BG,
                fg=MUTED,
                font=("Segoe UI", 10)
            ).pack(
                pady=(0, 8)
            )

            entry = self.make_entry(column)

            entry.configure(width=30, justify="center")

            entry.pack(ipady=10)

            if preview:

                current = self.db.get_profile()

                if current:
                    entry.insert(0, current["name"])

            def letter():

                return (entry.get().strip()[:1] or "?").upper()

            shown = {"photo": None}

            def repaint(event=None):

                self._avatar_paint(
                    avatar, 92, letter(), BG, shown["photo"]
                )

            def pick_photo(event=None):

                if preview:

                    # Just show the picture here; don't change the
                    # real profile photo.
                    path = filedialog.askopenfilename(
                        title="Choose a picture",
                        filetypes=[
                            ("Images", "*.png *.jpg *.jpeg *.webp *.gif"),
                            ("All files", "*.*")
                        ]
                    )

                    if path:

                        shown["photo"] = path

                        repaint()

                    return

                self.choose_profile_photo()

                repaint()

            for w in (avatar, add_photo):
                w.bind("<Button-1>", pick_photo)

            entry.bind("<KeyRelease>", repaint)

            repaint()

            def save(event=None):

                name = entry.get().strip()

                if not name:

                    entry.focus_set()

                    return

                if not preview:

                    self.db.save_profile(name)

                    self._refresh_profile_chip()

                swap(lambda: show_tour(0))

            go = self.make_button(
                column,
                "Continue",
                save,
                width=14
            )

            go.configure(selected=True)

            go.pack(pady=(22, 0))

            entry.bind("<Return>", save)

            entry.focus_set()

            reveal()

        show_welcome()

    # ========================================================
    # CLOSE
    # ========================================================

    # ========================================================
    # REMINDERS (run in the background while the app is open)
    # ========================================================

    REMINDER_DEFAULTS = {
        "Low": ("remind_low", 120),
        "Medium": ("remind_medium", 60),
        "High": ("remind_high", 30)
    }

    def _fmt_minutes(self, minutes):

        if minutes % 60 == 0:
            return f"{minutes // 60} h"

        if minutes > 60:
            return f"{minutes // 60} h {minutes % 60} min"

        return f"{minutes} min"

    def reminder_default(self, priority):

        key, fallback = self.REMINDER_DEFAULTS.get(
            priority,
            self.REMINDER_DEFAULTS["Medium"]
        )

        try:
            value = int(self.db.get_setting(key, str(fallback)))
        except (TypeError, ValueError):
            value = fallback

        return max(1, value)

    def reminder_interval_minutes(self, task):

        try:
            custom = int(task["remind_minutes"] or 0)
        except (KeyError, IndexError, TypeError, ValueError):
            custom = 0

        if custom > 0:
            return custom

        return self.reminder_default(task["priority"])

    def start_reminders(self):

        self.after(20000, self._reminder_tick)

    def _effective_interval(self, task):
        """The reminder gap for a task, shorter as its deadline nears."""

        base = self.reminder_interval_minutes(task) * 60

        dl = deadline_dt(task["deadline"])

        if dl is not None:

            secs = (dl - datetime.now()).total_seconds()

            if 0 < secs <= 3 * 3600:
                base = min(base, 20 * 60)

            elif 0 < secs <= DUE_SOON_SECONDS:
                base = min(base, 60 * 60)

        return base

    def _deadline_sweep(self, pending):
        """Once per tick: delete overdue tasks (if that is switched
        on), and raise the one-time 'due in an hour' / 'just became
        overdue' alerts. Returns the tasks that are still pending."""

        now = datetime.now()

        keep, removed, alerts = [], [], []

        for task in pending:

            state, label, _ = due_info(task["deadline"], now)

            if (
                state == "overdue"
                and self.auto_delete_overdue
                and task["id"] not in self._auto_skip
            ):

                removed.append(dict(task))

                self.db.delete_task(task["id"], keep_image=True)

                continue

            keep.append(task)

            dl = deadline_dt(task["deadline"])

            if dl is None:
                continue

            secs = (dl - now).total_seconds()

            if state == "soon" and secs <= DUE_ALERT_SECONDS:

                key = (task["id"], task["deadline"], "soon")

                if key not in self._deadline_alerted:

                    self._deadline_alerted.add(key)

                    alerts.append((task, label))

            elif state == "overdue" and -secs <= 30 * 60:

                # Only for tasks that have just run out: opening the
                # app must not announce every old task again.
                key = (task["id"], task["deadline"], "over")

                if key not in self._deadline_alerted:

                    self._deadline_alerted.add(key)

                    alerts.append((task, label))

        if removed:

            self.show_auto_removed(removed)

            if self.current_page in ("Dashboard", "Tasks"):
                self.show_page(self.current_page)
            else:
                self.refresh_sidebar_upnext()

        if alerts:
            self.show_deadline_alert(alerts)

        return keep

    def _small_popup(self, title, heading, lines, buttons):
        """A small always-on-top popup in the nudge style. `buttons`
        is a list of (label, command, primary)."""

        win = tk.Toplevel(self)

        win.title(title)
        win.configure(bg=BG)
        win.attributes("-topmost", True)

        self.center_window(win, 480, 170 + 24 * len(lines))

        self._nudge_beep()

        tk.Label(
            win,
            text=heading,
            bg=BG,
            fg=TEXT,
            font=("Segoe UI", 16, "bold")
        ).pack(
            anchor="w",
            padx=28,
            pady=(24, 8)
        )

        bar = tk.Frame(win, bg=BG)

        bar.pack(
            side="bottom",
            fill="x",
            padx=28,
            pady=20
        )

        for label, command, primary in reversed(buttons):

            button = self.make_button(
                bar,
                label,
                lambda c=command: (c(), win.destroy()),
                width=10
            )

            if primary:
                button.configure(selected=True)

            button.pack(
                side="right",
                padx=(8, 0)
            )

        for line in lines:

            tk.Label(
                win,
                text=line,
                bg=BG,
                fg=MUTED,
                font=("Segoe UI", 10),
                anchor="w",
                justify="left",
                wraplength=420
            ).pack(
                anchor="w",
                padx=28,
                pady=1
            )

        return win

    @staticmethod
    def _title_lines(titles, limit=4):

        def clip(text):
            return text if len(text) <= 38 else text[:37] + "…"

        lines = [clip(t) for t in titles[:limit]]

        if len(titles) > limit:
            lines.append(f"+ {len(titles) - limit} more")

        return lines

    def show_deadline_alert(self, alerts):

        if self._deadline_popup is not None:

            try:
                self._deadline_popup.destroy()
            except Exception:
                pass

        lines = self._title_lines(
            [f"{t['title']}  \u2014  {label}" for t, label in alerts]
        )

        self._deadline_popup = self._small_popup(
            "Deadline",
            "Deadline coming up" if all(
                l.startswith("Due") for _, l in alerts
            ) else "Deadline reached",
            lines,
            [
                (
                    "Open tasks",
                    lambda: (self.restore_window(), self.show_page("Tasks")),
                    True
                ),
                ("Dismiss", lambda: None, False)
            ]
        )

    def show_auto_removed(self, rows):

        if self._removed_popup is not None:

            try:
                self._removed_popup.destroy()
            except Exception:
                pass

        def undo():

            for row in rows:

                new_id = self.db.add_task(
                    row["title"],
                    row["description"],
                    row["deadline"],
                    row["priority"],
                    row["image_path"],
                    row["remind_minutes"]
                )

                # Back for good: do not sweep it away again.
                self._auto_skip.add(new_id)

            if self.current_page in ("Dashboard", "Tasks"):
                self.show_page(self.current_page)
            else:
                self.refresh_sidebar_upnext()

        lines = self._title_lines([r["title"] for r in rows])

        lines.append("")

        lines.append(
            "Overdue tasks are removed automatically. You can turn "
            "that off in Settings."
        )

        self._removed_popup = self._small_popup(
            "Overdue",
            "Removed overdue task" + ("s" if len(rows) > 1 else ""),
            lines,
            [
                ("Undo", undo, False),
                ("OK", lambda: None, True)
            ]
        )

    def toggle_auto_delete(self):

        self.auto_delete_overdue = not self.auto_delete_overdue

        self.db.set_setting(
            "auto_delete_overdue",
            "1" if self.auto_delete_overdue else "0"
        )

        try:

            self.settings_autodel_button.configure(
                text="On" if self.auto_delete_overdue else "Off",
                selected=self.auto_delete_overdue
            )

        except Exception:
            pass

    def _reminder_tick(self):

        try:

            if self.initialized and self.db and not self._quitting:

                now = time.time()
                pending = self._deadline_sweep(self.db.get_tasks(False))

                due = []
                seen = set()

                for task in pending:

                    task_id = task["id"]
                    seen.add(task_id)

                    # A task's clock starts the first time we see it
                    # (app start or task creation), so nothing fires
                    # the instant you open the app.
                    last = self._reminder_last.setdefault(task_id, now)

                    interval = self._effective_interval(task)

                    if now - last >= interval:
                        due.append(task)

                for task_id in list(self._reminder_last):

                    if task_id not in seen:
                        del self._reminder_last[task_id]

                if due:

                    for task in due:
                        self._reminder_last[task["id"]] = now

                    self.show_reminder(due)

        except Exception:
            pass

        finally:

            if not self._quitting:
                self.after(20000, self._reminder_tick)

    def play_alarm(self, continuous=False):
        """One burst of beeps, or — if continuous — a burst every
        second or so until stop_alarm() is called."""

        self.stop_alarm()

        stop = threading.Event()
        self._alarm_stop = stop

        def worker():

            try:
                import winsound
            except ImportError:
                winsound = None

            while not stop.is_set():

                if winsound is not None:

                    try:

                        for _ in range(3):

                            if stop.is_set():
                                return

                            winsound.Beep(1400, 160)

                            if stop.is_set():
                                return

                            winsound.Beep(1000, 160)

                            stop.wait(0.15)

                    except Exception:
                        return

                else:

                    self.after(0, self.bell)
                    stop.wait(0.4)

                if not continuous:
                    return

                stop.wait(1.0)

        threading.Thread(target=worker, daemon=True).start()

    def stop_alarm(self):

        if self._alarm_stop is not None:
            self._alarm_stop.set()

    def _attach_alarm(self, win, continuous):
        """Start the alarm and tie it to a popup: it stops the moment
        that popup goes away, however it's closed."""

        self._alarm_owner = win

        def on_destroy(event):

            if event.widget is win and self._alarm_owner is win:
                self.stop_alarm()

        win.bind("<Destroy>", on_destroy)

        self.play_alarm(continuous)

    def _poll_instance_event(self):
        """A second copy of the app was started: it signals this one
        and exits, and we bring our own window forward."""

        try:

            event = getattr(self, "_single_event", None)

            if event is not None:

                import ctypes

                if ctypes.windll.kernel32.WaitForSingleObject(
                    ctypes.c_void_p(event), 0
                ) == 0:

                    self.restore_window()

        except Exception:
            pass

        try:
            self.after(500, self._poll_instance_event)
        except Exception:
            pass

    def restore_window(self):

        try:

            if getattr(self, "_page_released", False):

                self._page_released = False

                self.show_page(self.current_page)

        except Exception:
            pass

        try:

            self.deiconify()
            self.lift()
            self.focus_force()

        except Exception:
            pass

    def show_reminder(self, tasks):
        """Alarm-style popup: beeps, then stays on top until dealt
        with — even if the main window is hidden in the tray."""

        if self._reminder_popup is not None:

            try:
                self._reminder_popup.destroy()
            except Exception:
                pass

            self._reminder_popup = None

        shown = list(tasks[:4])
        extra = len(tasks) - len(shown)

        win = tk.Toplevel(self)
        self._reminder_popup = win

        # Low-priority reminders beep once; Medium and High keep
        # ringing until you deal with the popup.
        self._attach_alarm(
            win,
            any(t["priority"] in ("Medium", "High") for t in tasks)
        )

        win.title("Studestics reminder")
        win.configure(bg=BG)
        win.attributes("-topmost", True)

        self.center_window(
            win,
            480,
            235 + 46 * len(shown) + (24 if extra else 0)
        )

        tk.Label(
            win,
            text="Reminder",
            bg=BG,
            fg=TEXT,
            font=("Segoe UI", 20, "bold")
        ).pack(
            anchor="w",
            padx=28,
            pady=(24, 2)
        )

        count = len(tasks)

        tk.Label(
            win,
            text=(
                "1 task still needs you."
                if count == 1
                else f"{count} tasks still need you."
            ),
            bg=BG,
            fg=MUTED,
            font=("Segoe UI", 10)
        ).pack(
            anchor="w",
            padx=28,
            pady=(0, 14)
        )

        bar = tk.Frame(
            win,
            bg=BG
        )

        bar.pack(
            side="bottom",
            fill="x",
            padx=28,
            pady=20
        )

        rows = tk.Frame(
            win,
            bg=BG
        )

        rows.pack(
            fill="x",
            padx=28
        )

        def finish(task_id, row):

            self.stop_alarm()

            if task_id is not None:

                self.db.complete_task(task_id)
                self.show_page(self.current_page)

            row.destroy()

            if not rows.winfo_children():
                win.destroy()

        for task in shown:

            row = tk.Frame(
                rows,
                bg=PANEL_2
            )

            row.pack(
                fill="x",
                pady=3
            )

            tk.Label(
                row,
                text="●",
                bg=PANEL_2,
                fg=priority_color(task["priority"]),
                font=("Segoe UI", 8)
            ).pack(
                side="left",
                padx=(12, 6),
                pady=10
            )

            title = task["title"]

            if len(title) > 32:
                title = title[:31] + "…"

            tk.Label(
                row,
                text=title,
                bg=PANEL_2,
                fg=TEXT,
                font=("Segoe UI", 10, "bold"),
                anchor="w"
            ).pack(
                side="left",
                fill="x",
                expand=True
            )

            if task["id"] is not None:

                self.make_button(
                    row,
                    "Done",
                    lambda tid=task["id"], r=row: finish(tid, r),
                    width=6
                ).pack(
                    side="right",
                    padx=8,
                    pady=6
                )

        if extra:

            tk.Label(
                win,
                text=f"+ {extra} more",
                bg=BG,
                fg=MUTED_2,
                font=("Segoe UI", 9)
            ).pack(
                anchor="w",
                padx=30,
                pady=(4, 0)
            )

        def snooze():

            for task in tasks:

                if task["id"] is None:
                    continue

                interval = self.reminder_interval_minutes(task) * 60

                # Make it come due again in 10 minutes.
                self._reminder_last[task["id"]] = (
                    time.time() - interval + 600
                )

            win.destroy()

        def open_app():

            self.restore_window()
            self.show_page("Tasks")
            win.destroy()

        self.make_button(
            bar,
            "Dismiss",
            win.destroy,
            width=9
        ).pack(
            side="right"
        )

        self.make_button(
            bar,
            "Snooze 10 min",
            snooze,
            width=12
        ).pack(
            side="right",
            padx=8
        )

        self.make_button(
            bar,
            "Open app",
            open_app,
            width=9
        ).pack(
            side="right"
        )

    def test_reminder(self):

        self.show_reminder([
            {
                "id": None,
                "title": "Test reminder — this is what an alarm looks like",
                "priority": "High"
            }
        ])

    def save_reminder_settings(self):

        values = {}

        for priority, var in self.reminder_vars.items():

            try:
                minutes = int(var.get().strip())
            except ValueError:
                minutes = 0

            if minutes < 1:

                self.settings_status.configure(
                    text="Reminder times must be whole minutes (1 or more).",
                    fg=RED
                )

                return

            values[priority] = minutes

        for priority, minutes in values.items():

            self.db.set_setting(
                self.REMINDER_DEFAULTS[priority][0],
                str(minutes)
            )

        self.settings_status.configure(
            text="Reminder times saved.",
            fg=GREEN
        )

    # ========================================================
    # TRAY / CLOSE
    # ========================================================

    def _poll_tray(self):

        try:

            while True:

                action = self._tray_queue.get_nowait()

                if action == "open":
                    self.restore_window()

                elif action == "float":
                    self.toggle_float()

                elif action == "quit":
                    self.quit_app()
                    return

        except queue.Empty:
            pass

        except Exception:
            pass

        if not self._quitting:
            self.after(300, self._poll_tray)

    def _set_app_icon(self):
        """Window / taskbar icon: the packaged studestics.ico if there
        is one, otherwise the same badge drawn in code."""

        try:

            base = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))

            ico = base / "studestics.ico"

            if ico.exists():

                self.iconbitmap(default=str(ico))

                return

        except Exception:
            pass

        try:

            if HAS_PIL:

                self._icon_photo = ImageTk.PhotoImage(app_icon_image(64))

                self.iconphoto(True, self._icon_photo)

        except Exception:
            pass

    def _release_memory(self):
        """While the window is hidden in the tray, throw away the
        page that was on screen and the picture caches. The page is
        rebuilt when the window comes back."""

        try:

            # Window came back before this ran: leave everything alone.
            if self.state() != "withdrawn":
                return

            self.clear_page()

            self._page_released = True

            _EMOJI_CACHE.clear()

            _PANEL_CORNERS.clear()

            gc.collect()

        except Exception:
            pass

    def hide_to_tray(self):

        self.withdraw()

        self.after(1500, self._release_memory)

        if self._tray_icon is None:

            img = app_icon_image(64)

            menu = pystray.Menu(
                pystray.MenuItem(
                    "Open Studestics",
                    lambda icon, item: self._tray_queue.put("open"),
                    default=True
                ),
                pystray.MenuItem(
                    lambda item: (
                        "Floating clock: On"
                        if self.float_on
                        else "Floating clock: Off"
                    ),
                    lambda icon, item: self._tray_queue.put("float")
                ),
                pystray.MenuItem(
                    "Quit",
                    lambda icon, item: self._tray_queue.put("quit")
                )
            )

            self._tray_icon = pystray.Icon(
                "studestics",
                img,
                "Studestics — reminders running",
                menu
            )

            threading.Thread(
                target=self._tray_icon.run,
                daemon=True
            ).start()

        if not self._tray_hint_shown:

            self._tray_hint_shown = True

            def hint():

                try:

                    self._tray_icon.notify(
                        "Still running in the background — reminders "
                        "will keep coming. Right-click the tray icon "
                        "to quit.",
                        "Studestics"
                    )

                except Exception:
                    pass

            self.after(1000, hint)

    def close_app(self):

        # With the tray available, the X button hides the app instead
        # of quitting, so reminders keep firing in the background.
        if (
            pystray is not None
            and HAS_PIL
            and not self._quitting
            and self.db is not None
        ):

            self.hide_to_tray()
            return

        self.quit_app()

    def quit_app(self):

        self._quitting = True

        if self.focus_job:

            try:

                self.after_cancel(
                    self.focus_job
                )

            except Exception:
                pass

        if self._tray_icon is not None:

            try:
                self._tray_icon.stop()
            except Exception:
                pass

        if self.db:

            self.db.close()

        self.destroy()


# ============================================================
# START
# ============================================================

def _configure_dpi_awareness():
    """Tell Windows this app handles its own scaling, instead of being
    blurily upscaled by the OS compositor — this is the #1 cause of a
    Tkinter app looking 'pixelated' on any scaled display (125%/150%,
    which is most laptops). Returns the display's scale factor (e.g.
    1.5 for 150%) so Tk's own widget/font scaling can be matched to it;
    without that second step, text and buttons would render sharp but
    tiny once Windows stops upscaling them for us.
    """

    if sys.platform != "win32":
        return 1.0

    try:

        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(1)

        scale_percent = ctypes.windll.shcore.GetScaleFactorForDevice(0)

        return max(1.0, scale_percent / 100.0)

    except Exception:

        try:

            import ctypes

            ctypes.windll.user32.SetProcessDPIAware()

        except Exception:
            pass

        return 1.0


def _acquire_single_instance():
    """Returns (ok, show_event). ok is False when another copy is
    already running; that copy has then been told to show itself."""

    if not sys.platform.startswith("win"):
        return True, None

    try:

        import ctypes

        kernel = ctypes.WinDLL("kernel32", use_last_error=True)

        kernel.CreateEventW.restype = ctypes.c_void_p
        kernel.CreateMutexW.restype = ctypes.c_void_p
        kernel.SetEvent.argtypes = [ctypes.c_void_p]

        event = kernel.CreateEventW(None, False, False, "Local\\Studestics.Show")

        # After "Restart now" the old copy is still closing, so wait
        # for its lock instead of mistaking it for a second copy.
        attempts = 40 if "--restarted" in sys.argv else 1

        for attempt in range(attempts):

            mutex = kernel.CreateMutexW(
                None, False, "Local\\Studestics.Instance"
            )

            already = ctypes.get_last_error() == 183 and mutex

            if not already:
                break

            if attempt < attempts - 1:

                kernel.CloseHandle(ctypes.c_void_p(mutex))
                time.sleep(0.25)

        if already:

            if event:
                kernel.SetEvent(event)

            return False, None

        # Keep the handles alive for the life of the process.
        _SINGLE_INSTANCE_HANDLES.extend([mutex, event])

        return True, event

    except Exception:

        return True, None


_SINGLE_INSTANCE_HANDLES = []


def main():

    ok, show_event = _acquire_single_instance()

    if not ok:
        return

    dpi_scale = _configure_dpi_awareness()

    # Without this Windows groups the window under python.exe and shows
    # Python's icon in the taskbar.
    try:

        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "Studestics.App"
        )

    except Exception:
        pass

    app = StudesticsApp()

    # Started by Windows at sign-in: never show the window at all.
    if "--background" in sys.argv:
        app.withdraw()

    app._single_event = show_event

    if show_event:
        app.after(500, app._poll_instance_event)

    if dpi_scale != 1.0:

        # Tk's default scaling assumes 96 DPI (1.333 units/point). Match
        # it to the real display scale so widgets and fonts come out the
        # correct physical size instead of shrinking now that Windows
        # isn't upscaling the whole window for us anymore.
        app.tk.call("tk", "scaling", 1.333333 * dpi_scale)

    app.mainloop()


if __name__ == "__main__":
    main()
