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
import random
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

# Bump VERSION for every release you publish on GitHub; the app compares
# it with the newest release tag (v1.0.1, v1.1.0 ...) of UPDATE_REPO.
VERSION = "1.6.4"
UPDATE_REPO = "alyavoidx/studestics"

APP_DIR = Path.home() / ".studestics"
DB_PATH = APP_DIR / "studestics.db"
ATTACH_DIR = APP_DIR / "attachments"

APP_DIR.mkdir(parents=True, exist_ok=True)
ATTACH_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# COLORS (themes)
# ============================================================

THEMES = {
    "Light": {
        "bg": "#F3F3F8", "sidebar": "#E9E9F1", "panel": "#FFFFFF",
        "panel2": "#F0F0F6", "border": "#D8D8E4", "text": "#1C1B26",
        "muted": "#5C5C70", "muted2": "#8C8C9E",
        "accent": "#7C3AED", "accent_hover": "#6D28D9",
        "light": True,
        "green": "#059669", "red": "#DC2626",
        "yellow": "#D97706", "blue": "#2563EB"
    },
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
    },
    "Sunset": {
        "bg": "#140C0A", "sidebar": "#190F0C", "panel": "#201410",
        "panel2": "#2D1C16", "border": "#43291F", "text": "#FFF0E6",
        "muted": "#C4A394", "muted2": "#8C6B5C",
        "accent": "#E8743B", "accent_hover": "#FFA06B"
    },
    "Ice": {
        "bg": "#07121A", "sidebar": "#0A1822", "panel": "#0D1F2B",
        "panel2": "#143042", "border": "#1F4A60", "text": "#E9F8FF",
        "muted": "#93B8CB", "muted2": "#5E8499",
        "accent": "#38A3D8", "accent_hover": "#6CC4F0"
    }
}

# The themes that ship with the app; anything else comes from a .css
# file in the themes folder.
BUILTIN_THEMES = tuple(THEMES)


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


# ------------------------------------------------------------
# Theme files (.css with variables), like shareable client themes
# ------------------------------------------------------------

THEMES_DIR = APP_DIR / "themes"

try:
    THEMES_DIR.mkdir(parents=True, exist_ok=True)
except Exception:
    pass

CUSTOM_THEME_FILES = {}

# Custom themes removed while they were the running theme: still
# needed until the next restart, but not shown in the picker.
REMOVED_THEMES = set()


def _css_hex(value):
    """'#abc' or '#aabbcc' -> '#AABBCC'; anything else -> None."""

    text = str(value or "").strip().lower()

    match = re.fullmatch(r"#([0-9a-f]{3}|[0-9a-f]{6})", text)

    if not match:
        return None

    digits = match.group(1)

    if len(digits) == 3:
        digits = "".join(c * 2 for c in digits)

    return "#" + digits.upper()


def parse_theme_css(text, fallback_name="Custom"):
    """Reads a theme file. Variables look like `--bg: #101018;`.
    Only --bg and --accent are required; everything else is worked
    out from them when it is missing. Returns (name, theme) or None.
    The name is the first /* comment */ in the file."""

    text = str(text or "")

    name = fallback_name

    found = re.search(r"/\*(.*?)\*/", text, re.S)

    if found and found.group(1).strip():
        name = found.group(1).strip().splitlines()[0].strip()

    name = re.sub(r"[^\w .'()-]", "", name).strip()[:24] or fallback_name

    values = {}

    for key, value in re.findall(r"--([\w-]+)\s*:\s*([^;}]+)", text):
        values[key.strip().lower()] = value.strip()

    bg = _css_hex(values.get("bg"))
    accent = _css_hex(values.get("accent"))

    if not bg or not accent:
        return None

    red, green, blue = _theme_rgb(bg)

    if "light" in values:
        light = values["light"].lower() in ("1", "true", "yes", "on")
    else:
        light = (red * 299 + green * 587 + blue * 114) / 1000 > 150

    def pick(*keys, fallback):

        for key in keys:

            found_value = _css_hex(values.get(key))

            if found_value:
                return found_value

        return fallback

    if light:

        toward = "#000000"

        defaults = {
            "sidebar": _theme_mix(bg, toward, 0.04),
            "panel": "#FFFFFF",
            "panel2": _theme_mix(bg, toward, 0.04),
            "border": _theme_mix(bg, toward, 0.12),
        }

        text_default = "#1C1B26"

    else:

        toward = "#FFFFFF"

        defaults = {
            "sidebar": _theme_mix(bg, toward, 0.025),
            "panel": _theme_mix(bg, toward, 0.055),
            "panel2": _theme_mix(bg, toward, 0.11),
            "border": _theme_mix(bg, toward, 0.19),
        }

        text_default = "#F2F2F7"

    text_col = pick("text", fallback=text_default)

    theme = {
        "bg": bg,
        "sidebar": pick("sidebar", fallback=defaults["sidebar"]),
        "panel": pick("panel", fallback=defaults["panel"]),
        "panel2": pick("panel2", "panel-2", fallback=defaults["panel2"]),
        "border": pick("border", fallback=defaults["border"]),
        "text": text_col,
        "muted": pick(
            "muted", fallback=_theme_mix(text_col, bg, 0.35)
        ),
        "muted2": pick(
            "muted2", "muted-2", fallback=_theme_mix(text_col, bg, 0.6)
        ),
        "accent": accent,
        "accent_hover": pick(
            "accent-hover", "accent2",
            fallback=_theme_mix(accent, "#FFFFFF", 0.3)
        )
    }

    if light:
        theme["light"] = True

    for key in ("green", "red", "yellow", "blue"):

        colour = _css_hex(values.get(key))

        if colour:
            theme[key] = colour

    first = _css_hex(values.get("logo-from"))
    second = _css_hex(values.get("logo-to"))

    if first and second:
        theme["logo_from"] = _theme_rgb(first)
        theme["logo_to"] = _theme_rgb(second)

    return name, theme


def theme_to_css(name, theme):
    """The text of a theme file for `theme`."""

    lines = [f"/* {name} */", ":root {"]

    for key, label in (
        ("bg", "bg"), ("sidebar", "sidebar"), ("panel", "panel"),
        ("panel2", "panel2"), ("border", "border"), ("text", "text"),
        ("muted", "muted"), ("muted2", "muted2"),
        ("accent", "accent"), ("accent_hover", "accent-hover")
    ):
        lines.append(f"  --{label}: {theme[key]};")

    if "logo_from" in theme:

        lines.append("  --logo-from: #%02X%02X%02X;" % tuple(theme["logo_from"]))
        lines.append("  --logo-to: #%02X%02X%02X;" % tuple(theme["logo_to"]))

    if theme.get("light"):
        lines.append("  --light: true;")

    lines.append("}")

    return "\n".join(lines) + "\n"


def load_custom_themes():
    """(Re)reads every .css file in the themes folder into THEMES."""

    for name in [n for n in THEMES if n not in BUILTIN_THEMES]:
        del THEMES[name]

    CUSTOM_THEME_FILES.clear()

    try:
        files = sorted(THEMES_DIR.glob("*.css"))
    except Exception:
        files = []

    for path in files:

        try:

            parsed = parse_theme_css(
                path.read_text(encoding="utf-8", errors="ignore"),
                path.stem
            )

        except Exception:
            parsed = None

        if not parsed:
            continue

        name, theme = parsed

        base, number = name, 2

        while name in THEMES:

            name = f"{base} ({number})"

            number += 1

        THEMES[name] = theme

        CUSTOM_THEME_FILES[name] = path


load_custom_themes()


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

IS_LIGHT = bool(_THEME.get("light"))

GREEN = _THEME.get("green", "#34D399")
RED = _THEME.get("red", "#F87171")
YELLOW = _THEME.get("yellow", "#FBBF24")
BLUE = _THEME.get("blue", "#60A5FA")

# Hover color for destructive buttons (Delete)
DANGER_HOVER = "#DC2626"

# Shades worked out from the theme, so every theme gets matching
# hover states, chips and "dim" cards.
HOVER_BG = _theme_mix(PANEL_2, TEXT, 0.07)
CHIP_BG = _theme_mix(PANEL_2, TEXT, 0.045)
TRACK = _theme_mix(PANEL_2, TEXT, 0.05)
SIDEBAR_HOVER = _theme_mix(SIDEBAR, TEXT, 0.05)
DEEP = _theme_mix(BG, "#000000", 0.07 if IS_LIGHT else 0.4)
COMPLETED_BG = _theme_mix(BG, GREEN, 0.06)
NAV_TEXT = _theme_mix(TEXT, BG, 0.18)
NAV_ICON = _theme_mix(MUTED, TEXT, 0.35)
NAV_HOVER_ICON = _theme_mix(TEXT, BG, 0.08)

ACCENT_RGB = _theme_rgb(PURPLE_HOVER)
ACCENT_LIGHT_RGB = _theme_rgb(PURPLE_LIGHT)

# Neutral flat pills (Edit, Pause...) as RGB tuples.
DANGER_FILL = (254, 226, 226) if IS_LIGHT else (42, 22, 24)
DANGER_EDGE = (248, 180, 180) if IS_LIGHT else (112, 42, 46)

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
GEMINI_MODEL = "gemini-3.5-flash-lite"

# If the primary model is ever unavailable, the app tries these in order
# before giving up — so a single Google-side deprecation or alias hiccup
# doesn't silently kill the chat until someone edits source code.
# Free-quota trimming: how many tasks/goals go into each prompt, the
# reply length cap, and how many chat turns share one server-side
# conversation before it's started fresh (long chains re-send the whole
# history to Gemini on every turn, which burns quota).
AI_CONTEXT_ITEMS = 5
AI_MAX_OUTPUT_TOKENS = 16384
AI_NOTES_MAX_OUTPUT_TOKENS = 32768
AI_RESET_AFTER_TURNS = 8

GEMINI_MODEL_FALLBACKS = [
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-flash-latest",
    "gemini-3.8-flash",
]


# ============================================================
# ALARM SOUNDS
# ============================================================

SOUNDS_DIR = APP_DIR / "sounds"

SOUND_PRESETS = ("Classic", "Chime", "Digital", "Gentle", "Pulse")

_SOUND_REV = "2"


def _sound_samples(name, rate=22050):
    """The samples (floats, -1..1) of one preset, about 1.5 s long."""

    out = []

    def silence(seconds):

        out.extend([0.0] * int(rate * seconds))

    def tone(freq, seconds, volume=0.55, decay=0.0, soft=False,
             harmonics=()):

        count = int(rate * seconds)

        fade = max(1, int(rate * 0.006))

        for i in range(count):

            t = i / rate

            value = math.sin(2 * math.pi * freq * t)

            for mult, amount in harmonics:
                value += amount * math.sin(2 * math.pi * freq * mult * t)

            if decay:
                value *= math.exp(-decay * t)

            envelope = 1.0

            if soft:

                envelope = math.sin(math.pi * i / max(1, count - 1)) ** 0.7

            else:

                if i < fade:
                    envelope = i / fade
                elif i > count - fade:
                    envelope = (count - i) / fade

            out.append(value * volume * envelope)

    if name == "Classic":

        for _ in range(3):

            tone(1400, 0.16)
            tone(1000, 0.16)
            silence(0.15)

        silence(0.25)

    elif name == "Chime":

        # Three bell notes that ring into each other.
        mix = [0.0] * int(rate * 2.2)

        for start, freq in ((0.0, 1047), (0.28, 1319), (0.56, 1568)):

            note = []

            saved = out[:]

            out.clear()

            tone(freq, 1.5, 0.4, decay=2.6, harmonics=((2.0, 0.35), (3.0, 0.12)))

            note = out[:]

            out[:] = saved

            offset = int(rate * start)

            for i, value in enumerate(note):

                if offset + i < len(mix):
                    mix[offset + i] += value

        out.extend(mix)

    elif name == "Digital":

        for _ in range(6):

            tone(2000, 0.07, 0.5)
            silence(0.07)

        silence(0.5)

    elif name == "Gentle":

        tone(660, 0.5, 0.5, soft=True, harmonics=((2.0, 0.2),))
        tone(880, 0.6, 0.5, soft=True, harmonics=((2.0, 0.2),))
        silence(0.4)

    else:  # Pulse

        for _ in range(4):

            tone(520, 0.22, 0.55, soft=True)
            silence(0.1)

        silence(0.3)

    return out


def sound_preset_path(name):
    """Makes the preset's .wav the first time it is needed."""

    import wave
    import array

    SOUNDS_DIR.mkdir(parents=True, exist_ok=True)

    path = SOUNDS_DIR / f"{name.lower()}_v{_SOUND_REV}.wav"

    if not path.exists():

        samples = _sound_samples(name)

        data = array.array(
            "h",
            [max(-32767, min(32767, int(v * 32767))) for v in samples]
        )

        with wave.open(str(path), "wb") as handle:

            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(22050)
            handle.writeframes(data.tobytes())

    return path


def mci_send(command):
    """Windows' built-in media player (plays wav, mp3, wma, m4a)."""

    import ctypes

    buffer = ctypes.create_unicode_buffer(255)

    error = ctypes.windll.winmm.mciSendStringW(command, buffer, 254, 0)

    return error, buffer.value


_LOFI_REV = "1"


def lofi_path():
    """A calm lofi loop (about a minute) made by the app itself, so
    nothing has to be downloaded. Written once, then reused."""

    import wave
    import array
    import random

    SOUNDS_DIR.mkdir(parents=True, exist_ok=True)

    path = SOUNDS_DIR / f"lofi_v{_LOFI_REV}.wav"

    if path.exists():
        return path

    rate = 22050
    beat = 60.0 / 72
    bar = beat * 4
    rng = random.Random(11)
    two_pi = 2 * math.pi

    def hz(midi):
        return 440.0 * 2 ** ((midi - 69) / 12.0)

    # (bass note, chord notes, melody notes that fit it)
    progression = [
        (38, (53, 57, 60, 64), (69, 72, 74, 76)),   # Dm9
        (43, (53, 59, 62, 64), (67, 71, 74, 76)),   # G13
        (36, (55, 59, 62, 64), (67, 71, 74, 79)),   # Cmaj9
        (45, (55, 59, 60, 64), (69, 72, 76, 79)),   # Am9
    ]

    # ---- one chord: soft electric-piano notes with a little tape wobble
    chord_len = int(rate * bar * 2)

    warp = [
        i / rate + 0.00095 * math.sin(math.pi * i / rate)
        for i in range(chord_len)
    ]

    envelope = []
    bright = []

    for i in range(chord_len):

        t = i / rate

        attack = min(1.0, t / 0.012)
        release = min(1.0, (chord_len - i) / (rate * 0.35))

        envelope.append(attack * release * math.exp(-t * 0.75))
        bright.append(math.exp(-t * 5.0))

    def chord_wave(notes):

        wave_out = [0.0] * chord_len

        for note in notes:

            f = hz(note) * two_pi

            for i in range(chord_len):

                w = warp[i] * f

                wave_out[i] += envelope[i] * (
                    math.sin(w) + 0.32 * bright[i] * math.sin(2 * w)
                )

        return [v * 0.11 for v in wave_out]

    chord_waves = [chord_wave(notes) for _, notes, _ in progression]

    # ---- bass, kick, snare, hat, melody pluck (each made once)
    def bass_wave(note, beats):

        n = int(rate * beat * beats)
        f = hz(note) * two_pi

        return [
            0.34 * math.sin(f * i / rate)
            * min(1.0, i / (rate * 0.01))
            * math.exp(-i / rate * 2.4)
            * min(1.0, (n - i) / (rate * 0.08))
            for i in range(n)
        ]

    def pluck_wave(note):

        n = int(rate * 1.1)
        f = hz(note) * two_pi

        return [
            0.15 * (
                math.sin(f * i / rate)
                + 0.25 * math.sin(2 * f * i / rate)
                * math.exp(-i / rate * 8)
            )
            * min(1.0, i / (rate * 0.008))
            * math.exp(-i / rate * 3.2)
            for i in range(n)
        ]

    kick = []

    n = int(rate * 0.22)
    phase = 0.0

    for i in range(n):

        t = i / rate

        phase += two_pi * (45 + 85 * math.exp(-t * 28)) / rate

        kick.append(0.8 * math.sin(phase) * math.exp(-t * 15))

    snare = []

    n = int(rate * 0.2)
    soft = 0.0

    for i in range(n):

        t = i / rate

        soft += 0.45 * (rng.uniform(-1, 1) - soft)

        snare.append(
            (0.32 * soft + 0.12 * math.sin(two_pi * 190 * t))
            * math.exp(-t * 22)
        )

    hat = []

    n = int(rate * 0.06)
    last = 0.0

    for i in range(n):

        t = i / rate

        noise = rng.uniform(-1, 1)

        hat.append(0.1 * (noise - last) * math.exp(-t * 80))

        last = noise

    # ---- lay it all out: 4 chords x 2 passes = 16 bars
    total = int(rate * bar * 16)

    mix = [0.0] * total

    def put(samples, at):

        start = int(at * rate)

        if start < 0:
            return

        end = min(total, start + len(samples))

        for i in range(start, end):
            mix[i] += samples[i - start]

    for index in range(8):

        bass, notes, melody = progression[index % 4]

        base = index * bar * 2

        put(chord_waves[index % 4], base)

        for bar_no in range(2):

            top = base + bar_no * bar

            put(bass_wave(bass, 1.6), top)
            put(bass_wave(bass + (7 if bar_no else 0), 1.0),
                top + beat * 2.5)

            put(kick, top + rng.uniform(0, 0.006))
            put(kick, top + beat * 2.5 + rng.uniform(0, 0.008))

            put(snare, top + beat * 1 + rng.uniform(0, 0.01))
            put(snare, top + beat * 3 + rng.uniform(0, 0.01))

            for step in range(8):

                swing = 0.09 * beat if step % 2 else 0.0

                put(
                    hat,
                    top + step * beat / 2 + swing
                    + rng.uniform(0, 0.006)
                )

            for step in range(8):

                if rng.random() < 0.32:

                    put(
                        pluck_wave(rng.choice(melody)),
                        top + step * beat / 2 + rng.uniform(0, 0.012)
                    )

    # ---- warm it up: roll off the highs, add a little vinyl crackle
    peak = max(abs(v) for v in mix) or 1.0

    scale = 0.62 / peak

    out = []

    y = 0.0

    for i in range(total):

        y += 0.62 * (mix[i] * scale - y)

        v = y + rng.uniform(-1, 1) * 0.003

        out.append(v)

    pops = int(total / rate * 5)

    for _ in range(pops):

        at = rng.randrange(total - 3)

        size = rng.uniform(0.015, 0.06) * rng.choice((-1, 1))

        out[at] += size
        out[at + 1] -= size * 0.5

    fade = int(rate * 0.01)

    for i in range(fade):

        k = i / fade

        out[i] *= k
        out[total - 1 - i] *= k

    data = array.array(
        "h",
        [max(-32767, min(32767, int(v * 32767))) for v in out]
    )

    temp = path.with_suffix(".tmp")

    with wave.open(str(temp), "wb") as handle:

        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(data.tobytes())

    temp.replace(path)

    return path



def picture_palette(path, count=6):
    """The main colours of a picture, best first, plus a small
    preview of it. Returns (list of (r, g, b), PIL image)."""

    import colorsys
    from PIL import ImageOps

    with Image.open(path) as opened:
        img = ImageOps.exif_transpose(opened).convert("RGB")

    preview = ImageOps.fit(img, (240, 150), Image.LANCZOS)

    small = img.copy()

    small.thumbnail((160, 160))

    quant = small.quantize(colors=12)

    palette = quant.getpalette() or []

    found = quant.getcolors() or []

    total = sum(n for n, _ in found) or 1

    scored = []

    for n, index in found:

        r, g, b = palette[index * 3:index * 3 + 3]

        _, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)

        # Common, colourful and not-too-dark colours win.
        scored.append(
            (math.sqrt(n / total) * (0.15 + s) * (0.25 + v), (r, g, b), v)
        )

    scored.sort(reverse=True)

    # Near-black colours make poor accents; use them only if there is
    # nothing else.
    bright = [item for item in scored if item[2] >= 0.22]

    chosen = []

    for _, rgb, _v in (bright or scored):

        if all(
            sum((a - b) ** 2 for a, b in zip(rgb, other)) > 55 ** 2
            for other in chosen
        ):
            chosen.append(rgb)

        if len(chosen) >= count:
            break

    return chosen or [(124, 58, 237)], preview


def theme_from_accent(rgb):
    """A dark theme built around one colour: tinted backgrounds and
    panels, and that colour (made strong enough) as the accent."""

    import colorsys

    h, s, v = colorsys.rgb_to_hsv(*(c / 255 for c in rgb))

    def hexhsv(hue, sat, val):

        r, g, b = colorsys.hsv_to_rgb(
            hue % 1.0, max(0.0, min(1.0, sat)), max(0.0, min(1.0, val))
        )

        return "#%02X%02X%02X" % (
            round(r * 255), round(g * 255), round(b * 255)
        )

    if s < 0.1:

        # A grey picture: keep the app grey, not red.
        tint, acc_s = s * 0.5, s

    else:

        tint = min(0.55, max(0.18, s * 0.65))
        acc_s = max(s, 0.5)

    acc_v = min(0.95, max(v, 0.78))

    return {
        "bg": hexhsv(h, tint, 0.075),
        "sidebar": hexhsv(h, tint, 0.095),
        "panel": hexhsv(h, tint * 0.95, 0.13),
        "panel2": hexhsv(h, tint * 0.9, 0.19),
        "border": hexhsv(h, tint * 0.8, 0.27),
        "text": hexhsv(h, 0.05 if s >= 0.1 else 0.0, 0.97),
        "muted": hexhsv(h, 0.14 if s >= 0.1 else 0.0, 0.76),
        "muted2": hexhsv(h, 0.2 if s >= 0.1 else 0.0, 0.52),
        "accent": hexhsv(h, acc_s, acc_v),
        "accent_hover": hexhsv(h, acc_s * 0.65, min(1.0, acc_v + 0.1))
    }


TIMER_BG_DEFAULTS = {
    "brightness": 100, "saturation": 100, "hue": 0,
    "blur": 0, "darkness": 25
}


def adjust_picture(img, p):
    """The timer background with the sliders applied. `blur` is in
    pixels on a 1920-wide screen and is scaled to the picture."""

    out = img

    if p["blur"]:

        out = out.filter(
            ImageFilter.GaussianBlur(p["blur"] * img.width / 1920.0)
        )

    if p["brightness"] != 100:
        out = ImageEnhance.Brightness(out).enhance(p["brightness"] / 100.0)

    if p["saturation"] != 100:
        out = ImageEnhance.Color(out).enhance(p["saturation"] / 100.0)

    if p["hue"]:

        shift = int(round(p["hue"] * 255 / 360.0))

        h, s, v = out.convert("HSV").split()

        h = h.point([(i + shift) % 256 for i in range(256)])

        out = Image.merge("HSV", (h, s, v)).convert("RGB")

    if p["darkness"]:

        out = Image.blend(
            out, Image.new("RGB", out.size, "#000000"),
            p["darkness"] / 100.0
        )

    return out


def cover_fit(img, size):
    """Scales a picture to cover `size` and crops the middle, with a
    fast reduction step for big photos."""

    w, h = size

    scale = max(w / img.width, h / img.height)

    new = (
        max(w, int(round(img.width * scale))),
        max(h, int(round(img.height * scale)))
    )

    img = img.resize(new, Image.LANCZOS, reducing_gap=2.0)

    left = (new[0] - w) // 2
    top = (new[1] - h) // 2

    return img.crop((left, top, left + w, top + h))


def render_timer_background(path, params, size):
    """The chosen picture with the sliders applied, at `size`. Heavy
    blur is done at half size and scaled up, which looks the same and
    is much faster."""

    from PIL import ImageOps

    work = size

    if params["blur"] >= 4:
        work = (max(2, size[0] // 2), max(2, size[1] // 2))

    with Image.open(path) as opened:

        try:
            opened.draft("RGB", (work[0] * 2, work[1] * 2))
        except Exception:
            pass

        base = ImageOps.exif_transpose(opened).convert("RGB")

    out = adjust_picture(cover_fit(base, work), params)

    if work != size:
        out = out.resize(size, Image.BICUBIC)

    return out


def render_timer_frames(path, params, size, min_ms=20, limit=120):
    """The frames of an animated GIF with the sliders applied, at full
    `size`, kept as small JPEG data: [[bytes, milliseconds], ...]. None
    when the picture isn't animated. Very long GIFs are thinned out."""

    import io
    from PIL import ImageSequence

    work = size

    if params["blur"] >= 4:
        work = (max(2, size[0] // 2), max(2, size[1] // 2))

    with Image.open(path) as opened:

        total = getattr(opened, "n_frames", 1)

        if total < 2:
            return None

        step = max(1, -(-total // limit))

        frames = []

        waited = 0
        pending = False

        for i, frame in enumerate(ImageSequence.Iterator(opened)):

            waited += max(20, int(frame.info.get("duration", 100) or 100))

            if i % step == 0:
                pending = True

            if pending and waited >= min_ms:

                shown = adjust_picture(
                    cover_fit(frame.convert("RGB"), work), params
                )

                if work != size:
                    shown = shown.resize(size, Image.BICUBIC)

                buffer = io.BytesIO()

                shown.save(buffer, "JPEG", quality=90)

                frames.append([buffer.getvalue(), waited])

                waited = 0
                pending = False

    return frames or None


def version_tuple(text):
    """'v1.2.3' -> (1, 2, 3); anything unreadable -> (0, 0, 0)."""

    numbers = [int(n) for n in re.findall(r"\d+", str(text).split("-")[0])]

    return tuple((numbers + [0, 0, 0])[:3])


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
    card=True,
    soft=False
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

    if bg is None and not soft:

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
    "Schedule": "calendar",
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

    elif kind == "calendar":

        d.rounded_rectangle(
            box(3.5, 5, 20.5, 20.5),
            radius=3 * u,
            fill=color if filled else None,
            outline=color,
            width=lw
        )

        d.line(
            [(3.5 * u, 10.2 * u), (20.5 * u, 10.2 * u)],
            fill=gone if filled else color,
            width=int(round(1.9 * u))
        )

        for x in (8, 16):

            d.rounded_rectangle(
                box(x - 1, 2.8, x + 1, 7),
                radius=1 * u,
                fill=color
            )

        for x, y in ((8, 14), (12, 14), (16, 14), (8, 17.4), (12, 17.4)):

            d.ellipse(
                box(x - 1.05, y - 1.05, x + 1.05, y + 1.05),
                fill=gone if filled else color
            )

    elif kind == "bell":

        d.ellipse(box(6, 3.8, 18, 15.5), fill=color)

        d.rounded_rectangle(
            box(4, 12.5, 20, 17.2), radius=2.2 * u, fill=color
        )

        d.ellipse(box(10.2, 17.6, 13.8, 21.2), fill=color)

        d.ellipse(box(10.6, 2.2, 13.4, 5), fill=color)

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

    def set_minutes(self, minutes):

        cur = self._ensure()

        minutes = max(0, min(24 * 60 - 1, int(minutes)))

        self.sel = cur.replace(hour=minutes // 60, minute=minutes % 60)

    def hour24(self):

        return (self.sel or self._ensure()).hour

    def minutes(self):

        cur = self.sel or self._ensure()

        return cur.hour * 60 + cur.minute

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


def office_file_text(path):
    """Plain text from a .docx, .pptx or .xlsx (these are zip files
    of XML). Spreadsheets give their text cells only."""

    import zipfile
    import html as html_lib

    ext = Path(path).suffix.lower()

    def strip(xml):
        return html_lib.unescape(re.sub(r"<[^>]+>", "", xml))

    with zipfile.ZipFile(path) as z:

        names = z.namelist()

        if ext == ".docx":

            xml = z.read("word/document.xml").decode("utf-8", "replace")

            return strip(re.sub(r"</w:p>", "\n", xml))

        if ext == ".pptx":

            slides = sorted(
                (
                    n for n in names
                    if re.match(r"ppt/slides/slide\d+\.xml$", n)
                ),
                key=lambda n: int(re.findall(r"\d+", n)[-1])
            )

            out = []

            for number, name in enumerate(slides, 1):

                xml = z.read(name).decode("utf-8", "replace")

                out.append(
                    f"--- Slide {number} ---\n"
                    + strip(re.sub(r"</a:p>", "\n", xml))
                )

            return "\n".join(out)

        xml = z.read("xl/sharedStrings.xml").decode("utf-8", "replace")

        return "\n".join(
            html_lib.unescape(t)
            for t in re.findall(r"<t[^>]*>(.*?)</t>", xml, re.S)
        )


BROWSER_EXES = (
    "chrome.exe", "msedge.exe", "firefox.exe", "brave.exe",
    "opera.exe", "vivaldi.exe"
)


def _user32():

    import ctypes
    from ctypes import wintypes

    u = ctypes.windll.user32

    u.GetForegroundWindow.restype = wintypes.HWND
    u.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    u.GetWindowTextW.argtypes = [
        wintypes.HWND, wintypes.LPWSTR, ctypes.c_int
    ]
    u.IsWindow.argtypes = [wintypes.HWND]
    u.IsIconic.argtypes = [wintypes.HWND]
    u.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    u.SetForegroundWindow.argtypes = [wintypes.HWND]
    u.PostMessageW.argtypes = [
        wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
    ]
    u.GetWindowThreadProcessId.argtypes = [
        wintypes.HWND, ctypes.POINTER(wintypes.DWORD)
    ]

    return u


def foreground_window_handle():
    """The window in front (an int), or 0."""

    if sys.platform != "win32":
        return 0

    try:
        return int(_user32().GetForegroundWindow() or 0)
    except Exception:
        return 0


def window_title(hwnd):
    """Title of one particular window ('' if it is gone)."""

    if sys.platform != "win32" or not hwnd:
        return ""

    try:

        import ctypes

        u = _user32()

        length = u.GetWindowTextLengthW(hwnd)

        if length <= 0:
            return ""

        buffer = ctypes.create_unicode_buffer(length + 1)
        u.GetWindowTextW(hwnd, buffer, length + 1)

        return buffer.value

    except Exception:
        return ""


def window_exists(hwnd):

    if sys.platform != "win32" or not hwnd:
        return False

    try:
        return bool(_user32().IsWindow(hwnd))
    except Exception:
        return False


def window_process_name(hwnd):
    """File name of the program that owns a window, e.g. chrome.exe."""

    if sys.platform != "win32" or not hwnd:
        return ""

    try:

        import ctypes
        from ctypes import wintypes

        u = _user32()
        k = ctypes.windll.kernel32

        k.OpenProcess.restype = wintypes.HANDLE
        k.OpenProcess.argtypes = [
            wintypes.DWORD, wintypes.BOOL, wintypes.DWORD
        ]
        k.QueryFullProcessImageNameW.argtypes = [
            wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
            ctypes.POINTER(wintypes.DWORD)
        ]
        k.CloseHandle.argtypes = [wintypes.HANDLE]

        pid = wintypes.DWORD(0)

        u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

        handle = k.OpenProcess(0x1000, False, pid.value)

        if not handle:
            return ""

        try:

            buffer = ctypes.create_unicode_buffer(1024)
            size = wintypes.DWORD(1024)

            if k.QueryFullProcessImageNameW(
                handle, 0, buffer, ctypes.byref(size)
            ):
                return os.path.basename(buffer.value).lower()

        finally:
            k.CloseHandle(handle)

    except Exception:
        pass

    return ""


def bring_window_to_front(hwnd):

    try:

        u = _user32()

        if u.IsIconic(hwnd):
            u.ShowWindow(hwnd, 9)

        u.SetForegroundWindow(hwnd)

    except Exception:
        pass


def press_ctrl_w():
    """Ctrl+W goes to whichever window is in front."""

    try:

        import ctypes

        u = ctypes.windll.user32

        u.keybd_event(0x11, 0, 0, 0)
        u.keybd_event(0x57, 0, 0, 0)
        u.keybd_event(0x57, 0, 2, 0)
        u.keybd_event(0x11, 0, 2, 0)

    except Exception:
        pass


def close_window_politely(hwnd):
    """Same as the window's own close button (WM_CLOSE)."""

    try:
        _user32().PostMessageW(hwnd, 0x0010, 0, 0)
    except Exception:
        pass


def screen_rect():
    """x, y, width, height covering every monitor."""

    try:

        import ctypes

        u = ctypes.windll.user32

        x, y = u.GetSystemMetrics(76), u.GetSystemMetrics(77)
        w, h = u.GetSystemMetrics(78), u.GetSystemMetrics(79)

        if w > 0 and h > 0:
            return x, y, w, h

    except Exception:
        pass

    return None


SCHEDULE_DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

SCHEDULE_DAY_NAMES = (
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
    "Saturday", "Sunday"
)


def parse_clock(text):
    """'11', '11:30', '9 pm', '9:30pm', '2330' -> minutes since
    midnight, or None when it isn't a time."""

    cleaned = str(text).strip().lower().replace(".", ":").replace(" ", "")

    found = re.fullmatch(r"(\d{1,2}):?(\d{2})?(am|pm|a|p)?", cleaned)

    if not found:
        return None

    hour = int(found.group(1))
    minute = int(found.group(2) or 0)
    suffix = found.group(3)

    if minute > 59:
        return None

    if suffix:

        if not 1 <= hour <= 12:
            return None

        hour = hour % 12 + (12 if suffix.startswith("p") else 0)

    elif hour > 23:
        return None

    return hour * 60 + minute


def format_clock(minutes):
    """Minutes since midnight -> '11:30 AM'."""

    hour, minute = divmod(int(minutes), 60)

    return f"{hour % 12 or 12}:{minute:02d} {'AM' if hour < 12 else 'PM'}"


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

            # The weekly timetable (Schedule page).
            self.connection.execute(
                """
                CREATE TABLE IF NOT EXISTS schedule (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    start_min INTEGER NOT NULL,
                    end_min INTEGER NOT NULL,
                    days TEXT NOT NULL DEFAULT '',
                    remind_before INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                )
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

            # One-time reminders: a date and time, fired once.
            if "remind_at" not in columns:

                self.connection.execute(
                    "ALTER TABLE tasks ADD COLUMN "
                    "remind_at TEXT DEFAULT ''"
                )

                self.connection.execute(
                    "ALTER TABLE tasks ADD COLUMN "
                    "remind_done INTEGER DEFAULT 0"
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
        remind_minutes=0,
        remind_at=""
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
                    remind_at,
                    created_at
                )
                VALUES (?, ?, ?, ?, 'Pending', ?, ?, ?, ?)
                """,
                (
                    title,
                    description,
                    deadline,
                    priority,
                    image_path,
                    int(remind_minutes or 0),
                    remind_at or "",
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
        remind_minutes=0,
        remind_at=""
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
                    remind_minutes=?,
                    remind_at=?,
                    remind_done=0
                WHERE id=?
                """,
                (
                    title,
                    description,
                    deadline,
                    priority,
                    image_path,
                    int(remind_minutes or 0),
                    remind_at or "",
                    task_id
                )
            )

            self.connection.commit()

    def mark_reminded(self, task_id):

        with self.lock:

            self.connection.execute(
                "UPDATE tasks SET remind_done=1 WHERE id=?",
                (task_id,)
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

    # --------------------------------------------------------
    # Schedule
    # --------------------------------------------------------

    def get_schedule(self):

        with self.lock:

            return self.connection.execute(
                "SELECT * FROM schedule ORDER BY start_min, id"
            ).fetchall()

    def add_schedule(self, title, start_min, end_min, days, remind_before):

        with self.lock:

            self.connection.execute(
                """
                INSERT INTO schedule(
                    title, start_min, end_min, days, remind_before,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    title, start_min, end_min,
                    ",".join(str(day) for day in sorted(days)),
                    remind_before,
                    datetime.now().isoformat(timespec="seconds")
                )
            )

            self.connection.commit()

    def update_schedule(
        self, block_id, title, start_min, end_min, days, remind_before
    ):

        with self.lock:

            self.connection.execute(
                """
                UPDATE schedule
                SET title=?, start_min=?, end_min=?, days=?,
                    remind_before=?
                WHERE id=?
                """,
                (
                    title, start_min, end_min,
                    ",".join(str(day) for day in sorted(days)),
                    remind_before, block_id
                )
            )

            self.connection.commit()

    def delete_all_schedule(self):

        with self.lock:

            self.connection.execute("DELETE FROM schedule")

            self.connection.commit()

    def clear_schedule_day(self, day):
        """Remove every block from one weekday. A block that repeats on
        other days stays on those days."""

        with self.lock:

            rows = self.connection.execute(
                "SELECT id, days FROM schedule"
            ).fetchall()

            for row in rows:

                days = [d for d in row["days"].split(",") if d != ""]

                if str(day) not in days:
                    continue

                days.remove(str(day))

                if days:

                    self.connection.execute(
                        "UPDATE schedule SET days=? WHERE id=?",
                        (",".join(days), row["id"])
                    )

                else:

                    self.connection.execute(
                        "DELETE FROM schedule WHERE id=?", (row["id"],)
                    )

            self.connection.commit()

    def delete_schedule(self, block_id):

        with self.lock:

            self.connection.execute(
                "DELETE FROM schedule WHERE id=?", (block_id,)
            )

            self.connection.commit()

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

            self.connection.execute("DELETE FROM schedule")
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

EMOJI_SHORTCODES_TEXT = """
smile 😄|grin 😁|grinning 😀|smiley 😃|laughing 😆|sweat_smile 😅|rofl 🤣
joy 😂|slight_smile 🙂|upside_down 🙃|wink 😉|blush 😊|innocent 😇
smiling_hearts 🥰|heart_eyes 😍|star_struck 🤩|kissing_heart 😘|kiss 😘
yum 😋|tongue 😛|wink_tongue 😜|zany 🤪|money_mouth 🤑|hug 🤗|shush 🤫
thinking 🤔|zipper_mouth 🤐|raised_eyebrow 🤨|neutral 😐|expressionless 😑
no_mouth 😶|smirk 😏|unamused 😒|rolling_eyes 🙄|grimacing 😬|lying 🤥
relieved 😌|pensive 😔|sleepy 😪|drooling 🤤|sleeping 😴|mask 😷|sick 🤒
nauseated 🤢|vomit 🤮|sneeze 🤧|hot 🥵|cold 🥶|woozy 🥴|dizzy_face 😵
exploding_head 🤯|cowboy 🤠|partying 🥳|sunglasses 😎|cool 😎|nerd 🤓
monocle 🧐|confused 😕|worried 😟|frown 🙁|open_mouth 😮|hushed 😯
astonished 😲|flushed 😳|pleading 🥺|fearful 😨|cold_sweat 😰|sad_relieved 😥
cry 😢|sob 😭|sobbing 😭|scream 😱|confounded 😖|persevere 😣|disappointed 😞
sweat 😓|weary 😩|tired 😫|yawn 🥱|triumph 😤|angry 😠|rage 😡|cursing 🤬
imp 😈|skull 💀|poop 💩|clown 🤡|ghost 👻|alien 👽|robot 🤖
see_no_evil 🙈|hear_no_evil 🙉|speak_no_evil 🙊|wave 👋|raised_hand ✋
ok_hand 👌|pinched 🤏|victory ✌️|crossed_fingers 🤞|love_you 🤟|metal 🤘
call_me 🤙|point_left 👈|point_right 👉|point_up 👆|point_down 👇
thumbsup 👍|+1 👍|thumbsdown 👎|-1 👎|fist 👊|clap 👏|raised_hands 🙌
handshake 🤝|pray 🙏|writing ✍️|muscle 💪|brain 🧠|eyes 👀|tongue_out 👅
shrug 🤷|facepalm 🤦|bow 🙇|heart ❤️|red_heart ❤️|orange_heart 🧡
yellow_heart 💛|green_heart 💚|blue_heart 💙|purple_heart 💜|black_heart 🖤
white_heart 🤍|broken_heart 💔|sparkling_heart 💖|two_hearts 💕|100 💯
hundred 💯|fire 🔥|sparkles ✨|star ⭐|glowing_star 🌟|boom 💥|zap ⚡
check ✅|x ❌|warning ⚠️|question ❓|exclamation ❗|rocket 🚀|rainbow 🌈
sun ☀️|moon 🌙|cloud ☁️|rain 🌧️|snowflake ❄️|ocean 🌊|tada 🎉|party 🎉
confetti 🎊|balloon 🎈|gift 🎁|trophy 🏆|medal 🏅|first_place 🥇|soccer ⚽
basketball 🏀|game 🎮|dice 🎲|puzzle 🧩|art 🎨|music 🎵|notes 🎶
headphones 🎧|guitar 🎸|microphone 🎤|dog 🐶|cat 🐱|mouse 🐭|rabbit 🐰
fox 🦊|bear 🐻|panda 🐼|tiger 🐯|lion 🦁|cow 🐮|pig 🐷|frog 🐸|monkey 🐵
chicken 🐔|penguin 🐧|owl 🦉|bee 🐝|butterfly 🦋|snail 🐌|turtle 🐢
snake 🐍|octopus 🐙|whale 🐳|dolphin 🐬|shark 🦈|unicorn 🦄|cactus 🌵
tree 🌳|seedling 🌱|clover 🍀|rose 🌹|sunflower 🌻|tulip 🌷
cherry_blossom 🌸|mushroom 🍄|apple 🍎|banana 🍌|watermelon 🍉|grapes 🍇
strawberry 🍓|cherries 🍒|peach 🍑|pineapple 🍍|avocado 🥑|broccoli 🥦
carrot 🥕|corn 🌽|bread 🍞|cheese 🧀|egg 🥚|pancakes 🥞|bacon 🥓
chicken_leg 🍗|burger 🍔|fries 🍟|pizza 🍕|hotdog 🌭|taco 🌮|ramen 🍜
noodles 🍜|sushi 🍣|ice_cream 🍦|donut 🍩|cookie 🍪|cake 🎂|cupcake 🧁
chocolate 🍫|candy 🍬|popcorn 🍿|coffee ☕|tea 🍵|milk 🥛|beer 🍺|wine 🍷
cocktail 🍹|bulb 💡|idea 💡|laptop 💻|computer 🖥️|keyboard ⌨️|phone 📱
camera 📷|tv 📺|battery 🔋|plug 🔌|email 📧|package 📦|key 🔑|lock 🔒
unlock 🔓|hammer 🔨|wrench 🔧|gear ⚙️|money 💰|credit_card 💳|gem 💎
bell 🔔|mute 🔕|megaphone 📢|mag 🔍|folder 📁|books 📚|book 📖|memo 📝
pencil ✏️|pen 🖊️|pushpin 📌|paperclip 📎|calendar 📅|alarm_clock ⏰
hourglass ⏳|chart 📊|chart_up 📈|chart_down 📉|graduation_cap 🎓
school 🏫|briefcase 💼|test_tube 🧪|microscope 🔬|telescope 🔭|dna 🧬
globe 🌍|map 🗺️|compass 🧭|mountain ⛰️|beach 🏖️|house 🏠|car 🚗|bike 🚲
airplane ✈️|clock 🕐|zzz 💤
love ❤️|hearts 💕|love_heart 💗|thumbs_up 👍|thumbs_down 👎|laugh 😂|lol 😂
lmao 🤣|happy 😊|sad 😢|crying 😭|ok 👌|hi 👋|bye 👋|lit 🔥|thanks 🙏
thank_you 🙏|please 🥺|oof 😬|rip 💀|dead 💀|mindblown 🤯|think 🤔|sus 🤨
cheers 🥂|hungry 🍽️|study 📚|sleep 😴|work 💼|good_luck 🤞|congrats 🎉
"""

EMOJI_SHORTCODES = {}

for _chunk in EMOJI_SHORTCODES_TEXT.replace("\n", "|").split("|"):

    _bits = _chunk.strip().split(" ", 1)

    if len(_bits) == 2 and _bits[1].strip():
        EMOJI_SHORTCODES[_bits[0].lower()] = _bits[1].strip()


def _add_official_emoji_names():
    """Every single-character emoji also gets its official Unicode name
    as a shortcode (growing_heart, face_with_tears_of_joy, ...), on top
    of the short hand-written ones above."""

    import unicodedata

    ranges = (
        (0x1F300, 0x1F64F), (0x1F680, 0x1F6C5),
        (0x1F910, 0x1F9FF), (0x1FA70, 0x1FAFF),
        (0x2600, 0x2604), (0x260E, 0x260E), (0x2614, 0x2615),
        (0x2648, 0x2653), (0x267F, 0x267F), (0x2693, 0x2693),
        (0x26A1, 0x26A1), (0x26BD, 0x26BE), (0x26C4, 0x26C5),
        (0x26D4, 0x26D4), (0x26EA, 0x26EA), (0x2705, 0x2705),
        (0x2728, 0x2728), (0x274C, 0x274C), (0x2764, 0x2764),
        (0x2B50, 0x2B50)
    )

    have = set(EMOJI_SHORTCODES.values())

    for low, high in ranges:

        for code in range(low, high + 1):

            try:
                name = unicodedata.name(chr(code))
            except ValueError:
                continue

            if "MODIFIER" in name:
                continue

            key = name.lower().replace(" ", "_").replace("-", "_")

            char = chr(code)

            if code < 0x1F000:
                char += "\uFE0F"

            if key not in EMOJI_SHORTCODES and (
                char not in have or len(key) < 40
            ):
                EMOJI_SHORTCODES[key] = char


try:
    _add_official_emoji_names()
except Exception:
    pass

EMOJI_NAMES = list(EMOJI_SHORTCODES)


def emoji_matches(query, limit=6):
    """Shortcode names that best fit what was typed after the colon:
    names starting with it, then names containing it, then close
    spellings. One row per emoji."""

    import difflib

    query = query.lower()

    starts = sorted(
        (n for n in EMOJI_NAMES if n.startswith(query)),
        key=lambda n: (len(n), n)
    )

    inside = sorted(
        (n for n in EMOJI_NAMES if query in n and n not in starts),
        key=lambda n: (len(n), n)
    )

    close = []

    if len(starts) + len(inside) < limit:

        close = [
            n for n in difflib.get_close_matches(
                query, EMOJI_NAMES, n=limit, cutoff=0.72
            )
            if n not in starts and n not in inside
        ]

    seen, out = set(), []

    for name in starts + inside + close:

        char = EMOJI_SHORTCODES[name]

        if char in seen:
            continue

        seen.add(char)

        out.append(name)

        if len(out) >= limit:
            break

    return out


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


_OrigLabel = tk.Label

_TEXT_FONTS = {
    False: (
        "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    ),
    True: (
        "C:/Windows/Fonts/segoeuib.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    )
}


class EmojiLabel(_OrigLabel):
    """A normal Label, except that text containing emoji is drawn as a
    picture (text and colour emoji together), because Tk itself shows
    emoji as empty boxes on Windows."""

    def __init__(self, master=None, cnf=None, **kw):

        self._etext = None
        self._ephoto = None

        text = kw.get("text")

        super().__init__(master, cnf or {}, **kw)

        if isinstance(text, str) and has_emoji(text):
            self._etext = text
            self._erender()

    def configure(self, cnf=None, **kw):

        if isinstance(cnf, dict):
            kw = {**cnf, **kw}

        if cnf is not None and not isinstance(cnf, dict):
            return super().configure(cnf)

        if not kw:
            return super().configure()

        redraw = any(
            k in kw for k in (
                "text", "fg", "foreground", "bg", "background", "font",
                "wraplength", "justify"
            )
        )

        if "text" in kw:

            value = kw["text"]

            if isinstance(value, str) and has_emoji(value):
                self._etext = value
            else:
                if self._etext is not None:
                    kw["image"] = ""
                self._etext = None
                self._ephoto = None

        result = super().configure(**kw)

        if self._etext is not None and redraw:
            self._erender()

        return result

    config = configure

    def cget(self, key):

        if key == "text" and self._etext is not None:
            return self._etext

        return super().cget(key)

    def _erender(self):

        try:
            text = self._etext

            rgb = lambda c: tuple(v >> 8 for v in self.winfo_rgb(c))

            fg = rgb(super().cget("fg"))
            bg = rgb(super().cget("bg"))

            font = tkfont.Font(self, font=super().cget("font"))
            info = font.actual()

            size = info["size"]

            px = abs(size) if size < 0 else int(
                round(size * self.winfo_fpixels("1i") / 72)
            )

            bold = info.get("weight") == "bold"

            S = 3
            P = px * S

            ttf = None

            for path in _TEXT_FONTS[bold]:
                try:
                    ttf = ImageFont.truetype(path, P)
                    break
                except Exception:
                    continue

            if ttf is None:
                raise RuntimeError("no font")

            wrap = 0
            try:
                wrap = int(float(super().cget("wraplength")))
            except Exception:
                pass

            max_w = wrap * S if wrap > 0 else 10 ** 6

            probe = ImageDraw.Draw(Image.new("RGB", (4, 4)))

            emo = int(P * 1.0)

            def width_of(piece, is_emoji):
                if is_emoji:
                    return emo + int(P * 0.08)
                return probe.textlength(piece, font=ttf)

            # Break into words (emoji count as their own word).
            tokens = []

            for piece, is_emoji in emoji_segments(text):
                if is_emoji:
                    tokens.append((piece, True))
                else:
                    for n, word in enumerate(re.split(r"( )", piece)):
                        if word:
                            tokens.append((word, False))

            lines, line, line_w = [], [], 0

            for piece, is_emoji in tokens:
                w = width_of(piece, is_emoji)
                if (
                    line and line_w + w > max_w
                    and not (piece == " ")
                ):
                    while line and line[-1][0] == " ":
                        line_w -= width_of(*line.pop())
                    lines.append((line, line_w))
                    line, line_w = [], 0
                    if piece == " ":
                        continue
                line.append((piece, is_emoji))
                line_w += w

            lines.append((line, line_w))

            ascent, descent = ttf.getmetrics()

            line_h = int((ascent + descent) * 1.08)

            width = max(1, int(max(w for _l, w in lines))) + 4

            height = line_h * len(lines) + 4

            img = Image.new("RGB", (width, height), bg)

            d = ImageDraw.Draw(img)

            centre = str(super().cget("justify")) == "center"

            for n, (items, w) in enumerate(lines):

                x = (width - w) / 2 if centre else 2

                base = 2 + n * line_h + ascent

                for piece, is_emoji in items:
                    if is_emoji:
                        tile = emoji_image(piece, emo)
                        if tile is not None:
                            img.paste(
                                tile,
                                (
                                    int(x),
                                    int(base - P * 0.33 - emo / 2)
                                ),
                                tile
                            )
                    else:
                        d.text((x, base), piece, font=ttf, fill=fg,
                               anchor="ls")
                    x += width_of(piece, is_emoji)

            img = img.resize(
                (max(1, width // S), max(1, height // S)), Image.LANCZOS
            )

            self._ephoto = ImageTk.PhotoImage(img)

            super().configure(
                image=self._ephoto, text="", compound="center"
            )

        except Exception:
            self._etext_failed = True


tk.Label = EmojiLabel


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


_LOGO_CACHE = {}


def _catmull_rom(points, per=24):
    """A smooth curve through the given points."""

    pts = [points[0]] + list(points) + [points[-1]]

    out = []

    for i in range(1, len(pts) - 2):

        p0, p1, p2, p3 = pts[i - 1], pts[i], pts[i + 1], pts[i + 2]

        for k in range(per):

            t = k / per
            t2, t3 = t * t, t * t * t

            out.append(tuple(
                0.5 * (
                    (2 * p1[j])
                    + (-p0[j] + p2[j]) * t
                    + (2 * p0[j] - 5 * p1[j] + 4 * p2[j] - p3[j]) * t2
                    + (-p0[j] + 3 * p1[j] - 3 * p2[j] + p3[j]) * t3
                )
                for j in (0, 1)
            ))

    out.append(points[-1])

    return out


def app_icon_image(size=256, theme=None):
    """The app's logo: a purple gradient rounded square with a white,
    softly curved S and a small sparkle. Used for the window, the
    taskbar, the tray, the sidebar and the welcome page."""

    # `theme` lets the Settings previews draw another theme's logo.
    theme_name = theme if theme in THEMES else THEME_NAME

    accent = THEMES[theme_name]["accent"]
    accent_hover = THEMES[theme_name]["accent_hover"]

    key = (int(size), theme_name)

    if key in _LOGO_CACHE:
        return _LOGO_CACHE[key].copy()

    big = max(48, size * 3)

    u = big / 100.0

    if theme_name == "Purple":

        # The original purple logo, exactly as it was.
        c1, c2, c3, c4 = (
            (109, 40, 217), (132, 80, 230), (150, 108, 240),
            (167, 139, 250)
        )

        shadow_colour = (40, 10, 90, 70)

    else:

        # Any other theme: the same logo in that theme's colours.
        # (Some themes look too alike, so they get their own pair.)
        own = {
            "Light": ((71, 85, 105), (148, 163, 184)),
            "Catppuccin": ((140, 100, 215), (196, 206, 255)),
            "Ocean": ((23, 52, 140), (83, 155, 250)),
            "Ice": ((8, 145, 160), (110, 231, 249))
        }

        if "logo_from" in THEMES[theme_name]:

            dark = tuple(THEMES[theme_name]["logo_from"])
            light = tuple(THEMES[theme_name]["logo_to"])

        elif theme_name in own:

            dark, light = own[theme_name]

        else:

            dark = _theme_rgb(_theme_mix(accent, "#000000", 0.14))
            light = _theme_rgb(_theme_mix(accent_hover, "#FFFFFF", 0.12))

        def blend(t):
            return tuple(
                int(round(a + (b - a) * t)) for a, b in zip(dark, light)
            )

        c1, c2, c3, c4 = dark, blend(0.35), blend(0.65), light

        shadow = _theme_rgb(
            _theme_mix("#%02X%02X%02X" % tuple(dark), "#000000", 0.6)
        )

        shadow_colour = shadow + (70,)

    corners = Image.new("RGBA", (2, 2))

    corners.putpixel((0, 0), c1 + (255,))
    corners.putpixel((1, 0), c2 + (255,))
    corners.putpixel((0, 1), c3 + (255,))
    corners.putpixel((1, 1), c4 + (255,))

    gradient = corners.resize((big, big), Image.BILINEAR)

    mask = Image.new("L", (big, big), 0)

    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, big - 1, big - 1],
        radius=int(big * 0.24),
        fill=255
    )

    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))

    img.paste(gradient, (0, 0), mask)

    points = [
        (71, 30), (60, 17), (45, 14), (31, 21), (29, 35), (40, 45),
        (58, 52), (70, 61), (69, 76), (56, 85), (41, 85), (27, 77)
    ]

    path = [(x * u, y * u) for x, y in _catmull_rom(points)]

    width = 12.5 * u

    shadow = Image.new("RGBA", (big, big), (0, 0, 0, 0))

    sd = ImageDraw.Draw(shadow)

    for x, y in path:

        sd.ellipse(
            [x - width / 2, y - width / 2 + 2 * u,
             x + width / 2, y + width / 2 + 2 * u],
            fill=shadow_colour
        )

    img.alpha_composite(shadow)

    d = ImageDraw.Draw(img)

    for x, y in path:

        d.ellipse(
            [x - width / 2, y - width / 2, x + width / 2, y + width / 2],
            fill=(255, 255, 255, 255)
        )

    cx, cy, r = 81 * u, 17 * u, 8.5 * u

    star = []

    for i in range(8):

        angle = math.radians(-90 + i * 45)

        radius = r if i % 2 == 0 else r * 0.28

        star.append(
            (cx + radius * math.cos(angle), cy + radius * math.sin(angle))
        )

    d.polygon(star, fill=(254, 240, 138, 255))

    result = img.resize((size, size), Image.LANCZOS)

    _LOGO_CACHE[key] = result

    return result.copy()


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

        # circle > 0 makes a round button of that size; plus draws a
        # "+" mark instead of text.
        self.circle = 0
        self.plus = False

        # wrap > 0: a fixed-width button whose text wraps onto as many
        # lines as it needs (used for long quiz answers).
        self.wrap = 0

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

        if self.circle:
            return self.circle

        padding = 26

        if self.wrap:
            return self.wrap + padding

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
        h = self.circle or self.HEIGHT

        self.canvas.delete("all")

        if self.wrap and not self.circle:

            probe = self.canvas.create_text(
                0, 0,
                text=self.text,
                font=self.font,
                width=self.wrap,
                anchor="nw"
            )

            box = self.canvas.bbox(probe)

            self.canvas.delete(probe)

            if box:
                h = max(h, box[3] - box[1] + 18)

        self.canvas.configure(
            width=w,
            height=h
        )

        if self.state == "disabled":
            bg_color, fg_color = PANEL_2, MUTED_2
        elif self.selected or self.hovered:
            bg_color, fg_color = self.active_color, "#FFFFFF"
        else:
            bg_color, fg_color = (
                getattr(self, "idle_color", None) or PANEL_2
            ), TEXT

        self.app._draw_bubble_background(
            self.canvas, w, h, min(h // 2, 18), bg_color
        )

        if self.plus:

            arm = h * 0.2

            for x1, y1, x2, y2 in (
                (w / 2 - arm, h / 2, w / 2 + arm, h / 2),
                (w / 2, h / 2 - arm, w / 2, h / 2 + arm)
            ):
                self.canvas.create_line(
                    x1, y1, x2, y2,
                    fill=fg_color, width=2, capstyle="round"
                )

        elif getattr(self, "icon", None) is not None:

            self.canvas.create_image(w / 2, h / 2, image=self.icon)

        else:

            self.canvas.create_text(
                w / 2, h / 2,
                text=self.text,
                font=self.font,
                fill=fg_color,
                **(
                    {"width": self.wrap, "justify": "center"}
                    if self.wrap else {}
                )
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

    def place(self, *args, **kwargs):
        self.canvas.place(*args, **kwargs)

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

        self.update_idletasks()
        self.geometry(
            f"1220x760+"
            f"{max(0, (self.winfo_screenwidth() - 1220) // 2)}+"
            f"{max(0, (self.winfo_screenheight() - 760) // 2 - 20)}"
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

        self.music_on = True
        self._music_stop_ev = None
        self._music_serial = 0
        self._music_failed = False
        self._fullscreen = False
        self._zen = None
        self._corner = None
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
        self.nudge_strict = False
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

    def _paint_titlebar(self, window):
        """Give a window's title bar the theme colours, so it stays
        dark (or light) when the window isn't the active one."""

        if sys.platform != "win32":
            return

        try:

            if window.overrideredirect():
                return

            import ctypes

            hwnd = ctypes.windll.user32.GetParent(window.winfo_id()) or \
                window.winfo_id()

            def colour(hex_text):

                hex_text = hex_text.lstrip("#")

                red, green, blue = (
                    int(hex_text[i:i + 2], 16) for i in (0, 2, 4)
                )

                return ctypes.c_int(red | (green << 8) | (blue << 16))

            red, green, blue = (
                int(BG.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)
            )

            dark = ctypes.c_int(
                1 if (red * 299 + green * 587 + blue * 114) / 1000 < 128
                else 0
            )

            # The window's own background brush is white by default and
            # shows through as white patches while the window is being
            # resized, minimised or maximised. Make it the theme colour.
            try:

                from ctypes import wintypes

                brush = getattr(self, "_bg_brush", None)

                if brush is None:

                    gdi = ctypes.windll.gdi32

                    gdi.CreateSolidBrush.restype = ctypes.c_void_p

                    brush = gdi.CreateSolidBrush(
                        red | (green << 8) | (blue << 16)
                    )

                    self._bg_brush = brush

                set_class = ctypes.windll.user32.SetClassLongPtrW

                set_class.argtypes = [
                    wintypes.HWND, ctypes.c_int, ctypes.c_void_p
                ]

                set_class.restype = ctypes.c_void_p

                for handle in {hwnd, window.winfo_id()}:
                    set_class(handle, -10, brush)    # GCLP_HBRBACKGROUND

            except Exception:
                pass

            dwm = ctypes.windll.dwmapi

            for attribute, value in (
                (20, dark),          # dark title bar
                (35, colour(BG)),    # caption colour
                (34, colour(getattr(window, "_glow", BORDER))),  # window border
                (36, colour(TEXT))   # caption text
            ):

                dwm.DwmSetWindowAttribute(
                    hwnd,
                    attribute,
                    ctypes.byref(value),
                    4
                )

        except Exception:
            pass

    def _title_bar_hook(self):

        def on_map(event):

            window = event.widget

            try:

                if window.winfo_toplevel() is window:

                    if (
                        window is not self
                        and sys.platform == "win32"
                        and not window.overrideredirect()
                        and not getattr(window, "_minimal_bar", False)
                    ):

                        # Every pop-up gets the same minimal header: no
                        # icon, no title text, no min/max - only the cross.
                        # The normal frame stays, so corners stay rounded.
                        window._minimal_bar = True

                        if not hasattr(window, "_glow"):
                            window._glow = PURPLE

                        try:
                            window.title("")
                            ico = getattr(self, "_blank_ico", None)
                            if ico is None:
                                import tempfile
                                from PIL import Image
                                ico = os.path.join(
                                    tempfile.gettempdir(),
                                    "studestics_blank.ico"
                                )
                                Image.new(
                                    "RGBA", (32, 32), (0, 0, 0, 0)
                                ).save(
                                    ico, format="ICO",
                                    sizes=[(16, 16), (32, 32)]
                                )
                                self._blank_ico = ico
                            window.iconbitmap(ico)
                        except Exception:
                            pass

                    window.after(20, lambda: self._paint_titlebar(window))

            except Exception:
                pass

        self.bind_all("<Map>", on_map, add="+")

    def finish_startup(self):

        if not self.initialized:
            return

        self._title_bar_hook()

        self._paint_titlebar(self)

        try:
            if self.db.get_setting("window_state", "normal") == "zoomed":
                self.state("zoomed")
        except Exception:
            pass

        self.show_page(
            "Dashboard"
        )

        self.start_reminders()

        self.after(1600, self.prewarm_timer_background)

        self.bind("<F11>", self.toggle_fullscreen)
        self.bind_all("<KeyPress>", self._zen_keys, add="+")
        self._install_text_shortcuts()
        self.bind("<Escape>", self._leave_fullscreen, add="+")

        self._music_watch()

        profile = self.db.get_profile()

        # Clean up after a self-update, then look for a newer release.
        try:

            if getattr(sys, "frozen", False):
                Path(sys.executable + ".old").unlink(missing_ok=True)

        except Exception:
            pass

        self.after(8000, self._auto_update_tick)

        # Load Gemini in the background a few seconds after a normal
        # start, so the first chat message doesn't wait for it.
        if "--background" not in sys.argv:
            self.after(4000, self._warm_gemini)

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

        # One-time: older installs were saved on "gemini-flash-latest",
        # which can take a minute to answer. Move them to the fast
        # model; a model they picked themselves is left alone.
        try:

            if self.db.get_setting("gemini_model_v2", "") != "1":

                if self.db.get_setting(
                    "gemini_model", ""
                ) in ("", "gemini-flash-latest"):

                    self.db.set_setting("gemini_model", GEMINI_MODEL)

                self.db.set_setting("gemini_model_v2", "1")

        except Exception:
            pass

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

        self.nudge_strict = (
            self.db.get_setting("nudge_strict", "0") == "1"
        )

        self.music_on = (
            self.db.get_setting("focus_music", "1") == "1"
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
            "Schedule",
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

        # Stops short of the right edge so its square background
        # doesn't poke out of the rounded highlight's corners.
        chip_text.pack(
            side="left",
            fill="x",
            expand=True,
            padx=(0, 14)
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
            self.sidebar_avatar,
            chip_text,
            self.sidebar_user,
            self.sidebar_user_sub
        )

        # The highlight is a rounded shape drawn behind everything,
        # like the one on the menu items above.
        chip_bg = tk.Canvas(
            self.sidebar_chip,
            bg=SIDEBAR,
            highlightthickness=0,
            bd=0
        )

        chip_bg.place(x=0, y=0, relwidth=1, relheight=1)

        # Canvas.lower() means 'lower an item'; this lowers the widget.
        tk.Misc.lower(chip_bg)

        chip_state = {"color": SIDEBAR, "photo": None}

        def chip_paint(color):

            try:

                w = chip_bg.winfo_width()
                h = chip_bg.winfo_height()

                chip_bg.delete("all")

                if color == SIDEBAR or w < 4 or h < 4:
                    return

                if HAS_PIL:

                    scale = 4

                    img = Image.new("RGB", (w * scale, h * scale), SIDEBAR)

                    ImageDraw.Draw(img).rounded_rectangle(
                        [0, 0, w * scale - 1, h * scale - 1],
                        radius=14 * scale,
                        fill=color
                    )

                    chip_state["photo"] = ImageTk.PhotoImage(
                        img.resize((w, h), Image.LANCZOS)
                    )

                    chip_bg.create_image(
                        0, 0, anchor="nw", image=chip_state["photo"]
                    )

                else:

                    chip_bg.create_rectangle(
                        0, 0, w, h, fill=color, outline=""
                    )

            except Exception:
                pass

        chip_bg.bind(
            "<Configure>", lambda e: chip_paint(chip_state["color"])
        )

        def chip_color(color):

            if chip_state["color"] == color:
                return

            chip_state["color"] = color

            chip_paint(color)

            for w in chip_widgets:

                try:
                    w.configure(bg=color)
                except Exception:
                    pass

            # The round photo is drawn with its corners in the
            # background colour, so it has to be redrawn in the new one
            # or a dark square shows around it.
            try:

                profile = self.db.get_profile()

                letter = (
                    (profile["name"].strip()[:1] or "?").upper()
                    if profile else "?"
                )

                self._avatar_paint(self.sidebar_avatar, 34, letter, color)

            except Exception:
                pass

        for w in chip_widgets + (self.sidebar_chip, chip_bg):

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

    def make_switch(self, parent, on=False, command=None, bg=None):
        """An on/off switch: a pill with a round knob that slides.
        Anti-aliased. Returns the canvas; it has .set_on(value) and
        .is_on()."""

        bg = bg or BG

        w, h = 46, 26

        canvas = tk.Canvas(
            parent,
            width=w,
            height=h,
            bg=bg,
            highlightthickness=0,
            bd=0,
            cursor="hand2"
        )

        state = {"on": bool(on), "pos": 1.0 if on else 0.0, "job": None}

        off_colour = _theme_mix(PANEL_2, TEXT, 0.22)

        cache = {}

        def render(pos):

            key = round(pos * 10)

            if key in cache:
                return cache[key]

            t = key / 10

            colour = _theme_mix(off_colour, PURPLE, t)

            if HAS_PIL:

                k = 4

                img = Image.new("RGB", (w * k, h * k), bg)

                pen = ImageDraw.Draw(img)

                pen.rounded_rectangle(
                    (0, 0, w * k - 1, h * k - 1),
                    radius=h * k // 2,
                    fill=colour
                )

                pad = 3

                size = h - 2 * pad

                x0 = pad + t * (w - h)

                pen.ellipse(
                    (
                        x0 * k, pad * k,
                        (x0 + size) * k, (pad + size) * k
                    ),
                    fill="#FFFFFF"
                )

                photo = ImageTk.PhotoImage(
                    img.resize((w, h), Image.LANCZOS)
                )

                cache[key] = photo

                return photo

            return None

        def draw():

            canvas.delete("all")

            photo = render(state["pos"])

            if photo is not None:

                canvas.create_image(0, 0, anchor="nw", image=photo)

            else:

                canvas.create_rectangle(
                    0, 0, w, h,
                    fill=PURPLE if state["on"] else off_colour,
                    outline=""
                )

        def glide(target):

            if state["job"] is not None:

                try:
                    canvas.after_cancel(state["job"])
                except Exception:
                    pass

            def step():

                pos = state["pos"]

                if abs(target - pos) < 0.11:

                    state["pos"] = target
                    state["job"] = None
                    draw()

                    return

                state["pos"] = pos + (0.25 if target > pos else -0.25)

                draw()

                state["job"] = canvas.after(14, step)

            step()

        def set_on(value, animate=True):

            state["on"] = bool(value)

            target = 1.0 if state["on"] else 0.0

            if animate:
                glide(target)
            else:
                state["pos"] = target
                draw()

        def click(event=None):

            set_on(not state["on"])

            if command:
                command(state["on"])

        canvas.bind("<Button-1>", click)

        canvas.set_on = set_on
        canvas.is_on = lambda: state["on"]
        canvas.toggle = click

        draw()

        return canvas

    def make_button(
        self,
        parent,
        text,
        command,
        width=None,
        active=PURPLE_HOVER
    ):

        if active == PURPLE_HOVER and text in ("Dismiss", "Cancel"):
            active = RED

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

        kicker = {
            "error": "Error",
            "warning": "Warning",
            "info": "Notice",
            "ask": "Please confirm"
        }[kind]

        shell = self._alert_shell(
            kicker, title, accent,
            "check" if kind == "info" else "bell",
            message, width=480
        )

        window = shell["win"]

        buttons = tk.Frame(shell["foot"], bg=BG)

        buttons.pack()

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

            self.make_button(
                buttons,
                "Cancel",
                lambda: finish(False),
                width=10
            ).pack(side="left", padx=4)

            confirm = self.make_button(
                buttons,
                yes_text,
                lambda: finish(True),
                width=10,
                active="#DC2626" if danger else PURPLE_HOVER
            )

            confirm.configure(selected=True)

            confirm.pack(side="left", padx=4)

        else:

            ok = self.make_button(
                buttons,
                "OK",
                lambda: finish(True),
                width=10
            )

            ok.configure(selected=True)

            ok.pack()

            window.bind("<Return>", lambda e: finish(True))

        window.bind("<Escape>", lambda e: finish(False))

        window.protocol("WM_DELETE_WINDOW", lambda: finish(False))

        self._alert_show(shell)

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

    def make_title_box(self, parent):
        """A one-line title box that can hold emoji (the :name: menu
        works in it too). Read it with emoji_read, fill it with
        emoji_write."""

        box = tk.Text(
            parent,
            height=1,
            wrap="none",
            undo=True,
            bg=PANEL_2,
            fg=TEXT,
            insertbackground=TEXT,
            relief="flat",
            bd=0,
            padx=6,
            pady=9,
            highlightthickness=1,
            highlightbackground=BORDER,
            highlightcolor=PURPLE,
            font=("Segoe UI", 10)
        )

        self.emoji_attach(box)

        def enter(event):
            if self._emoji_visible() and self._emoji_w is box:
                return self._emoji_key(0)
            return "break"

        box.bind("<Return>", enter)
        box.bind("<Tab>", lambda e: (box.tk_focusNext().focus_set(), "break")[1])
        box.bind(
            "<ISO_Left_Tab>",
            lambda e: (box.tk_focusPrev().focus_set(), "break")[1]
        )

        return box

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

        return header

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

        if getattr(self, "current_page", None) == "AI Chat":
            self._save_chat_draft()

        self.current_page = page_name

        for name, item in self.sidebar_buttons.items():
            item.set_active(name == page_name)

        self._sidebar_timer_update()

        self.refresh_sidebar_upnext()

        self.clear_page()

        # A cover hides the page while it is built and laid out, so the
        # cards are never seen jumping from a small size to the real one.
        cover = None

        try:

            cover = tk.Frame(self.main, bg=BG)

            cover.place(x=0, y=0, relwidth=1, relheight=1)

            cover.lift()

            # Safety net: if building the page ever fails, the cover
            # must not stay on screen.
            self.after(
                1500,
                lambda c=cover: c.winfo_exists() and c.destroy()
            )

        except Exception:
            cover = None

        if page_name == "Dashboard":
            self.build_dashboard()

        elif page_name == "Tasks":
            self.build_tasks()

        elif page_name == "Goals":
            self.build_goals()

        elif page_name == "Notes":
            self.build_notes()

        elif page_name == "Schedule":
            self.build_schedule()

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

        if cover is not None:

            try:
                cover.destroy()
            except Exception:
                pass

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

        for w in (avatar,):

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

        self._dashboard_target_card()

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

    def _dashboard_target_card(self):
        """Today's focus minutes against a daily target, and the
        study streak. The target changes in steps of 15 minutes."""

        try:
            stats = self.db.focus_stats()
        except Exception:
            return

        try:
            target = int(self.db.get_setting("daily_target_min", "60"))
        except ValueError:
            target = 60

        state = {"target": max(15, min(600, target))}

        today_min = int(stats["today"] // 60)

        streak = stats["streak"]

        outer, body = self.rounded_panel(
            self.page,
            radius=14,
            accent=PURPLE_HOVER,
            fit=True
        )

        outer.pack(fill="x", pady=(0, 24))

        top = tk.Frame(body, bg=PANEL)

        top.pack(fill="x", padx=18, pady=(14, 0))

        tk.Label(
            top, text="Daily focus target", bg=PANEL, fg=MUTED,
            font=("Segoe UI", 9)
        ).pack(side="left")

        tk.Label(
            top,
            text=f"{streak} day streak",
            bg=PANEL,
            fg=YELLOW if streak else MUTED_2,
            font=("Segoe UI", 10, "bold")
        ).pack(side="right")

        mid = tk.Frame(body, bg=PANEL)

        mid.pack(fill="x", padx=18, pady=(2, 0))

        value = tk.Label(
            mid, bg=PANEL, font=("Segoe UI", 20, "bold")
        )

        value.pack(side="left")

        bar = tk.Canvas(
            body, height=10, bg=PANEL, highlightthickness=0, bd=0
        )

        bar.pack(fill="x", padx=18, pady=(8, 16))

        track = _theme_mix(PANEL_2, TEXT, 0.12)

        def paint(event=None):

            goal = state["target"]

            reached = today_min >= goal

            value.configure(
                text=f"{today_min} / {goal} min",
                fg=GREEN if reached else PURPLE_HOVER
            )

            bar.delete("all")

            width = max(bar.winfo_width(), 24)

            bar.create_line(
                5, 5, width - 5, 5, width=10, capstyle="round",
                fill=track
            )

            fraction = min(1.0, today_min / goal)

            if fraction > 0:

                bar.create_line(
                    5, 5, max(5.5, 5 + (width - 10) * fraction), 5,
                    width=10, capstyle="round",
                    fill=GREEN if reached else PURPLE_HOVER
                )

        def change(step):

            state["target"] = max(15, min(600, state["target"] + step))

            self.db.set_setting(
                "daily_target_min", str(state["target"])
            )

            paint()

        plus = self.make_button(
            mid, "+15", lambda: change(15), width=4
        )

        plus.pack(side="right")

        self.make_button(
            mid, "-15", lambda: change(-15), width=4
        ).pack(side="right", padx=(0, 8))

        bar.bind("<Configure>", paint)

        paint()

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
            "danger": (DANGER_FILL, DANGER_EDGE,
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

    def _canvas_text(self, canvas, x, y, **kw):
        """canvas.create_text that also draws colour emoji."""

        text = kw.get("text", "")

        if not (isinstance(text, str) and has_emoji(text)):
            return canvas.create_text(x, y, **kw)

        font = kw.get("font")
        fill = kw.get("fill", TEXT)
        anchor = kw.get("anchor", "nw")
        tags = kw.get("tags", "")

        line = font.metrics("linespace")

        top = y - line if anchor.startswith("s") else (
            y - line / 2 if anchor in ("w", "e", "center") else y
        )

        size = max(10, int(line * 0.76))

        if not hasattr(canvas, "_etext_photos"):
            canvas._etext_photos = []

        cursor = x

        for piece, is_emoji in emoji_segments(text):
            if is_emoji:
                pil = emoji_image(piece, size)
                if pil is not None and fill == "#0A0A12":
                    # The outline copy: the emoji's shape in dark.
                    shadow = Image.new("RGBA", pil.size, (10, 10, 18, 255))
                    shadow.putalpha(pil.getchannel("A"))
                    pil = shadow
                if pil is not None:
                    photo = ImageTk.PhotoImage(pil)
                    canvas._etext_photos.append(photo)
                    canvas.create_image(
                        cursor, top + (line - size) / 2, anchor="nw",
                        image=photo, tags=tags
                    )
                cursor += size + 2
            elif piece:
                canvas.create_text(
                    cursor, top, anchor="nw", text=piece, font=font,
                    fill=fill, tags=tags
                )
                cursor += font.measure(piece)

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
            canvas._etext_photos = []

            def outlined(x, y, **kw):
                if has_photo:
                    dark = dict(kw)
                    dark["fill"] = "#0A0A12"
                    for dx, dy in (
                        (-2, 0), (2, 0), (0, -2), (0, 2),
                        (-1, -1), (1, -1), (-1, 1), (1, 1)
                    ):
                        self._canvas_text(canvas, x + dx, y + dy, **dark)
                self._canvas_text(canvas, x, y, **kw)


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

            outlined(
                18, 20,
                anchor="nw",
                text=fit(title, title_font, max_text_w),
                font=title_font,
                fill=GREEN if is_completed else ("#FFFFFF" if has_photo else TEXT),
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

            outlined(
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

                outlined(
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
                        "#FFFFFF"
                        if (has_photo or actions[i]["kind"] == "primary")
                        else (
                            RED
                            if (
                                actions[i]["kind"] == "danger"
                                and state["hover"] != i
                            )
                            else (
                                "#FFFFFF"
                                if actions[i]["kind"] == "danger"
                                else TEXT
                            )
                        )
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

            # Drawn at 4x and scaled down, so the corners are smooth.
            mask_big = Image.new("L", (width * 4, card_height * 4), 0)
            ImageDraw.Draw(mask_big).rounded_rectangle(
                [0, 0, width * 4 - 1, card_height * 4 - 1],
                radius=radius * 4,
                fill=255
            )
            mask = mask_big.resize((width, card_height), Image.LANCZOS)

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

        tk.Frame(window, bg=PURPLE, height=4).pack(fill="x")

        self.center_window(window, 700, 908)

        window.configure(
            bg=BG
        )

        window.transient(
            self
        )

        window.grab_set()

        self._form_header(
            window, "Task",
            "Edit task" if editing else "Create task", "check"
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

        title = self.make_title_box(form)

        title.pack(fill="x", pady=(5, 12))

        if editing:
            self.emoji_write(title, task["title"])
            title.mark_set("insert", "end-1c")
            title.see("insert")

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

        self.emoji_attach(description)

        if editing:
            self.emoji_write(description, task["description"] or "")
            description.mark_set("insert", "end-1c")
            description.see("insert")

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

        custom_panel = tk.Frame(reveal_inner, bg=BG)

        custom_panel.pack(fill="x")

        tk.Label(
            custom_panel,
            text="Remind me every  (minutes)",
            bg=BG,
            fg=MUTED
        ).pack(
            anchor="w",
            pady=(2, 0)
        )

        remind_entry = self.make_entry(
            custom_panel
        )

        remind_entry.pack(
            fill="x",
            ipady=8,
            pady=(5, 4)
        )

        tk.Label(
            custom_panel,
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
        once_state = {"on": False}
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

                once_state["on"] = False

                once_switch.set_on(False)

                form.update_idletasks()

                animate_reveal(reveal_inner.winfo_reqheight())

                window.after(280, remind_entry.focus_set)

            else:

                animate_reveal(1)

        def toggle_once(value):
            """One-time reminder: just a switch. The task's deadline
            (date and time, set above) is when it fires, once."""

            once_state["on"] = bool(value)

            if once_state["on"] and custom_state["on"]:

                custom_state["on"] = False

                custom_button.configure(selected=False)

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

        once_row = tk.Frame(form, bg=BG)

        once_row.pack(fill="x", pady=(2, 12))

        once_switch = self.make_switch(
            once_row,
            on=False,
            command=toggle_once
        )

        once_switch.pack(side="left")

        once_text = tk.Label(
            once_row,
            text="One-time reminder",
            bg=BG,
            fg=TEXT,
            font=("Segoe UI", 10),
            cursor="hand2"
        )

        once_text.pack(side="left", padx=(12, 0))

        once_text.bind("<Button-1>", lambda e: once_switch.toggle())

        tk.Label(
            once_row,
            text="Remind me once, at the deadline above",
            bg=BG,
            fg=MUTED_2,
            font=("Segoe UI", 8)
        ).pack(side="left", padx=(12, 0))

        try:

            if editing and task["remind_at"]:

                once_state["on"] = True

                once_switch.set_on(True, animate=False)

        except Exception:
            pass

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

            task_title = self.emoji_read(title).strip()

            if not task_title:

                messagebox.showwarning(
                    "Task",
                    "Enter a task title.",
                    parent=window
                )

                return

            task_description = self.emoji_read(description).strip()

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

            remind_at = ""

            if once_state["on"]:

                try:

                    when = datetime.strptime(
                        deadline_picker["get"](), "%Y-%m-%d %H:%M:%S"
                    )

                except ValueError:

                    messagebox.showwarning(
                        "Task",
                        "One-time reminder: choose a deadline date "
                        "and time first. That is when you will be "
                        "reminded.",
                        parent=window
                    )

                    return

                if when <= datetime.now():

                    messagebox.showwarning(
                        "Task",
                        "That time has already passed.",
                        parent=window
                    )

                    return

                remind_at = when.strftime("%Y-%m-%d %H:%M:%S")

                remind_minutes = 0

            if editing:

                self.db.update_task(
                    task["id"],
                    task_title,
                    task_description,
                    deadline_picker["get"](),
                    priority_state["value"],
                    selected_path.get(),
                    remind_minutes,
                    remind_at
                )

            else:

                self.db.add_task(
                    task_title,
                    task_description,
                    deadline_picker["get"](),
                    priority_state["value"],
                    selected_path.get(),
                    remind_minutes,
                    remind_at
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

        def redraw(force=False):

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

            try:

                focused = frame.focus_get()

                for entry, text in (
                    (hour_entry, f"{state.hour12():02d}"),
                    (minute_entry, f"{state.minute():02d}")
                ):

                    if force or focused is not entry:
                        entry.delete(0, "end")
                        entry.insert(0, text)

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

        def clock_box(parent, limit, down, up, commit):

            box = tk.Frame(parent, bg=BG)

            self.make_button(
                box, "\u2212", lambda: (down(), redraw(True)), width=2
            ).pack(side="left")

            entry = self.make_entry(box)

            entry.configure(width=3, justify="center")

            entry.pack(side="left", padx=6, ipady=5)

            self.make_button(
                box, "+", lambda: (up(), redraw(True)), width=2
            ).pack(side="left")

            def finish(*_):

                digits = "".join(c for c in entry.get() if c.isdigit())

                if digits:
                    commit(int(digits))

                redraw(True)

            def arrow(step):

                (up if step > 0 else down)()

                redraw(True)

                return "break"

            entry.bind("<FocusOut>", finish)
            entry.bind("<Return>", finish)
            entry.bind("<Up>", lambda e: arrow(1))
            entry.bind("<Down>", lambda e: arrow(-1))
            entry.bind(
                "<MouseWheel>", lambda e: arrow(1 if e.delta > 0 else -1)
            )
            entry.bind(
                "<FocusIn>",
                lambda e: entry.after(
                    10, lambda: entry.select_range(0, "end")
                )
            )

            return box, entry

        def commit_hour(value):

            pm = state.ampm() == "PM"

            value = max(1, min(12, value))

            state.set_minutes(
                ((value % 12) + (12 if pm else 0)) * 60 + state.minute()
            )

        def commit_minute(value):

            state.set_minutes(
                state.hour24() * 60 + max(0, min(59, value))
            )

        time_row = tk.Frame(side, bg=BG)

        time_row.pack(anchor="w")

        hour_box, hour_entry = clock_box(
            time_row, 12,
            lambda: state.bump_hour(-1),
            lambda: state.bump_hour(1),
            commit_hour
        )

        hour_box.pack(side="left")

        tk.Label(
            time_row,
            text=":",
            bg=BG,
            fg=MUTED,
            font=("Segoe UI", 13, "bold")
        ).pack(side="left", padx=4)

        minute_box, minute_entry = clock_box(
            time_row, 59,
            lambda: state.bump_minute(-5),
            lambda: state.bump_minute(5),
            commit_minute
        )

        minute_box.pack(side="left")

        ampm_button = self.make_button(
            time_row,
            state.ampm(),
            lambda: (state.toggle_ampm(), redraw(True)),
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
            canvas._etext_photos = []

            canvas.create_image(
                0, 0, anchor="nw", image=photo, tags="card_bg"
            )

            max_text_w = max(
                60,
                width - pill_w - pill_margin - 18 - 24
            )

            self._canvas_text(
                canvas,
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
                        "#FFFFFF"
                        if (has_photo or actions[i]["kind"] == "primary")
                        else (
                            RED
                            if (
                                actions[i]["kind"] == "danger"
                                and state["hover"] != i
                            )
                            else (
                                "#FFFFFF"
                                if actions[i]["kind"] == "danger"
                                else TEXT
                            )
                        )
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

            # Drawn at 4x and scaled down, so the corners are smooth.
            mask_big = Image.new("L", (width * 4, card_height * 4), 0)
            ImageDraw.Draw(mask_big).rounded_rectangle(
                [0, 0, width * 4 - 1, card_height * 4 - 1],
                radius=radius * 4,
                fill=255
            )
            mask = mask_big.resize((width, card_height), Image.LANCZOS)

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

        tk.Frame(window, bg=PURPLE, height=4).pack(fill="x")

        self.center_window(window, 560, 528)

        window.configure(bg=BG)

        window.transient(self)

        window.grab_set()

        self._form_header(
            window, "Goal",
            "Edit goal" if editing else "Create goal", "target"
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

        entry = self.make_title_box(form)

        entry.pack(fill="x", pady=(5, 12))

        if editing:
            self.emoji_write(entry, goal["title"])
            entry.mark_set("insert", "end-1c")
            entry.see("insert")

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

        self.emoji_attach(description)

        if editing:
            self.emoji_write(description, goal["description"] or "")
            description.mark_set("insert", "end-1c")
            description.see("insert")

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

            value = self.emoji_read(entry).strip()

            if not value:

                messagebox.showwarning(
                    "Goal",
                    "Enter a goal title.",
                    parent=window
                )

                return

            text = self.emoji_read(description).strip()

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

    # ========================================================
    # AI QUIZ FROM NOTES
    # ========================================================

    def _make_quiz(self, text, count=5):
        """Ask Gemini for multiple-choice questions about `text`.
        Returns a list of dicts: q, options (4), answer (0-3), why."""

        import json

        client = self._gemini_client()

        prompt = (
            f"Write {count} multiple-choice questions that test "
            "understanding of the study notes below. Use only facts "
            "from the notes. Each question has exactly 4 options and "
            "one correct answer. Reply with ONLY a JSON array, no "
            "other text, like: "
            '[{"q": "...", "options": ["a", "b", "c", "d"], '
            '"answer": 0, "why": "one short sentence"}] '
            "where answer is the index (0-3) of the correct option. "
            "Important: the four options must be about the same length "
            "and level of detail, so the correct one can't be spotted "
            "by being longer or more specific. The wrong options must "
            "be believable and as carefully worded as the right one. "
            "Keep each option under 100 characters. Spread the correct "
            "answer across all four positions.\n\n"
            "NOTES:\n" + text[:12000]
        )

        last_error = None

        for model_name in self._gemini_model_candidates():

            try:

                reply = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config={
                        "response_mime_type": "application/json",
                        "max_output_tokens": min(
                            30000, 800 + 260 * count
                        ),
                        # Big quizzes take a while; don't use the short
                        # chat timeout.
                        "http_options": {"timeout": 240000}
                    }
                )

                raw = (reply.text or "").strip()

                if raw.startswith("```"):
                    raw = raw.strip("`")
                    raw = raw[raw.find("["):]

                start, end = raw.find("["), raw.rfind("]")

                data = json.loads(raw[start:end + 1])

                quiz = []

                for item in data:

                    options = [str(o) for o in item["options"]][:4]

                    answer = int(item["answer"])

                    if len(options) == 4 and 0 <= answer < 4:

                        # Mix the order ourselves, since the AI likes
                        # putting the answer first.
                        right = options[answer]

                        random.shuffle(options)

                        answer = options.index(right)

                        quiz.append({
                            "q": str(item["q"]),
                            "options": options,
                            "answer": answer,
                            "why": str(item.get("why", ""))
                        })

                if quiz:
                    return quiz

                last_error = RuntimeError("No usable questions came back.")

            except Exception as exc:

                last_error = exc

        raise last_error or RuntimeError("Couldn't make a quiz.")

    def start_quiz(self, text):

        text = (text or "").strip()

        if len(text.split()) < 25:

            messagebox.showinfo(
                "Quiz me",
                "Write a bit more first. A quiz needs at least a few "
                "sentences of notes (select part of the text to quiz "
                "only that part)."
            )

            return

        if not self.get_gemini_key():

            messagebox.showinfo(
                "Quiz me",
                "Add your Gemini API key in Settings first."
            )

            return

        win = tk.Toplevel(self)

        win.title("Quiz me")

        tk.Frame(win, bg=PURPLE, height=4).pack(fill="x")
        win.configure(bg=BG)
        win.resizable(False, False)
        win.transient(self)

        self.center_window(win, 600, 334)

        body = tk.Frame(win, bg=BG)

        body.pack(fill="both", expand=True, padx=30, pady=24)

        state = {
            "quiz": [], "index": 0, "score": 0, "alive": True,
            "count": 5
        }

        win.bind("<Destroy>", lambda e: state.update(alive=False)
                 if e.widget is win else None)

        def clear():

            for child in body.winfo_children():
                child.destroy()

        def fit(extra=0, minimum=300, center=True):
            """Size the window to what is in it."""

            if not state["alive"]:
                return

            win.update_idletasks()

            height = max(minimum, win.winfo_reqheight() + extra)

            if center:
                self.center_window(win, 600, height)
            else:
                # Grow downwards in place, so the window doesn't jump.
                win.geometry(f"600x{height}")

        def header(kicker, heading, accent=PURPLE, icon="note", top=6):
            self._form_header(
                body, kicker, heading, icon,
                pady=(top, 2), padx=0, accent=accent
            ).pack_configure(anchor="w")

        def label(text, size=11, bold=False, colour=TEXT, **kw):

            widget = tk.Label(
                body,
                text=text,
                bg=BG,
                fg=colour,
                font=("Segoe UI", size, "bold" if bold else "normal"),
                wraplength=540,
                justify="left",
                **kw
            )

            widget.pack(anchor="w")

            return widget

        def show_loading():

            clear()

            header("Quiz", "Making your quiz\u2026", top=30)

            count = state["count"]

            label(
                f"Gemini is writing {count} question"
                f"{'s' if count != 1 else ''} from your notes. "
                + (
                    "This takes a few seconds."
                    if count <= 10 else
                    "A big quiz can take up to a minute."
                ),
                10,
                colour=MUTED
            )

            fit(minimum=260)

        def show_setup():

            clear()

            header("Quiz", "Quiz me", top=10)

            label(
                "How many questions do you want? Drag the slider.",
                10,
                colour=MUTED
            )

            number = tk.Label(
                body,
                bg=BG,
                fg=PURPLE_HOVER,
                font=("Segoe UI", 40, "bold")
            )

            number.pack(pady=(22, 0))

            caption = tk.Label(
                body,
                bg=BG,
                fg=MUTED,
                font=("Segoe UI", 10)
            )

            caption.pack()

            track_w = 480

            slider = tk.Canvas(
                body,
                width=track_w + 24,
                height=44,
                bg=BG,
                highlightthickness=0,
                cursor="hand2"
            )

            slider.pack(pady=(16, 0))

            def redraw():

                value = state["count"]

                x = 12 + (value - 1) / 49 * track_w

                slider.delete("all")

                if HAS_PIL:

                    # Drawn four times bigger and shrunk, so the edges
                    # are smooth instead of jagged.
                    try:

                        k = 4
                        w = track_w + 24
                        h = 44

                        img = Image.new("RGB", (w * k, h * k), BG)

                        pen = ImageDraw.Draw(img)

                        def bar(x1, x2, colour):

                            pen.rounded_rectangle(
                                (x1 * k, 19 * k, x2 * k, 25 * k),
                                radius=3 * k,
                                fill=colour
                            )

                        bar(12, 12 + track_w, PANEL_2)
                        bar(12, max(x, 15), PURPLE)

                        pen.ellipse(
                            ((x - 11) * k, 11 * k, (x + 11) * k, 33 * k),
                            fill=PURPLE_HOVER
                        )

                        photo = ImageTk.PhotoImage(
                            img.resize((w, h), Image.LANCZOS)
                        )

                        slider._photo = photo

                        slider.create_image(0, 0, anchor="nw", image=photo)

                        number.configure(text=str(value))

                        caption.configure(
                            text="question" if value == 1 else "questions"
                        )

                        return

                    except Exception:
                        slider.delete("all")

                slider.create_line(
                    12, 22, 12 + track_w, 22,
                    width=6, fill=PANEL_2, capstyle="round"
                )

                slider.create_line(
                    12, 22, x, 22,
                    width=6, fill=PURPLE, capstyle="round"
                )

                slider.create_oval(
                    x - 11, 11, x + 11, 33,
                    fill=PURPLE_HOVER, outline=BG, width=3
                )

                number.configure(text=str(value))

                caption.configure(
                    text="question" if value == 1 else "questions"
                )

            def drag(event):

                value = round((event.x - 12) / track_w * 49) + 1

                state["count"] = max(1, min(50, value))

                redraw()

            slider.bind("<Button-1>", drag)
            slider.bind("<B1-Motion>", drag)

            ends = tk.Frame(body, bg=BG)

            ends.pack(fill="x", padx=12)

            tk.Label(
                ends, text="1", bg=BG, fg=MUTED_2,
                font=("Segoe UI", 9)
            ).pack(side="left")

            tk.Label(
                ends, text="50", bg=BG, fg=MUTED_2,
                font=("Segoe UI", 9)
            ).pack(side="right")

            row = tk.Frame(body, bg=BG)

            row.pack(pady=(26, 0))

            go = self.make_button(row, "Start quiz", begin, width=14)

            go.configure(selected=True)

            go.pack(side="left")

            self.make_button(
                row, "Cancel", win.destroy, width=9
            ).pack(side="left", padx=10)

            redraw()

            fit(minimum=380)

        def show_error(message):

            clear()

            header("Quiz", "Couldn't make a quiz", RED, top=20)

            label(message[:300], 10, colour=RED)

            row = tk.Frame(body, bg=BG)

            row.pack(anchor="w", pady=(18, 0))

            retry = self.make_button(row, "Try again", begin, width=12)

            retry.configure(selected=True)

            retry.pack(side="left")

            self.make_button(
                row, "Close", win.destroy, width=9
            ).pack(side="left", padx=10)

            fit(minimum=260)

        def show_question():

            clear()

            quiz = state["quiz"]

            item = quiz[state["index"]]

            label(
                f"Question {state['index'] + 1} of {len(quiz)}",
                10,
                True,
                PURPLE_HOVER
            )

            progress = tk.Canvas(
                body,
                width=540,
                height=6,
                bg=BG,
                highlightthickness=0
            )

            progress.pack(anchor="w", pady=(8, 0))

            progress.create_rectangle(
                0, 0, 540, 6, fill=PANEL_2, outline=""
            )

            progress.create_rectangle(
                0, 0, 540 * state["index"] // len(quiz), 6,
                fill=PURPLE, outline=""
            )

            label(item["q"], 15, True).pack_configure(pady=(18, 18))

            result = tk.Label(
                body,
                text="",
                bg=BG,
                fg=GREEN,
                font=("Segoe UI", 10, "bold"),
                wraplength=540,
                justify="left"
            )

            why = tk.Label(
                body,
                text="",
                bg=BG,
                fg=MUTED,
                font=("Segoe UI", 10),
                wraplength=540,
                justify="left"
            )

            buttons = []

            footer = tk.Frame(body, bg=BG)

            def choose(number):

                for button in buttons:
                    button.configure(state="disabled")

                correct = number == item["answer"]

                if correct:
                    state["score"] += 1

                buttons[item["answer"]].configure(selected=True)

                result.configure(
                    text=(
                        "Correct!"
                        if correct else
                        "Not quite. The answer is highlighted."
                    ),
                    fg=GREEN if correct else RED
                )

                why.configure(text=item["why"])

                last = state["index"] + 1 >= len(quiz)

                nxt = self.make_button(
                    footer,
                    "See score" if last else "Next",
                    advance,
                    width=12
                )

                nxt.configure(selected=True)

                nxt.pack(side="right", pady=(14, 0))

                # Make room for the verdict, explanation and Next.
                fit(extra=8, minimum=200, center=False)

            for number, option in enumerate(item["options"]):

                button = self.make_button(
                    body,
                    option,
                    lambda n=number: choose(n),
                    width=57
                )

                button.wrap = 510
                button._redraw()

                button.pack(anchor="w", pady=5)

                buttons.append(button)

            result.pack(anchor="w", pady=(14, 2))

            why.pack(anchor="w")

            footer.pack(side="bottom", fill="x")

            fit(extra=8, minimum=200)

        def advance():

            state["index"] += 1

            if state["index"] >= len(state["quiz"]):
                show_score()
            else:
                show_question()

        def show_score():

            clear()

            total = len(state["quiz"])

            score = state["score"]

            header("Quiz", "Quiz done", GREEN, "check", top=20)

            label(
                f"You got {score} of {total}.",
                14,
                True,
                GREEN if score * 2 >= total else YELLOW
            )

            label(
                "Great work." if score == total else
                "Nice. Read the notes once more and try again."
                if score * 2 >= total else
                "Worth another read of the notes, then try again.",
                10,
                colour=MUTED
            ).pack_configure(pady=(6, 0))

            row = tk.Frame(body, bg=BG)

            row.pack(anchor="w", pady=(22, 0))

            again = self.make_button(
                row, "New quiz", show_setup, width=12
            )

            again.configure(selected=True)

            again.pack(side="left")

            self.make_button(
                row, "Close", win.destroy, width=9
            ).pack(side="left", padx=10)

            fit(minimum=300)

        def begin():

            state.update(quiz=[], index=0, score=0)

            show_loading()

            def work():

                try:
                    quiz = self._make_quiz(text, state["count"])
                except Exception as exc:
                    message = str(exc)
                    self.after(
                        0,
                        lambda: state["alive"] and show_error(message)
                    )
                    return

                def ready():

                    if not state["alive"]:
                        return

                    state["quiz"] = quiz

                    show_question()

                self.after(0, ready)

            threading.Thread(target=work, daemon=True).start()

        show_setup()

    def build_notes(self):

        header = self.page_header(
            "Notes",
            "A simple text editor. Write here, or open and edit .txt "
            "files. Press Quiz me for a quiz on your notes, or "
            "type /notes in AI Chat to have the AI write them."
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

        self.emoji_attach(editor)

        self.emoji_write(editor, self._note_text)
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

            self._note_text = self.emoji_read(editor)
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
            self.emoji_write(editor, text)
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
                    handle.write(self.emoji_read(editor))

            except Exception as exc:

                messagebox.showerror(
                    "Save failed",
                    str(exc),
                    parent=self
                )

                return False

            self._note_text = self.emoji_read(editor)
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

        def quiz_me():

            try:
                chosen = self.emoji_read(editor, "sel.first", "sel.last")
            except tk.TclError:
                chosen = ""

            self.start_quiz(chosen or self.emoji_read(editor))

        quiz_button = self.make_button(
            header, "Quiz me", quiz_me, width=11
        )

        quiz_button.configure(selected=True)

        quiz_button.place(relx=1.0, x=0, rely=0.5, anchor="e")

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
        editor.bind("<KeyRelease>", update_status, add="+")
        editor.bind("<ButtonRelease-1>", update_status)
        editor.bind("<Control-s>", save)
        editor.bind("<Control-S>", save_as)
        editor.bind("<Control-o>", open_file)
        editor.bind("<Control-n>", new_note)
        editor.bind("<Destroy>", on_destroy)

        self._bind_word_delete(editor)

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
    # SCHEDULE
    # ========================================================

    def build_schedule(self):

        self.page_header(
            "Schedule",
            "Plan your days like a timetable. Studestics reminds you "
            "when a block starts."
        )

        today = datetime.now().weekday()

        if getattr(self, "_sched_day", None) is None:
            self._sched_day = today

        top = tk.Frame(self.page, bg=BG)

        top.pack(fill="x", pady=(0, 14))

        self.make_button(
            top, "+ New block", lambda: self.schedule_dialog()
        ).pack(side="left")

        if self.db.get_schedule():

            self.make_button(
                top,
                "Delete all blocks",
                self.delete_all_schedule_confirm,
                active=DANGER_HOVER
            ).pack(side="left", padx=(8, 0))

            self.make_button(
                top,
                "Clear this day",
                self.clear_schedule_day_confirm,
                width=13,
                active=DANGER_HOVER
            ).pack(side="left", padx=(8, 0))

        tabs = tk.Frame(top, bg=BG)

        tabs.pack(side="right")

        tab_buttons = {}

        holder = tk.Frame(
            self.page,
            bg=PANEL,
            highlightthickness=1,
            highlightbackground=BORDER
        )

        holder.pack(fill="both", expand=True)

        scroller = tk.Canvas(
            holder, bg=PANEL, highlightthickness=0, bd=0
        )

        scroller.pack(fill="both", expand=True)

        inner = tk.Frame(scroller, bg=PANEL)

        inner_id = scroller.create_window((0, 0), window=inner, anchor="nw")

        inner.bind(
            "<Configure>",
            lambda e: scroller.configure(scrollregion=scroller.bbox("all"))
        )

        scroller.bind(
            "<Configure>",
            lambda e: scroller.itemconfigure(inner_id, width=e.width)
        )

        self._sched_scroller = scroller

        self.bind_all("<MouseWheel>", self._schedule_wheel)

        def describe_days(days):

            if len(days) == 7:
                return "Every day"

            if days == {0, 1, 2, 3, 4}:
                return "Weekdays"

            if days == {5, 6}:
                return "Weekends"

            return ", ".join(SCHEDULE_DAYS[d] for d in sorted(days))

        def describe_reminder(minutes):

            if minutes < 0:
                return "No reminder"

            if minutes == 0:
                return "Reminds you at the start"

            return f"Reminds you {minutes} min before"

        def render(animate=True):

            try:

                if not inner.winfo_exists():
                    return

            except Exception:
                return

            for widget in inner.winfo_children():
                widget.destroy()

            shown = self._sched_day

            for index, button in tab_buttons.items():
                button.configure(selected=(index == shown))

            now = datetime.now()

            now_min = now.hour * 60 + now.minute

            blocks = [
                b for b in self.db.get_schedule()
                if str(shown) in b["days"].split(",")
            ]

            heading = SCHEDULE_DAY_NAMES[shown]

            if shown == today:
                heading = f"Today  ·  {heading}"

            tk.Label(
                inner,
                text=heading,
                bg=PANEL,
                fg=TEXT,
                font=("Segoe UI", 13, "bold")
            ).pack(anchor="w", padx=20, pady=(16, 2))

            tk.Label(
                inner,
                text=(
                    f"{len(blocks)} block" + ("" if len(blocks) == 1 else "s")
                    if blocks else "Nothing planned yet."
                ),
                bg=PANEL,
                fg=MUTED_2,
                font=("Segoe UI", 9)
            ).pack(anchor="w", padx=20, pady=(0, 10))

            if not blocks:

                return

            next_id = None

            if shown == today:

                for b in blocks:

                    if b["start_min"] > now_min:
                        next_id = b["id"]
                        break

            timelines = []

            for pos, b in enumerate(blocks):

                running = (
                    shown == today
                    and b["start_min"] <= now_min < b["end_min"]
                )

                finished = shown == today and b["end_min"] <= now_min

                wrap = tk.Frame(inner, bg=PANEL)

                wrap.pack(fill="x", padx=16)

                rail = tk.Canvas(
                    wrap, width=38, height=1, bg=PANEL,
                    highlightthickness=0, bd=0
                )

                rail.pack(side="left", fill="y")

                span = max(1, b["end_min"] - b["start_min"])

                fraction = (
                    1.0 if finished
                    else (now_min - b["start_min"]) / span if running
                    else 0.0
                )

                state = (
                    "done" if finished
                    else "now" if running else "later"
                )

                timelines.append((
                    rail, pos == 0, pos == len(blocks) - 1,
                    state, max(0.0, min(1.0, fraction))
                ))

                row = tk.Frame(wrap, bg=PANEL_2)

                row.pack(side="left", fill="x", expand=True, pady=5)

                accent = tk.Frame(
                    row,
                    bg=GREEN if running else PURPLE,
                    width=4
                )

                accent.pack(side="left", fill="y")

                def hover(on, bar=accent, w=wrap, live=running, r=rail):

                    base = GREEN if live else PURPLE

                    bar.configure(
                        bg=(GREEN if live else PURPLE_HOVER) if on else base,
                        width=7 if on else 4
                    )

                def over(event, w=wrap, h=hover):

                    h(True)

                def away(event, w=wrap, h=hover):

                    # Moving between the row's own children is not a
                    # leave.
                    inside = w.winfo_containing(
                        w.winfo_pointerx(), w.winfo_pointery()
                    )

                    while inside is not None and inside is not w:

                        inside = getattr(inside, "master", None)

                    if inside is None:
                        h(False)

                wrap.bind("<Enter>", over)
                wrap.bind("<Leave>", away)

                for child in (row,):
                    child.bind("<Enter>", over)
                    child.bind("<Leave>", away)

                tk.Label(
                    row,
                    text=(
                        f"{format_clock(b['start_min'])} – "
                        f"{format_clock(b['end_min'])}"
                    ),
                    bg=PANEL_2,
                    fg=TEXT,
                    font=("Segoe UI", 11, "bold"),
                    width=19,
                    anchor="w"
                ).pack(side="left", padx=(16, 8), pady=16)

                middle = tk.Frame(row, bg=PANEL_2)

                middle.pack(side="left", fill="x", expand=True)

                title = b["title"]

                if len(title) > 40:
                    title = title[:39] + "…"

                tk.Label(
                    middle,
                    text=title,
                    bg=PANEL_2,
                    fg=TEXT,
                    font=("Segoe UI", 11),
                    anchor="w"
                ).pack(anchor="w", pady=(12, 0))

                days = {int(d) for d in b["days"].split(",") if d != ""}

                tk.Label(
                    middle,
                    text=(
                        f"{describe_days(days)}  ·  "
                        f"{describe_reminder(b['remind_before'])}"
                    ),
                    bg=PANEL_2,
                    fg=MUTED_2,
                    font=("Segoe UI", 9),
                    anchor="w"
                ).pack(anchor="w", pady=(0, 12))

                actions = tk.Frame(row, bg=PANEL_2)

                actions.pack(side="right", padx=(8, 12))

                self.make_button(
                    actions,
                    "Delete",
                    lambda blk=b: self.delete_schedule_confirm(blk),
                    width=7,
                    active=DANGER_HOVER
                ).pack(side="right", padx=(6, 0), pady=12)

                self.make_button(
                    actions,
                    "Edit",
                    lambda blk=b: self.schedule_dialog(blk),
                    width=6
                ).pack(side="right", pady=12)

                if running or b["id"] == next_id:

                    tk.Label(
                        row,
                        text="NOW" if running else "NEXT",
                        bg=GREEN if running else PURPLE,
                        fg="#07140B" if running else "#FFFFFF",
                        font=("Segoe UI", 8, "bold"),
                        padx=9,
                        pady=2
                    ).pack(side="right", padx=(0, 4))

            tk.Frame(inner, bg=PANEL, height=8).pack()

            def draw(t):

                for rail, first, last, state, frac in timelines:

                    try:

                        paint_rail(rail, first, last, state, frac, t)

                    except Exception:
                        pass

            if animate:

                started = time.time()

                def step():

                    try:

                        if not inner.winfo_exists():
                            return

                    except Exception:
                        return

                    t = min(1.0, (time.time() - started) / 0.55)

                    draw(1 - (1 - t) ** 3)

                    if t < 1.0:
                        inner.after(16, step)

                inner.after(30, step)

            else:

                inner.after(30, lambda: draw(1.0))

        def paint_rail(rail, first, last, state, frac, t):
            """Order-tracker style rail: a dot per block joined by a
            line that fills green as the day goes by. Drawn with
            Pillow at 4x so the circles are smooth."""

            rail.update_idletasks()

            h = rail.winfo_height()

            w = 38

            if h < 4:
                return

            k = 4

            img = Image.new("RGBA", (w * k, h * k), _hex_rgb(PANEL) + (255,))

            d = ImageDraw.Draw(img)

            x = w / 2

            mid = h / 2

            grey = _hex_rgb(BORDER)

            green = _hex_rgb(GREEN)

            purple = _hex_rgb(PURPLE)

            back = _hex_rgb(PANEL)

            def line(y0, y1, color):

                if y1 - y0 > 0.5:

                    d.line(
                        [(x * k, y0 * k), (x * k, y1 * k)],
                        fill=color, width=3 * k
                    )

            def disc(r, fill, outline=None, width=0):

                box = [
                    (x - r) * k, (mid - r) * k,
                    (x + r) * k, (mid + r) * k
                ]

                d.ellipse(
                    box, fill=fill,
                    outline=outline, width=int(width * k)
                )

            if not first:

                line(0, mid, grey)

                if state in ("done", "now"):
                    line(0, mid * t, green)

            if not last:

                line(mid, h, grey)

                if state == "done":
                    line(mid, mid + (h - mid) * t, green)

                elif state == "now":
                    line(mid, mid + (h - mid) * frac * t, green)

            if state == "done":

                disc(11, green)

                d.line(
                    [
                        ((x - 5) * k, mid * k),
                        ((x - 1.5) * k, (mid + 4) * k),
                        ((x + 5) * k, (mid - 4) * k)
                    ],
                    fill=(7, 20, 11), width=int(2.6 * k), joint="curve"
                )

            elif state == "now":

                disc(11, back, green, 3)
                disc(5, green)

            else:

                disc(10.5, back, purple, 3)

            img = img.resize((w, h), Image.LANCZOS)

            photo = ImageTk.PhotoImage(img)

            rail.delete("all")

            rail.create_image(0, 0, image=photo, anchor="nw")

            rail._photo = photo

        def pick(index):

            self._sched_day = index

            render()

        for index, name in enumerate(SCHEDULE_DAYS):

            button = self.make_button(
                tabs, name, lambda i=index: pick(i), width=5
            )

            button.pack(side="left", padx=(0, 6))

            tab_buttons[index] = button

        render()

        # Keep NOW / NEXT right while the page stays open.
        def refresh():

            try:

                if (
                    self.current_page == "Schedule"
                    and inner.winfo_exists()
                ):

                    render(False)

                    self.after(60000, refresh)

            except Exception:
                pass

        self.after(60000, refresh)

    def _schedule_wheel(self, event):

        try:

            scroller = getattr(self, "_sched_scroller", None)

            if (
                self.current_page != "Schedule"
                or scroller is None
                or not scroller.winfo_exists()
                or event.widget.winfo_toplevel() is not self
            ):
                return

            first, last = scroller.yview()

            if first <= 0.0 and last >= 1.0:
                return

            scroller.yview_scroll(int(-1 * (event.delta / 120)), "units")

        except Exception:
            pass

    def schedule_dialog(self, block=None, day=None):
        """Add a block to the timetable, or edit `block` (a row)."""

        editing = block is not None

        window = tk.Toplevel(self)

        window.title("Edit block" if editing else "New block")

        tk.Frame(window, bg=PURPLE, height=4).pack(fill="x")

        self.center_window(window, 600, 618)

        window.configure(bg=BG)

        window.transient(self)

        window.grab_set()

        self._form_header(
            window, "Schedule",
            "Edit block" if editing else "New block", "calendar"
        )

        buttons = tk.Frame(window, bg=BG)

        buttons.pack(side="bottom", fill="x", padx=28, pady=(14, 22))

        tk.Frame(window, bg=BORDER, height=1).pack(side="bottom", fill="x")

        form = tk.Frame(window, bg=BG)

        form.pack(fill="both", expand=True, padx=28)

        tk.Label(form, text="What", bg=BG, fg=MUTED).pack(anchor="w")

        title_entry = self.make_entry(form)

        title_entry.pack(fill="x", ipady=8, pady=(5, 14))

        now = datetime.now()

        if editing:

            start0, end0 = block["start_min"], block["end_min"]

            days0 = {int(d) for d in block["days"].split(",") if d != ""}

            remind0 = block["remind_before"]

            title_entry.insert(0, block["title"])

        else:

            days0 = {self._sched_day if day is None else day}

            # Pick up where the day's last block ends, so a timetable
            # can be filled in without typing every time.
            shown_day = str(min(days0))

            ends = [
                b["end_min"] for b in self.db.get_schedule()
                if shown_day in b["days"].split(",")
            ]

            if ends:
                start0 = min(max(ends), 23 * 60 + 30)
            else:
                start0 = min(23 * 60, (now.hour + 1) * 60)

            end0 = min(24 * 60 - 1, start0 + 60)

            remind0 = 0

        tk.Label(form, text="When", bg=BG, fg=MUTED).pack(anchor="w")

        times = tk.Frame(form, bg=BG)

        times.pack(fill="x", pady=(5, 14))

        start_entry = self.make_entry(times)

        start_entry.configure(width=9, justify="center")

        start_entry.pack(side="left", ipady=7)

        start_entry.insert(0, format_clock(start0))

        tk.Label(times, text="to", bg=BG, fg=MUTED).pack(
            side="left", padx=10
        )

        end_entry = self.make_entry(times)

        end_entry.configure(width=9, justify="center")

        end_entry.pack(side="left", ipady=7)

        end_entry.insert(0, format_clock(end0))

        def tidy(entry):

            value = parse_clock(entry.get())

            if value is not None:

                entry.delete(0, "end")
                entry.insert(0, format_clock(value))

        def nudge(entry, step):

            value = parse_clock(entry.get())

            if value is None:
                return "break"

            value = max(0, min(24 * 60 - 1, value + step))

            entry.delete(0, "end")
            entry.insert(0, format_clock(value))

            return "break"

        def word_back(event):

            w = event.widget

            if w.selection_present():

                w.delete("sel.first", "sel.last")

                return "break"

            end = w.index("insert")

            text = w.get()

            start = end

            while start > 0 and text[start - 1].isspace():
                start -= 1

            while start > 0 and not text[start - 1].isspace():
                start -= 1

            w.delete(start, end)

            return "break"

        def word_forward(event):

            w = event.widget

            if w.selection_present():

                w.delete("sel.first", "sel.last")

                return "break"

            start = w.index("insert")

            text = w.get()

            end = start

            while end < len(text) and not text[end].isspace():
                end += 1

            while end < len(text) and text[end].isspace():
                end += 1

            w.delete(start, end)

            return "break"

        def select_all(event):

            event.widget.select_range(0, "end")

            event.widget.icursor("end")

            return "break"

        for entry in (title_entry, start_entry, end_entry):

            entry.bind("<Control-BackSpace>", word_back)
            entry.bind("<Control-Delete>", word_forward)
            entry.bind("<Control-a>", select_all)
            entry.bind("<Control-A>", select_all)

        def flip_meridiem(event):

            w = event.widget

            value = parse_clock(w.get())

            if value is None:
                return

            text = w.get().strip()

            spot = w.index("@%d" % event.x)

            if len(text) >= 2 and text[-2:].upper() in ("AM", "PM") \
                    and spot >= len(w.get()) - 2:

                w.delete(0, "end")
                w.insert(0, format_clock((value + 720) % 1440))

                w.focus_set()

                return "break"

        for entry in (start_entry, end_entry):

            entry.bind("<Button-1>", flip_meridiem, add="+")

        for entry in (start_entry, end_entry):

            entry.bind("<FocusOut>", lambda e, w=entry: tidy(w))
            entry.bind("<Up>", lambda e, w=entry: nudge(w, 15))
            entry.bind("<Down>", lambda e, w=entry: nudge(w, -15))
            entry.bind(
                "<MouseWheel>",
                lambda e, w=entry: nudge(w, 15 if e.delta > 0 else -15)
            )

        tk.Label(
            times,
            text="Click AM / PM to flip  ·  ↑ ↓ ±15 min",
            bg=BG,
            fg=MUTED_2,
            font=("Segoe UI", 9)
        ).pack(side="left", padx=14)

        lengths = tk.Frame(form, bg=BG)

        lengths.pack(fill="x", pady=(0, 14))

        tk.Label(lengths, text="Lasts", bg=BG, fg=MUTED).pack(
            side="left", padx=(0, 10)
        )

        def set_length(minutes):

            begin = parse_clock(start_entry.get())

            if begin is None:
                return

            end_entry.delete(0, "end")
            end_entry.insert(
                0, format_clock(min(begin + minutes, 24 * 60 - 1))
            )

        for label, minutes in (
            ("30 min", 30), ("45 min", 45), ("1 hr", 60),
            ("1.5 hr", 90), ("2 hr", 120)
        ):

            self.make_button(
                lengths, label, lambda m=minutes: set_length(m), width=6
            ).pack(side="left", padx=(0, 6))


        tk.Label(form, text="Repeats on", bg=BG, fg=MUTED).pack(anchor="w")

        chosen = set(days0)

        day_row = tk.Frame(form, bg=BG)

        day_row.pack(fill="x", pady=(5, 14))

        day_buttons = {}

        def paint_days():

            for index, button in day_buttons.items():
                button.configure(selected=(index in chosen))

            try:
                all_button.configure(
                    selected=(len(chosen) == len(SCHEDULE_DAYS))
                )
            except Exception:
                pass

        def toggle(index):

            if index in chosen:
                chosen.discard(index)
            else:
                chosen.add(index)

            paint_days()

        for index, name in enumerate(SCHEDULE_DAYS):

            button = self.make_button(
                day_row, name, lambda i=index: toggle(i), width=4
            )

            button.pack(side="left", padx=(0, 6))

            day_buttons[index] = button

        def toggle_all():

            if len(chosen) == len(SCHEDULE_DAYS):
                chosen.clear()
            else:
                chosen.update(range(len(SCHEDULE_DAYS)))

            paint_days()

        all_button = self.make_button(
            day_row, "All", toggle_all, width=4
        )

        all_button.pack(side="left")

        paint_days()

        tk.Label(
            form, text="Remind me before it starts", bg=BG, fg=MUTED
        ).pack(anchor="w")

        remind = {"value": remind0}

        remind_row = tk.Frame(form, bg=BG)

        remind_row.pack(fill="x", pady=(5, 0))

        remind_buttons = {}

        def paint_remind():

            for minutes, button in remind_buttons.items():
                button.configure(selected=(minutes == remind["value"]))

        def pick_remind(minutes):

            remind["value"] = minutes

            paint_remind()

        for label, minutes in (
            ("Off", -1), ("At start", 0), ("5 min", 5),
            ("10 min", 10), ("15 min", 15)
        ):

            button = self.make_button(
                remind_row, label,
                lambda m=minutes: pick_remind(m), width=8
            )

            button.pack(side="left", padx=(0, 6))

            remind_buttons[minutes] = button

        paint_remind()

        def save():

            name = title_entry.get().strip()

            if not name:

                messagebox.showwarning(
                    "Schedule", "Write what this block is.", parent=window
                )

                return

            start = parse_clock(start_entry.get())
            end = parse_clock(end_entry.get())

            if start is None or end is None:

                messagebox.showwarning(
                    "Schedule",
                    "Times look like 11:00, 9:30 pm or 14:15.",
                    parent=window
                )

                return

            if end <= start:

                messagebox.showwarning(
                    "Schedule",
                    "The block has to end after it starts.",
                    parent=window
                )

                return

            if not chosen:

                messagebox.showwarning(
                    "Schedule", "Pick at least one day.", parent=window
                )

                return

            if editing:

                self.db.update_schedule(
                    block["id"], name, start, end, chosen, remind["value"]
                )

            else:

                self.db.add_schedule(
                    name, start, end, chosen, remind["value"]
                )

            # Show the day this block was made for.
            if self._sched_day not in chosen:
                self._sched_day = min(chosen)

            window.destroy()

            if self.current_page == "Schedule":
                self.show_page("Schedule")

        save_button = self.make_button(
            buttons,
            "Save changes" if editing else "Add block",
            save,
            width=13
        )

        save_button.configure(selected=True)
        save_button.pack(side="right")

        self.make_button(
            buttons, "Cancel", window.destroy, width=9
        ).pack(side="right", padx=(0, 10))

        title_entry.focus_set()

        window.bind("<Return>", lambda e: save())

    def delete_all_schedule_confirm(self):

        count = len(self.db.get_schedule())

        if not count:
            return

        if not messagebox.askyesno(
            "Delete all blocks",
            f"Delete all {count} block" + ("" if count == 1 else "s")
            + " on every day of your schedule? This can't be undone."
        ):
            return

        self.db.delete_all_schedule()

        self.show_page("Schedule")

    def clear_schedule_day_confirm(self):

        day = self._sched_day

        name = SCHEDULE_DAY_NAMES[day]

        count = sum(
            1 for b in self.db.get_schedule()
            if str(day) in b["days"].split(",")
        )

        if not count:

            messagebox.showinfo(
                "Clear this day", f"Nothing is planned on {name}."
            )

            return

        if not messagebox.askyesno(
            "Clear this day",
            f"Delete the {count} block" + ("" if count == 1 else "s")
            + f" on {name}? Blocks that also repeat on other days stay "
            "on those days."
        ):
            return

        self.db.clear_schedule_day(day)

        self.show_page("Schedule")

    def delete_schedule_confirm(self, block):

        if not messagebox.askyesno(
            "Delete block",
            f'Delete "{block["title"]}" from your schedule?'
        ):
            return

        self.db.delete_schedule(block["id"])

        self.show_page("Schedule")

    def _schedule_tick(self):
        """Pops up a reminder when a block is about to start."""

        try:

            if self.initialized and self.db and not self._quitting:

                now = datetime.now()

                minute = now.hour * 60 + now.minute

                stamp = now.strftime("%Y-%m-%d")

                if getattr(self, "_sched_stamp", "") != stamp:

                    self._sched_stamp = stamp
                    self._sched_fired = set()

                due = []

                for block in self.db.get_schedule():

                    if block["remind_before"] < 0:
                        continue

                    if str(now.weekday()) not in block["days"].split(","):
                        continue

                    trigger = block["start_min"] - block["remind_before"]

                    # A reminder that is more than 10 minutes late
                    # (the app was closed) is skipped, not shown late.
                    if (
                        trigger <= minute < min(trigger + 10, block["end_min"])
                        and block["id"] not in self._sched_fired
                    ):

                        self._sched_fired.add(block["id"])

                        due.append(block)

                if due:
                    self.show_schedule_alarm(due)

        except Exception:
            pass

        finally:

            if not self._quitting:
                self.after(15000, self._schedule_tick)

    def show_schedule_alarm(self, blocks):
        """Card for a block that is starting: a short beep, stays on top
        until dealt with, even if the app is hidden in the tray."""

        old = getattr(self, "_sched_popup", None)

        if old is not None:

            try:
                old.destroy()
            except Exception:
                pass

        blocks = list(blocks)

        first = blocks[0]

        def minute_now():

            now = datetime.now()

            return now.hour * 60 + now.minute

        def range_text(block):

            return (
                f"{format_clock(block['start_min'])} – "
                f"{format_clock(block['end_min'])}"
            )

        def status():

            gap = first["start_min"] - minute_now()

            if len(blocks) > 1:
                return f"{len(blocks)} blocks are starting."

            if gap > 0:
                return (
                    f"Starts in {gap} minute" + ("" if gap == 1 else "s")
                    + f"   ·   {range_text(first)}"
                )

            return f"Starting now   ·   {range_text(first)}"

        starting = first["start_min"] <= minute_now()

        accent = GREEN if starting else PURPLE

        if len(blocks) == 1:

            heading = first["title"]

            if len(heading) > 90:
                heading = heading[:89] + "…"

        else:

            heading = "Up next"

        shell = self._alert_shell(
            "Starting now" if starting else "Up next",
            heading, accent, "calendar", status()
        )

        win = shell["win"]

        self._sched_popup = win

        win.title("Studestics schedule")

        self._attach_alarm(win, False)

        body = shell["body"]

        if len(blocks) > 1:

            for block in blocks[:4]:

                self._alert_row(
                    body, accent, block["title"], range_text(block)
                )

            if len(blocks) > 4:

                tk.Label(
                    body, text=f"+ {len(blocks) - 4} more", bg=BG,
                    fg=MUTED_2, font=("Segoe UI", 9)
                ).pack(anchor="w", pady=(4, 0))

        # What comes after, so the day has a shape.
        try:

            today = str(datetime.now().weekday())

            ids = {b["id"] for b in blocks}

            later = [
                b for b in self.db.get_schedule()
                if today in b["days"].split(",")
                and b["id"] not in ids
                and b["start_min"] >= first["end_min"] - 1
            ]

            if later:

                nxt = later[0]

                tk.Label(
                    body,
                    text=(
                        f"After this:  {format_clock(nxt['start_min'])}"
                        f"   {nxt['title']}"
                    ),
                    bg=BG, fg=MUTED_2, font=("Segoe UI", 9), anchor="w"
                ).pack(anchor="w", pady=(6, 0))

        except Exception:
            pass

        def refresh():

            try:

                if not win.winfo_exists():
                    return

                shell["sub"].configure(text=status())

                if first["start_min"] <= minute_now():
                    shell["kicker"].configure(
                        text="STARTING NOW", fg=GREEN
                    )
                    shell["strip"].configure(bg=GREEN)

                win.after(15000, refresh)

            except Exception:
                pass

        win.after(15000, refresh)

        def snooze(minutes):

            win.destroy()

            self.after(
                minutes * 60 * 1000,
                lambda b=list(blocks): self.show_schedule_alarm(b)
            )

        foot = shell["foot"]

        self._alert_snooze_row(foot, (5, 10, 15), snooze)

        bar = tk.Frame(foot, bg=BG)

        bar.pack()

        def open_app():
            self.restore_window()
            self._sched_day = datetime.now().weekday()
            self.show_page("Schedule")
            win.destroy()

        self.make_button(
            bar, "Dismiss", win.destroy, width=10, active=RED
        ).pack(
            side="left", padx=4
        )

        self.make_button(bar, "Open app", open_app, width=10).pack(
            side="left", padx=4
        )

        go = self.make_button(
            bar, "Start focus",
            lambda: (self._start_focus_from_alert(), win.destroy()),
            width=10
        )

        go.configure(selected=True)

        go.pack(side="left", padx=4)

        self._alert_show(shell)

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

        # Made before the drawer, so the drawer slides over them.
        self._build_focus_corner(panel)

        self._build_focus_drawer(panel)
        self._build_float_toggle(panel)

        self._refresh_focus_presets()
        self.update_focus_ui()

        # Get the timer background ready for the full screen view.
        self.prewarm_timer_background()

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

        shown = tasks
        extra = 0

        win = tk.Toplevel(self)

        win._glow = PURPLE

        win.title("Choose a task")
        win.configure(bg=BG)
        win.transient(self)
        win.grab_set()


        tk.Frame(win, bg=PURPLE, height=4).pack(fill="x")

        tk.Label(
            win, text="FOCUS MODE", bg=BG, fg=PURPLE,
            font=("Segoe UI", 9, "bold")
        ).pack(anchor="w", padx=28, pady=(20, 0))

        self._glow_heading(
            win, "Focus on which task?", PURPLE, 18
        ).pack(anchor="w", padx=28, pady=(2, 14))

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

        rows = []

        if shown:

            holder = tk.Frame(win, bg=BG)

            holder.pack(fill="x", padx=28)

            canvas = tk.Canvas(
                holder, bg=BG, highlightthickness=0, bd=0, height=10
            )

            canvas.pack(fill="x")

            list_frame = tk.Frame(canvas, bg=BG)

            inner = canvas.create_window(
                (0, 0), window=list_frame, anchor="nw"
            )

            canvas.bind(
                "<Configure>",
                lambda e: canvas.itemconfigure(inner, width=e.width)
            )

        else:

            list_frame = tk.Frame(win, bg=BG)

        for task in shown:

            row, _meta = self._alert_row(
                list_frame,
                priority_color(task["priority"]),
                task["title"],
                f"{task['priority']} priority",
                action=(
                    "Select",
                    lambda tid=task["id"]: pick(tid)
                )
            )

            rows.append((row, task["id"]))

        state = {"i": 0}

        if shown:

            win.update_idletasks()

            row_h = rows[0][0].winfo_reqheight() + 8

            visible = min(len(rows), 3)

            canvas.configure(
                height=row_h * visible,
                scrollregion=(0, 0, 0, row_h * len(rows))
            )

            def highlight():
                for n, (row, _id) in enumerate(rows):
                    try:
                        row.action_button.configure(
                            selected=(n == state["i"])
                        )
                    except Exception:
                        pass
                top = state["i"] * row_h
                view_top = canvas.canvasy(0)
                view_h = canvas.winfo_height()
                if top < view_top:
                    canvas.yview_moveto(top / (row_h * len(rows)))
                elif top + row_h > view_top + view_h:
                    canvas.yview_moveto(
                        (top + row_h - view_h) / (row_h * len(rows))
                    )

            def move(step):
                state["i"] = (state["i"] + step) % len(rows)
                highlight()
                return "break"

            win.bind("<Up>", lambda e: move(-1))
            win.bind("<Down>", lambda e: move(1))
            win.bind(
                "<Return>", lambda e: pick(rows[state["i"]][1])
            )

            def wheel(e):
                if len(rows) > visible:
                    canvas.yview_scroll(int(-e.delta / 120), "units")
                return "break"

            win.bind("<MouseWheel>", wheel)

            canvas.configure(yscrollincrement=row_h // 2)

            highlight()

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

        win.update_idletasks()

        self.center_window(win, 480, win.winfo_reqheight())

        win.focus_set()

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

        # The round-over popup must not end up behind the cover.
        self._leave_fullscreen()

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

            if explain:

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
            "Full-screen overlay",
            "",
            lambda parent: self.make_switch(
                parent,
                on=self.nudge_strict,
                command=self.set_nudge_strict,
                bg=SIDEBAR
            )
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

        # Packed ahead of everything else so that on a short window it
        # is the options above that give way, not this list.
        words_box.pack(
            side="bottom",
            fill="x",
            padx=(left, 22),
            pady=(0, 24),
            before=drawer.pack_slaves()[0]
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

    # --------------------------------------------------------
    # Lofi music and full screen (bottom right of the Focus page)
    # --------------------------------------------------------

    def _corner_icon_image(self, kind, size, color, on):

        scale = 8

        big = size * scale

        img = Image.new("RGBA", (big, big), (0, 0, 0, 0))

        d = ImageDraw.Draw(img)

        u = big / 26.0

        def line(points, width):

            d.line(
                [(x * u, y * u) for x, y in points],
                fill=color,
                width=int(round(width * u)),
                joint="curve"
            )

            r = width * u / 2

            for x, y in (points[0], points[-1]):

                d.ellipse(
                    [x * u - r, y * u - r, x * u + r, y * u + r],
                    fill=color
                )

        if kind == "music":

            d.ellipse([3 * u, 16 * u, 10.5 * u, 22 * u], fill=color)
            d.ellipse([14 * u, 14 * u, 21.5 * u, 20 * u], fill=color)

            d.rectangle(
                [9 * u, 6 * u, 10.8 * u, 19 * u],
                fill=color
            )

            d.rectangle(
                [20 * u, 4 * u, 21.8 * u, 17 * u],
                fill=color
            )

            d.polygon(
                [
                    (9 * u, 6 * u), (21.8 * u, 3.6 * u),
                    (21.8 * u, 7.4 * u), (9 * u, 9.8 * u)
                ],
                fill=color
            )

            if not on:

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

        elif not on:

            # Corners pointing out: "make it bigger".
            line([(4, 10), (4, 4), (10, 4)], 2.2)
            line([(16, 4), (22, 4), (22, 10)], 2.2)
            line([(22, 16), (22, 22), (16, 22)], 2.2)
            line([(10, 22), (4, 22), (4, 16)], 2.2)

        else:

            # Corners pointing in: "back to normal".
            line([(4, 9), (9, 9), (9, 4)], 2.2)
            line([(17, 4), (17, 9), (22, 9)], 2.2)
            line([(22, 17), (17, 17), (17, 22)], 2.2)
            line([(9, 22), (9, 17), (4, 17)], 2.2)

        return img.resize((size, size), Image.LANCZOS)

    def _build_focus_corner(self, panel):

        corner = {"hover": None, "icons": {}}

        self._corner = corner

        corner["tip"] = tk.Label(
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

        def make(kind, offset, command):

            icon = tk.Canvas(
                panel,
                width=38,
                height=38,
                bg=PANEL,
                highlightthickness=0,
                bd=0,
                cursor="hand2"
            )

            icon.place(
                relx=1.0,
                rely=1.0,
                x=offset,
                y=-14,
                anchor="se"
            )

            def hover(on):

                corner["hover"] = kind if on else None

                self._paint_corner()

                self._corner_tip(on)

            def click(event=None):

                command()

                self._corner_tip(True)

            icon.bind("<Enter>", lambda e: hover(True))
            icon.bind("<Leave>", lambda e: hover(False))
            icon.bind("<Button-1>", click)

            corner["icons"][kind] = icon

        make("full", -14, self.toggle_fullscreen)
        make("music", -58, self.toggle_music)

        self._paint_corner()

    def _paint_corner(self):

        corner = self._corner

        if not corner:
            return

        for kind, icon in corner["icons"].items():

            on = self.music_on if kind == "music" else self._fullscreen

            hovered = corner["hover"] == kind

            if kind == "music" and self.music_on:
                color = PURPLE_LIGHT if hovered else PURPLE_HOVER
            else:
                color = TEXT if hovered else MUTED

            try:

                icon.delete("all")

                if HAS_PIL:

                    photo = ImageTk.PhotoImage(
                        self._corner_icon_image(kind, 26, color, on)
                    )

                    icon.icon_photo = photo

                    icon.create_image(19, 19, image=photo)

                else:

                    icon.create_text(
                        19, 19,
                        text="♪" if kind == "music" else "⛶",
                        fill=color,
                        font=("Segoe UI", 16)
                    )

            except Exception:
                pass

    def _corner_tip(self, on):

        corner = self._corner

        if not corner:
            return

        tip = corner["tip"]

        try:

            kind = corner["hover"]

            if not on or kind is None:

                tip.place_forget()

                return

            if kind == "music":

                text = (
                    "Lofi music: On  (click to turn off)"
                    if self.music_on
                    else "Lofi music: Off  (click to turn on)"
                )

            else:

                text = "Timer only, full screen  (F or F11)"

            tip.configure(text=text)

            tip.place(
                relx=1.0,
                rely=1.0,
                x=-14,
                y=-60,
                anchor="se"
            )

            tk.Misc.tkraise(tip)

        except Exception:
            pass

    def toggle_fullscreen(self, event=None):
        """Distraction-free view: a full-screen cover with only the
        timer in the middle."""

        if self._fullscreen:
            self._leave_fullscreen()
        else:
            self._enter_fullscreen()

        return "break"

    def _monitor_rect(self):
        """x, y, width, height of the screen the app is on."""

        try:

            import ctypes
            from ctypes import wintypes

            class MONITORINFO(ctypes.Structure):

                _fields_ = [
                    ("cbSize", wintypes.DWORD),
                    ("rcMonitor", wintypes.RECT),
                    ("rcWork", wintypes.RECT),
                    ("dwFlags", wintypes.DWORD)
                ]

            user32 = ctypes.windll.user32

            user32.MonitorFromWindow.restype = wintypes.HANDLE
            user32.MonitorFromWindow.argtypes = [
                wintypes.HWND, wintypes.DWORD
            ]

            hwnd = user32.GetParent(self.winfo_id()) or self.winfo_id()

            monitor = user32.MonitorFromWindow(hwnd, 2)

            info = MONITORINFO()
            info.cbSize = ctypes.sizeof(MONITORINFO)

            if user32.GetMonitorInfoW(monitor, ctypes.byref(info)):

                r = info.rcMonitor

                return r.left, r.top, r.right - r.left, r.bottom - r.top

        except Exception:
            pass

        return 0, 0, self.winfo_screenwidth(), self.winfo_screenheight()

    def _enter_fullscreen(self):

        if self._fullscreen:
            return

        x, y, sw, sh = self._monitor_rect()

        win = tk.Toplevel(self)

        win.withdraw()

        win.overrideredirect(True)
        win.configure(bg=BG)
        win.geometry(f"{sw}x{sh}+{x}+{y}")

        # Owned by the main window, so Windows counts both as one
        # program in Alt+Tab (one press moves to the next program).
        try:
            win.transient(self)
        except Exception:
            pass

        # Not "always on top", so Alt+Tab and the taskbar can bring
        # another window in front of it.
        canvas = tk.Canvas(
            win,
            bg=BG,
            highlightthickness=0,
            bd=0,
            cursor="arrow"
        )

        canvas.pack(fill="both", expand=True)

        # The same clock style as on the Focus page and floating clock.
        style = (
            self.float_style
            if self.float_style in FLOAT_SIZES
            else "ring"
        )

        base_w, base_h = FLOAT_SIZES[style]

        if style in ("ring", "ticks"):
            ring_zoom = 0.46 * sh / base_h
        else:
            # The wide ones: about 40% of the screen width.
            ring_zoom = min(0.40 * sw / base_w, 0.30 * sh / base_h)

        lay = float_layout(style, ring_zoom)

        shape_w, shape_h = lay["size"]

        diameter = shape_h

        zen = {
            "win": win,
            "canvas": canvas,
            "key": None,
            "job": None,
            "photo": None
        }

        self._zen = zen

        self._fullscreen = True

        cx, cy = sw / 2, sh / 2

        # The picture chosen in Settings, behind everything else.
        bg_image = self.timer_background_image((sw, sh))

        if bg_image is not None:

            zen["bg_photo"] = ImageTk.PhotoImage(bg_image)

            canvas.create_image(
                0, 0, anchor="nw", image=zen["bg_photo"], tags="bgpic"
            )

            self.after(60, lambda: self._start_bg_animation(zen, sw, sh))

        ox, oy = cx - shape_w / 2, cy - shape_h / 2

        tx, ty, tpx = lay["time"]
        sx, sy, spx = lay["status"]

        time_id = canvas.create_text(
            ox + tx, oy + ty,
            text="",
            fill=TEXT,
            font=("Segoe UI", -tpx, "bold")
        )

        status_id = canvas.create_text(
            ox + sx, oy + sy,
            text="",
            fill=MUTED,
            font=("Segoe UI", -spx)
        )

        hint_id = canvas.create_text(
            cx, sh - 40,
            text="Space to pause or resume   |   F or Esc to leave",
            fill=MUTED_2,
            font=("Segoe UI", -14)
        )

        def paint():

            zen["job"] = None

            if not self._fullscreen or self._zen is not zen:
                return

            if self.focus_finished:
                fraction, color, status = 1.0, GREEN, "Complete"
            else:

                fraction = (
                    self.focus_seconds / max(1, self._phase_total())
                )

                if self.focus_phase != "focus":
                    color, status = BLUE, "Break"
                elif self.focus_running:
                    color, status = PURPLE_HOVER, "Focusing"
                else:
                    color, status = PURPLE_HOVER, "Paused"

            key = (round(fraction, 3), color)

            if key != zen["key"]:

                zen["key"] = key

                canvas.delete("ring")

                if HAS_PIL:

                    img, _ = render_float(
                        style,
                        fraction,
                        color,
                        None if bg_image is not None else BG,
                        zoom=ring_zoom,
                        card=style in ("pill", "bar"),
                        soft=bg_image is not None
                    )

                    zen["photo"] = ImageTk.PhotoImage(img)

                    canvas.create_image(
                        cx, cy,
                        image=zen["photo"],
                        tags="ring"
                    )

                else:

                    r = diameter / 2 - 14

                    canvas.create_oval(
                        cx - r, cy - r, cx + r, cy + r,
                        outline=BORDER, width=12, tags="ring"
                    )

                    if fraction > 0:

                        canvas.create_arc(
                            cx - r, cy - r, cx + r, cy + r,
                            start=90,
                            extent=-min(359.9, 360 * fraction),
                            style="arc",
                            outline=color,
                            width=12,
                            tags="ring"
                        )

                # Just under the time, but above the picture.
                canvas.tag_lower("ring", time_id)

            # An overlay window doesn't always get the keyboard from
            # Windows; take it back if it is somewhere else.
            try:

                holder = self.focus_get()

                # Only when the focus is in this app's main window. If
                # another app has it (you Alt+Tabbed), leave it alone.
                if holder is not None and holder.winfo_toplevel() is self:

                    win.lift()
                    win.focus_force()
                    canvas.focus_set()

            except Exception:
                pass

            canvas.itemconfigure(time_id, text=self.focus_time_text())
            canvas.itemconfigure(status_id, text=status)

            zen["job"] = win.after(250, paint)

        def hide_hint():

            try:

                canvas.delete(hint_id)

                canvas.configure(cursor="none")

            except Exception:
                pass

        for sequence in ("<Escape>", "<F11>", "<Double-Button-1>"):
            win.bind(sequence, lambda e: self._leave_fullscreen())

        # Click anywhere to make sure the keys reach this window.
        canvas.bind("<Button-1>", lambda e: canvas.focus_set())

        paint()

        win.deiconify()

        try:

            win.lift()
            win.focus_force()
            canvas.focus_set()

        except Exception:
            pass

        win.after(3500, hide_hint)

        self._paint_corner()

    def _zen_keys(self, event):
        """Space pauses or resumes and F goes in or out of the
        timer-only view."""

        try:

            if event.state & (0x4 | 0x20000):
                return

            key = event.keysym

            if self._fullscreen:

                if key == "space":

                    self.toggle_focus()

                    return "break"

                if key in ("f", "F"):

                    self._leave_fullscreen()

                    return "break"

                if key == "Escape":

                    self._leave_fullscreen()

                return

            if (
                key in ("f", "F", "space")
                and self.current_page == "Focus Mode"
                and event.widget.winfo_toplevel() is self
            ):

                kind = event.widget.winfo_class()

                if kind in (
                    "Entry", "Text", "TEntry", "TCombobox", "Spinbox"
                ):
                    return

                if key == "space":
                    self.toggle_focus()
                else:
                    self._enter_fullscreen()

                return "break"

        except Exception:
            pass

    def _leave_fullscreen(self, event=None):

        zen = getattr(self, "_zen", None)

        self._fullscreen = False
        self._zen = None

        if zen:

            try:

                if zen["job"]:
                    zen["win"].after_cancel(zen["job"])

            except Exception:
                pass

            try:
                zen["win"].destroy()
            except Exception:
                pass

            # Give the keyboard back to the main window; without this
            # Windows leaves it with nobody and Space does nothing.
            def regain():

                try:

                    self.lift()
                    self.focus_force()

                except Exception:
                    pass

            self.after(40, regain)

        self._paint_corner()

    def toggle_music(self):

        self.music_on = not self.music_on

        self.db.set_setting(
            "focus_music",
            "1" if self.music_on else "0"
        )

        self._paint_corner()

        # The watcher below starts or stops it within a moment.

    def _music_playing(self):

        ev = self._music_stop_ev

        return ev is not None and not ev.is_set()

    def _music_watch(self):
        """Lofi plays while a focus round is running, and stops when
        you pause, reset, take a break or the round ends."""

        try:

            if not getattr(self, "_quitting", False):

                want = (
                    self.music_on
                    and self.focus_running
                    and self.focus_phase == "focus"
                )

                playing = self._music_playing()

                if want and not playing and not self._music_failed:
                    self._music_start()

                elif not want and playing:
                    self._music_stop()

        except Exception:
            pass

        if not getattr(self, "_quitting", False):
            self.after(500, self._music_watch)

    def _music_start(self):

        if sys.platform != "win32" or self._music_playing():
            return

        stop = threading.Event()

        self._music_stop_ev = stop

        self._music_serial += 1

        alias = f"studlofi{self._music_serial}"

        def run():

            opened = False

            try:

                path = lofi_path()

                if stop.is_set():
                    return

                error, _ = mci_send(
                    f'open "{path}" type waveaudio alias {alias}'
                )

                if error:

                    self._music_failed = True

                    return

                opened = True

                mci_send(f"setaudio {alias} volume to 450")

                error, _ = mci_send(f"play {alias}")

                if error:

                    self._music_failed = True

                    return

                while not stop.is_set():

                    stop.wait(0.1)

                    error, mode = mci_send(f"status {alias} mode")

                    if error:
                        break

                    if mode == "stopped":

                        mci_send(f"seek {alias} to start")
                        mci_send(f"play {alias}")

            except Exception:

                self._music_failed = True

            finally:

                if opened:

                    try:

                        mci_send(f"stop {alias}")
                        mci_send(f"close {alias}")

                    except Exception:
                        pass

                stop.set()

        threading.Thread(target=run, daemon=True).start()

    def _music_stop(self):

        ev = self._music_stop_ev

        self._music_stop_ev = None

        if ev is not None:
            ev.set()

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

        if finished == "focus":

            if next_phase == "long":
                heading = "Set complete"
            else:
                heading = f"Round {self.pomo_done} done"

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

            kicker, accent, icon = "Focus round", GREEN, "check"

        else:

            heading = "Break's over"

            summary = (
                f"Ready for round {self.pomo_done + 1} "
                f"of {POMO_ROUNDS}?"
            )

            kicker, accent, icon = "Break", YELLOW, "clock"

        shell = self._alert_shell(kicker, heading, accent, icon, summary)

        win = shell["win"]

        # A full focus round rings until you answer; the end of a
        # break is a single, gentler beep.
        self._attach_alarm(win, finished == "focus")

        bar = tk.Frame(shell["foot"], bg=BG)

        bar.pack()

        def start_next():
            win.destroy()
            if not self.focus_running:
                self.toggle_focus()

        def skip():
            win.destroy()
            self.skip_break()

        if finished == "focus":

            self.make_button(
                bar, "Skip break", skip, width=10
            ).pack(side="left", padx=4)

            if task is not None:

                def mark_done():
                    self.db.complete_task(task["id"])
                    self.focus_task_id = None
                    win.destroy()
                    self.show_page(self.current_page)

                self.make_button(
                    bar, "Mark done", mark_done, width=10
                ).pack(side="left", padx=4)

        else:

            self.make_button(
                bar, "Dismiss", win.destroy, width=10, active=RED
            ).pack(side="left", padx=4)

        primary = self.make_button(
            bar,
            "Start break" if finished == "focus" else "Start focus",
            start_next,
            width=10
        )

        primary.configure(selected=True)

        primary.pack(side="left", padx=4)

        self._alert_show(shell)

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

                self._nudge_fire(word, now)

                return

    def _nudge_fire(self, word, now):

        hwnd = foreground_window_handle()

        if self.nudge_strict and hwnd:

            self._nudge_cooldown_until = now + 3

            self.focus_nudges += 1

            self.show_strict_overlay(word, hwnd)

            return

        self._nudge_cooldown_until = now + NUDGE_COOLDOWN_SECONDS

        self.focus_nudges += 1

        self.show_nudge(word)

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

    def set_nudge_strict(self, value):

        self.nudge_strict = bool(value)

        self.db.set_setting(
            "nudge_strict",
            "1" if self.nudge_strict else "0"
        )

    def show_strict_overlay(self, word, hwnd):
        """A full-screen block that stays until the distracting
        window or tab is closed, the timer ends, or focus is turned
        off. Alt+F4 and Esc do nothing to it."""

        task = self._focus_task()

        exe = window_process_name(hwnd)
        is_browser = exe in BROWSER_EXES

        win = tk.Toplevel(self)
        self._nudge_popup = win

        win.configure(bg=BG)
        win.overrideredirect(True)

        rect = screen_rect() or (
            0, 0, self.winfo_screenwidth(), self.winfo_screenheight()
        )

        win.geometry("%dx%d+%d+%d" % (rect[2], rect[3], rect[0], rect[1]))
        win.attributes("-topmost", True)

        win.protocol("WM_DELETE_WINDOW", lambda: None)

        for sequence in ("<Alt-F4>", "<Escape>", "<Alt-Key>"):
            win.bind(sequence, lambda e: "break")

        self._nudge_beep()

        box = tk.Frame(win, bg=BG)

        box.place(relx=0.5, rely=0.5, anchor="center")

        tk.Label(
            box, text="Back to it", bg=BG, fg=TEXT,
            font=("Segoe UI", 36, "bold")
        ).pack()

        tk.Label(
            box,
            text=(
                f"That looks like {word.title()}, and your focus "
                "timer is still running."
            ),
            bg=BG, fg=MUTED, font=("Segoe UI", 14),
            wraplength=720, justify="center"
        ).pack(pady=(10, 0))

        clock = tk.Label(
            box, text=self.focus_time_text(), bg=BG, fg=PURPLE,
            font=("Segoe UI", 48, "bold")
        )

        clock.pack(pady=(24, 0))

        if task is not None:

            label = task["title"]

            if len(label) > 60:
                label = label[:59] + "…"

            tk.Label(
                box, text=f'Still on: "{label}"', bg=BG, fg=TEXT,
                font=("Segoe UI", 13)
            ).pack(pady=(4, 0))

        shown = window_title(hwnd)

        if len(shown) > 70:
            shown = shown[:69] + "…"

        tk.Label(
            box, text=shown, bg=BG, fg=MUTED_2,
            font=("Segoe UI", 10)
        ).pack(pady=(26, 8))

        state = {"attempts": 0, "grace_until": 0.0}

        def button_text():

            if is_browser and state["attempts"] == 0:
                return "Close this tab"

            if is_browser:
                return "Close the whole window"

            return "Close this app"

        def finish():

            try:
                win.destroy()
            except Exception:
                pass

            self._nudge_popup = None

            self._nudge_cooldown_until = time.time() + 3

        def press_ctrl_w_if_front():

            if foreground_window_handle() == hwnd:
                press_ctrl_w()

        def close_clicked():

            if not window_exists(hwnd):
                finish()
                return

            state["attempts"] += 1

            # Step aside so the tab visibly closes and any "are you
            # sure?" box can be answered.
            win.withdraw()

            if is_browser and state["attempts"] == 1:

                bring_window_to_front(hwnd)

                win.after(250, press_ctrl_w_if_front)

            else:

                close_window_politely(hwnd)

            state["grace_until"] = time.time() + 8

        action = self.make_button(
            box, button_text(), close_clicked, width=24
        )

        action.configure(selected=True)

        action.pack()

        def still_distracting():

            title = window_title(hwnd).lower()

            return any(
                w and w in title for w in self.nudge_words
            )

        def tick():

            try:

                if not win.winfo_exists():
                    return

            except Exception:
                return

            if (
                not self.focus_running
                or self.focus_phase != "focus"
                or not self.nudge_on
                or not self.nudge_strict
                or not window_exists(hwnd)
                or not still_distracting()
            ):
                finish()
                return

            if time.time() < state["grace_until"]:
                win.after(400, tick)
                return

            if state["grace_until"]:

                # The tab or app didn't close: bring the block back.
                state["grace_until"] = 0.0

                action.configure(text=button_text())

                win.deiconify()

            clock.configure(text=self.focus_time_text())

            win.attributes("-topmost", True)
            win.lift()

            # Keep keyboard focus here, except while Task Manager is
            # in front, so it can always be used.
            if "task manager" not in foreground_window_title().lower():

                try:
                    win.focus_force()
                except Exception:
                    pass

            win.after(400, tick)

        try:
            win.focus_force()
        except Exception:
            pass

        win.after(400, tick)

    def edit_nudge_words(self):
        """Add and remove nudge words one at a time. Edits stay in a
        local list until Save, so Cancel throws them away."""

        win = tk.Toplevel(self)

        win.title("Distraction words")

        tk.Frame(win, bg=PURPLE, height=4).pack(fill="x")
        win.configure(bg=BG)
        win.transient(self)
        win.grab_set()

        self.center_window(win, 580, 564)

        words = list(self.nudge_words)

        self._glow_heading(
            win, "Distraction words", PURPLE, 18
        ).pack(anchor="w", padx=28, pady=(24, 4))

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

            for item in items:

                label, command, active = item[:3]

                drop = item[3] if len(item) > 3 else None

                # Same padding RoundedButton adds, plus the gap.
                needed = chip_font.measure(label) + 26 + 8

                if drop:
                    needed += 24

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

                if drop:

                    # One pill: click the word to add it, click the
                    # x at its right end to hide the suggestion.
                    pill = self.make_button(
                        row,
                        label + "   ×",
                        command,
                        active=active
                    )

                    pill.pack(side="left", padx=(0, 8))

                    def click(event, pill=pill, command=command, drop=drop):

                        if event.x >= pill.canvas.winfo_width() - 34:
                            drop()
                        else:
                            command()

                    pill.canvas.bind("<Button-1>", click)

                else:

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
                w for w in NUDGE_SUGGESTIONS
                if w not in words and w not in hidden
            ][:8]

            sugg_label.configure(
                text="Quick add" if available else ""
            )

            flow(
                sugg,
                [
                    (
                        f"+ {w}",
                        lambda w=w: add_word(w),
                        PURPLE_HOVER,
                        lambda w=w: hide_suggestion(w)
                    )
                    for w in available
                ]
            )

            fit()

        def fit():
            """Make the window as tall as what is in it."""

            try:

                win.update_idletasks()

                width = max(win.winfo_width(), 580)

                height = min(
                    win.winfo_reqheight() + 4,
                    win.winfo_screenheight() - 80
                )

                if first_fit["done"]:

                    win.geometry(f"{width}x{height}")

                else:

                    first_fit["done"] = True

                    self.center_window(win, 580, height)

            except Exception:
                pass

        first_fit = {"done": False}

        # Suggestions the user crossed out; they stay gone.
        hidden = set(
            parse_words(
                self.db.get_setting("nudge_hidden_suggestions", "")
            )
        )

        def hide_suggestion(word):

            hidden.add(word)

            self.db.set_setting(
                "nudge_hidden_suggestions",
                ", ".join(sorted(hidden))
            )

            render()

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

            hidden.clear()

            self.db.set_setting("nudge_hidden_suggestions", "")

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

        summary = f"{self._focus_len_text()} done."

        if task is not None:
            title = task["title"]
            if len(title) > 30:
                title = title[:29] + "…"
            summary += f' You were working on "{title}".'

        shell = self._alert_shell(
            "Focus", "Focus session complete", GREEN, "check", summary
        )

        win = shell["win"]

        self._attach_alarm(win, True)

        bar = tk.Frame(shell["foot"], bg=BG)

        bar.pack()

        self.make_button(
            bar, "Dismiss", win.destroy, width=10, active=RED
        ).pack(side="left", padx=4)

        if task is not None:

            def mark_done():
                self.db.complete_task(task["id"])
                self.focus_task_id = None
                win.destroy()
                self.show_page(self.current_page)

            go = self.make_button(
                bar, "Mark task done", mark_done, width=14
            )

        else:

            go = self.make_button(
                bar, "Open app",
                lambda: (self.restore_window(), win.destroy()),
                width=10
            )

        go.configure(selected=True)

        go.pack(side="left", padx=4)

        self._alert_show(shell)

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

        self._warm_gemini()

        self.page_header(
            "AI Chat",
            "Your study assistant, powered by Gemini. Type /notes "
            "for notes, or /schedule to plan your days."
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
                "planning, assignments or goals.\n\n"
                "Tip: type /notes and a topic, for example "
                "/notes photosynthesis, and I'll write study notes "
                "into your Notes tab. Use /newnotes instead to "
                "replace your old notes."
            )

        else:

            # Only the latest messages are drawn when the page opens;
            # drawing a long history word by word is what made the
            # page slow. Everything stays saved.
            for message in messages[-20:]:

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

        self._restore_chat_draft()

        # A slim thumb on the right edge that only shows when there is
        # more text than the three visible lines.
        bar = tk.Canvas(
            self.chat_input, width=8, bg=PANEL_2,
            highlightthickness=0, bd=0, cursor="hand2"
        )

        self._chat_scrollbar = bar

        def draw_thumb(first, last):

            first, last = float(first), float(last)

            if first <= 0.0 and last >= 1.0:

                bar.place_forget()

                return

            full = max(20, self.chat_input.winfo_height() - 8)

            bar.place(relx=1.0, x=-11, y=4, width=8, height=full)

            bar.delete("all")

            top = 4 + first * (full - 8)

            bottom = max(top + 16, 4 + last * (full - 8))

            bar.create_line(
                4, top, 4, bottom, width=5, capstyle="round",
                fill=PURPLE
            )

        self.chat_input.configure(yscrollcommand=draw_thumb)

        def drag(event):

            full = max(20, self.chat_input.winfo_height() - 8)

            first, last = self.chat_input.yview()

            self.chat_input.yview_moveto(
                max(0.0, event.y / full - (last - first) / 2)
            )

        bar.bind("<Button-1>", drag)
        bar.bind("<B1-Motion>", drag)

        def chat_wheel(event):

            # Past three lines the box scrolls instead of the page.
            try:

                if int(self.chat_input.cget("height")) >= 3:

                    first, last = self.chat_input.yview()

                    if first > 0.0 or last < 1.0:

                        self.chat_input.yview_scroll(
                            -1 if event.delta > 0 else 1, "units"
                        )

                        return "break"

            except Exception:
                pass

        self.chat_input.bind("<MouseWheel>", chat_wheel)

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

        # While the grey hint is showing, a click only parks the cursor
        # at the start, and paste/cut start from an empty box.
        self.chat_input.bind(
            "<Button-1>", self._chat_placeholder_click, add="+"
        )
        self.chat_input.bind(
            "<ButtonRelease-1>", self._chat_placeholder_click, add="+"
        )
        self.chat_input.bind(
            "<<Paste>>", self._chat_placeholder_before_edit, add="+"
        )
        self.chat_input.bind(
            "<<Cut>>", self._chat_placeholder_before_edit, add="+"
        )

        # Typing / opens a list of commands (arrows, Tab, Enter, Esc).
        self._slash_menu = None
        self._slash_index = 0
        self._slash_matches = []

        self.chat_input.bind("<Up>", lambda e: self._slash_key(-1))
        self.chat_input.bind("<Down>", lambda e: self._slash_key(1))
        self.chat_input.bind("<Tab>", lambda e: self._slash_key(0))
        self.chat_input.bind("<Escape>", lambda e: self._slash_key(9))
        self.chat_input.bind(
            "<FocusOut>", lambda e: self._hide_slash_menu(), add="+"
        )

        self.chat_input.bind(
            "<FocusOut>", lambda e: self._hide_emoji_menu(), add="+"
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

        self.chat_attach_button = self.make_button(
            input_area,
            "",
            self.pick_chat_files
        )

        self.chat_attach_button.circle = 38
        self.chat_attach_button.plus = True
        self.chat_attach_button._redraw()

        self.chat_attach_button.pack(
            side="left",
            padx=(0, 10),
            before=self.chat_input
        )

        self.chat_attach_bar = tk.Frame(outer, bg=PANEL)

        self._chat_input_area = input_area

        self._refresh_chat_attachments()

        self.chat_input.focus_set()

        self.after(
            50,
            self.scroll_chat
        )

        if self.chat_busy:

            if getattr(self, "_chat_stop_enabled", True):
                self.chat_send_button.configure(text="Stop")

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
        """The app's logo mark, drawn from the same image as the
        window and taskbar icon."""

        if HAS_PIL and size > 2:

            photo = ImageTk.PhotoImage(app_icon_image(size))

            canvas.logo_photo = photo

            canvas.create_image(0, 0, anchor="nw", image=photo)

            return

        canvas.create_rectangle(
            0, 0, size, size,
            fill=PURPLE,
            outline=""
        )

        canvas.create_text(
            size / 2, size / 2,
            text="S",
            font=("Segoe UI", int(size * 0.4), "bold"),
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

        # Made once: creating two Font objects for every bubble was a
        # big part of the delay when the chat page opened.
        fonts = getattr(self, "_bubble_fonts", None)

        if fonts is None:

            fonts = (
                tkfont.Font(family="Segoe UI", size=10),
                tkfont.Font(family="Segoe UI", size=10, weight="bold")
            )

            self._bubble_fonts = fonts

        regular_font, bold_font = fonts

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

        canvas._bubble_bg = bg_color

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
                    fill=(
                        # Your own (purple) bubbles need a lighter
                        # highlight, or it would vanish into them.
                        _theme_mix(PURPLE, TEXT, 0.4)
                        if getattr(canvas, "_bubble_bg", None) == PURPLE
                        else PURPLE
                    ),
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

        paths = []

        if is_user:
            content, paths = self._bubble_attachments(content)

        if paths:

            files_row = tk.Frame(holder, bg=PANEL)

            files_row.pack(anchor="e", pady=(0, 4 if content else 0))

            for path in paths:

                self._chat_attach_tile(
                    files_row, path, size=120, removable=False
                ).pack(side="left", padx=(8, 0))

            if not content:
                return None

        canvas = self.create_bubble_canvas(
            holder,
            content,
            bg_color,
            fg_color
        )

        canvas.pack(anchor="e" if is_user else "w")

        if not is_user and content.strip():
            self._add_copy_label(holder, lambda: content)

        return canvas

    def _copy_icon(self, kind):
        """The copy icon (two sheets) or a tick, drawn anti-aliased.
        kind: normal | hover | done. None without Pillow."""

        if not HAS_PIL:
            return None

        cache = self.__dict__.setdefault("_copy_icons", {})

        if kind in cache:
            return cache[kind]

        colour = {
            "normal": MUTED_2, "hover": TEXT, "done": GREEN
        }[kind]

        size, k = 16, 6

        img = Image.new("RGBA", (size * k, size * k), (0, 0, 0, 0))

        pen = ImageDraw.Draw(img)

        line = int(1.6 * k)

        if kind == "done":

            pen.line(
                [(3 * k, 8.5 * k), (6.5 * k, 12 * k), (13 * k, 4 * k)],
                fill=colour, width=int(2 * k), joint="curve"
            )

        else:

            pen.rounded_rectangle(
                (5 * k, 1.5 * k, 14.5 * k, 11 * k),
                radius=2 * k, outline=colour, width=line
            )

            pen.rounded_rectangle(
                (1.5 * k, 5 * k, 11 * k, 14.5 * k),
                radius=2 * k, outline=colour, width=line, fill=PANEL
            )

        photo = ImageTk.PhotoImage(
            img.resize((size, size), Image.LANCZOS)
        )

        cache[kind] = photo

        return photo

    def _add_copy_label(self, holder, get_text):
        """A small copy icon under an AI message."""

        label = tk.Label(
            holder, bg=PANEL, fg=MUTED_2,
            font=("Segoe UI", 9), cursor="hand2", bd=0
        )

        def show(kind):

            icon = self._copy_icon(kind)

            if icon is not None:
                label.configure(image=icon, text="")
                label.image = icon
            else:
                label.configure(
                    image="",
                    text={"normal": "Copy", "hover": "Copy",
                          "done": "Copied"}[kind],
                    fg={"normal": MUTED_2, "hover": TEXT,
                        "done": GREEN}[kind]
                )

            label.kind = kind

        show("normal")

        label.pack(anchor="w", pady=(3, 0))

        def reset():

            try:
                if label.winfo_exists():
                    show("normal")
            except Exception:
                pass

        def copy(event=None):

            try:
                self.clipboard_clear()
                self.clipboard_append(get_text())
            except Exception:
                return

            show("done")

            label.after(1500, reset)

        def enter(event=None):

            if label.kind == "normal":
                show("hover")

        def leave(event=None):

            if label.kind == "hover":
                show("normal")

        label.bind("<Button-1>", copy)
        label.bind("<Enter>", enter)
        label.bind("<Leave>", leave)

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

    def _bind_word_delete(self, text_widget):
        """Ctrl+Backspace deletes the word before the cursor and
        Ctrl+Delete the word after it, like in any Windows editor."""

        def delete_word_backward(event):

            try:

                selected = text_widget.tag_ranges("sel")

                if selected:
                    text_widget.delete(selected[0], selected[1])
                    return "break"

                line, col = map(int, text_widget.index("insert").split("."))

                if col == 0:

                    text_widget.delete("insert -1c", "insert")

                    return "break"

                before = text_widget.get(f"{line}.0", "insert")

                match = re.search(r"(\w+|[^\w\s]+)\s*$|\s+$", before)

                start = match.start() if match else col - 1

                text_widget.delete(f"{line}.{start}", "insert")

            except tk.TclError:
                pass

            return "break"

        def delete_word_forward(event):

            try:

                selected = text_widget.tag_ranges("sel")

                if selected:
                    text_widget.delete(selected[0], selected[1])
                    return "break"

                line, col = map(int, text_widget.index("insert").split("."))

                after = text_widget.get("insert", f"{line}.end")

                if not after:

                    text_widget.delete("insert", "insert +1c")

                    return "break"

                match = re.match(r"\s*(\w+|[^\w\s]+)|\s+", after)

                end = match.end() if match else 1

                text_widget.delete("insert", f"{line}.{col + end}")

            except tk.TclError:
                pass

            return "break"

        text_widget.bind("<Control-BackSpace>", delete_word_backward)
        text_widget.bind("<Control-Delete>", delete_word_forward)

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

        self._bind_word_delete(text_widget)

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

    # --------------------------------------------------------
    # Chat input placeholder + autosize
    # --------------------------------------------------------

    CHAT_PLACEHOLDER_TEXT = "Message Studestics AI...  (try /notes topic)"

    CHAT_PLACEHOLDER_IGNORE_KEYS = {
        "Shift_L", "Shift_R", "Control_L", "Control_R",
        "Alt_L", "Alt_R", "Caps_Lock", "Tab", "Escape",
        "Left", "Right", "Up", "Down", "Home", "End",
        "Prior", "Next"
    }

    def _save_chat_draft(self):
        """Keep what was typed in the message box when leaving AI Chat."""

        try:

            if self.chat_placeholder_active:
                draft = ""
            else:
                draft = self._chat_input_string()

            self._chat_draft = draft

            self.db.set_setting("chat_draft", draft)

        except Exception:
            pass

    def _restore_chat_draft(self):

        try:

            draft = getattr(self, "_chat_draft", None)

            if draft is None:
                draft = self.db.get_setting("chat_draft", "") or ""

            if not draft:
                return

            self.clear_chat_placeholder()

            for part, is_emoji in emoji_segments(draft):

                if is_emoji:
                    self._put_emoji_image(part)
                elif part:
                    self.chat_input.insert("insert", part)

            self.chat_input.mark_set("insert", "end-1c")

            self.chat_input.edit_reset()

            self.autosize_chat_input()

        except Exception:
            pass

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

        # Count wrapped lines as they look, not just Enter presses.
        try:

            self.chat_input.update_idletasks()

            counted = self.chat_input.count(
                "1.0", "end-1c", "displaylines"
            )

            # "count" gives the number of line breaks between the two
            # points, so a one-line box reports 0.
            display_lines = 1 + int(
                counted[0] if isinstance(counted, (tuple, list))
                else (counted or 0)
            )

        except Exception:

            display_lines = int(
                self.chat_input.index("end-1c").split(".")[0]
            )

        new_height = min(
            max(display_lines, 1),
            3
        )

        if int(self.chat_input.cget("height")) != new_height:

            self.chat_input.configure(
                height=new_height
            )

        # Keep the line being typed in view once the box has to scroll.
        try:

            self.chat_input.update_idletasks()

            self.chat_input.see("insert")

        except Exception:
            pass

    def _chat_placeholder_click(self, event=None):

        if self.chat_placeholder_active:

            def park():
                if self.chat_placeholder_active:
                    self.chat_input.tag_remove("sel", "1.0", "end")
                    self.chat_input.mark_set("insert", "1.0")

            self.chat_input.after_idle(park)

    def _chat_placeholder_before_edit(self, event=None):

        self.clear_chat_placeholder()

    def _fix_placeholder_edit(self):
        """Safety net: if the hint text got edited some other way
        (partly deleted, or text pasted into it), drop the hint so the
        box holds only what the person typed."""

        if not self.chat_placeholder_active:
            return

        cur = self.chat_input.get("1.0", "end-1c")
        hint = self.CHAT_PLACEHOLDER_TEXT

        if cur == hint:
            return

        if cur in hint:
            new = ""
        elif cur.startswith(hint):
            new = cur[len(hint):]
        elif cur.endswith(hint):
            new = cur[:-len(hint)]
        else:
            new = cur

        self.chat_input.delete("1.0", "end")
        self.chat_input.insert("1.0", new)
        self.chat_input.mark_set("insert", "end-1c")
        self.chat_input.configure(fg=TEXT)
        self.chat_placeholder_active = False
        self.chat_input.edit_reset()

    SLASH_COMMANDS = [
        (
            "/notes", "topic",
            "Write study notes into your Notes tab "
            "(adds to your old notes)"
        ),
        (
            "/newnotes", "topic",
            "Write new notes and replace your old notes"
        ),
        (
            "/quiz", "topic or file",
            "Quiz yourself on a topic, or on a file you attached"
        ),
        (
            "/schedule", "what to plan or change",
            "Let the AI add, change or delete Schedule blocks"
        )
    ]

    def _slash_visible(self):

        menu = getattr(self, "_slash_menu", None)

        try:
            return bool(
                menu is not None
                and menu.winfo_exists()
                and menu.winfo_ismapped()
            )
        except Exception:
            return False

    def _hide_slash_menu(self):

        menu = getattr(self, "_slash_menu", None)

        if menu is not None:
            try:
                menu.place_forget()
            except Exception:
                pass

    # ---- emoji in other multi-line boxes (Notes, descriptions) -----

    def emoji_attach(self, w):
        """Give a Text box the :name: menu and real colour emoji. Read
        it back with emoji_read and fill it with emoji_write."""

        w._emoji_photos = {}
        w._emoji_chars = {}

        w.bind(
            "<KeyRelease>",
            lambda e: self._emoji_typed(w, e), add="+"
        )

        w.bind("<FocusOut>", lambda e: self._hide_emoji_menu(), add="+")

        def mine():

            return self._emoji_visible() and self._emoji_w is w

        for key, code in (
            ("<Up>", -1), ("<Down>", 1), ("<Tab>", 0), ("<Escape>", 9),
            ("<Return>", 0)
        ):

            w.bind(
                key,
                lambda e, c=code: self._emoji_key(c) if mine() else None
            )

    def _emoji_typed(self, w, event):

        if event.keysym in (
            "Up", "Down", "Tab", "Escape", "Return", "Shift_L",
            "Shift_R", "Control_L", "Control_R"
        ):
            return

        try:
            self._update_emoji_menu(w)
        except Exception:
            pass

    def _emoji_insert(self, w, char):

        if w is getattr(self, "chat_input", None):
            self._put_emoji_image(char)
            return

        pil = emoji_image(char, 20)

        if pil is None:
            w.insert("insert", char)
            return

        photo = ImageTk.PhotoImage(pil)

        name = w.image_create("insert", image=photo, padx=1)

        w._emoji_photos[name] = photo
        w._emoji_chars[name] = char

    def emoji_read(self, w, start="1.0", end="end-1c"):
        """The box's text with each emoji image turned back into its
        real character."""

        try:
            items = w.dump(start, end, text=True, image=True)
        except Exception:
            return w.get(start, end)

        out = []

        for kind, value, _index in items:

            if kind == "text":

                try:
                    value = value.encode(
                        "utf-16", "surrogatepass"
                    ).decode("utf-16", "replace")
                except Exception:
                    pass

                out.append(value)

            elif kind == "image":

                out.append(getattr(w, "_emoji_chars", {}).get(value, ""))

        return "".join(out)

    def emoji_write(self, w, text, index="1.0"):
        """Insert text, drawing any emoji in it as images."""

        w.mark_set("_emoji_at", index)

        w.mark_gravity("_emoji_at", "right")

        for part, is_emoji in emoji_segments(text):

            if is_emoji:

                keep = w.index("insert")

                w.mark_set("insert", "_emoji_at")

                self._emoji_insert(w, part)

                w.mark_set("_emoji_at", "insert")

                w.mark_set("insert", keep)

            elif part:

                w.insert("_emoji_at", part)

    # ---- :name: emoji suggestions (AI Chat) --------------------

    def _emoji_visible(self):

        menu = getattr(self, "_emoji_menu", None)

        try:
            return bool(
                menu is not None
                and menu.winfo_exists()
                and menu.winfo_ismapped()
            )
        except Exception:
            return False

    def _hide_emoji_menu(self):

        menu = getattr(self, "_emoji_menu", None)

        if menu is not None:
            try:
                menu.place_forget()
            except Exception:
                pass

    def _update_emoji_menu(self, w=None):
        """Typing :yu shows matching emoji (closest first); typing the
        closing colon of a known name, like :yum:, swaps it for the
        emoji straight away."""

        w = w or getattr(self, "chat_input", None)

        self._emoji_w = w

        if w is getattr(self, "chat_input", None) and getattr(
                self, "chat_placeholder_active", False
        ):
            self._hide_emoji_menu()
            return

        before = w.get("1.0", "insert")

        done = re.search(r"(?:^|\s):([A-Za-z0-9_+\-]+):$", before)

        if done and done.group(1).lower() in EMOJI_SHORTCODES:

            name = done.group(1)

            start = w.search(
                ":" + name + ":", "insert", "1.0",
                backwards=True, nocase=True
            )

            if start:

                w.delete(start, "insert")

                self._emoji_insert(w, EMOJI_SHORTCODES[name.lower()])

                self._hide_emoji_menu()

                return

        typing = re.search(r"(?:^|\s):([A-Za-z0-9_+\-]{1,})$", before)

        names = emoji_matches(typing.group(1)) if typing else []

        if not names:
            self._hide_emoji_menu()
            return

        if (
            names != getattr(self, "_emoji_names", [])
            or not self._emoji_visible()
        ):
            self._emoji_index = 0

        self._emoji_names = names

        self._emoji_query = typing.group(1)

        self._draw_emoji_menu()

    def _draw_emoji_menu(self):

        menu = getattr(self, "_emoji_menu", None)

        try:
            alive = menu is not None and menu.winfo_exists()
            # The menu has to live in the same window as the box it
            # belongs to (a dialog is its own window).
            if alive and menu.winfo_toplevel() is not (
                self._emoji_w.winfo_toplevel()
            ):
                menu.destroy()
                alive = False
        except Exception:
            alive = False

        if not alive:
            menu = tk.Frame(
                self._emoji_w.winfo_toplevel(),
                bg=PANEL_2,
                highlightthickness=1,
                highlightbackground=BORDER
            )

            self._emoji_menu = menu

        for child in menu.winfo_children():
            child.destroy()

        self._emoji_rows = []

        self._emoji_menu_photos = []

        for i, name in enumerate(self._emoji_names):

            char = EMOJI_SHORTCODES[name]

            row = tk.Frame(menu, bg=PANEL_2, cursor="hand2")

            row.pack(fill="x")

            parts = [row]

            pil = emoji_image(char, 22)

            if pil is not None:

                photo = ImageTk.PhotoImage(pil)

                self._emoji_menu_photos.append(photo)

                icon = tk.Label(row, image=photo, bg=PANEL_2)

            else:

                icon = tk.Label(
                    row, text=char, bg=PANEL_2, fg=TEXT,
                    font=("Segoe UI", 12)
                )

            icon.pack(side="left", padx=(12, 8), pady=5)

            label = tk.Label(
                row, text=f":{name}:", bg=PANEL_2, fg=TEXT,
                font=("Segoe UI", 10)
            )

            label.pack(side="left", pady=5)

            parts += [icon, label]

            self._emoji_rows.append(parts)

            for part in parts:

                part.bind(
                    "<Button-1>", lambda e, n=i: self._emoji_pick(n)
                )

                part.bind(
                    "<Enter>", lambda e, n=i: self._emoji_hover(n)
                )

        self._paint_emoji_rows()

        w = self._emoji_w

        if w is getattr(self, "chat_input", None):

            # Above the box, lined up with the colon (not stuck at the
            # far left while you type at the end of a long line).
            width = max(260, min(w.winfo_width(), 340))

            # Pinned to the colon that started the shortcode, so it
            # stays put while the letters after it are typed.
            try:

                begin = w.search(
                    ":" + getattr(self, "_emoji_query", ""), "insert",
                    "1.0", backwards=True, nocase=True
                )

                box = w.bbox(begin) if begin else None

            except Exception:
                box = None

            x = (box[0] - 10) if box else 0

            x = max(0, min(x, w.winfo_width() - width))

            menu.place(in_=w, x=x, y=-8, anchor="sw", width=width)

        else:

            menu.update_idletasks()

            box = w.bbox("insert") or (10, 10, 0, 18)

            height = menu.winfo_reqheight()

            x = max(0, min(box[0], max(0, w.winfo_width() - 300)))

            y = box[1] + box[3] + 4
            if int(w.cget("height")) == 1:
                y = w.winfo_height() + 4
            elif y + height > w.winfo_height():
                y = max(0, box[1] - height - 4)

            menu.place(in_=w, x=x, y=y, anchor="nw", width=280)

        menu.lift()

    def _paint_emoji_rows(self):

        for i, parts in enumerate(getattr(self, "_emoji_rows", [])):

            color = BORDER if i == self._emoji_index else PANEL_2

            for part in parts:
                try:
                    part.configure(bg=color)
                except Exception:
                    pass

    def _emoji_hover(self, index):

        if index != self._emoji_index:
            self._emoji_index = index
            self._paint_emoji_rows()

    def _emoji_pick(self, index=None):

        names = getattr(self, "_emoji_names", [])

        if not names:
            return

        if index is None:
            index = self._emoji_index

        name = names[min(index, len(names) - 1)]

        query = getattr(self, "_emoji_query", "")

        self._hide_emoji_menu()

        w = getattr(self, "_emoji_w", None)

        start = w.search(
            ":" + query, "insert", "1.0", backwards=True, nocase=True
        )

        if start:
            w.delete(start, "insert")

        self._emoji_insert(w, EMOJI_SHORTCODES[name])

        w.focus_set()

        if w is getattr(self, "chat_input", None):
            self.autosize_chat_input()

    def _emoji_key(self, code):

        count = len(self._emoji_names)

        if code in (-1, 1):
            self._emoji_index = (self._emoji_index + code) % count
            self._paint_emoji_rows()
        elif code == 0:
            self._emoji_pick()
        else:
            self._hide_emoji_menu()

        return "break"

    def _update_slash_menu(self):

        if self.chat_placeholder_active:
            text = ""
        else:
            text = self.chat_input.get("1.0", "end-1c")

        matches = []

        if text.startswith("/") and not any(c.isspace() for c in text):
            matches = [
                c for c in self.SLASH_COMMANDS
                if c[0].startswith(text.lower())
            ]

        if not matches:
            self._hide_slash_menu()
            return

        if (
            matches != self._slash_matches
            or not self._slash_visible()
        ):
            self._slash_index = 0

        self._slash_matches = matches

        self._draw_slash_menu()

    def _draw_slash_menu(self):

        menu = self._slash_menu

        try:
            alive = menu is not None and menu.winfo_exists()
        except Exception:
            alive = False

        if not alive:

            menu = tk.Frame(
                self.chat_input.master.master,
                bg=PANEL_2,
                highlightthickness=1,
                highlightbackground=BORDER
            )

            self._slash_menu = menu

        for child in menu.winfo_children():
            child.destroy()

        self._slash_rows = []

        for i, (cmd, arg, desc) in enumerate(self._slash_matches):

            row = tk.Frame(menu, bg=PANEL_2, cursor="hand2")

            row.pack(fill="x")

            top = tk.Frame(row, bg=PANEL_2)

            top.pack(fill="x", padx=12, pady=(7, 0))

            name = tk.Label(
                top, text=cmd, bg=PANEL_2, fg=TEXT,
                font=("Segoe UI", 10, "bold")
            )

            name.pack(side="left")

            hint = tk.Label(
                top, text=arg, bg=PANEL_2, fg=MUTED_2,
                font=("Segoe UI", 9, "italic")
            )

            hint.pack(side="left", padx=(8, 0))

            info = tk.Label(
                row, text=desc, bg=PANEL_2, fg=MUTED_2,
                font=("Segoe UI", 9), anchor="w", justify="left"
            )

            info.pack(fill="x", padx=12, pady=(0, 7))

            parts = [row, top, name, hint, info]

            self._slash_rows.append(parts)

            for part in parts:

                part.bind(
                    "<Button-1>",
                    lambda e, n=i: self._slash_pick(n)
                )

                part.bind(
                    "<Enter>",
                    lambda e, n=i: self._slash_hover(n)
                )

        self._paint_slash_rows()

        width = max(320, min(self.chat_input.winfo_width(), 540))

        menu.place(
            in_=self.chat_input,
            x=0,
            y=-8,
            anchor="sw",
            width=width
        )

        menu.lift()

    def _paint_slash_rows(self):

        for i, parts in enumerate(getattr(self, "_slash_rows", [])):

            color = BORDER if i == self._slash_index else PANEL_2

            for part in parts:
                try:
                    part.configure(bg=color)
                except Exception:
                    pass

    def _slash_hover(self, index):

        if index != self._slash_index:
            self._slash_index = index
            self._paint_slash_rows()

    def _slash_pick(self, index=None):

        if index is None:
            index = self._slash_index

        if not self._slash_matches:
            return

        command = self._slash_matches[
            min(index, len(self._slash_matches) - 1)
        ][0]

        self._hide_slash_menu()

        self.clear_chat_placeholder()

        self.chat_input.delete("1.0", "end")
        self.chat_input.insert("1.0", command + " ")
        self.chat_input.mark_set("insert", "end-1c")
        self.chat_input.focus_set()

    def _slash_key(self, code):

        if self._emoji_visible():
            return self._emoji_key(code)

        if not self._slash_visible():
            return None

        count = len(self._slash_matches)

        if code in (-1, 1):
            self._slash_index = (self._slash_index + code) % count
            self._paint_slash_rows()
        elif code == 0:
            self._slash_pick()
        else:
            self._hide_slash_menu()

        return "break"

    def on_chat_input_changed(self, event=None):

        self._fix_placeholder_edit()

        try:
            self._update_emoji_menu()
        except Exception:
            pass

        try:
            self._update_slash_menu()
        except Exception:
            pass

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

        if self._emoji_visible():
            self._emoji_pick()
            return "break"

        if self._slash_visible():
            self._slash_pick()
            return "break"

        if self.chat_busy:
            return "break"

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
            "STUDENT CONTEXT (background only. Do not mention their "
            "tasks or goals unless they ask about them or it is "
            "directly relevant to what they asked.)\n\n"
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

    # Types Gemini reads directly (photos, PDF, audio, video).
    CHAT_IMAGE_TYPES = {
        ".png": "image/png", ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg", ".webp": "image/webp",
        ".gif": "image/gif", ".heic": "image/heic",
        ".heif": "image/heif", ".pdf": "application/pdf",
        ".mp3": "audio/mp3", ".wav": "audio/wav",
        ".aac": "audio/aac", ".flac": "audio/flac",
        ".ogg": "audio/ogg",
        ".mp4": "video/mp4", ".mov": "video/quicktime",
        ".avi": "video/x-msvideo", ".webm": "video/webm",
        ".mpeg": "video/mpeg", ".mpg": "video/mpeg",
        ".wmv": "video/x-ms-wmv", ".flv": "video/x-flv",
        ".3gp": "video/3gpp"
    }

    # Pictures that get a thumbnail.
    CHAT_PHOTO_EXTS = (
        ".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp",
        ".tif", ".tiff", ".ico", ".heic", ".heif"
    )

    CHAT_TEXT_TYPES = (
        ".txt", ".md", ".csv", ".json", ".py", ".js", ".html",
        ".css", ".c", ".cpp", ".java", ".log", ".xml", ".yaml", ".yml"
    )

    CHAT_MAX_FILES = 5
    CHAT_MAX_FILE_MB = 15

    def pick_chat_files(self):

        if self.chat_busy:
            return

        paths = filedialog.askopenfilenames(
            parent=self,
            title="Attach files or photos",
            filetypes=[("All files", "*.*")]
        )

        if not paths:
            return

        current = getattr(self, "chat_attachments", [])

        for path in paths:

            ext = Path(path).suffix.lower()

            try:
                too_big = (
                    os.path.getsize(path)
                    > self.CHAT_MAX_FILE_MB * 1024 * 1024
                )
            except OSError:
                too_big = False

            if too_big:
                messagebox.showinfo(
                    "Attach",
                    f"{Path(path).name} is over "
                    f"{self.CHAT_MAX_FILE_MB} MB.",
                    parent=self
                )
                continue

            if path in current:
                continue

            if len(current) >= self.CHAT_MAX_FILES:
                messagebox.showinfo(
                    "Attach",
                    f"You can attach up to {self.CHAT_MAX_FILES} "
                    "files to one message.",
                    parent=self
                )
                break

            current.append(path)

        self.chat_attachments = current

        self._refresh_chat_attachments()

    def _refresh_chat_attachments(self):
        """Shows the attached files as small chips above the box."""

        bar = getattr(self, "chat_attach_bar", None)

        if bar is None:
            return

        try:

            for child in bar.winfo_children():
                child.destroy()

            files = getattr(self, "chat_attachments", [])

            if not files:
                bar.pack_forget()
                return

            for path in files:

                tile = self._chat_attach_tile(bar, path)

                tile.pack(side="left", padx=(0, 10))

            if not bar.winfo_ismapped():

                bar.pack(
                    fill="x", padx=15, pady=(10, 0),
                    before=self._chat_input_area
                )

        except Exception:
            pass

    def _chat_attach_tile(self, parent, path, size=76, removable=True):
        """One attached file: a rounded photo thumbnail (or a file
        card for PDFs and text) with a small x to remove it."""

        box = tk.Frame(parent, bg=PANEL)

        name = Path(path).name
        ext = Path(path).suffix.lower()

        cache = self.__dict__.setdefault("_chat_thumb_cache", {})

        photo = cache.get((path, size))

        if photo is None and HAS_PIL:

            try:

                from PIL import ImageOps

                if ext in self.CHAT_PHOTO_EXTS:

                    base = Image.open(path)

                    base = ImageOps.exif_transpose(base).convert("RGB")

                    base = ImageOps.fit(
                        base, (size, size), Image.LANCZOS
                    )

                else:

                    base = Image.new("RGB", (size, size), PANEL_2)

                mask = Image.new("L", (size * 4, size * 4), 0)

                ImageDraw.Draw(mask).rounded_rectangle(
                    [0, 0, size * 4 - 1, size * 4 - 1],
                    radius=int(size * 0.18) * 4,
                    fill=255
                )

                mask = mask.resize((size, size), Image.LANCZOS)

                out = Image.new("RGB", (size, size), PANEL)

                out.paste(base, mask=mask)

                photo = ImageTk.PhotoImage(out)

                cache[(path, size)] = photo

            except Exception:
                photo = None

        is_photo = ext in self.CHAT_PHOTO_EXTS

        if photo is not None and is_photo:

            tk.Label(
                box, image=photo, bg=PANEL, bd=0
            ).pack()

        else:

            label = name if len(name) <= 11 else name[:9] + ".."

            tk.Label(
                box,
                image=photo if photo is not None else "",
                text=(ext.lstrip(".").upper() or "FILE") + "\n" + label,
                compound="center",
                bg=PANEL_2 if photo is None else PANEL,
                fg=TEXT,
                font=("Segoe UI", 9, "bold"),
                width=9 if photo is None else 0,
                height=4 if photo is None else 0,
                bd=0
            ).pack()

        if removable:

            badge = tk.Label(
                box, text="×", bg=BG, fg=TEXT,
                font=("Segoe UI", 10, "bold"), padx=5,
                cursor="hand2"
            )

            badge.place(relx=1.0, x=-4, y=4, anchor="ne")

            badge.bind(
                "<Button-1>",
                lambda e, p=path: self._remove_chat_attachment(p)
            )

        return box

    _FILES_TRAILER = re.compile(r"\n*\[\[files:(.*?)\]\]\s*$", re.S)
    _ATTACH_NOTE = re.compile(r"\n*\(Attached: [^\n]*\)\s*$")
    _ATTACH_DEFAULT = "Please look at the attached file(s)."

    def _strip_file_trailer(self, content):
        """Removes the hidden list of attached file paths."""

        return self._FILES_TRAILER.sub("", content or "").strip()

    def _bubble_attachments(self, content):
        """(text to show, attached file paths) for a user message."""

        paths = []

        match = self._FILES_TRAILER.search(content or "")

        if match:
            paths = [p for p in match.group(1).split("|") if p]

        text = self._strip_file_trailer(content)

        if paths:

            text = self._ATTACH_NOTE.sub("", text).strip()

            if text == self._ATTACH_DEFAULT:
                text = ""

        return text, paths

    def _remove_chat_attachment(self, path):

        files = getattr(self, "chat_attachments", [])

        if path in files:
            files.remove(path)

        self._refresh_chat_attachments()

    def _chat_attachment_parts(self, paths):
        """Reads the attached files into Gemini parts."""

        from google.genai import types

        parts = []

        for path in paths:

            name = Path(path).name
            ext = Path(path).suffix.lower()

            try:

                if ext in self.CHAT_IMAGE_TYPES:

                    with open(path, "rb") as handle:
                        data = handle.read()

                    parts.append(types.Part.from_bytes(
                        data=data,
                        mime_type=self.CHAT_IMAGE_TYPES[ext]
                    ))

                elif ext in (".bmp", ".tif", ".tiff", ".ico"):

                    import io

                    buffer = io.BytesIO()

                    Image.open(path).convert("RGB").save(buffer, "PNG")

                    parts.append(types.Part.from_bytes(
                        data=buffer.getvalue(),
                        mime_type="image/png"
                    ))

                elif ext in (".docx", ".pptx", ".xlsx"):

                    parts.append(types.Part(
                        text=(
                            f"[Attached file: {name}]\n"
                            + office_file_text(path)[:300000]
                        )
                    ))

                else:

                    with open(path, "rb") as handle:
                        raw = handle.read(300000)

                    if b"\x00" in raw[:4096]:
                        raise RuntimeError(
                            "this type of file can't be read yet "
                            "(photos, PDFs, audio, video, Word, "
                            "PowerPoint, Excel and text files work)"
                        )

                    parts.append(types.Part(
                        text=(
                            f"[Attached file: {name}]\n"
                            + raw.decode("utf-8", "replace")
                        )
                    ))

            except Exception as exc:

                raise RuntimeError(
                    f"Couldn't read {name}: {exc}"
                )

        return parts

    def send_chat(self):

        if self.chat_busy:

            # While a reply is streaming the button reads "Stop".
            self._chat_stop = True

            return

        if not self.get_gemini_key():

            messagebox.showwarning(
                "Gemini",
                "Add your Gemini API key in Settings first.",
                parent=self
            )

            return

        text = self.get_chat_input_text()

        attachments = list(getattr(self, "chat_attachments", []))

        if not text and attachments:
            text = "Please look at the attached file(s)."

        if not text:
            return

        self.chat_input.delete(
            "1.0",
            "end"
        )

        self.show_chat_placeholder()

        if attachments:

            self.chat_attachments = []

            self._refresh_chat_attachments()

            text += "\n\n(Attached: " + ", ".join(
                Path(p).name for p in attachments
            ) + ")\n[[files:" + "|".join(attachments) + "]]"

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

        self._chat_stop = False

        if text.lower().startswith((
            "/notes", "/newnotes", "/quiz", "/schedule"
        )):

            self.chat_send_button.configure(
                state="disabled"
            )

        else:

            self.chat_send_button.configure(
                text="Stop",
                state="normal"
            )

        self.start_typing_animation()

        self._first_token_s = None

        def slow_hint():

            try:

                if self.chat_busy and self.stream_canvas is None:

                    self.chat_status.configure(
                        text="Gemini is slow right now…",
                        fg=YELLOW
                    )

            except Exception:
                pass

        self.after(10000, slow_hint)

        threading.Thread(
            target=self.ai_worker,
            args=(text, attachments),
            daemon=True
        ).start()

    def _gemini_client(self):
        """One Gemini client, made once and reused, so a message
        doesn't pay for the import and a fresh connection each time."""

        key = self.get_gemini_key()

        if not key:
            raise RuntimeError("Gemini API key is missing.")

        cached = getattr(self, "_gemini_client_obj", None)

        if cached and cached[0] == key:
            return cached[1]

        from google import genai

        client = genai.Client(
            api_key=key,
            http_options={
                "timeout": 12000
            }
        )

        self._gemini_client_obj = (key, client)

        return client

    def _install_text_shortcuts(self):
        """Standard editing shortcuts for every text box in the app
        (Tk lacks Ctrl+Backspace / Ctrl+Delete and maps Ctrl+A to
        'start of line'): Ctrl+Backspace, Ctrl+Delete, Ctrl+A."""

        def usable(w):

            try:
                return str(w.cget("state")) not in ("disabled", "readonly")
            except Exception:
                return True

        def is_text(w):
            return isinstance(w, tk.Text)

        def before(w):

            if is_text(w):
                return w.get("1.0", "insert")

            return w.get()[:int(w.index("insert"))]

        def after(w):

            if is_text(w):
                return w.get("insert", "end-1c")

            return w.get()[int(w.index("insert")):]

        def remove_selection(w):

            try:

                if is_text(w):

                    if w.tag_ranges("sel"):
                        w.delete("sel.first", "sel.last")
                        return True

                elif w.selection_present():
                    w.delete("sel.first", "sel.last")
                    return True

            except Exception:
                pass

            return False

        def word_back(event):

            w = event.widget

            if not usable(w):
                return "break"

            if remove_selection(w):
                return "break"

            text = before(w)

            i = len(text)

            while i > 0 and text[i - 1].isspace():
                i -= 1

            while i > 0 and not text[i - 1].isspace():
                i -= 1

            count = len(text) - i

            if count:

                if is_text(w):
                    w.delete(f"insert-{count}c", "insert")
                else:
                    pos = int(w.index("insert"))
                    w.delete(pos - count, pos)

            return "break"

        def word_forward(event):

            w = event.widget

            if not usable(w):
                return "break"

            if remove_selection(w):
                return "break"

            text = after(w)

            i = 0

            while i < len(text) and not text[i].isspace():
                i += 1

            while i < len(text) and text[i].isspace():
                i += 1

            if i:

                if is_text(w):
                    w.delete("insert", f"insert+{i}c")
                else:
                    pos = int(w.index("insert"))
                    w.delete(pos, pos + i)

            return "break"

        def select_all(event):

            w = event.widget

            try:

                if is_text(w):

                    w.tag_add("sel", "1.0", "end-1c")
                    w.mark_set("insert", "end-1c")

                else:

                    w.select_range(0, "end")
                    w.icursor("end")

            except Exception:
                pass

            return "break"

        # ---- undo / redo -------------------------------------------
        # Text boxes get Tk's own undo stack the first time they are
        # focused; single-line boxes (which have none) get a small
        # history of their own, grouped so one burst of typing is one
        # step.

        def history(w):

            state = getattr(w, "_undo_state", None)

            if state is None:

                state = w._undo_state = {
                    "steps": [w.get()], "at": 0, "when": 0.0
                }

            return state

        def on_focus(event):

            w = event.widget

            try:

                if is_text(w):

                    if not int(w.cget("undo")):

                        w.configure(
                            undo=True, autoseparators=True, maxundo=-1
                        )

                else:
                    history(w)

            except Exception:
                pass

        def on_key_release(event):

            w = event.widget

            if is_text(w):
                return

            try:

                state = history(w)

                current = w.get()

                if current == state["steps"][state["at"]]:
                    return

                now = time.time()

                del state["steps"][state["at"] + 1:]

                if now - state["when"] < 0.8 and state["at"] > 0:
                    state["steps"][state["at"]] = current

                else:

                    state["steps"].append(current)

                    state["at"] += 1

                    if len(state["steps"]) > 300:

                        del state["steps"][0]

                        state["at"] -= 1

                state["when"] = now

            except Exception:
                pass

        def restore(w, state):

            w.delete(0, "end")
            w.insert(0, state["steps"][state["at"]])
            w.icursor("end")

            state["when"] = 0.0

        def undo(event):

            w = event.widget

            try:

                if is_text(w):

                    if not int(w.cget("undo")):
                        return "break"

                    w.edit_undo()

                else:

                    state = history(w)

                    if state["at"] > 0:

                        state["at"] -= 1

                        restore(w, state)

            except Exception:
                pass

            return "break"

        def redo(event):

            w = event.widget

            try:

                if is_text(w):

                    if not int(w.cget("undo")):
                        return "break"

                    w.edit_redo()

                else:

                    state = history(w)

                    if state["at"] < len(state["steps"]) - 1:

                        state["at"] += 1

                        restore(w, state)

            except Exception:
                pass

            return "break"

        for cls in ("Entry", "TEntry", "Text"):

            self.bind_class(cls, "<FocusIn>", on_focus, add="+")
            self.bind_class(cls, "<KeyRelease>", on_key_release, add="+")
            self.bind_class(cls, "<Control-z>", undo)
            self.bind_class(cls, "<Control-Z>", redo)
            self.bind_class(cls, "<Control-y>", redo)
            self.bind_class(cls, "<Control-Y>", redo)

            self.bind_class(cls, "<Control-BackSpace>", word_back)
            self.bind_class(cls, "<Control-Delete>", word_forward)
            self.bind_class(cls, "<Control-a>", select_all)
            self.bind_class(cls, "<Control-A>", select_all)

    def _warm_gemini(self):
        """Load Gemini in the background when the chat page opens, so
        the first message doesn't wait for it."""

        if getattr(self, "_gemini_warm", False):
            return

        if not self.get_gemini_key():
            return

        self._gemini_warm = True

        def work():

            try:

                self._gemini_client()

                # Build the request types now, so the first message
                # doesn't pay for (or trip over) it.
                from google.genai import types

                types.GenerateContentConfig(max_output_tokens=16)

                types.Content(
                    role="user",
                    parts=[types.Part(text="hi")]
                )

            except Exception:
                self._gemini_warm = False

        threading.Thread(target=work, daemon=True).start()

    def _ai_fast_path(
        self, client, user_text, started_at, setup_s, extra_parts=None
    ):
        """Answer through the standard streaming call. It starts
        sending words much sooner than the Interactions call, which
        waited 13-16 s before the first word. Returns True when it
        answered; False means "use the older path instead" (an SDK
        without this call, or anything unexpected before the first
        word). Real errors after words have arrived are raised."""

        if time.time() < getattr(self, "_fast_path_off_until", 0):
            return False

        try:

            from google.genai import types

            models = client.models

            stream_call = models.generate_content_stream

            # The recent chat, kept short so every request stays small.
            turns = []

            for row in self.db.get_messages()[-12:]:

                content = self._strip_file_trailer(row["content"] or "")

                if not content:
                    continue

                if content.startswith((
                    "Gemini error", "Gemini timed out", "(Interrupted)"
                )):
                    continue

                role = "user" if row["role"] == "user" else "model"

                turns.append((role, content[:1500]))

            # The model needs the conversation to start with the student.
            while turns and turns[0][0] != "user":
                turns.pop(0)

            if not turns or turns[-1][0] != "user":
                turns.append(("user", user_text))

            # Merge neighbours with the same role (an error message in
            # between was left out above).
            merged = []

            for role, text in turns:

                if merged and merged[-1][0] == role:
                    merged[-1] = (role, merged[-1][1] + "\n" + text)
                else:
                    merged.append((role, text))

            turns = merged

            contents = [
                types.Content(
                    role=role,
                    parts=[types.Part(text=text)]
                )
                for role, text in turns
            ]

            config = types.GenerateContentConfig(
                system_instruction=(
                    "You are Studestics AI, a friendly study and "
                    "productivity assistant. Be helpful, practical, "
                    "concise and encouraging. Help the student "
                    "understand topics, plan work, organize tasks and "
                    "study. Do not use emoji — the display environment "
                    "cannot render most of them. "
                    "There is no length limit on your replies. If the "
                    "student asks for a long or detailed answer, write "
                    "all of it in ONE reply. Never split an answer "
                    "into parts and never ask the student to say when "
                    "to continue.\n\n"
                    + self.get_ai_context()
                ),
                max_output_tokens=AI_MAX_OUTPUT_TOKENS
            )

        except Exception:

            # This SDK can't do it at all: don't try again.
            self._fast_path_off_until = float("inf")

            return False

        if extra_parts:
            contents[-1].parts.extend(extra_parts)

        full_text = ""
        used_model = None
        bubble_started = False
        last_update = 0.0

        for model_name in self._gemini_model_candidates():

            try:

                for chunk in stream_call(
                    model=model_name,
                    contents=contents,
                    config=config
                ):

                    piece = ""

                    try:
                        piece = chunk.text or ""
                    except Exception:
                        piece = ""

                    if not piece:
                        continue

                    full_text += piece

                    if not bubble_started:

                        bubble_started = True

                        waited = time.time() - started_at

                        self._first_token_s = waited

                        self._reply_info = (model_name, setup_s, waited)

                        self.after(0, self.ai_stream_started)

                    now = time.time()

                    if now - last_update >= 0.05:

                        last_update = now

                        self.after(
                            0,
                            lambda t=full_text: self.ai_stream_update(t)
                        )

                    # The Stop button: keep what has arrived.
                    if getattr(self, "_chat_stop", False):
                        break

                used_model = model_name

                break

            except Exception as exc:

                text = str(exc).lower()

                if bubble_started:
                    raise

                missing = (
                    "not_found" in text
                    or "404" in text
                    or "not found" in text
                )

                busy = any(
                    word in text for word in (
                        "503", "500", "unavailable", "overloaded",
                        "internal", "timeout", "timed out", "deadline",
                        "429", "resource_exhausted", "connection",
                        "disconnected", "reset"
                    )
                )

                # Model missing, or briefly busy / slow: try the next
                # model. A busy moment must not push the rest of the
                # session onto the slow path.
                if missing or busy:
                    continue

                # Key and other errors read the same on either path:
                # let the older path report them (and look again soon).
                self._fast_path_off_until = time.time() + 60

                return False

        if used_model is None:

            # Every model was busy; look again in a moment.
            self._fast_path_off_until = time.time() + 20

            return False

        if used_model != self.get_gemini_model():

            self.db.set_setting("gemini_model", used_model)

            self.after(
                0,
                lambda m=used_model: self._notify_model_fallback(m)
            )

        if bubble_started:

            self.after(
                0,
                lambda t=full_text: self.ai_stream_update(t)
            )

        if not full_text:
            raise RuntimeError("Gemini returned an empty response.")

        self.db.add_message("assistant", full_text.strip())

        self.after(
            0,
            lambda result=full_text.strip():
                self.ai_stream_finished(result, None)
        )

        return True

    # --------------------------------------------------------
    # /notes command in AI Chat
    # --------------------------------------------------------

    def _plain_notes(self, text):
        """The Notes page is a plain text editor, so strip Markdown."""

        out = []

        for raw in str(text or "").replace("\r", "").split("\n"):

            line = raw.rstrip()

            stripped = line.lstrip()

            if stripped.startswith("#"):
                line = stripped.lstrip("#").strip()

            line = line.replace("**", "").replace("__", "")
            line = line.replace("`", "")

            if line.lstrip().startswith("* "):

                indent = line[:len(line) - len(line.lstrip())]

                line = indent + "- " + line.lstrip()[2:]

            out.append(line)

        return "\n".join(out).strip()

    def _append_to_notes(self, text, replace=False):
        """Adds text to the end of what is in the Notes editor (the
        saved draft), marked as unsaved. With replace=True the old
        notes are dropped and the editor becomes a new, untitled note
        (so a file you had open is not overwritten)."""

        old = getattr(self, "_note_text", None)

        if old is None:
            old = self.db.get_setting("notes_draft", "")

        # The Notes page reads these when it opens.
        if not hasattr(self, "_note_path"):
            self._note_path = self.db.get_setting("notes_file", "")

        if replace:
            old = ""
            self._note_path = ""
            self.db.set_setting("notes_file", "")

        new = (
            (old.rstrip("\n") + "\n\n" if old.strip() else "")
            + text.strip()
            + "\n"
        )

        self._note_text = new

        self.db.set_setting("notes_draft", new)
        self.db.set_setting("notes_dirty", "1")

        self._note_dirty = True

    def _notes_command(self, user_text, replace=False, extra_parts=None):
        """/notes <topic>  writes study notes on the topic into Notes.
        /notes  alone saves the AI's last answer as notes.
        /newnotes does the same but replaces the old notes."""

        cmd_len = len("/newnotes") if replace else len("/notes")

        clean, _paths = self._bubble_attachments(user_text)

        topic = clean.strip()[cmd_len:].strip()

        extra_parts = extra_parts or []

        label = topic or "your attached file"

        verb = "Replaced your notes with" if replace else "Added"

        reply, error = "", None

        try:

            if not topic and not extra_parts:

                last = ""

                for row in reversed(self.db.get_messages()):

                    content = (row["content"] or "").strip()

                    if (
                        row["role"] != "user"
                        and content
                        and not content.startswith((
                            "Gemini", "(Interrupted)", "Added ",
                            "Replaced ", "Use /notes"
                        ))
                    ):
                        last = content
                        break

                if not last:

                    reply = (
                        "Use /notes followed by what you want notes on, "
                        "for example:  /notes photosynthesis, class 10\n\n"
                        "I write them into your Notes tab. Then press "
                        "Quiz me there to be quizzed on them. Typing "
                        "/notes on its own saves my last answer as notes."
                    )

                else:

                    self._append_to_notes(
                        self._plain_notes(last), replace
                    )

                    reply = (
                        (
                            "Replaced your notes with my last answer. "
                            if replace else
                            "Added my last answer to your Notes tab. "
                        )
                        + "Open Notes and press Quiz me to be quizzed."
                    )

            else:

                client = self._gemini_client()

                if extra_parts and topic:
                    target = f"from the attached file(s), on: {topic}"
                elif extra_parts:
                    target = "from the attached file(s)"
                else:
                    target = f"on: {topic}"

                prompt = (
                    "Write clear, well-organised study notes for a "
                    f"student {target}\n\n"
                    "Plain text only. No Markdown symbols at all (no "
                    "asterisks, no # headings, no backticks). Start "
                    "with a one-line title, then short sections, each "
                    "with a heading line followed by '- ' bullet "
                    "points. Include key definitions, formulas and a "
                    "short example where it helps. Cover the topic "
                    "fully. If the student asks for a length (for "
                    "example 2000 words or 3 pages), write that "
                    "much and do not stop early; otherwise about 400 "
                    "to 800 words."
                )

                text = ""

                last_error = None

                for model_name in self._gemini_model_candidates():

                    try:

                        result = client.models.generate_content(
                            model=model_name,
                            contents=(
                                [*extra_parts, prompt]
                                if extra_parts else prompt
                            ),
                            config={
                                "max_output_tokens":
                                    AI_NOTES_MAX_OUTPUT_TOKENS,
                                "http_options": {"timeout": 300000}
                            }
                        )

                        text = (result.text or "").strip()

                        if text:
                            break

                    except Exception as exc:

                        last_error = exc

                if not text:

                    raise last_error or RuntimeError(
                        "Gemini returned no notes."
                    )

                notes = self._plain_notes(text)

                self._append_to_notes(notes, replace)

                reply = (
                    (
                        f"Replaced your notes with new notes on "
                        f"\"{label}\" "
                        if replace else
                        f"Added notes on \"{label}\" to your Notes tab "
                    )
                    + f"({len(notes.split())} words). Open Notes to read "
                    "or edit them, and press Quiz me to be quizzed."
                )

            self.db.add_message("assistant", reply)

        except Exception as exc:

            error = str(exc)

        self.after(0, lambda: self._notes_cmd_done(reply, error))

    def _schedule_command(self, user_text, extra_parts=None):
        """/schedule <request>: Gemini edits the Schedule tab. It sees
        the current blocks and the recent chat, and can add, change
        (rename, move, re-day) and delete blocks. /schedule undo puts
        the schedule back the way it was before the last change."""

        clean, _paths = self._bubble_attachments(user_text)

        request = clean.strip()[len("/schedule"):].strip()

        extra_parts = extra_parts or []

        reply, error = "", None

        def days_text(days):

            return ", ".join(SCHEDULE_DAYS[d] for d in sorted(days))

        def day_set(text):

            return {int(d) for d in str(text).split(",") if d != ""}

        def describe(row):

            return (
                f"{format_clock(row['start_min'])} - "
                f"{format_clock(row['end_min'])}  {row['title']}  ("
                + days_text(day_set(row["days"])) + ")"
            )

        try:

            if request.lower() in ("undo", "undo that", "revert"):

                saved = getattr(self, "_schedule_undo", None)

                if saved is None:

                    reply = "There's nothing to undo yet."

                else:

                    self.db.delete_all_schedule()

                    for item in saved:

                        self.db.add_schedule(
                            item["title"], item["start_min"],
                            item["end_min"], day_set(item["days"]),
                            item["remind_before"]
                        )

                    self._schedule_undo = None

                    reply = (
                        f"Put your schedule back ({len(saved)} block"
                        + ("" if len(saved) == 1 else "s") + ")."
                    )

            elif not request and not extra_parts:

                reply = (
                    "Use /schedule followed by what you want, for "
                    "example:\n/schedule study maths 4 to 5pm on "
                    "Tuesday, remind me 10 minutes before\n"
                    "/schedule move chemistry to 6pm\n"
                    "/schedule rename the blocks to study, break, "
                    "revision\n/schedule delete everything on Friday\n"
                    "/schedule undo\n\nI can add, rename, move and "
                    "delete blocks, and I remember the recent chat. You "
                    "can also attach a photo of a timetable."
                )

            else:

                import json

                client = self._gemini_client()

                now = datetime.now()

                rows = self.db.get_schedule()

                existing = [
                    f"id={r['id']} | {days_text(day_set(r['days']))} | "
                    f"{format_clock(r['start_min'])}-"
                    f"{format_clock(r['end_min'])} | {r['title']} | "
                    f"reminder {r['remind_before']}"
                    for r in rows
                ]

                recent = []

                for row in self.db.get_messages()[-9:]:

                    text = (row["content"] or "").strip()

                    if text:

                        who = "Student" if row["role"] == "user" else "You"

                        recent.append(f"{who}: {text[:300]}")

                prompt = (
                    "You edit a student's weekly timetable. Today is "
                    f"{now.strftime('%A %d %B %Y')}, the time is "
                    f"{now.strftime('%H:%M')}.\n\n"
                    "CURRENT SCHEDULE:\n"
                    + ("\n".join(existing) or "(empty)")
                    + "\n\nRECENT CHAT (oldest first):\n"
                    + ("\n".join(recent) or "(none)")
                    + "\n\nNEW REQUEST: "
                    + (request or "use the attached file(s)")
                    + "\n\nAnswer with JSON only:\n"
                    '{"reply":"short note or question, or empty",'
                    '"add":[{"title":"Study maths","start":"16:00",'
                    '"end":"17:00","days":["Tue"],"remind":5}],'
                    '"update":[{"id":3,"title":"New name","start":"17:00",'
                    '"end":"18:00","days":["Tue"],"remind":0}],'
                    '"delete":[4]}\n\n'
                    "Rules:\n"
                    "- Decide whether the request means ADD new blocks, "
                    "CHANGE existing ones (rename, move, resize, change "
                    "days or reminder: use update with the block's id and "
                    "only the fields that change) or DELETE. \"Name "
                    "them\", \"rename\", \"move\", \"make it longer\" and "
                    "\"change\" are updates to existing blocks, never new "
                    "blocks. Use the recent chat to work out what "
                    "\"them\", \"it\" or \"the old one\" refers to.\n"
                    "- Delete only when the student clearly asks to "
                    "remove, clear or replace something.\n"
                    "- start and end are 24-hour HH:MM on a 5-minute "
                    "grid, end after start, normally 15 to 120 minutes "
                    "long unless asked. Blocks on the same day must not "
                    "overlap.\n"
                    "- days uses Mon Tue Wed Thu Fri Sat Sun. Use ONLY "
                    "the days the request names (\"tomorrow\" is the day "
                    "after today); all weekdays only if it says "
                    "weekdays or every day; if it names no day, use "
                    "today's day, or the day of the blocks it is "
                    "changing.\n"
                    "- remind is minutes before the start: -1 for none, "
                    "0, 5, 10 or 15; default 0.\n"
                    "- Titles are short and meaningful, never \"Block "
                    "1\".\n"
                    "- Plan like a kind, realistic person, not a drill "
                    "sergeant. Do NOT create blocks named Break or Rest: "
                    "breaks are simply the gaps between blocks. Leave at "
                    "least 10 to 15 minutes between blocks, a longer "
                    "gap (30 to 60 minutes) for dinner or lunch, and "
                    "free time in the evening. Prefer fewer, longer "
                    "sessions (45 to 90 minutes), about 3 to 5 blocks "
                    "for an evening, unless the student asks for more. "
                    "Use the subjects the student names or that appear "
                    "in the schedule or chat; if they gave none, use "
                    "simple names like Study session.\n"
                    "- When asked to plan a whole stretch or a whole "
                    "day (for example \"3:30 to 10 pm\"), make it a "
                    "balanced day, not all studying: at most about half "
                    "of the time is study. Include real life as named "
                    "blocks: Dinner (and Lunch if it fits), exercise or "
                    "a Walk, Free time or a hobby, time with family or "
                    "friends, and a Wind down before bed. Study blocks "
                    "come in a few sessions with different subjects, "
                    "and the evening ends light.\n"
                    "- Words like \"these blocks\", \"them\" or "
                    "\"my schedule\" mean the blocks that already "
                    "exist: change their times or names with update, "
                    "reuse as many as fit, add only the extra ones "
                    "needed and delete surplus ones only if the student "
                    "asked for fewer. Never add a block that duplicates "
                    "or overlaps an existing one.\n"
                    "- Do only what was asked. If the request is unclear, "
                    "return empty lists and ask one short question in "
                    "reply. Never invent a time the student did not "
                    "imply."
                )

                data, last_error = None, None

                for model_name in self._gemini_model_candidates():

                    try:

                        result = client.models.generate_content(
                            model=model_name,
                            contents=(
                                [*extra_parts, prompt]
                                if extra_parts else prompt
                            ),
                            config={
                                "response_mime_type": "application/json",
                                "http_options": {"timeout": 120000}
                            }
                        )

                        raw = (result.text or "").strip()

                        if "{" in raw:

                            data = json.loads(
                                raw[raw.index("{"):raw.rindex("}") + 1]
                            )

                            break

                    except Exception as exc:

                        last_error = exc

                if data is None:

                    raise last_error or RuntimeError(
                        "Gemini returned no schedule."
                    )

                def parse_days(value, fallback):

                    found = {
                        SCHEDULE_DAYS.index(str(d)[:3].title())
                        for d in (value or [])
                        if str(d)[:3].title() in SCHEDULE_DAYS
                    }

                    return found or fallback

                def parse_remind(value, fallback):

                    try:
                        value = int(value)
                    except Exception:
                        return fallback

                    return value if value in (-1, 0, 5, 10, 15) else fallback

                by_id = {r["id"]: r for r in rows}

                snapshot = [dict(r) for r in rows]

                removed, edited, added = [], [], []

                changed = False

                handled = set()

                for item in data.get("delete", []) or []:

                    try:
                        target = by_id.get(int(item))
                    except Exception:
                        target = None

                    if target is not None and target["id"] not in handled:

                        handled.add(target["id"])

                        self.db.delete_schedule(target["id"])

                        removed.append(describe(target))

                        changed = True

                for item in data.get("update", []) or []:

                    try:
                        target = by_id.get(int(item.get("id")))
                    except Exception:
                        target = None

                    if target is None or target["id"] in handled:
                        continue

                    handled.add(target["id"])

                    title = str(
                        item.get("title") or target["title"]
                    ).strip()[:80] or target["title"]

                    start = (
                        parse_clock(item["start"])
                        if item.get("start") else target["start_min"]
                    )

                    end = (
                        parse_clock(item["end"])
                        if item.get("end") else target["end_min"]
                    )

                    if start is None or end is None or end <= start:
                        start, end = target["start_min"], target["end_min"]

                    days = parse_days(
                        item.get("days"), day_set(target["days"])
                    )

                    remind = parse_remind(
                        item.get("remind"), target["remind_before"]
                    )

                    self.db.update_schedule(
                        target["id"], title, start, end, days, remind
                    )

                    edited.append(describe({
                        "title": title, "start_min": start,
                        "end_min": end,
                        "days": ",".join(str(d) for d in days)
                    }))

                    changed = True

                busy = {d: [] for d in range(7)}

                for r in self.db.get_schedule():

                    for d in day_set(r["days"]):
                        busy[d].append((r["start_min"], r["end_min"]))

                skipped = 0

                for item in data.get("add", []) or []:

                    title = str(item.get("title", "")).strip()

                    start = parse_clock(item.get("start", ""))
                    end = parse_clock(item.get("end", ""))

                    if (
                        not title or start is None or end is None
                        or end <= start
                    ):
                        continue

                    days = parse_days(item.get("days"), {now.weekday()})

                    if any(
                        start < b_end and b_start < end
                        for d in days for b_start, b_end in busy[d]
                    ):
                        skipped += 1
                        continue

                    for d in days:
                        busy[d].append((start, end))

                    remind = parse_remind(item.get("remind"), 0)

                    self.db.add_schedule(
                        title[:80], start, end, days, remind
                    )

                    added.append(describe({
                        "title": title[:80], "start_min": start,
                        "end_min": end,
                        "days": ",".join(str(d) for d in days)
                    }))

                    changed = True

                note = str(data.get("reply") or "").strip()

                if changed:

                    self._schedule_undo = snapshot

                    sections = []

                    for label, group in (
                        ("Added", added), ("Changed", edited),
                        ("Removed", removed)
                    ):

                        if group:

                            sections.append(
                                f"{label} {len(group)} block"
                                + ("" if len(group) == 1 else "s")
                                + ":\n" + "\n".join(group)
                            )

                    if skipped:

                        sections.append(
                            f"Skipped {skipped} block"
                            + ("" if skipped == 1 else "s")
                            + " that would overlap one you already have."
                        )

                    reply = (
                        (note + "\n\n" if note else "")
                        + "\n\n".join(sections)
                        + "\n\nOpen Schedule to see it. Type "
                        "/schedule undo to put it back."
                    )

                else:

                    reply = note or (
                        "I couldn't tell what to change. Try something "
                        "like:  /schedule move chemistry to 6pm"
                    )

            self.db.add_message("assistant", reply)

        except Exception as exc:

            error = str(exc)

        self.after(
            0,
            lambda: self._notes_cmd_done(reply, error, "schedule")
        )

    def _quiz_command(self, user_text, extra_parts=None):
        """/quiz <topic>, or /quiz with files attached: get some study
        text, then open the quiz window on it."""

        clean, _paths = self._bubble_attachments(user_text)

        topic = clean.strip()[len("/quiz"):].strip()

        extra_parts = extra_parts or []

        reply, error, material = "", None, ""

        try:

            if not topic and not extra_parts:

                reply = (
                    "Use /quiz followed by a topic, for example "
                    "/quiz photosynthesis, or attach a file with the "
                    "+ button and type /quiz. I'll make a "
                    "multiple-choice quiz from it."
                )

            else:

                if extra_parts and all(
                    getattr(p, "text", None) for p in extra_parts
                ):

                    material = "\n\n".join(p.text for p in extra_parts)

                else:

                    client = self._gemini_client()

                    if extra_parts:

                        prompt = (
                            "Write out the full content of the attached "
                            "file(s) as plain text for studying. Keep "
                            "every fact, definition and number. No "
                            "commentary."
                            + (f" Focus on: {topic}" if topic else "")
                        )

                        contents = [*extra_parts, prompt]

                    else:

                        contents = (
                            "Write clear study notes of about 500 words "
                            f"on: {topic}. Plain text only."
                        )

                    last_error = None

                    for model_name in self._gemini_model_candidates():

                        try:

                            result = client.models.generate_content(
                                model=model_name,
                                contents=contents,
                                config={
                                    "max_output_tokens":
                                        AI_NOTES_MAX_OUTPUT_TOKENS,
                                    "http_options": {"timeout": 240000}
                                }
                            )

                            material = (result.text or "").strip()

                            if material:
                                break

                        except Exception as exc:

                            last_error = exc

                    if not material:

                        raise last_error or RuntimeError(
                            "Gemini returned nothing to make a quiz from."
                        )

                reply = "Making your quiz now."

            self.db.add_message("assistant", reply)

        except Exception as exc:

            error = str(exc)

        self.after(
            0, lambda: self._quiz_cmd_done(reply, error, material)
        )

    def _quiz_cmd_done(self, reply, error, material):

        self.chat_busy = False

        try:

            self.remove_typing_bubble()

            self.chat_send_button.configure(
                text="Send", state="normal"
            )

            if error:

                self.chat_status.configure(text="Error", fg=RED)

                self.add_chat_bubble(
                    "assistant",
                    "Couldn't make the quiz: " + error[:300]
                )

            else:

                self.chat_status.configure(text="Ready", fg=GREEN)

                self.add_chat_bubble("assistant", reply)

            self.scroll_chat()

        except Exception:
            pass

        if material and not error:
            self.start_quiz(material)

    def _notes_cmd_done(self, reply, error, what="notes"):

        self.chat_busy = False

        self.remove_typing_bubble()

        try:
            self.chat_send_button.configure(
                text="Send", state="normal"
            )
        except Exception:
            pass

        if error:

            self.chat_status.configure(text="Error", fg=RED)

            self.add_chat_bubble(
                "assistant",
                f"Couldn't write the {what}: " + error[:300]
            )

        else:

            self.chat_status.configure(
                text="Schedule updated" if what == "schedule"
                else "Notes added",
                fg=GREEN
            )

            self.add_chat_bubble("assistant", reply)

        self.scroll_chat()

    def ai_worker(
        self,
        user_text,
        attachments=None
    ):

        try:

            extra_parts = (
                self._chat_attachment_parts(attachments)
                if attachments else []
            )

            if user_text.strip().lower().startswith("/quiz"):

                self._quiz_command(user_text, extra_parts=extra_parts)

                return

            if user_text.strip().lower().startswith("/schedule"):

                self._schedule_command(user_text, extra_parts=extra_parts)

                return

            if user_text.strip().lower().startswith("/newnotes"):

                self._notes_command(
                    user_text, replace=True, extra_parts=extra_parts
                )

                return

            if user_text.strip().lower().startswith("/notes"):

                self._notes_command(user_text, extra_parts=extra_parts)

                return

            started_at = time.time()

            # Gemini is NOT imported during startup; the first chat
            # visit (or the first message) loads it, and the same
            # connection is reused after that.
            client = self._gemini_client()

            setup_s = time.time() - started_at

            if self._ai_fast_path(
                client, user_text, started_at, setup_s, extra_parts
            ):
                return

            if attachments:
                raise RuntimeError(
                    "This Gemini setup can't take attachments right "
                    "now. Try again in a moment."
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
                    # "minimal" starts answering fastest; models that
                    # don't know it fall back to "low" (see create()).
                    "thinking_level": getattr(
                        self, "_thinking_level", "minimal"
                    ),
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
                    "environment cannot render most of them. "
                    "There is no length limit on your replies. If the "
                    "student asks for a long or detailed answer, write "
                    "all of it in ONE reply. Never split an answer "
                    "into parts and never ask the student to say when "
                    "to continue."
                )
            }

            def create(**kw):

                try:

                    return client.interactions.create(**kw)

                except Exception as exc:

                    level = kw.get("generation_config", {}).get(
                        "thinking_level"
                    )

                    if (
                        level == "minimal"
                        and "thinking" in str(exc).lower()
                    ):

                        self._thinking_level = "low"

                        kw = dict(kw)

                        kw["generation_config"] = dict(
                            kw["generation_config"],
                            thinking_level="low"
                        )

                        return client.interactions.create(**kw)

                    raise

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
                        create(**kwargs)
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
                                create(**kwargs)
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

            created_s = time.time() - started_at

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

                            self._first_token_s = time.time() - started_at

                            self._reply_info = (
                                used_model or "",
                                setup_s,
                                created_s
                            )

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
                text="Send",
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

            waited = getattr(self, "_first_token_s", None)

            info = getattr(self, "_reply_info", None)

            if waited is not None and info:

                label = (
                    f"Ready  ·  {info[0]}  ·  first words {waited:.1f}s "
                    f"(setup {info[1]:.1f}s, request {info[2] - info[1]:.1f}s, "
                    f"thinking {waited - info[2]:.1f}s)"
                )

            elif waited is not None:

                label = f"Ready  ·  first words in {waited:.1f}s"

            else:

                label = "Ready"

            if getattr(self, "_chat_stop", False):
                label = "Stopped"

            self.chat_status.configure(
                text=label,
                fg=GREEN
            )

            if self.stream_canvas is not None and answer:

                self._add_copy_label(
                    self.stream_canvas.master, lambda a=answer: a
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

        chart_state = {"month": False}

        head = tk.Frame(left, bg=PANEL)

        head.pack(fill="x", padx=20, pady=(20, 12))

        head_title = tk.Label(
            head, bg=PANEL, fg=TEXT, font=("Segoe UI", 14, "bold")
        )

        head_title.pack(anchor="w")

        head_sub = tk.Label(
            head, bg=PANEL, fg=MUTED, font=("Segoe UI", 9)
        )

        head_sub.pack(anchor="w", pady=(2, 0))

        toggle = self.make_button(head, "View month", None, width=11)

        toggle.place(relx=1.0, y=0, anchor="ne")

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

        def show_range():

            days = 30 if chart_state["month"] else 7

            data = self.db.focus_daily_seconds(days)

            chart_state["data"] = data

            head_title.configure(
                text="Last 30 days" if days == 30 else "Last 7 days"
            )

            head_sub.configure(
                text="Time focused per day  \u00b7  "
                + fmt_duration(sum(secs for _, secs in data))
                + " in total"
            )

            toggle.configure(
                text="View week" if days == 30 else "View month"
            )

            chart._chart_key = None

            self._draw_week_chart(chart, data)

        def switch_range():
            chart_state["month"] = not chart_state["month"]
            show_range()

        toggle.command = switch_range

        chart_state["data"] = self.db.focus_daily_seconds(7)

        chart.bind(
            "<Configure>",
            lambda event: self._draw_week_chart(
                chart, chart_state["data"]
            )
        )

        show_range()

        self.section_title(
            right,
            "Recent sessions",
            "Your latest focus sessions"
        )

        sessions = self.db.recent_focus_sessions(100000)

        if not sessions:
            self.empty_text(
                right,
                "No focus sessions yet. Finish one in "
                "Focus Mode and it shows up here."
            )

        # Every session is kept; the list scrolls.
        scroller = tk.Canvas(
            right, bg=PANEL, highlightthickness=0, bd=0, width=10,
            height=10
        )

        scroller.pack(fill="both", expand=True, pady=(0, 14))

        rows_frame = tk.Frame(scroller, bg=PANEL)

        rows_window = scroller.create_window(
            (0, 0), window=rows_frame, anchor="nw"
        )

        scroller.bind(
            "<Configure>",
            lambda e: scroller.itemconfigure(rows_window, width=e.width)
        )

        rows_frame.bind(
            "<Configure>",
            lambda e: scroller.configure(
                scrollregion=scroller.bbox("all")
            )
        )

        self._bind_mousewheel(scroller)

        for session in sessions:
            self._analytics_session_row(
                rows_frame,
                session
            )

    def _analytics_session_row(self, parent, session):

        row = tk.Frame(
            parent,
            bg=PANEL
        )

        if getattr(parent, "_rows_added", 0) > 0:

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

        parent._rows_added = getattr(parent, "_rows_added", 0) + 1

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

    def _draw_line_chart(self, canvas, data):
        """Smooth line graph with a soft fill, for the month view."""

        try:
            width = canvas.winfo_width()
            height = canvas.winfo_height()

            if width < 80 or height < 80:
                return

            key = (width, height, len(data))

            if getattr(canvas, "_chart_key", None) == key:
                return

            canvas._chart_key = key

            canvas.delete("all")

            label_h = 24
            top_pad = 26
            left_pad = 14
            right_pad = 30

            plot_h = height - label_h - top_pad
            base_y = top_pad + plot_h

            count = len(data)

            step = (width - left_pad - right_pad) / (count - 1)

            biggest = max([secs for _, secs in data] + [30 * 60])

            pts = [
                (
                    left_pad + i * step,
                    base_y - plot_h * secs / biggest
                )
                for i, (_d, secs) in enumerate(data)
            ]

            for frac in (0, 0.5, 1.0):
                gy = base_y - plot_h * frac
                canvas.create_line(
                    0, gy, width, gy,
                    fill=mix_color(BORDER, PANEL, 0.35 if frac else 0.0),
                    dash=(2, 4) if frac else ()
                )

            # Smooth curve through the points (Catmull-Rom), never
            # dipping below the baseline or above the top.
            curve = []

            for i in range(count - 1):
                p0 = pts[max(i - 1, 0)]
                p1 = pts[i]
                p2 = pts[i + 1]
                p3 = pts[min(i + 2, count - 1)]
                for s in range(10):
                    u = s / 10
                    x = 0.5 * (
                        2 * p1[0] + (-p0[0] + p2[0]) * u
                        + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * u * u
                        + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * u ** 3
                    )
                    y = 0.5 * (
                        2 * p1[1] + (-p0[1] + p2[1]) * u
                        + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * u * u
                        + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * u ** 3
                    )
                    curve.append((x, min(base_y, max(top_pad, y))))

            curve.append(pts[-1])

            if HAS_PIL:

                S = 3

                big = (width * S, height * S)

                img = Image.new("RGBA", big, (0, 0, 0, 0))

                # Soft fill under the line, fading towards the baseline.
                mask = Image.new("L", big, 0)

                ImageDraw.Draw(mask).polygon(
                    [(x * S, y * S) for x, y in curve]
                    + [(curve[-1][0] * S, base_y * S),
                       (curve[0][0] * S, base_y * S)],
                    fill=255
                )

                grad = Image.new("L", (1, height * S), 0)

                for gy in range(height * S):
                    frac = max(
                        0.0,
                        min(1.0, (gy / S - top_pad) / max(1, plot_h))
                    )
                    grad.putpixel((0, gy), int(95 * (1 - frac)))

                grad = grad.resize(big)

                fade = Image.composite(
                    grad, Image.new("L", big, 0), mask
                )

                img.paste(
                    Image.new("RGBA", big, _hex_rgb(PURPLE) + (255,)),
                    (0, 0), fade
                )

                d = ImageDraw.Draw(img)

                d.line(
                    [(x * S, y * S) for x, y in curve],
                    fill=_hex_rgb(PURPLE_HOVER) + (255,),
                    width=int(2.6 * S),
                    joint="curve"
                )

                for i, (_d, secs) in enumerate(data):

                    is_today = i == count - 1

                    if secs <= 0 and not is_today:
                        continue

                    x, y = pts[i]

                    r = (5 if is_today else 3.6) * S

                    d.ellipse(
                        [x * S - r - S, y * S - r - S,
                         x * S + r + S, y * S + r + S],
                        fill=_hex_rgb(PANEL) + (255,)
                    )

                    d.ellipse(
                        [x * S - r, y * S - r, x * S + r, y * S + r],
                        fill=_hex_rgb(
                            PURPLE_HOVER if is_today else PURPLE
                        ) + (255,)
                    )

                img = img.resize((width, height), Image.LANCZOS)

                photo = ImageTk.PhotoImage(img)

                canvas.chart_photo = photo

                canvas.create_image(0, 0, anchor="nw", image=photo)

            else:

                canvas.create_line(
                    *[c for pt in curve for c in pt],
                    fill=PURPLE_HOVER, width=2, smooth=True
                )

            for i, (day, secs) in enumerate(data):

                x, y = pts[i]

                if i == count - 1:
                    canvas.create_text(
                        width - 4, height - label_h / 2 + 2,
                        text="Today", fill=TEXT, anchor="e",
                        font=("Segoe UI", 9)
                    )
                elif i % 5 == 0 and i < count - 3:
                    try:
                        label = datetime.strptime(
                            day, "%Y-%m-%d"
                        ).strftime("%d").lstrip("0")
                    except Exception:
                        label = day
                    canvas.create_text(
                        x, height - label_h / 2 + 2, text=label,
                        fill=MUTED, font=("Segoe UI", 9)
                    )

                if secs > 0 and secs == biggest:
                    canvas.create_text(
                        x, y - 14, text=fmt_duration(secs),
                        fill=MUTED, font=("Segoe UI", 8)
                    )

        except Exception:
            pass

    def _draw_week_chart(self, canvas, data):
        """Bar chart that fills whatever space it is given and redraws
        when the window is resized. Bars are anti-aliased via Pillow."""

        if len(data) > 10:
            return self._draw_line_chart(canvas, data)

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
            many = count > 10

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
                        ).strftime("%d" if many else "%a")
                        if many:
                            label = label.lstrip("0")
                            if index % 3 != 0:
                                label = ""
                    except Exception:
                        label = day

                canvas.create_text(
                    center,
                    height - label_h / 2 + 2,
                    text=label,
                    fill=TEXT if index == count - 1 else MUTED,
                    font=("Segoe UI", 9)
                )

                if secs > 0 and (not many or secs == biggest):
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

                # A wheel turn in a pop-up window (update notes, a
                # dialog) is not meant for the page behind it.
                if event.widget.winfo_toplevel() is not self:
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

        self.gemini_model_var = tk.StringVar(
            value=self.get_gemini_model()
        )

        # ---- model dropdown (slides open) ----
        model_names = []

        for name in (
            [GEMINI_MODEL]
            + list(GEMINI_MODEL_FALLBACKS)
            + ["gemini-flash-lite-latest"]
        ):

            if name not in model_names:
                model_names.append(name)

        builtin_names = list(model_names)

        # Names the student typed under "Custom..." are kept in the list.
        try:

            import json

            for name in json.loads(
                self.db.get_setting("custom_models", "[]")
            ):

                if isinstance(name, str) and name not in model_names:
                    model_names.append(name)

        except Exception:
            pass

        if self.gemini_model_var.get() not in model_names:
            model_names.append(self.gemini_model_var.get())

        def model_note(name):

            if name == GEMINI_MODEL:
                return "Default"

            if name not in builtin_names:
                return "Custom"

            if "lite" in name:
                return "Fast, big free quota"

            return "Smarter, smaller free quota"

        box_row = tk.Frame(model_row, bg=PANEL)

        box_row.pack(fill="x")

        dropdown = tk.Frame(
            box_row,
            bg=PANEL_2,
            highlightthickness=1,
            highlightbackground=BORDER,
            cursor="hand2"
        )

        dropdown.pack(side="left", fill="x", expand=True)

        current_label = tk.Label(
            dropdown,
            textvariable=self.gemini_model_var,
            bg=PANEL_2,
            fg=TEXT,
            font=("Segoe UI", 10),
            anchor="w",
            padx=12,
            pady=10
        )

        current_label.pack(side="left", fill="x", expand=True)

        arrow = tk.Label(
            dropdown,
            text="\u25BE",
            bg=PANEL_2,
            fg=MUTED,
            font=("Segoe UI", 11),
            padx=12
        )

        arrow.pack(side="right")

        def tint(colour):

            for widget in (dropdown, current_label, arrow):
                widget.configure(bg=colour)

        edit = {"entry": None}

        def choose_model(name):

            if name is None:

                enter_edit()

                return

            self.gemini_model_var.set(name)

            self.db.set_setting("gemini_model", name)

            self.settings_status.configure(
                text=f"Model set to {name}.",
                fg=GREEN
            )

        def leave_edit():

            entry = edit["entry"]

            edit["entry"] = None

            if entry is not None:
                entry.destroy()

            save_button.canvas.pack_forget()

            current_label.pack(side="left", fill="x", expand=True)

            arrow.pack(side="right")

            dropdown.configure(cursor="hand2")

        def save_custom():

            entry = edit["entry"]

            name = entry.get().strip() if entry is not None else ""

            leave_edit()

            if not name:
                return

            if name not in model_names:

                model_names.append(name)

                try:

                    import json

                    self.db.set_setting(
                        "custom_models",
                        json.dumps([
                            n for n in model_names
                            if n not in builtin_names
                        ])
                    )

                except Exception:
                    pass

            choose_model(name)

        def remove_custom(name):

            if name in model_names and name not in builtin_names:
                model_names.remove(name)

            try:

                import json

                self.db.set_setting(
                    "custom_models",
                    json.dumps([
                        n for n in model_names
                        if n not in builtin_names
                    ])
                )

            except Exception:
                pass

            # Removing the model in use goes back to the default.
            if self.gemini_model_var.get() == name:
                choose_model(GEMINI_MODEL)

        save_button = self.make_button(
            box_row,
            "Save",
            save_custom,
            width=9
        )

        def enter_edit():

            if edit["entry"] is not None:
                return

            current_label.pack_forget()
            arrow.pack_forget()

            dropdown.configure(cursor="")

            entry = tk.Entry(
                dropdown,
                bg=PANEL_2,
                fg=TEXT,
                insertbackground=TEXT,
                relief="flat",
                bd=0,
                highlightthickness=0,
                font=("Segoe UI", 10)
            )

            entry.pack(
                side="left",
                fill="x",
                expand=True,
                padx=12,
                ipady=10
            )

            edit["entry"] = entry

            save_button.pack(side="left", padx=(8, 0))

            entry.bind("<Return>", lambda e: save_custom())
            entry.bind("<Escape>", lambda e: leave_edit())

            entry.focus_set()

        menu = {"win": None}

        def close_menu(animate=True):

            win = menu["win"]

            menu["win"] = None

            if win is None:
                return

            def done():

                try:
                    win.destroy()
                except Exception:
                    pass

            if not animate:
                done()
                return

            try:

                width, full, left, top = win._geo

                steps = 5

                def step(i=steps):

                    try:

                        t = i / steps

                        win.geometry(
                            f"{width}x{full}+{left}+{top - int(6 * (1 - t))}"
                        )

                        win.attributes("-alpha", t)

                        if i <= 0:
                            done()
                        else:
                            win.after(12, lambda: step(i - 1))

                    except Exception:
                        done()

                step()

            except Exception:
                done()

        def open_menu(event=None):

            if edit["entry"] is not None:
                return

            if menu["win"] is not None:

                close_menu()

                return

            win = tk.Toplevel(self)

            win.withdraw()
            win.overrideredirect(True)
            win.attributes("-topmost", True)
            win.attributes("-alpha", 0.0)
            win.configure(bg=BORDER)

            inner = tk.Frame(win, bg=PANEL_2)

            inner.pack(padx=1, pady=1, fill="both")

            tk.Frame(inner, bg=PANEL_2, height=4).pack()

            now = self.gemini_model_var.get()

            def add_row(name, text, note):

                row = tk.Frame(inner, bg=PANEL_2, cursor="hand2")

                row.pack(fill="x", padx=4, pady=1)

                mark = tk.Label(
                    row,
                    text="\u2713" if name == now else "",
                    bg=PANEL_2,
                    fg=PURPLE_HOVER,
                    font=("Segoe UI", 10, "bold"),
                    width=2
                )

                mark.pack(side="left", padx=(6, 0))

                title = tk.Label(
                    row,
                    text=text,
                    bg=PANEL_2,
                    fg=TEXT,
                    font=("Segoe UI", 10),
                    anchor="w",
                    pady=8
                )

                title.pack(side="left")

                cross = None

                if name is not None and name not in builtin_names:

                    cross = tk.Label(
                        row,
                        text="\u2715",
                        bg=PANEL_2,
                        fg=MUTED_2,
                        font=("Segoe UI", 9),
                        padx=10,
                        cursor="hand2"
                    )

                    cross.pack(side="right")

                    cross.bind(
                        "<Enter>",
                        lambda e: cross.configure(fg=RED)
                    )

                    cross.bind(
                        "<Leave>",
                        lambda e: cross.configure(fg=MUTED_2)
                    )

                    cross.bind(
                        "<ButtonRelease-1>",
                        lambda e, n=name: (
                            close_menu(),
                            remove_custom(n)
                        )
                    )

                hint = tk.Label(
                    row,
                    text=note,
                    bg=PANEL_2,
                    fg=MUTED_2,
                    font=("Segoe UI", 8),
                    padx=12
                )

                hint.pack(side="right")

                parts = (row, mark, title, hint)

                def paint(colour):

                    for part in parts + ((cross,) if cross else ()):
                        part.configure(bg=colour)

                for part in parts:

                    part.bind("<Enter>", lambda e: paint(HOVER_BG))
                    part.bind("<Leave>", lambda e: paint(PANEL_2))

                    part.bind(
                        "<ButtonRelease-1>",
                        lambda e, n=name: (
                            close_menu(),
                            choose_model(n)
                        )
                    )

            for name in model_names:
                add_row(name, name, model_note(name))

            add_row(None, "Custom\u2026", "Type any model name")

            tk.Frame(inner, bg=PANEL_2, height=4).pack()

            win.update_idletasks()

            width = dropdown.winfo_width()
            full = win.winfo_reqheight()
            left = dropdown.winfo_rootx()
            top = dropdown.winfo_rooty() + dropdown.winfo_height() + 4

            win._geo = (width, full, left, top)

            anchor = (dropdown.winfo_rootx(), dropdown.winfo_rooty())

            # The window keeps its full size the whole time (resizing a
            # window every frame is what made it stutter); it only
            # fades in and slides down a few pixels.
            win.geometry(f"{width}x{full}+{left}+{top - 10}")

            win.attributes("-alpha", 0.0)

            win.deiconify()
            win.lift()

            menu["win"] = win

            self._model_menu_closer = lambda: close_menu(False)

            steps = 7

            def grow(i=1):

                try:

                    if menu["win"] is not win:
                        return

                    t = 1 - (1 - i / steps) ** 3

                    win.geometry(
                        f"{width}x{full}+{left}+{top - int(10 * (1 - t))}"
                    )

                    win.attributes("-alpha", t)

                    if i < steps:
                        win.after(14, lambda: grow(i + 1))

                except Exception:
                    pass

            grow()

            started = time.time()

            def watch():

                try:

                    if menu["win"] is not win:
                        return

                    if (
                        dropdown.winfo_rootx(),
                        dropdown.winfo_rooty()
                    ) != anchor:

                        close_menu(False)

                        return

                    import ctypes

                    pressed = (
                        ctypes.windll.user32.GetAsyncKeyState(0x01)
                        & 0x8000
                    )

                    if pressed and time.time() - started > 0.2:

                        px, py = win.winfo_pointerxy()

                        def inside(widget):

                            return (
                                widget.winfo_rootx() <= px
                                < widget.winfo_rootx()
                                + widget.winfo_width()
                                and widget.winfo_rooty() <= py
                                < widget.winfo_rooty()
                                + widget.winfo_height()
                            )

                        # A click on a row is handled by the row itself.
                        if not inside(win) and not inside(dropdown):
                            close_menu()
                            return

                    win.after(25, watch)

                except Exception:
                    pass

            win.after(60, watch)

        for widget in (dropdown, current_label, arrow):

            widget.bind("<Button-1>", open_menu)
            widget.bind("<Enter>", lambda e: tint(HOVER_BG))
            widget.bind("<Leave>", lambda e: tint(PANEL_2))

        dropdown.bind("<Destroy>", lambda e: close_menu(False))

        self._model_menu_closer = lambda: close_menu(False)

        if not getattr(self, "_model_wheel_bound", False):

            self._model_wheel_bound = True

            def wheel_closes(event):

                closer = getattr(self, "_model_menu_closer", None)

                if closer is not None:

                    try:
                        closer()
                    except Exception:
                        pass

            self.bind_all("<MouseWheel>", wheel_closes, add="+")

        tk.Label(
            panel,
            text=(
                "If Gemini ever renames or retires a model, choose "
                "Custom and type the new name — no code changes "
                "needed. Flash-Lite "
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

        test_row = tk.Frame(rem_panel, bg=PANEL)

        test_row.pack(fill="x", padx=25, pady=(10, 0))

        tk.Label(
            test_row, text="Test alarm", bg=PANEL, fg=MUTED,
            font=("Segoe UI", 10)
        ).pack(side="left", padx=(0, 12))

        for level in ("Low", "Medium", "High"):

            self.make_button(
                test_row,
                level,
                lambda l=level: self.test_reminder(l),
                width=8,
                active=priority_color(level)
            ).pack(side="left", padx=(0, 8))

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

        timer_bg_panel = self._build_timer_bg_card()

        sound_panel = self._build_sound_card()

        update_panel = self._build_update_card()

        background_panel = self._build_background_card()

        # Group the cards under headings, in this order.
        order = [
            (self._settings_heading(
                "Appearance",
                "Colours and theme."
            ), None),
            (appearance_panel, (0, 15)),
            (timer_bg_panel, (0, 15)),
            (self._settings_heading(
                "General",
                "The AI connection and reminders."
            ), None),
            (panel_outer, (0, 15)),
            (rem_panel_outer, (0, 15)),
            (sound_panel, (0, 15)),
            *(
                [(startup_panel, (0, 15))]
                if startup_panel is not None
                else []
            ),
            (background_panel, (0, 15)),
            (update_panel, (0, 15)),
            (self._settings_heading(
                "Focus Mode",
                "Timer length, distraction alerts and the clock."
            ), None),
            (focus_panel_outer, (0, 15)),
            (float_panel_outer, (0, 15)),
            (self._settings_heading(
                "Data",
                "Back up, restore or clear what you've stored in Studestics."
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
            appearance_panel, sound_panel, update_panel,
            background_panel
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

    # --------------------------------------------------------
    # Custom themes: files, import, and "from a picture"
    # --------------------------------------------------------

    def open_themes_folder(self):

        try:

            THEMES_DIR.mkdir(parents=True, exist_ok=True)

            if sys.platform == "win32":
                os.startfile(str(THEMES_DIR))

        except Exception:
            pass

    def _save_custom_theme(self, name, theme):
        """Writes the theme file, selects the theme and refreshes the
        Settings page (the new colours apply after a restart)."""

        safe = re.sub(r"[^\w-]+", "_", name).strip("_") or "theme"

        path = THEMES_DIR / f"{safe}.css"

        THEMES_DIR.mkdir(parents=True, exist_ok=True)

        path.write_text(theme_to_css(name, theme), encoding="utf-8")

        load_custom_themes()

        for loaded, file in CUSTOM_THEME_FILES.items():

            if file == path:

                self.db.set_setting("theme", loaded)

                break

        self.show_page("Settings")

    def remove_custom_theme(self, name):
        """Deletes a theme the user added (its file in the themes
        folder). The built-in themes can't be removed."""

        path = CUSTOM_THEME_FILES.get(name)

        if not path:
            return

        if not messagebox.askyesno(
            "Remove theme",
            f'Remove the theme "{name}"? Its file is deleted from '
            "the themes folder."
        ):
            return

        try:
            Path(path).unlink()
        except Exception as exc:
            messagebox.showerror("Remove theme", str(exc))
            return

        if (self.db.get_setting("theme", "") or THEME_NAME) == name:
            self.db.set_setting("theme", "Purple")

        load_custom_themes()

        if name == THEME_NAME:
            # still running with it until the next restart
            THEMES[THEME_NAME] = _THEME
            REMOVED_THEMES.add(name)

        self.show_page("Settings")

    def import_theme_file(self):

        path = filedialog.askopenfilename(
            title="Import a theme",
            filetypes=[("Theme files", "*.css"), ("All files", "*.*")]
        )

        if not path:
            return

        try:

            parsed = parse_theme_css(
                Path(path).read_text(encoding="utf-8", errors="ignore"),
                Path(path).stem
            )

        except Exception as exc:

            messagebox.showerror("Import theme", f"Couldn't read it.\n{exc}")

            return

        if not parsed:

            messagebox.showinfo(
                "Import theme",
                "A theme file needs at least a background and an accent "
                "colour, like:\n\n--bg: #101018;\n--accent: #7aa2f7;"
            )

            return

        name, theme = parsed

        if name in BUILTIN_THEMES:
            name += " (custom)"

        self._save_custom_theme(name, theme)

    def _set_timer_background(self, path):
        """Keeps a copy of the picture and remembers it."""

        folder = APP_DIR / "backgrounds"

        folder.mkdir(parents=True, exist_ok=True)

        for old in folder.glob("timer_bg.*"):

            try:
                old.unlink()
            except Exception:
                pass

        dest = folder / ("timer_bg" + Path(path).suffix.lower())

        shutil.copyfile(path, dest)

        self.db.set_setting("timer_bg_path", str(dest))

        return dest

    def theme_from_picture(self):

        if not HAS_PIL:

            messagebox.showinfo(
                "Theme from picture", "This needs the Pillow package."
            )

            return

        path = filedialog.askopenfilename(
            title="Pick a picture",
            filetypes=[
                ("Pictures", "*.png *.jpg *.jpeg *.webp *.bmp *.gif"),
                ("All files", "*.*")
            ]
        )

        if not path:
            return

        try:
            colours, preview = picture_palette(path)
        except Exception as exc:

            messagebox.showerror(
                "Theme from picture", f"Couldn't read that picture.\n{exc}"
            )

            return

        win = tk.Toplevel(self)

        win.title("Theme from picture")

        tk.Frame(win, bg=PURPLE, height=4).pack(fill="x")
        win.configure(bg=BG)
        win.resizable(False, False)
        win.transient(self)
        win.grab_set()

        self.center_window(win, 560, 604)

        self._glow_heading(
            win, "Theme from picture", PURPLE, 18
        ).pack(anchor="w", padx=28, pady=(24, 2))

        tk.Label(
            win,
            text="Click the colour the app should be built around.",
            bg=BG, fg=MUTED, font=("Segoe UI", 10)
        ).pack(anchor="w", padx=28)

        top = tk.Frame(win, bg=BG)

        top.pack(anchor="w", padx=28, pady=(16, 0))

        photo = ImageTk.PhotoImage(preview)

        picture = tk.Label(top, image=photo, bd=0)

        picture.image = photo

        picture.pack(side="left")

        tile = tk.Canvas(
            top, width=126, height=78, bg=BG, highlightthickness=0, bd=0
        )

        tile.pack(side="left", padx=(20, 0), anchor="n")

        swatches = tk.Frame(win, bg=BG)

        swatches.pack(anchor="w", padx=28, pady=(18, 0))

        chosen = {"rgb": colours[0]}

        buttons = []

        def purge_logo():

            for key in [k for k in _LOGO_CACHE if k[1] == "__preview__"]:
                del _LOGO_CACHE[key]

        def show_preview():

            theme = theme_from_accent(chosen["rgb"])

            THEMES["__preview__"] = theme

            purge_logo()

            self._draw_theme_tile(tile, "__preview__", False, theme)

            for rgb, canvas in buttons:

                canvas.delete("all")

                on = rgb == chosen["rgb"]

                canvas.create_oval(
                    3, 3, 33, 33,
                    fill="#%02x%02x%02x" % rgb,
                    outline=TEXT if on else BG,
                    width=3
                )

        for rgb in colours:

            canvas = tk.Canvas(
                swatches, width=36, height=36, bg=BG,
                highlightthickness=0, bd=0, cursor="hand2"
            )

            canvas.pack(side="left", padx=(0, 6))

            buttons.append((rgb, canvas))

            canvas.bind(
                "<Button-1>",
                lambda e, c=rgb: (chosen.update(rgb=c), show_preview())
            )

        tk.Label(
            win, text="Name", bg=BG, fg=MUTED, font=("Segoe UI", 9, "bold")
        ).pack(anchor="w", padx=28, pady=(18, 4))

        name_var = tk.StringVar(
            value=Path(path).stem.replace("_", " ").title()[:24]
        )

        entry = self.make_entry(win, textvariable=name_var)

        entry.pack(fill="x", padx=28, ipady=7)

        use_bg = {"on": True}

        row = tk.Frame(win, bg=BG)

        row.pack(fill="x", padx=28, pady=(16, 0))

        tk.Label(
            row,
            text="Also use it as the full screen timer background",
            bg=BG, fg=TEXT, font=("Segoe UI", 10)
        ).pack(side="left")

        self.make_switch(
            row, on=True, bg=BG,
            command=lambda value: use_bg.update(on=bool(value))
        ).pack(side="right")

        bar = tk.Frame(win, bg=BG)

        bar.pack(side="bottom", fill="x", padx=28, pady=20)

        def close():

            THEMES.pop("__preview__", None)

            purge_logo()

            win.destroy()

        def create():

            name = re.sub(r"[^\w .'()-]", "", name_var.get()).strip()[:24]

            name = name or "Picture theme"

            if name in BUILTIN_THEMES:
                name += " (picture)"

            theme = theme_from_accent(chosen["rgb"])

            try:

                if use_bg["on"]:
                    self._set_timer_background(path)

                THEMES.pop("__preview__", None)

                purge_logo()

                win.destroy()

                self._save_custom_theme(name, theme)

            except Exception as exc:

                messagebox.showerror("Theme from picture", str(exc))

        make = self.make_button(bar, "Create theme", create, width=14)

        make.configure(selected=True)

        make.pack(side="right")

        self.make_button(
            bar, "Cancel", close, width=9
        ).pack(side="right", padx=8)

        win.protocol("WM_DELETE_WINDOW", close)

        show_preview()

        # Exactly as tall as what is in it, so nothing is cut off.
        win.update_idletasks()

        self.center_window(win, 560, win.winfo_reqheight() + 6)

    # --------------------------------------------------------
    # Timer background (Settings card)
    # --------------------------------------------------------

    def _timer_bg_params(self):

        params = {}

        for key, default in TIMER_BG_DEFAULTS.items():

            try:

                params[key] = int(
                    self.db.get_setting(f"timer_bg_{key}", str(default))
                )

            except ValueError:

                params[key] = default

        return params

    def _timer_bg_args(self, size):
        """(cache key, path, sliders) for the saved picture, or None.
        Reads the database, so only call it from the main thread."""

        if not HAS_PIL:
            return None

        path = self.db.get_setting("timer_bg_path", "")

        if not path or not Path(path).exists():
            return None

        try:
            stamp = Path(path).stat().st_mtime
        except OSError:
            return None

        params = self._timer_bg_params()

        key = (path, stamp, tuple(size), tuple(sorted(params.items())))

        return key, path, params

    def timer_background_image(self, size):
        """The picture with the saved sliders applied, or None. The
        last result is kept, so opening the full screen timer is
        instant when it was prepared ahead of time."""

        args = self._timer_bg_args(size)

        if args is None:
            return None

        key, path, params = args

        cached = getattr(self, "_tbg_cache", None)

        if cached and cached[0] == key:
            return cached[1]

        try:
            image = render_timer_background(path, params, tuple(size))
        except Exception:
            return None

        self._tbg_cache = (key, image)

        return image

    def prewarm_timer_background(self):
        """Prepares the picture in the background so the full screen
        timer opens without a wait."""

        try:

            x, y, sw, sh = self._monitor_rect()

            args = self._timer_bg_args((sw, sh))

            if args is None:
                return

            key, path, params = args

            cached = getattr(self, "_tbg_cache", None)

            need_still = not (cached and cached[0] == key)

            need_frames = (
                path.lower().endswith(".gif")
                and not self._frames_ready(key)
            )

            if not need_still and not need_frames:
                return

            def work():

                if need_still:

                    try:
                        image = render_timer_background(
                            path, dict(params), (sw, sh)
                        )
                    except Exception:
                        return

                    self._tbg_cache = (key, image)

                if need_frames:
                    self._make_frames(key, path, dict(params), (sw, sh))

            threading.Thread(target=work, daemon=True).start()

        except Exception:
            pass

    def _frames_ready(self, key):

        cached = getattr(self, "_tbg_frames", None)

        return bool(cached and cached[0] == key)

    def _make_frames(self, key, path, params, size):
        """Prepares the frames of a GIF (runs in a thread, once)."""

        if getattr(self, "_tbg_frames_busy", None) == key:
            return

        self._tbg_frames_busy = key

        try:
            frames = render_timer_frames(path, params, size)
        except Exception:
            frames = None

        self._tbg_frames = (key, frames)

    def _start_bg_animation(self, zen, sw, sh):
        """Plays an animated GIF behind the full screen timer."""

        args = self._timer_bg_args((sw, sh))

        if args is None or not args[1].lower().endswith(".gif"):
            return

        key, path, params = args

        if not self._frames_ready(key):

            threading.Thread(
                target=self._make_frames,
                args=(key, path, dict(params), (sw, sh)),
                daemon=True
            ).start()

        win, canvas = zen["win"], zen["canvas"]

        # One picture the size of the screen; every frame is pasted
        # into it, so nothing new is made per frame.
        screen = ImageTk.PhotoImage(Image.new("RGB", (sw, sh)))

        zen["bg_screen"] = screen

        cursor = {"i": 0, "shown": False}

        def play():

            if getattr(self, "_zen", None) is not zen:
                return

            try:

                if not win.winfo_exists():
                    return

            except Exception:
                return

            if not self._frames_ready(key):

                zen["anim"] = win.after(300, play)

                return

            frames = self._tbg_frames[1]

            if not frames:
                return

            started = time.perf_counter()

            data, wait = frames[cursor["i"] % len(frames)]

            cursor["i"] += 1

            try:

                import io

                with Image.open(io.BytesIO(data)) as picture:

                    picture.load()

                    screen.paste(picture)

                if not cursor["shown"]:

                    canvas.itemconfig("bgpic", image=screen)

                    cursor["shown"] = True

            except Exception:
                return

            spent = (time.perf_counter() - started) * 1000

            zen["anim"] = win.after(max(1, int(wait - spent)), play)

        play()

    def _timer_bg_changed(self):
        """The picture or a slider changed."""

        self.prewarm_timer_background()

    def _make_slider(self, parent, label, low, high, value, on_change):
        """A small slider: on_change(value, final) while dragging and
        once more (final=True) when let go."""

        row = tk.Frame(parent, bg=PANEL)

        tk.Label(
            row, text=label, bg=PANEL, fg=TEXT, width=11, anchor="w",
            font=("Segoe UI", 10)
        ).pack(side="left")

        width = 230

        canvas = tk.Canvas(
            row, width=width, height=26, bg=PANEL,
            highlightthickness=0, bd=0, cursor="hand2"
        )

        canvas.pack(side="left")

        readout = tk.Label(
            row, text=str(value), bg=PANEL, fg=MUTED, width=5,
            anchor="e", font=("Segoe UI", 10)
        )

        readout.pack(side="left")

        state = {"value": value}

        def draw():

            span = width - 20

            x = 10 + (state["value"] - low) / (high - low) * span

            canvas.delete("all")

            canvas.create_line(
                10, 13, width - 10, 13, fill=BORDER, width=4,
                capstyle="round"
            )

            canvas.create_line(
                10, 13, x, 13, fill=PURPLE, width=4, capstyle="round"
            )

            canvas.create_oval(
                x - 8, 5, x + 8, 21, fill=PURPLE_HOVER, outline=""
            )

            readout.configure(text=str(state["value"]))

        def move(event, final=False):

            span = width - 20

            ratio = max(0.0, min(1.0, (event.x - 10) / span))

            state["value"] = int(round(low + ratio * (high - low)))

            draw()

            on_change(state["value"], final)

        canvas.bind("<Button-1>", move)
        canvas.bind("<B1-Motion>", move)
        canvas.bind("<ButtonRelease-1>", lambda e: move(e, True))

        draw()

        return row

    def _build_timer_bg_card(self):

        outer, card = self.rounded_panel(self.page, radius=16, fit=True)

        tk.Label(
            card, text="Timer background", bg=PANEL, fg=TEXT,
            font=("Segoe UI", 11, "bold")
        ).pack(anchor="w", padx=25, pady=(18, 2))

        tk.Label(
            card,
            text=(
                "A picture behind the timer when you press F or the "
                "full screen button."
            ),
            bg=PANEL, fg=MUTED_2, font=("Segoe UI", 9)
        ).pack(anchor="w", padx=25)

        body = tk.Frame(card, bg=PANEL)

        body.pack(anchor="w", padx=25, pady=(14, 16))

        left = tk.Frame(body, bg=PANEL)

        left.pack(side="left", anchor="n")

        pw, ph = 384, 216

        preview = tk.Canvas(
            left, width=pw, height=ph, bg=PANEL_2, highlightthickness=1,
            highlightbackground=BORDER, bd=0
        )

        preview.pack()

        right = tk.Frame(body, bg=PANEL)

        right.pack(side="left", anchor="n", padx=(26, 0))

        params = self._timer_bg_params()

        state = {"base": None, "job": None, "photo": None}

        def load_base():

            state["base"] = None

            path = self.db.get_setting("timer_bg_path", "")

            if not path or not Path(path).exists() or not HAS_PIL:
                return

            try:

                from PIL import ImageOps

                with Image.open(path) as opened:

                    state["base"] = ImageOps.fit(
                        ImageOps.exif_transpose(opened).convert("RGB"),
                        (pw, ph), Image.LANCZOS
                    )

            except Exception:
                state["base"] = None

        def redraw():

            state["job"] = None

            try:
                preview.delete("all")
            except Exception:
                return

            if state["base"] is None:

                preview.create_text(
                    pw / 2, ph / 2,
                    text="No picture yet",
                    fill=MUTED_2, font=("Segoe UI", 10)
                )

                return

            image = adjust_picture(state["base"], params)

            state["photo"] = ImageTk.PhotoImage(image)

            preview.create_image(0, 0, anchor="nw", image=state["photo"])

            preview.create_text(
                pw / 2, ph / 2, text="25:00", fill=TEXT,
                font=("Segoe UI", -52, "bold")
            )

        def soon():

            if state["job"] is None:
                state["job"] = preview.after(60, redraw)

        def pick():

            path = filedialog.askopenfilename(
                title="Pick a picture",
                filetypes=[
                    ("Pictures", "*.png *.jpg *.jpeg *.webp *.bmp *.gif"),
                    ("All files", "*.*")
                ]
            )

            if not path:
                return

            try:
                self._set_timer_background(path)
            except Exception as exc:
                messagebox.showerror("Timer background", str(exc))
                return

            load_base()
            redraw()

            self._timer_bg_changed()

        def remove():

            self.db.set_setting("timer_bg_path", "")

            load_base()
            redraw()

            self._timer_bg_changed()

        buttons = tk.Frame(right, bg=PANEL)

        buttons.pack(anchor="w", pady=(0, 10))

        self.make_button(
            buttons, "Choose picture", pick, width=14
        ).pack(side="left")

        self.make_button(
            buttons, "Remove", remove, width=8
        ).pack(side="left", padx=8)

        tk.Label(
            right,
            text="GIFs work too, and move in the full screen timer.",
            bg=PANEL, fg=MUTED_2, font=("Segoe UI", 9)
        ).pack(anchor="w", pady=(0, 8))

        def slider(key, label, low, high):

            def changed(value, final):

                params[key] = value

                soon()

                if final:

                    self.db.set_setting(f"timer_bg_{key}", str(value))

                    self._timer_bg_changed()

            self._make_slider(
                right, label, low, high, params[key], changed
            ).pack(anchor="w", pady=2)

        slider("brightness", "Brightness", 20, 200)
        slider("saturation", "Saturation", 0, 200)
        slider("hue", "Hue", -180, 180)
        slider("blur", "Blur", 0, 40)
        slider("darkness", "Darkness", 0, 90)

        def reset():

            for key, default in TIMER_BG_DEFAULTS.items():

                params[key] = default

                self.db.set_setting(f"timer_bg_{key}", str(default))

            self._timer_bg_changed()

            self.show_page("Settings")

        self.make_button(
            right, "Reset sliders", reset, width=13
        ).pack(anchor="w", pady=(10, 0))

        load_base()
        redraw()

        tk.Frame(card, bg=PANEL, height=16).pack()

        return outer

    def _build_data_card(self):

        outer, card = self.rounded_panel(
            self.page,
            radius=16,
            fit=True
        )

        rows = (
            (
                "Back up and restore",
                "Save everything to a file, or restore it from one. "
                "Restoring replaces your data and restarts the app.",
                (
                    ("Back up", self.backup_data),
                    ("Restore", self.restore_data)
                ),
                None
            ),
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

            if isinstance(button, tuple):

                # The two buttons sit side by side on the right.
                buttons = tk.Frame(row, bg=PANEL)

                buttons.pack(side="right")

                for position, (label, action) in enumerate(button):

                    self.make_button(
                        buttons,
                        label,
                        action,
                        width=10
                    ).pack(
                        side="left",
                        padx=(10 if position else 0, 0)
                    )

            else:

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

    def _draw_theme_tile(self, canvas, name, selected, t=None):
        """One theme preview tile."""


        t = t or THEMES[name]

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

        # The theme's logo, small, in the top right corner.
        if HAS_PIL:

            canvas.logo_photo = ImageTk.PhotoImage(
                app_icon_image(18, name)
            )

            canvas.create_image(
                w - 30, 13, anchor="nw", image=canvas.logo_photo
            )

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
            self._draw_theme_tile(canvas, name, selected)

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

        shown = 0
        row = None

        for name in list(THEMES):

            if name.startswith("__") or name in REMOVED_THEMES:
                continue

            if shown % 9 == 0:

                row = tk.Frame(tiles, bg=PANEL)

                row.pack(anchor="w", pady=(0, 6))

            shown += 1

            cell = tk.Frame(row, bg=PANEL)

            cell.pack(side="left", padx=4, anchor="n")

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

            if name in CUSTOM_THEME_FILES:

                pill = tk.Canvas(
                    cell,
                    width=64,
                    height=20,
                    bg=PANEL,
                    highlightthickness=0,
                    bd=0,
                    cursor="hand2"
                )

                pill.pack(pady=(5, 0))

                def paint(hover, c=pill):

                    c.delete("all")

                    self._draw_bubble_background(
                        c, 64, 20, 10,
                        DANGER_HOVER if hover else PANEL_2
                    )

                    c.create_text(
                        32, 10,
                        text="Remove",
                        fill="#FFFFFF" if hover else MUTED,
                        font=("Segoe UI", 8)
                    )

                paint(False)

                pill.bind("<Enter>", lambda e, f=paint: f(True))
                pill.bind("<Leave>", lambda e, f=paint: f(False))

                pill.bind(
                    "<Button-1>",
                    lambda e, n=name: self.remove_custom_theme(n)
                )

        actions = tk.Frame(card, bg=PANEL)

        actions.pack(anchor="w", padx=25, pady=(6, 4))

        self.make_button(
            actions, "Theme from picture", self.theme_from_picture,
            width=17
        ).pack(side="left")

        self.make_button(
            actions, "Import theme", self.import_theme_file, width=13
        ).pack(side="left", padx=8)

        self.make_button(
            actions, "Themes folder", self.open_themes_folder, width=13
        ).pack(side="left")

        tk.Label(
            card,
            text=(
                "Themes are small .css files with colour variables. "
                "Drop one in the themes folder or import it, and share "
                "yours the same way."
            ),
            bg=PANEL,
            fg=MUTED_2,
            font=("Segoe UI", 9)
        ).pack(anchor="w", padx=25, pady=(0, 4))

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

    def _run_in_background(self):

        try:
            return self.db.get_setting("run_in_background", "1") != "0"
        except Exception:
            return True

    def _build_background_card(self):

        outer, card = self.rounded_panel(
            self.page,
            radius=16,
            fit=True
        )

        row = tk.Frame(card, bg=PANEL)

        row.pack(fill="x", padx=25, pady=18)

        left = tk.Frame(row, bg=PANEL)

        left.pack(side="left", fill="x", expand=True)

        tk.Label(
            left,
            text="Run in background",
            bg=PANEL,
            fg=TEXT,
            font=("Segoe UI", 11, "bold")
        ).pack(anchor="w")

        tk.Label(
            left,
            text="On: closing the window keeps Studestics in the tray so "
                 "reminders still fire. Off: closing the window quits the app.",
            bg=PANEL,
            fg=MUTED_2,
            font=("Segoe UI", 9),
            wraplength=560,
            justify="left"
        ).pack(anchor="w", pady=(2, 0))

        enabled = self._run_in_background()

        self.settings_background_button = self.make_button(
            row,
            "On" if enabled else "Off",
            self.toggle_background,
            width=8
        )

        self.settings_background_button.configure(selected=enabled)

        self.settings_background_button.pack(side="right")

        return outer

    def toggle_background(self):

        target = not self._run_in_background()

        try:
            self.db.set_setting("run_in_background", "1" if target else "0")
        except Exception:
            pass

        try:
            self.settings_background_button.configure(
                text="On" if target else "Off",
                selected=target
            )
        except Exception:
            pass

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

    def backup_data(self):
        """Saves a consistent copy of the database to a chosen file."""

        path = filedialog.asksaveasfilename(
            parent=self,
            title="Back up your data",
            defaultextension=".db",
            initialfile=f"Studestics backup {date.today().isoformat()}.db",
            filetypes=[("Studestics backup", "*.db"), ("All files", "*.*")]
        )

        if not path:
            return

        try:

            with self.db.lock:

                target = sqlite3.connect(path)

                try:
                    self.db.connection.backup(target)
                finally:
                    target.close()

        except Exception as exc:

            messagebox.showerror(
                "Back up",
                f"Couldn't save the backup:\n{exc}",
                parent=self
            )

            return

        messagebox.showinfo(
            "Back up",
            f"Saved to:\n{path}\n\n"
            "The backup includes your Gemini API key, so keep it "
            "private. To restore it later, press Restore in this "
            "same section.",
            parent=self
        )

    def restore_data(self):
        """Replaces the whole database with a chosen backup, then
        restarts."""

        path = filedialog.askopenfilename(
            parent=self,
            title="Restore a backup",
            filetypes=[("Studestics backup", "*.db"), ("All files", "*.*")]
        )

        if not path:
            return

        try:

            probe = sqlite3.connect(
                Path(path).resolve().as_uri() + "?mode=ro", uri=True
            )

            try:

                tables = {
                    row[0] for row in probe.execute(
                        "SELECT name FROM sqlite_master "
                        "WHERE type='table'"
                    )
                }

            finally:
                probe.close()

        except Exception:

            tables = set()

        if not {"settings", "tasks", "goals"} <= tables:

            messagebox.showerror(
                "Restore",
                "That file isn't a Studestics backup.",
                parent=self
            )

            return

        if not messagebox.askyesno(
            "Restore",
            "Replace everything in Studestics (tasks, goals, chat, "
            "focus history, settings and your Gemini key) with this "
            "backup?\n\nStudestics will restart. This can't be "
            "undone, so press Back up first if you want to keep what "
            "is here now.",
            icon="warning",
            parent=self
        ):
            return

        try:

            with self.db.lock:

                source = sqlite3.connect(path)

                try:
                    source.backup(self.db.connection)
                finally:
                    source.close()

        except Exception as exc:

            messagebox.showerror(
                "Restore",
                f"Couldn't restore the backup:\n{exc}",
                parent=self
            )

            return

        # The Notes editor must not write its old text back.
        for attr in ("_note_text", "_note_path", "_note_dirty"):

            if hasattr(self, attr):
                delattr(self, attr)

        messagebox.showinfo(
            "Restore",
            "Done. Studestics will restart now.",
            parent=self
        )

        self.restart_app()

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
                "Add tasks with a deadline and a priority, and get "
                "reminders you can snooze or finish right from the pop-up."
            ),
            (
                "calendar",
                PURPLE_HOVER,
                "Build your week",
                "Schedule is a weekly timetable with an alarm for each "
                "block. Or type /schedule in AI Chat and let the AI plan it."
            ),
            (
                "clock",
                YELLOW,
                "Stay on one thing",
                "Pick a task in Focus Mode and start the timer, or run "
                "Pomodoro rounds. A small floating clock follows you."
            ),
            (
                "note",
                GREEN,
                "Notes and quizzes",
                "Write notes, then press Quiz me and the AI turns them "
                "into a quiz. Short on notes? Type /notes in AI Chat."
            ),
            (
                "chat",
                GREEN,
                "Ask for help",
                "Chat with Gemini about your plans and study topics. "
                "It needs a free API key, and the next page shows how."
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
        self.after(15000, self._schedule_tick)

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

    # ---- alert cards: reminders, schedule, deadlines ------------

    @staticmethod
    def _row_get(row, key, default=""):

        try:
            value = row[key]
        except (KeyError, IndexError, TypeError):
            return default

        return default if value is None else value

    def _glow_heading(
        self, parent, text, accent, size=18, bg=BG, wrap=None
    ):
        """A heading whose letters have a dark outline so they pop. Falls back to a plain label if the font
        or Pillow isn't available."""

        def plain():
            return tk.Label(
                parent, text=text, bg=bg, fg=TEXT,
                font=("Segoe UI", size, "bold"), anchor="w",
                justify="left", wraplength=wrap or 0
            )

        # Emoji in the text: the normal label draws them (in colour).
        if not HAS_PIL or has_emoji(text):
            return plain()

        try:
            from PIL import ImageFilter

            font = None
            px = max(10, int(round(self.winfo_fpixels("1i") / 72 * size)))
            big = px * 3

            for path in (
                "C:/Windows/Fonts/segoeuib.ttf",
                "C:/Windows/Fonts/seguisb.ttf",
                "C:/Windows/Fonts/arialbd.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
            ):
                try:
                    font = ImageFont.truetype(path, big)
                    break
                except Exception:
                    continue

            if font is None:
                return plain()

            probe = ImageDraw.Draw(Image.new("RGB", (4, 4)))

            max_w = (wrap or 10000) * 3

            lines, current = [], ""

            for word in text.split(" "):
                trial = (current + " " + word).strip()
                if current and probe.textlength(trial, font=font) > max_w:
                    lines.append(current)
                    current = word
                else:
                    current = trial

            lines.append(current)

            stroke = max(3, int(big * 0.07))

            ascent, descent = font.getmetrics()

            line_h = ascent + descent + stroke

            pad = int(big * 0.14)

            pad_y = stroke + 4

            width = int(
                max(probe.textlength(l, font=font) for l in lines)
            ) + pad * 2

            height = line_h * len(lines) + pad_y * 2

            def layer(**kw):
                img = Image.new("L", (width, height), 0)
                d = ImageDraw.Draw(img)
                for n, line in enumerate(lines):
                    d.text((pad, pad_y + n * line_h), line, font=font,
                           fill=255, **kw)
                return img

            ring = layer(stroke_width=stroke)
            fill = layer()

            canvas = Image.new("RGB", (width, height), _hex_rgb(bg))

            tint = Image.new("RGB", (width, height), (8, 8, 14))

            canvas.paste(tint, (0, 0), ring)
            canvas.paste(
                Image.new("RGB", (width, height), _hex_rgb(TEXT)),
                (0, 0), fill
            )

            canvas = canvas.resize(
                (width // 3, height // 3), Image.LANCZOS
            )

            photo = ImageTk.PhotoImage(canvas)

            label = tk.Label(parent, image=photo, bg=bg, bd=0, anchor="w")

            label.image = photo

            return label

        except Exception:
            return plain()

    def _form_header(
        self, win, kicker, heading, icon, pady=(22, 16), padx=28,
        accent=PURPLE
    ):
        """Badge + small label + big heading, like the alert cards."""

        head = tk.Frame(win, bg=BG)

        head.pack(fill="x", padx=padx, pady=pady)

        photo = self._alert_badge(icon, accent, 48)

        badge = tk.Label(head, image=photo, bg=BG, bd=0)

        badge.image = photo

        badge.pack(side="left")

        column = tk.Frame(head, bg=BG)

        column.pack(side="left", padx=(14, 0))

        tk.Label(
            column, text=kicker.upper(), bg=BG, fg=accent,
            font=("Segoe UI", 10, "bold")
        ).pack(anchor="w")

        self._glow_heading(
            column, heading, accent, 19
        ).pack(anchor="w")

        return head

    def _alert_badge(self, icon, accent, size=56):
        """Round tinted badge with a glyph, drawn at 4x for smooth
        edges."""

        scale = 4

        big = size * scale

        img = Image.new("RGBA", (big, big), _hex_rgb(BG) + (255,))

        ImageDraw.Draw(img).ellipse(
            [0, 0, big - 1, big - 1],
            fill=_hex_rgb(mix_color(accent, BG, 0.80))
        )

        img = img.resize((size, size), Image.LANCZOS)

        glyph = nav_icon_image(icon, accent, 26)

        img.paste(glyph, ((size - 26) // 2, (size - 26) // 2), glyph)

        return ImageTk.PhotoImage(img)

    def _alert_shell(
        self, kicker, heading, accent, icon, subtitle="", width=500
    ):
        """The look shared by every alert: a coloured top edge, a
        round badge, a small label, a big heading and a quiet line
        under it, with room for rows and a button area."""

        win = tk.Toplevel(self)
        win.withdraw()
        win._glow = accent
        win.configure(bg=BG)
        win.attributes("-topmost", True)
        win.resizable(False, False)

        strip = tk.Frame(win, bg=accent, height=4)

        strip.pack(fill="x")

        foot = tk.Frame(win, bg=BG)

        foot.pack(side="bottom", fill="x", padx=28, pady=(14, 20))

        tk.Frame(win, bg=BORDER, height=1).pack(side="bottom", fill="x")

        head = tk.Frame(win, bg=BG)

        head.pack(fill="x", padx=28, pady=(22, 0))

        photo = self._alert_badge(icon, accent)

        badge = tk.Label(head, image=photo, bg=BG, bd=0)

        badge.image = photo

        badge.pack(side="left", anchor="center")

        column = tk.Frame(head, bg=BG)

        column.pack(side="left", fill="x", expand=True, padx=(16, 0))

        kicker_label = tk.Label(
            column, text=kicker.upper(), bg=BG, fg=accent,
            font=("Segoe UI", 11, "bold")
        )

        kicker_label.pack(anchor="w")

        # Longer headings get a smaller size so they still fit.
        n = len(heading)

        heading_size = (
            20 if n <= 22 else 18 if n <= 34 else
            16 if n <= 48 else 14 if n <= 70 else 12
        )

        title_label = self._glow_heading(
            column, heading, accent, heading_size, wrap=width - 130
        )

        title_label.pack(anchor="w", fill="x")

        sub_label = tk.Label(
            column, text=subtitle, bg=BG, fg=MUTED,
            font=("Segoe UI", 10), anchor="w", justify="left",
            wraplength=width - 130
        )

        if subtitle:
            sub_label.pack(anchor="w", fill="x", pady=(2, 0))

        body = tk.Frame(win, bg=BG)

        body.pack(fill="x", padx=28, pady=(16, 0))

        win.bind("<Escape>", lambda e: win.destroy())

        return {
            "win": win, "strip": strip, "foot": foot, "body": body,
            "kicker": kicker_label, "title": title_label,
            "sub": sub_label, "width": width
        }

    def _alert_show(self, shell):
        """Size, centre and fade the card in."""

        win = shell["win"]

        win.update_idletasks()

        width = max(shell["width"], win.winfo_reqwidth() + 8)

        height = win.winfo_reqheight() + 4
        x = max(0, (win.winfo_screenwidth() - width) // 2)
        y = max(0, (win.winfo_screenheight() - height) // 2 - 30)
        geo = f"{width}x{height}+{x}+{y}"
        def strip_buttons():
            try:
                import ctypes
                user32 = ctypes.windll.user32
                hwnd = user32.GetParent(win.winfo_id()) or win.winfo_id()
                style = user32.GetWindowLongW(hwnd, -16)
                user32.SetWindowLongW(
                    hwnd, -16, style & ~(0x20000 | 0x10000)
                )
                user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x37)
            except Exception:
                pass

        win.geometry(geo)
        strip_buttons()
        win.deiconify()
        win.after(60, strip_buttons)
        win.geometry(geo)
        win.after(40, lambda: win.winfo_exists() and win.geometry(geo))


    def _alert_row(
        self, parent, accent, title, meta="", meta_color=None, action=None
    ):
        """One item card: rounded, with a coloured edge, the title, a
        small line under it and an optional button on the right that
        sits on its own darker pill."""

        row, card = self.rounded_panel(
            parent, radius=12, accent=accent, fit=True
        )

        row.pack(fill="x", pady=4)

        if action is not None:

            label, command = action

            holder = tk.Frame(card, bg=PANEL)

            holder.pack(side="right", padx=(0, 10), pady=8)

            button = self.make_button(holder, label, command, width=6)

            row.action_button = button

            # Darker than the card, so it reads as set into it.
            button.idle_color = mix_color(PANEL, BG, 0.6)

            button._redraw()

            button.pack()

        column = tk.Frame(card, bg=PANEL)

        column.pack(
            side="left", fill="x", expand=True, padx=(14, 6), pady=10
        )

        if len(title) > 34:
            title = title[:33] + "…"

        tk.Label(
            column, text=title, bg=PANEL, fg=TEXT,
            font=("Segoe UI", 11, "bold"), anchor="w"
        ).pack(anchor="w")

        meta_label = None

        if meta:
            meta_label = tk.Label(
                column, text=meta, bg=PANEL, fg=meta_color or MUTED_2,
                font=("Segoe UI", 9), anchor="w"
            )
            meta_label.pack(anchor="w")

        return row, meta_label

    def _alert_snooze_row(self, foot, minutes_list, command, mute=None):
        """'Snooze  5m 10m 30m' pills, and an optional Mute."""

        outer = tk.Frame(foot, bg=BG)

        outer.pack(fill="x", pady=(0, 12))

        line = tk.Frame(outer, bg=BG)

        line.pack()

        tk.Label(
            line, text="Snooze", bg=BG, fg=MUTED,
            font=("Segoe UI", 9)
        ).pack(side="left", padx=(0, 10))

        for minutes in minutes_list:

            text = f"{minutes}m" if minutes < 60 else f"{minutes // 60}h"

            self.make_button(
                line, text, lambda m=minutes: command(m), width=4
            ).pack(side="left", padx=(0, 6))

        if mute is not None:

            self.make_button(line, "Mute", mute, width=6).pack(
                side="left", padx=(10, 0)
            )

        return line

    def _start_focus_from_alert(self, task_id=None):

        try:

            if task_id is not None:
                self.focus_task_id = task_id

            self.restore_window()

            self.show_page("Focus Mode")

            if not self.focus_running:
                self.after(350, self.toggle_focus)

        except Exception:
            pass

    def _small_popup(
        self, title, heading, lines, buttons, accent=None, icon="clock"
    ):
        """A small always-on-top alert in the shared card style.
        `buttons` is a list of (label, command, primary)."""

        if accent is None:

            low = heading.lower()

            accent = RED if ("reached" in low or "removed" in low) else YELLOW

        shell = self._alert_shell(title, heading, accent, icon)

        win = shell["win"]

        win.title(title)

        self._nudge_beep()

        if lines:

            card = tk.Frame(shell["body"], bg=PANEL_2)

            card.pack(fill="x")

            tk.Frame(card, bg=accent, width=4).pack(side="left", fill="y")

            inner = tk.Frame(card, bg=PANEL_2)

            inner.pack(side="left", fill="x", expand=True, padx=14, pady=10)

            for line in lines:

                tk.Label(
                    inner, text=line, bg=PANEL_2,
                    fg=TEXT if line else MUTED, font=("Segoe UI", 10),
                    anchor="w", justify="left", wraplength=400
                ).pack(anchor="w", pady=1)

        bar = tk.Frame(shell["foot"], bg=BG)

        bar.pack(fill="x")

        for label, command, primary in reversed(buttons):

            button = self.make_button(
                bar, label,
                lambda c=command: (c(), win.destroy()),
                width=10,
                active=RED if label == "Dismiss" else PURPLE_HOVER
            )

            if primary:
                button.configure(selected=True)

            button.pack(side="right", padx=(8, 0))

        self._alert_show(shell)

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
                once_due = []
                seen = set()

                for task in pending:

                    task_id = task["id"]
                    seen.add(task_id)

                    # One-time reminder: fires once at its date and
                    # time (or when the app next runs, if it was
                    # closed then), and never repeats.
                    try:
                        at_text = task["remind_at"] or ""
                    except (KeyError, IndexError):
                        at_text = ""

                    if at_text:

                        try:

                            when = datetime.strptime(
                                at_text, "%Y-%m-%d %H:%M:%S"
                            )

                            if (
                                not task["remind_done"]
                                and datetime.now() >= when
                            ):
                                once_due.append(task)

                        except Exception:
                            pass

                        continue

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

                if due or once_due:

                    for task in due:
                        self._reminder_last[task["id"]] = now

                    for task in once_due:
                        self.db.mark_reminded(task["id"])

                    self.show_reminder(due + once_due)

        except Exception:
            pass

        finally:

            if not self._quitting:
                self.after(20000, self._reminder_tick)

    # --------------------------------------------------------
    # Alarm sound
    # --------------------------------------------------------

    def _alarm_path(self):
        """The wav/mp3 the chosen alarm sound points at."""

        try:

            choice = self.db.get_setting("alarm_sound", "Classic")

            if choice == "Custom":

                custom = self.db.get_setting("alarm_custom", "")

                if custom and Path(custom).exists():
                    return str(custom)

                choice = "Classic"

            if choice not in SOUND_PRESETS:
                choice = "Classic"

            return str(sound_preset_path(choice))

        except Exception:

            return ""

    def play_alarm(self, continuous=False, path=None):
        """The chosen sound once, or — if continuous — over and over
        until stop_alarm() is called. Falls back to plain beeps when
        the sound can't be played."""

        self.stop_alarm()

        stop = threading.Event()
        self._alarm_stop = stop

        path = path or self._alarm_path()

        self._alarm_serial = getattr(self, "_alarm_serial", 0) + 1

        alias = f"studalarm{self._alarm_serial}"

        def play_file():

            if not path or sys.platform != "win32":
                return False

            try:

                kind = (
                    "waveaudio"
                    if str(path).lower().endswith(".wav")
                    else "mpegvideo"
                )

                error, _ = mci_send(
                    f'open "{path}" type {kind} alias {alias}'
                )

                if error:
                    return False

                error, _ = mci_send(f"play {alias}")

                if error:

                    mci_send(f"close {alias}")

                    return False

            except Exception:

                return False

            started = time.time()

            try:

                while not stop.is_set():

                    stop.wait(0.2)

                    error, mode = mci_send(f"status {alias} mode")

                    if error or mode == "stopped":

                        if not continuous:
                            break

                        stop.wait(0.8)

                        if stop.is_set():
                            break

                        mci_send(f"seek {alias} to start")
                        mci_send(f"play {alias}")

                    if not continuous and time.time() - started > 30:
                        break

            finally:

                try:

                    mci_send(f"stop {alias}")
                    mci_send(f"close {alias}")

                except Exception:
                    pass

            return True

        def beeps():

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

        def worker():

            if not play_file():
                beeps()

        threading.Thread(target=worker, daemon=True).start()

    def stop_alarm(self):

        if self._alarm_stop is not None:
            self._alarm_stop.set()

    def _build_sound_card(self):

        outer, card = self.rounded_panel(
            self.page,
            radius=16,
            fit=True
        )

        tk.Label(
            card,
            text="Alarm sound",
            bg=PANEL,
            fg=TEXT,
            font=("Segoe UI", 11, "bold")
        ).pack(anchor="w", padx=25, pady=(18, 2))

        tk.Label(
            card,
            text="Played for reminders and when a focus session ends.",
            bg=PANEL,
            fg=MUTED_2,
            font=("Segoe UI", 9)
        ).pack(anchor="w", padx=25, pady=(0, 8))

        chips = {}

        def current():

            value = self.db.get_setting("alarm_sound", "Classic")

            return value if value in SOUND_PRESETS + ("Custom",) else "Classic"

        def custom_name():

            path = self.db.get_setting("alarm_custom", "")

            if path and Path(path).exists():

                name = re.sub(r"^\d+_", "", Path(path).name)

                return name if len(name) <= 34 else name[:33] + "…"

            return "No file chosen"

        def refresh():

            chosen = current()

            for name, chip in chips.items():

                try:
                    chip.configure(selected=(name == chosen))
                except Exception:
                    pass

            try:
                file_label.configure(text=custom_name())
            except Exception:
                pass

        def preview(name):

            if name == "Custom":

                path = self.db.get_setting("alarm_custom", "")

                if not path or not Path(path).exists():

                    messagebox.showinfo(
                        "Alarm sound",
                        "Choose a sound file first.",
                        parent=self
                    )

                    return

                self.play_alarm(False, path)

            else:

                self.play_alarm(False, str(sound_preset_path(name)))

        def select(name):

            if name == "Custom":

                path = self.db.get_setting("alarm_custom", "")

                if not path or not Path(path).exists():

                    choose_file()

                    return

            self.db.set_setting("alarm_sound", name)

            refresh()

            preview(name)

        def choose_file():

            path = filedialog.askopenfilename(
                title="Choose an alarm sound",
                filetypes=[
                    ("Audio", "*.mp3 *.wav *.wma *.m4a *.aac"),
                    ("All files", "*.*")
                ]
            )

            if not path:
                return

            self.stop_alarm()

            try:

                SOUNDS_DIR.mkdir(parents=True, exist_ok=True)

                source = Path(path)

                safe = re.sub(r"[^A-Za-z0-9._-]", "_", source.name)

                destination = (
                    SOUNDS_DIR /
                    f"{int(datetime.now().timestamp())}_{safe}"
                )

                shutil.copy2(source, destination)

                old = self.db.get_setting("alarm_custom", "")

                self.db.set_setting("alarm_custom", str(destination))
                self.db.set_setting("alarm_sound", "Custom")

                if old and old != str(destination):

                    try:
                        Path(old).unlink(missing_ok=True)
                    except Exception:
                        pass

            except Exception as exc:

                messagebox.showerror(
                    "Alarm sound",
                    str(exc),
                    parent=self
                )

                return

            refresh()

            preview("Custom")

        # One row of buttons: click one to pick it and hear it.
        strip = tk.Frame(card, bg=PANEL)

        strip.pack(fill="x", padx=21, pady=(0, 4))

        for name in SOUND_PRESETS + ("Custom",):

            chip = self.make_button(
                strip,
                "\u25B6  " + name,
                lambda n=name: select(n),
                width=11
            )

            chip.pack(side="left", padx=4)

            chips[name] = chip

        custom_row = tk.Frame(card, bg=PANEL)

        custom_row.pack(fill="x", padx=25, pady=(8, 0))

        tk.Label(
            custom_row,
            text="Your own sound:",
            bg=PANEL,
            fg=MUTED,
            font=("Segoe UI", 9)
        ).pack(side="left")

        file_label = tk.Label(
            custom_row,
            text="",
            bg=PANEL,
            fg=TEXT,
            font=("Segoe UI", 9)
        )

        file_label.pack(side="left", padx=(8, 12))

        self.make_button(
            custom_row,
            "Choose file",
            choose_file,
            width=11
        ).pack(side="left")

        tk.Frame(card, bg=PANEL, height=14).pack()

        refresh()

        return outer

    # --------------------------------------------------------
    # Updates
    # --------------------------------------------------------

    def check_for_updates(self, manual=False):
        """Ask GitHub for the newest release. Quiet unless there is
        something new (or the person pressed the button)."""

        if getattr(self, "_update_busy", False):
            return

        self._update_busy = True

        def say(text, color=None):

            def apply():

                label = getattr(self, "_update_status", None)

                try:

                    if label is not None and label.winfo_exists():
                        label.configure(text=text, fg=color or MUTED_2)

                except Exception:
                    pass

            self.after(0, apply)

        if manual:
            say("Checking…")

        def worker():

            try:

                import json
                import urllib.request

                request = urllib.request.Request(
                    f"https://api.github.com/repos/{UPDATE_REPO}"
                    "/releases/latest",
                    headers={
                        "User-Agent": "Studestics",
                        "Accept": "application/vnd.github+json"
                    }
                )

                with urllib.request.urlopen(request, timeout=12) as reply:
                    data = json.load(reply)

                tag = str(data.get("tag_name", ""))

                if version_tuple(tag) <= version_tuple(VERSION):

                    if manual:
                        say(f"You're up to date (v{VERSION}).", GREEN)

                    return

                asset = None

                for item in data.get("assets", []):

                    if str(item.get("name", "")).lower().endswith(".exe"):

                        asset = item
                        break

                info = {
                    "tag": tag,
                    "notes": str(data.get("body") or "").strip(),
                    "page": str(data.get("html_url") or ""),
                    "url": asset.get("browser_download_url") if asset else "",
                    "size": int(asset.get("size") or 0) if asset else 0,
                    "digest": str(asset.get("digest") or "") if asset else ""
                }

                skipped = self.db.get_setting("update_skipped", "")

                if not manual and skipped == tag:
                    return

                # Already downloaded and swapped in earlier this run.
                if getattr(self, "_update_ready_tag", "") == tag:

                    say(f"{tag} is ready. Restart to use it.", GREEN)

                    return

                if not self._can_self_update(info):

                    say(f"Version {tag} is available.", YELLOW)

                    self.after(0, lambda: self.show_update_popup(info))

                    return

                say(f"Version {tag} is available.", YELLOW)

                self.after(0, lambda: self.show_update_popup(info))

            except Exception:

                if manual:
                    say("Couldn't check. Are you online?", RED)

            finally:

                self._update_busy = False

        threading.Thread(target=worker, daemon=True).start()

    def _auto_update_tick(self):

        try:

            if self.db.get_setting("auto_update_check", "1") == "1":
                self.check_for_updates(False)

        except Exception:
            pass

        if not self._quitting:
            self.after(12 * 3600 * 1000, self._auto_update_tick)

    def _notes_box(self, parent, text):
        """The release notes in a box you can scroll with the mouse
        wheel, so the whole list can be read."""

        frame = tk.Frame(parent, bg=BG)

        box = tk.Text(
            frame,
            width=64,
            height=11,
            bg=BG,
            fg=MUTED,
            font=("Segoe UI", 10),
            wrap="word",
            relief="flat",
            bd=0,
            highlightthickness=0,
            padx=0,
            pady=0,
            cursor="arrow",
            spacing1=1,
            spacing3=1
        )

        box.insert("1.0", self._clean_notes(text, max_lines=None))

        box.configure(state="disabled")

        bar = tk.Canvas(
            frame,
            width=6,
            bg=BG,
            highlightthickness=0,
            bd=0
        )

        def update_bar(first, last):

            first, last = float(first), float(last)

            bar.delete("all")

            if first <= 0.0 and last >= 1.0:
                return

            height = max(1, bar.winfo_height())

            top = first * height
            bottom = max(top + 24, last * height)

            bar.create_rectangle(
                0, top, 6, min(height, bottom),
                fill=BORDER, outline=""
            )

        box.configure(yscrollcommand=update_bar)

        def wheel(event):

            box.yview_scroll(int(-1 * (event.delta / 120)), "units")

            # stop here, so nothing behind the window scrolls too
            return "break"

        box.bind("<MouseWheel>", wheel)

        box.pack(side="left", fill="both", expand=True)

        bar.pack(side="right", fill="y", padx=(8, 0))

        frame.after(200, lambda: update_bar(*box.yview()))

        return frame

    def _clean_notes(self, text, max_lines=7):
        """Release notes are written in Markdown; show them as plain
        lines. max_lines=None keeps all of them, with a blank line
        between sections."""

        lines = []

        for raw in str(text or "").splitlines():

            line = raw.strip()

            if not line:

                if max_lines is None and lines and lines[-1] != "":
                    lines.append("")

                continue

            line = line.lstrip("#").strip()
            line = line.replace("**", "").replace("`", "")

            if line.startswith(("- ", "* ")):
                line = "•  " + line[2:]

            lines.append(line)

        while lines and lines[-1] == "":
            lines.pop()

        if not lines:
            return "No release notes."

        if max_lines is not None and len(lines) > max_lines:
            lines = lines[:max_lines] + ["…"]

        return "\n".join(lines)

    def _can_self_update(self, info):
        """True for the packaged .exe when the release carries one."""

        if getattr(sys, "frozen", False):

            return info.get("url", "").startswith(
                f"https://github.com/{UPDATE_REPO}/releases/download/"
            )

        # Running as a script: the update replaces Studestics.py.
        return Path(__file__).resolve().suffix.lower() in (".py", ".pyw")

    def _fetch_and_swap(self, info, progress=None):
        """Download the new .exe, check it, and put it in place of the
        running one (Windows lets a running .exe be renamed, not
        overwritten). The next start is the new version. Runs in a
        thread; raises if anything goes wrong, leaving the old .exe."""

        import hashlib
        import urllib.request

        if not getattr(sys, "frozen", False):
            return self._fetch_source(info, progress)

        exe = Path(sys.executable)

        fresh = exe.with_name(exe.name + ".new")

        try:

            request = urllib.request.Request(
                info["url"],
                headers={"User-Agent": "Studestics"}
            )

            digest = hashlib.sha256()

            done = 0

            last_pct = -1

            with urllib.request.urlopen(request, timeout=30) as reply:

                total = int(
                    reply.headers.get("Content-Length")
                    or info.get("size")
                    or 0
                )

                with open(fresh, "wb") as handle:

                    while True:

                        chunk = reply.read(262144)

                        if not chunk:
                            break

                        handle.write(chunk)
                        digest.update(chunk)
                        done += len(chunk)

                        if progress:

                            pct = (
                                done * 100 // total if total
                                else -max(1, done)
                            )

                            if pct != last_pct:

                                last_pct = pct
                                progress(pct)

            if info.get("size") and done != info["size"]:
                raise RuntimeError("The download was incomplete.")

            expected = info.get("digest", "").lower()

            if expected.startswith("sha256:") and (
                digest.hexdigest() != expected[7:]
            ):
                raise RuntimeError("The download didn't match its checksum.")

            backup = exe.with_name(exe.name + ".old")

            try:
                backup.unlink()
            except Exception:
                pass

            os.replace(exe, backup)

            try:
                os.replace(fresh, exe)
            except Exception:
                os.replace(backup, exe)
                raise

        except Exception:

            try:
                fresh.unlink()
            except Exception:
                pass

            raise

    def _fetch_source(self, info, progress=None):
        """Script install: download the release's source, take
        Studestics.py out of it and put it in place of this file (the
        old one is kept as .bak)."""

        import io
        import urllib.request
        import zipfile

        script = Path(__file__).resolve()

        code = None

        # Just the one file for this release: small and quick. (The
        # whole source zip is the fallback.)
        try:

            single = urllib.request.Request(
                f"https://raw.githubusercontent.com/{UPDATE_REPO}/"
                f"{info['tag']}/{script.name}",
                headers={"User-Agent": "Studestics"}
            )

            data = bytearray()

            with urllib.request.urlopen(single, timeout=30) as reply:

                total = int(reply.headers.get("Content-Length") or 0)

                while True:

                    chunk = reply.read(65536)

                    if not chunk:
                        break

                    data += chunk

                    if progress:
                        progress(
                            len(data) * 100 // total if total
                            else -max(1, len(data))
                        )

            if data:
                code = bytes(data)

        except Exception:
            code = None

        if code is None:

            request = urllib.request.Request(
                f"https://github.com/{UPDATE_REPO}/archive/refs/tags/"
                f"{info['tag']}.zip",
                headers={"User-Agent": "Studestics"}
            )

            buffer = io.BytesIO()

            with urllib.request.urlopen(request, timeout=30) as reply:

                total = int(reply.headers.get("Content-Length") or 0)

                while True:

                    chunk = reply.read(65536)

                    if not chunk:
                        break

                    buffer.write(chunk)

                    if progress:
                        progress(
                            buffer.tell() * 100 // total if total
                            else -max(1, buffer.tell())
                        )

            with zipfile.ZipFile(buffer) as archive:

                names = [
                    name for name in archive.namelist()
                    if name.rsplit("/", 1)[-1].lower() == script.name.lower()
                ]

                if not names:
                    raise RuntimeError(f"{script.name} isn't in this release.")

                code = archive.read(min(names, key=len))

        compile(code, script.name, "exec")

        # The file inside the release must really be the new version,
        # otherwise the app would restart into the same version again.
        import re

        found = re.search(
            rb'^VERSION\s*=\s*["\']([^"\']+)["\']', code, re.MULTILINE
        )

        packed = found.group(1).decode() if found else "?"

        if version_tuple(packed) != version_tuple(info["tag"]):
            raise RuntimeError(
                f"The {info['tag']} release contains {script.name} "
                f"version {packed}. Re-upload the updated file to the "
                "repo and recreate the release."
            )

        backup = script.with_name(script.name + ".bak")

        try:
            backup.write_bytes(script.read_bytes())
        except Exception:
            pass

        temp = script.with_name(script.name + ".new")

        temp.write_bytes(code)

        os.replace(temp, script)

    def _update_window(self, title, width=580):
        """A themed popup shell: returns (window, body, buttons)."""

        old = getattr(self, "_update_popup", None)

        if old is not None:

            try:
                old.destroy()
            except Exception:
                pass

        win = tk.Toplevel(self)

        self._update_popup = win

        tk.Frame(win, bg=PURPLE, height=4).pack(fill="x")

        win.title(title)
        win.configure(bg=BG)
        win.resizable(False, False)
        win.transient(self)

        buttons = tk.Frame(win, bg=BG)

        buttons.pack(side="bottom", fill="x", padx=28, pady=(10, 22))

        tk.Frame(win, bg=BORDER, height=1).pack(side="bottom", fill="x")

        body = tk.Frame(win, bg=BG)

        body.pack(fill="both", expand=True, padx=28)

        return win, body, buttons

    def _finish_update_window(self, win, width=580):

        win.update_idletasks()

        self.center_window(win, width, max(280, win.winfo_reqheight() + 8))

    def show_changelog(self):
        """What's new in the version that's installed: the release notes
        for this version, read from its GitHub release."""

        if getattr(self, "_changelog_busy", False):
            return

        self._changelog_busy = True

        def say(text, color=None):

            def apply():

                label = getattr(self, "_update_status", None)

                try:

                    if label is not None and label.winfo_exists():
                        label.configure(text=text, fg=color or MUTED_2)

                except Exception:
                    pass

            self.after(0, apply)

        say("Loading the changelog\u2026")

        def worker():

            try:

                import json
                import urllib.request

                request = urllib.request.Request(
                    f"https://api.github.com/repos/{UPDATE_REPO}"
                    f"/releases/tags/v{VERSION}",
                    headers={
                        "User-Agent": "Studestics",
                        "Accept": "application/vnd.github+json"
                    }
                )

                with urllib.request.urlopen(request, timeout=12) as reply:
                    data = json.load(reply)

                notes = str(data.get("body") or "").strip()

                page = str(data.get("html_url") or "")

                if not notes:
                    raise RuntimeError("empty")

                say("Checks GitHub for a newer version when the app starts.")

                self.after(0, lambda: self._changelog_window(notes, page))

            except Exception:

                say(
                    "Couldn't load the changelog. Are you online, and is "
                    f"v{VERSION} published on GitHub?",
                    RED
                )

            finally:

                self._changelog_busy = False

        threading.Thread(target=worker, daemon=True).start()

    def _changelog_window(self, notes, page):

        win, body, buttons = self._update_window("Changelog")

        tk.Label(
            body,
            text="What's new",
            bg=BG,
            fg=TEXT,
            font=("Segoe UI", 18, "bold")
        ).pack(anchor="w", pady=(24, 2))

        tk.Label(
            body,
            text=f"You have Studestics v{VERSION}",
            bg=BG,
            fg=PURPLE_HOVER,
            font=("Segoe UI", 10, "bold")
        ).pack(anchor="w")

        self._notes_box(body, notes).pack(
            anchor="w", fill="x", pady=(14, 0)
        )

        def open_page():

            try:

                import webbrowser

                webbrowser.open(
                    page
                    or f"https://github.com/{UPDATE_REPO}/releases"
                )

            except Exception:
                pass

        close = self.make_button(buttons, "Close", win.destroy, width=9)

        close.configure(selected=True)

        close.pack(side="right")

        self.make_button(
            buttons, "Open on GitHub", open_page, width=15
        ).pack(side="right", padx=(0, 10))

        self._finish_update_window(win)

    def show_update_popup(self, info, reason=""):
        """For when the app can't update itself (running from source,
        or the release has no .exe), or when the automatic update
        failed: explains why and opens the download page."""

        win, body, buttons = self._update_window("Update available")

        tk.Label(
            body,
            text="A new version is out",
            bg=BG,
            fg=TEXT,
            font=("Segoe UI", 18, "bold")
        ).pack(anchor="w", pady=(24, 2))

        tk.Label(
            body,
            text=f"Studestics {info['tag']}  (you have v{VERSION})",
            bg=BG,
            fg=PURPLE_HOVER,
            font=("Segoe UI", 10, "bold")
        ).pack(anchor="w")

        self._notes_box(body, info["notes"]).pack(
            anchor="w", fill="x", pady=(14, 0)
        )

        can_install = self._can_self_update(info)

        if not reason and not can_install:
            reason = "This release has no Studestics.exe attached yet."

        if reason:

            tk.Label(
                body,
                text=reason,
                bg=BG,
                fg=YELLOW,
                font=("Segoe UI", 9),
                wraplength=510,
                justify="left"
            ).pack(anchor="w", pady=(12, 0))

        def open_page():

            try:

                import webbrowser

                webbrowser.open(
                    info["page"]
                    or f"https://github.com/{UPDATE_REPO}/releases/latest"
                )

            except Exception:
                pass

            win.destroy()

        def skip():

            self.db.set_setting("update_skipped", info["tag"])

            win.destroy()

        status = tk.Label(
            body,
            text="",
            bg=BG,
            fg=MUTED,
            font=("Segoe UI", 10, "bold"),
            wraplength=510,
            justify="left"
        )

        status.pack(anchor="w", pady=(10, 0))

        def set_status(text, colour=MUTED):

            def apply():

                try:
                    status.configure(text=text, fg=colour)
                except Exception:
                    pass

            self.after(0, apply)

        def update_now():

            go.configure(state="disabled")
            later.configure(state="disabled")
            skip_btn.configure(state="disabled")

            set_status("Downloading\u2026  0%")

            def work():

                try:

                    def show(pct):

                        if pct >= 0:
                            set_status(f"Downloading\u2026  {pct}%")
                        else:
                            set_status(
                                "Downloading\u2026  "
                                f"{-pct / 1048576:.1f} MB"
                            )

                    self._fetch_and_swap(info, show)

                except Exception as exc:

                    def failed():

                        set_status(f"Update failed: {exc}", RED)

                        go.configure(state="normal", text="Try again")
                        later.configure(state="normal")
                        skip_btn.configure(state="normal")

                    self.after(0, failed)

                    return

                set_status("Updated. Restarting\u2026", GREEN)

                self.after(700, self.restart_app)

            threading.Thread(target=work, daemon=True).start()

        go = self.make_button(
            buttons,
            "Update now" if can_install else "Open download page",
            update_now if can_install else open_page,
            width=14 if can_install else 19
        )

        go.configure(selected=True)

        go.pack(side="right")

        later = self.make_button(
            buttons,
            "Later",
            win.destroy,
            width=8
        )

        later.pack(side="right", padx=(0, 10))

        skip_btn = self.make_button(
            buttons,
            "Skip this version",
            skip,
            width=15
        )

        skip_btn.pack(side="left")

        self._finish_update_window(win)

    def show_update_ready_popup(self, info):
        """The new version is already downloaded and in place; it only
        needs a restart."""

        win, body, buttons = self._update_window("Update ready")

        tk.Label(
            body,
            text="Update ready",
            bg=BG,
            fg=TEXT,
            font=("Segoe UI", 18, "bold")
        ).pack(anchor="w", pady=(24, 2))

        tk.Label(
            body,
            text=(
                f"Studestics {info['tag']} was downloaded in the "
                "background. Restart to start using it."
            ),
            bg=BG,
            fg=PURPLE_HOVER,
            font=("Segoe UI", 10, "bold"),
            wraplength=510,
            justify="left"
        ).pack(anchor="w")

        self._notes_box(body, info["notes"]).pack(
            anchor="w", fill="x", pady=(14, 0)
        )

        go = self.make_button(
            buttons,
            "Restart now",
            lambda: (win.destroy(), self.restart_app()),
            width=14
        )

        go.configure(selected=True)

        go.pack(side="right")

        self.make_button(
            buttons,
            "Restart later",
            win.destroy,
            width=14
        ).pack(side="right", padx=(0, 10))

        self._finish_update_window(win)

    def _build_update_card(self):

        outer, card = self.rounded_panel(
            self.page,
            radius=16,
            fit=True
        )

        row = tk.Frame(card, bg=PANEL)

        row.pack(fill="x", padx=25, pady=18)

        left = tk.Frame(row, bg=PANEL)

        left.pack(side="left", fill="x", expand=True)

        tk.Label(
            left,
            text=f"Updates  ·  v{VERSION}",
            bg=PANEL,
            fg=TEXT,
            font=("Segoe UI", 11, "bold")
        ).pack(anchor="w")

        self._update_status = tk.Label(
            left,
            text="Checks GitHub for a newer version when the app starts.",
            bg=PANEL,
            fg=MUTED_2,
            font=("Segoe UI", 9),
            wraplength=480,
            justify="left"
        )

        self._update_status.pack(anchor="w", pady=(2, 0))

        auto_on = self.db.get_setting("auto_update_check", "1") == "1"

        def toggle():

            now_on = self.db.get_setting("auto_update_check", "1") != "1"

            self.db.set_setting("auto_update_check", "1" if now_on else "0")

            toggle_button.configure(
                text="Auto: On" if now_on else "Auto: Off",
                selected=now_on
            )

        toggle_button = self.make_button(
            row,
            "Auto: On" if auto_on else "Auto: Off",
            toggle,
            width=10
        )

        toggle_button.configure(selected=auto_on)

        toggle_button.pack(side="right")

        self.make_button(
            row,
            "Check now",
            lambda: self.check_for_updates(True),
            width=11
        ).pack(side="right", padx=(0, 8))

        self.make_button(
            row,
            "See changelog",
            self.show_changelog,
            width=13
        ).pack(side="right", padx=(0, 8))

        return outer

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

            was_hidden = self.state() == "withdrawn"

            self.deiconify()

            # Tk brings a hidden maximised window back as a normal one.
            if was_hidden and getattr(self, "_was_zoomed", False):
                self.state("zoomed")

            self.lift()
            self.focus_force()

        except Exception:
            pass

    def show_reminder(self, tasks):
        """Task reminder card: beeps, then stays on top until dealt
        with, even if the main window is hidden in the tray."""

        if self._reminder_popup is not None:

            try:
                self._reminder_popup.destroy()
            except Exception:
                pass

            self._reminder_popup = None

        tasks = list(tasks)

        count = len(tasks)

        rank = {"High": 3, "Medium": 2}

        top = max(tasks, key=lambda t: rank.get(t["priority"], 1))

        accent = priority_color(top["priority"])

        def meta_of(task):
            """('High priority  ·  Overdue by 12 min', colour)"""

            state, label, color = due_info(self._row_get(task, "deadline"))

            text = f"{task['priority']} priority"

            if label:
                text += f"   ·   {label}"

            return text, (color or MUTED_2)

        if count == 1:

            heading = top["title"]

            if len(heading) > 90:
                heading = heading[:89] + "…"

            subtitle = ""

        else:

            heading = f"{count} tasks need you"

            subtitle = "Still waiting for you."

        shell = self._alert_shell("Reminder", heading, accent, "bell", subtitle)

        win = shell["win"]

        self._reminder_popup = win

        win.title("Studestics reminder")

        # Every reminder keeps ringing until you deal with the card;
        # the mute button silences it without closing the card.
        loud = True

        self._attach_alarm(win, loud)

        body = shell["body"]

        live = []

        def finish(task_id, row=None):

            self.stop_alarm()

            if task_id is not None:

                self.db.complete_task(task_id)

                self.show_page(self.current_page)

            if row is not None:

                row.destroy()

                if not [w for w in body.winfo_children() if w.winfo_exists()]:
                    win.destroy()

            else:

                win.destroy()

        if count == 1:

            text, color = meta_of(top)

            shell["sub"].configure(text=text, fg=color)

            shell["sub"].pack(anchor="w", fill="x", pady=(2, 0))

            live.append((top, shell["sub"], "title"))

        else:

            for task in tasks[:4]:

                text, color = meta_of(task)

                row, meta_label = self._alert_row(
                    body, priority_color(task["priority"]), task["title"],
                    text, color
                )

                if task["id"] is not None:

                    self.make_button(
                        row, "Done",
                        lambda tid=task["id"], r=row: finish(tid, r),
                        width=6
                    ).pack(side="right", padx=10, pady=8)

                live.append((task, meta_label, "row"))

            if count > 4:

                tk.Label(
                    body, text=f"+ {count - 4} more", bg=BG, fg=MUTED_2,
                    font=("Segoe UI", 9)
                ).pack(anchor="w", pady=(4, 0))

        # Keep "Overdue by 12 min" honest while the card is open.
        def tick():

            try:

                if not win.winfo_exists():
                    return

                for task, label, _kind in live:

                    text, color = meta_of(task)

                    label.configure(text=text, fg=color)

                win.after(20000, tick)

            except Exception:
                pass

        win.after(20000, tick)

        def snooze(minutes):

            for task in tasks:

                if task["id"] is None:
                    continue

                interval = self.reminder_interval_minutes(task) * 60

                # Make it come due again after `minutes`.
                self._reminder_last[task["id"]] = (
                    time.time() - interval + minutes * 60
                )

            win.destroy()

        foot = shell["foot"]

        self._alert_snooze_row(
            foot, (5, 10, 30, 60), snooze,
            mute=self.stop_alarm if loud else None
        )

        bar = tk.Frame(foot, bg=BG)

        bar.pack()

        first_id = next(
            (t["id"] for t in tasks if t["id"] is not None), None
        )

        def open_app():
            self.restore_window()
            self.show_page("Tasks")
            win.destroy()

        self.make_button(
            bar, "Dismiss", win.destroy, width=9, active=RED
        ).pack(
            side="left", padx=4
        )

        if first_id is not None and count == 1:
            self.make_button(
                bar, "Done", lambda: finish(first_id), width=9
            ).pack(side="left", padx=4)

        if first_id is not None:
            self.make_button(bar, "Open app", open_app, width=9).pack(
                side="left", padx=4
            )
            go = self.make_button(
                bar, "Start focus",
                lambda: (self._start_focus_from_alert(first_id),
                         win.destroy()),
                width=9
            )
        else:
            go = self.make_button(bar, "Open app", open_app, width=9)

        go.configure(selected=True)

        go.pack(side="left", padx=4)

        self._alert_show(shell)

    def test_reminder(self, priority="High"):
        self.show_reminder([
            {
                "id": None,
                "title": (
                    f"Test {priority.lower()} reminder \U0001F514 "
                    "this is what an alarm looks like"
                ),
                "priority": priority
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

                elif isinstance(action, tuple) and action[0] == "menu":
                    self.show_tray_menu(action[1], action[2])

                elif action == "quit":
                    self.quit_app()
                    return

        except queue.Empty:
            pass

        except Exception:
            pass

        if not self._quitting:
            self.after(100, self._poll_tray)

    def _set_app_icon(self):
        """Window / taskbar icon: the packaged studestics.ico if there
        is one, otherwise the same badge drawn in code."""

        try:

            base = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))

            ico = base / "studestics.ico"

            # The packaged .ico is purple, so other themes draw their
            # own coloured logo instead.
            if ico.exists() and THEME_NAME == "Purple":

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

    def show_tray_menu(self, x, y):
        """A small themed menu next to the tray icon."""

        old = getattr(self, "_tray_menu_win", None)

        if old is not None:

            try:
                old.destroy()
            except Exception:
                pass

        win = tk.Toplevel(self)

        self._tray_menu_win = win

        win.withdraw()
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.configure(bg=BORDER)

        inner = tk.Frame(win, bg=PANEL)

        inner.pack(padx=1, pady=1)

        def close(event=None):

            try:
                win.destroy()
            except Exception:
                pass

        def add(text, command, bold=False, colour=TEXT):

            row = tk.Label(
                inner,
                text=text,
                bg=PANEL,
                fg=colour,
                font=("Segoe UI", 10, "bold" if bold else "normal"),
                anchor="w",
                padx=14,
                pady=8,
                cursor="hand2"
            )

            row.pack(fill="x", padx=6, pady=1)

            row.bind("<Enter>", lambda e: row.configure(bg=HOVER_BG))
            row.bind("<Leave>", lambda e: row.configure(bg=PANEL))

            row.bind(
                "<ButtonRelease-1>",
                lambda e: (close(), command())
            )

        tk.Frame(inner, bg=PANEL, height=5).pack()

        add("Open Studestics", self.restore_window, bold=True)

        add(
            "Floating clock: On" if self.float_on
            else "Floating clock: Off",
            self.toggle_float
        )

        tk.Frame(inner, bg=BORDER, height=1).pack(
            fill="x", padx=14, pady=4
        )

        add("Quit", self.quit_app, colour=RED)

        tk.Frame(inner, bg=PANEL, height=5).pack()

        win.update_idletasks()

        width = win.winfo_reqwidth()
        height = win.winfo_reqheight()

        left = max(
            8, min(x - width // 2, self.winfo_screenwidth() - width - 8)
        )

        top = y - height - 12

        if top < 8:
            top = y + 12

        win.geometry(f"{width}x{height}+{left}+{top}")

        try:

            import ctypes

            hwnd = ctypes.windll.user32.GetParent(win.winfo_id()) or \
                win.winfo_id()

            # Rounded corners on Windows 11.
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, 33, ctypes.byref(ctypes.c_int(2)), 4
            )

        except Exception:
            pass

        win.deiconify()
        win.lift()

        try:
            win.focus_force()
        except Exception:
            pass

        win.bind("<Escape>", close)

        started = time.time()

        def watch():

            try:

                if not win.winfo_exists():
                    return

                import ctypes

                pressed = (
                    ctypes.windll.user32.GetAsyncKeyState(0x01) & 0x8000
                    or ctypes.windll.user32.GetAsyncKeyState(0x02) & 0x8000
                )

                if pressed and time.time() - started > 0.25:

                    px, py = win.winfo_pointerxy()

                    inside = (
                        win.winfo_rootx() <= px
                        < win.winfo_rootx() + width
                        and win.winfo_rooty() <= py
                        < win.winfo_rooty() + height
                    )

                    if not inside:
                        close()
                        return

                win.after(50, watch)

            except Exception:
                pass

        win.after(100, watch)

    def _remember_window_state(self):
        """Remember whether the window was maximised, for next launch."""

        try:
            state = self.state()
            if state in ("zoomed", "normal"):
                self._was_zoomed = (state == "zoomed")
            if state in ("zoomed", "normal") and self.db:
                self.db.set_setting("window_state", state)
        except Exception:
            pass

    def hide_to_tray(self):

        self._remember_window_state()

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

            queue_ref = self._tray_queue

            class ThemedIcon(pystray.Icon):
                """Right-click opens Studestics' own menu (drawn in the
                app's theme) instead of the plain Windows one."""

                def _on_notify(self, wparam, lparam):

                    if lparam == 0x0205:    # WM_RBUTTONUP

                        try:

                            import ctypes
                            from ctypes import wintypes

                            point = wintypes.POINT()

                            ctypes.windll.user32.GetCursorPos(
                                ctypes.byref(point)
                            )

                            queue_ref.put(("menu", point.x, point.y))

                            return

                        except Exception:
                            pass

                    return super()._on_notify(wparam, lparam)

            self._tray_icon = ThemedIcon(
                "studestics",
                img,
                "Studestics — reminders running",
                menu
            )

            threading.Thread(
                target=self._tray_icon.run,
                daemon=True
            ).start()

    def close_app(self):

        # With the tray available, the X button hides the app instead
        # of quitting, so reminders keep firing in the background.
        if (
            pystray is not None
            and HAS_PIL
            and not self._quitting
            and self.db is not None
            and self._run_in_background()
        ):

            self.hide_to_tray()
            return

        self.quit_app()

    def quit_app(self):

        self._remember_window_state()

        self._quitting = True

        try:
            self._music_stop()
        except Exception:
            pass

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


def _install_crash_log():
    """Writes errors (and hard crashes) to ~/.studestics/crash.log so
    a problem can be read afterwards instead of the app just closing."""

    import datetime
    import traceback

    log_path = APP_DIR / "crash.log"

    def write(title, text):

        try:

            with open(log_path, "a", encoding="utf-8") as handle:

                handle.write(
                    f"\n--- {datetime.datetime.now():%Y-%m-%d %H:%M:%S}"
                    f"  v{VERSION}  {title}\n{text}\n"
                )

        except Exception:
            pass

    try:

        if log_path.exists() and log_path.stat().st_size > 200000:
            log_path.unlink()

    except Exception:
        pass

    try:

        import faulthandler

        handle = open(log_path, "a", encoding="utf-8")

        faulthandler.enable(file=handle, all_threads=True)

        _SINGLE_INSTANCE_HANDLES.append(handle)

    except Exception:
        pass

    def on_error(kind, value, trace):

        write(kind, "".join(traceback.format_exception(kind, value, trace)))

    sys.excepthook = on_error

    try:

        threading.excepthook = lambda args: on_error(
            args.exc_type, args.exc_value, args.exc_traceback
        )

    except Exception:
        pass

    return write


def main():

    write_log = _install_crash_log()

    # Background threads get a big stack. Building Gemini's data types
    # (pydantic) recurses deeply and crashed the app hard in a normal
    # small-stack thread.
    try:
        threading.stack_size(64 * 1024 * 1024)
    except Exception:
        pass

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

    def tk_error(kind, value, trace):

        import traceback

        write_log(
            "Tk callback",
            "".join(traceback.format_exception(kind, value, trace))
        )

    app.report_callback_exception = tk_error

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
