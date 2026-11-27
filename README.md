<div align="center">

# Studestics

**A study planner for Windows that keeps your tasks, goals, notes and focus time in one place.**

[![Latest release](https://img.shields.io/github/v/release/alyavoidx/studestics?style=flat-square)](https://github.com/alyavoidx/studestics/releases/latest)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue?style=flat-square)](LICENSE)
![Platform](https://img.shields.io/badge/platform-Windows-0078D6?style=flat-square)

</div>

---

## Download

1. Go to the [latest release](https://github.com/alyavoidx/studestics/releases/latest).
2. Download **`Studestics-Setup.exe`** and run it. It has a setup wizard with a "Create a desktop shortcut" tick box, a Start menu entry and an uninstaller.
3. Prefer no install? Download **`Studestics.exe`** and run it from anywhere.

Windows may show a "Windows protected your PC" screen the first time, because the app is from an independent developer. Click **More info**, then **Run anyway**.

Studestics checks for updates by itself and can update in place, so you only need to download it once.

## What it does

| | |
|---|---|
| **Dashboard** | Your day at a glance: what's due, what's next, how today is going. |
| **Tasks** | Tasks with priorities, due dates and reminders that repeat until you deal with them. |
| **Goals** | Longer-term goals you can track and break down. |
| **Notes** | A tabbed note editor. Drag tabs to reorder them, jump with `Ctrl+1` to `Ctrl+9`, and add links. |
| **Schedule** | Plan your week and see it laid out. |
| **Focus Mode** | A focus timer with distraction alerts, and a floating clock you can leave on screen. |
| **AI Chat** | Ask a study assistant powered by Google Gemini to help plan and explain things. |
| **Analytics** | Focus time per day, streaks, sessions finished and more. |
| **Profile** | Your picture, name and stats. |

Studestics also sits in the **system tray** so reminders keep working when the window is closed. Right-click the tray icon for its own themed menu.

## Themes

Nine themes are built in: **Light, Purple, Catppuccin, Matcha, Ocean, Rose, Sunset, Ice** and **Neon** (black with soft glowing text). You can also add or import your own in **Settings → Themes**. The app and its shortcut icons take on the theme's colours after a restart.

## AI Chat setup

AI Chat uses your own Google Gemini API key:

1. Get a free key from [Google AI Studio](https://aistudio.google.com/apikey).
2. Open **Settings** in Studestics and paste it in.

Messages you send in AI Chat go to Google's Gemini service. Everything else stays on your computer.

## Your data

Everything is saved locally in `C:\Users\<you>\.studestics\`. Uninstalling the app leaves that folder alone, so reinstalling gives you your tasks, notes and settings back.

## Run from source

You need Python 3.10 or newer.

```bash
git clone https://github.com/alyavoidx/studestics.git
cd studestics
pip install -r requirements.txt
python Studestics.py
```

### Build the `.exe`

```bat
build_exe.bat
```

This produces `dist\Studestics.exe`.

### Build the installer

1. Install [Inno Setup](https://jrsoftware.org/isinfo.php) (6.1 or newer).
2. Open `Studestics.iss` and press **Ctrl+F9**.

The installer doesn't contain the app. It downloads the newest `Studestics.exe` from the latest GitHub release, so you only need to compile it once. Every release must include a file named exactly `Studestics.exe`.

### Releasing

Set `VERSION` in `Studestics.py`, build, then publish a GitHub release whose tag matches it (for example `VERSION = "1.7.0"` and tag `v1.7.0`) with `Studestics.exe` attached.

## Credits

- Emoji graphics: [Twemoji](https://github.com/jdecked/twemoji), licensed [CC-BY 4.0](https://creativecommons.org/licenses/by/4.0/).
- Emoji names and keywords: [Emojibase](https://emojibase.dev/), MIT licence.
- Neon theme font: [Share Tech Mono](https://fonts.google.com/specimen/Share+Tech+Mono), [SIL Open Font License](OFL-ShareTechMono.txt).
- AI Chat: [Google Gemini](https://ai.google.dev/).

## License

Released under the [MIT License](LICENSE).

---

<div align="center">

**Leave a star if you like the project.**

🩹 💛 🌟 ✨ 📚 🎯 ☕

</div>
