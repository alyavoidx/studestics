<div align="center">

<img src="docs/screenshots/logo.png" alt="Studestics" width="110">

# Studestics

**A dark, rounded study planner for Windows.**
Tasks, goals, notes, a schedule, a focus timer and an AI study buddy, in one small app.

[Latest release](https://github.com/alyavoidx/studestics/releases/latest) | [Report a bug](https://github.com/alyavoidx/studestics/issues) | [Changelog](https://github.com/alyavoidx/studestics/releases)

![release](https://img.shields.io/github/v/release/alyavoidx/studestics?style=flat-square&color=b48ef5&label=release)
![downloads](https://img.shields.io/github/downloads/alyavoidx/studestics/total?style=flat-square&color=7aa2f7&label=downloads)
![stars](https://img.shields.io/github/stars/alyavoidx/studestics?style=flat-square&color=e0af68)
![platform](https://img.shields.io/badge/platform-Windows%2010%2B-0a84ff?style=flat-square)
![made with](https://img.shields.io/badge/made%20with-Python%20%2B%20Tkinter-3776ab?style=flat-square)
![license](https://img.shields.io/badge/license-MIT-9ece6a?style=flat-square)

<br>

<img src="docs/screenshots/dashboard.png" alt="Studestics dashboard" width="860">

</div>

> [!CAUTION]
> The only official place to download Studestics is this GitHub repository.
> Any other website, repository or account offering downloads or claiming to be us is not controlled by us. Do not download from them.

<br>

## Contents

- [Install](#install)
- [Features](#features)
- [Screenshots](#screenshots)
- [Keyboard shortcuts](#keyboard-shortcuts)
- [FAQ](#faq)
- [Running from source](#running-from-source)
- [Building the exe](#building-the-exe)
- [Code signing policy](#code-signing-policy)
- [Privacy](#privacy)
- [Contributors](#contributors)
- [Credits](#credits)
- [License](#license)

<br>

## Install

1. Download **`Studestics-Setup.exe`** from the [latest release](https://github.com/alyavoidx/studestics/releases/latest) and run it. A setup wizard lets you pick a folder and tick **Create a desktop shortcut**, and adds a Start menu entry and an uninstaller.
   Prefer no install? Download `Studestics.exe` instead and run it from anywhere.
2. Open Studestics. There is nothing else to set up, and a short tour walks you through the app the first time.
3. Studestics keeps itself up to date: when a new version is out you get an **Update now** button inside the app.

> [!IMPORTANT]
> Studestics is **Windows only** (Windows 10 and above). Your data stays on your computer in a local database.

> [!NOTE]
> Windows SmartScreen may warn about an app it hasn't seen much. Click **More info**, then **Run anyway**. You can also read every line of the source in this repository.

<br>

## Features

### Plan

| | |
|---|---|
| **Tasks** | Deadlines, priorities (Low / Medium / High), descriptions, photo cards, and a "Due in" label on every card. Completed tasks live on their own page. |
| **Reminders** | Repeating reminders with a different pace per priority, or a custom interval per task. A *Next reminder* strip shows the time left for each priority. |
| **Goals** | Longer-term goals with their own cards. |
| **Notes** | A clean text editor with tabs you can drag to reorder. Hit **Quiz me** and Studestics turns a note into a quiz with 1 to 50 questions. |
| **Schedule** | Weekly blocks with repeating days, a running-block highlight, and **Copy this day**. |

### Focus

| | |
|---|---|
| **Timer** | Presets or your own minutes and seconds, linked to a task. |
| **Pomodoro** | Focus rounds with short and long breaks, and a break limit (5 to 30 min) in Settings so breaks stay breaks. |
| **Stopwatch** | Count up with laps. The ring fills through each lap, and the lap list shows fastest and slowest. |
| **Floating clock** | A small always-on-top timer in several styles that appears when you leave the app. |
| **Distraction nudges** | A gentle reminder if you wander off to something else during a session. |
| **Keep awake** | Your PC won't sleep in the middle of a session. |

### Understand

| | |
|---|---|
| **Dashboard** | Today at a glance, with a daily focus target and a "Goal reached" state. |
| **Analytics** | Charts of your focus time, tasks and habits. |
| **Profile** | Your photo, streaks, totals and a 7-day chart. |
| **AI Chat** | Ask questions about your studies. It uses Google Gemini and your own free API key, which you paste in during the first-run tour. |

### Make it yours

- Themes: Purple, Catppuccin, Matcha, Ocean, Rose, Light, Sunset, Ice and Neon (black with soft glowing text). The shortcut icons take on your theme too
- Make a theme from a picture, or load a theme `.css` file
- Timer backgrounds, including GIFs
- Liquid-glass buttons that refract the picture behind them
- Alarm sounds (presets or your own file)
- Smooth start-up animation, which you can turn off
- Lives in the tray, starts quietly at sign-in, and only ever runs one copy
- Emoji in task and goal titles (type `:tick` and friends)

<br>

## Screenshots

<div align="center">

| Tasks | Focus |
|:---:|:---:|
| <img src="docs/screenshots/tasks.png" width="420"> | <img src="docs/screenshots/focus.png" width="420"> |

| Schedule | Analytics |
|:---:|:---:|
| <img src="docs/screenshots/schedule.png" width="420"> | <img src="docs/screenshots/analytics.png" width="420"> |

</div>

<br>

## Keyboard shortcuts

| Where | Keys | Does |
|---|---|---|
| Focus page | `Space` | Start / pause |
| Focus page | `R` | Reset |
| Stopwatch | `L` | Lap |
| Notes | `Ctrl` + `1` to `9` | Jump to that tab (`9` is the last one) |
| Pop-ups | `Enter` / `Esc` | Confirm / close |
| Pop-ups | Arrow keys | Move between options |
| Custom focus time | `Enter` | Set the timer and close the row |

<br>

## FAQ

<details>
<summary><b>Is it free?</b></summary>

Yes. The AI features need a free Google Gemini API key, which you create yourself.
</details>

<details>
<summary><b>Where is my data stored?</b></summary>

In a local database on your computer. Settings has buttons to delete all tasks, all goals, or all user data (your API key is kept).
</details>

<details>
<summary><b>Is there a Mac, Linux or Android version?</b></summary>

No. Studestics is built for Windows only.
</details>

<details>
<summary><b>Does the AI see my notes?</b></summary>

Only when you ask it to, for example when you use **Quiz me** on a note. Those requests go to Google Gemini through your own API key.
</details>

<details>
<summary><b>The window looks cut off or the sidebar is crowded.</b></summary>

Make the window a little taller, or maximise it. The sidebar lists scroll when there isn't enough room, and the app remembers your window size.
</details>

<details>
<summary><b>I found a bug.</b></summary>

Please [open an issue](https://github.com/alyavoidx/studestics/issues) with a screenshot or a short video. It helps a lot.
</details>

<br>

## Running from source

You need Python 3.10 or newer on Windows.

```powershell
git clone https://github.com/alyavoidx/studestics.git
cd studestics
pip install pillow pystray google-genai
python Studestics.py
```

## Building the exe

Double-click `build_exe.bat` (it also bundles the Neon theme font, `ShareTechMono-Regular.ttf`, so keep that file next to `Studestics.py`).

The exe is created in `dist/`. Keep the `VERSION` line at the top of `Studestics.py` equal to the release tag, because the built-in updater compares them.

### Building the installer

Install [Inno Setup](https://jrsoftware.org/isinfo.php) (6.1 or newer), open `Studestics.iss` and press **Ctrl+F9**. The installer doesn't contain the app: it downloads the newest `Studestics.exe` from the latest release, so you only need to compile it once. Every release must include a file named exactly `Studestics.exe`.

<br>

## Code signing policy

Free code signing provided by [SignPath.io](https://signpath.io), certificate by [SignPath Foundation](https://signpath.org).

Studestics.exe is built from the source in this repository by a GitHub Actions workflow ([`.github/workflows/release.yml`](.github/workflows/release.yml)). Every release is signed only after it is approved manually.

| Role | Who |
|---|---|
| Authors (commit access) | [alyavoidx](https://github.com/alyavoidx) |
| Reviewers | [alyavoidx](https://github.com/alyavoidx) |
| Approvers (approve each signing request) | [alyavoidx](https://github.com/alyavoidx) |

## Privacy

Studestics keeps your tasks, goals, notes and settings in a local database on your computer.

It does not send data anywhere on its own. It contacts the network only when:

- **You use an AI feature** (AI Chat, or **Quiz me** on a note). The text you send goes to Google Gemini with your own API key, under [Google's terms](https://ai.google.dev/gemini-api/terms).
- **It checks for updates**, which asks GitHub for the latest release number.

The Gemini features only run when you use them, and you can use the app without ever adding an API key.

<br>

## Contributors

<a href="https://github.com/alyavoidx/studestics/graphs/contributors">
<img src="https://contrib.rocks/image?repo=alyavoidx/studestics" alt="Contributors">
</a>

<br>

## Credits

- Emoji graphics: [Twemoji](https://github.com/jdecked/twemoji), licensed [CC-BY 4.0](https://creativecommons.org/licenses/by/4.0/).
- Emoji names and keywords: [Emojibase](https://emojibase.dev/), MIT licence.
- Neon theme font: [Share Tech Mono](https://fonts.google.com/specimen/Share+Tech+Mono), [SIL Open Font License](OFL-ShareTechMono.txt).
- AI Chat: [Google Gemini](https://ai.google.dev/).

<br>

## License

See [LICENSE](LICENSE).

---

<div align="center">

**Leave a star if you like the project.**

❤️‍🩹🫶🌟

</div>
