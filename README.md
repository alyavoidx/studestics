# Studestics

A dark, rounded study planner for Windows: tasks with deadlines and reminders,
goals, a focus timer with a floating clock, analytics, and an AI chat powered
by Gemini.

## Download

Get the latest `Studestics.exe` from the
[Releases](../../releases/latest) page and run it. Windows may show a
SmartScreen warning because the app isn't signed: click **More info**, then
**Run anyway**.

## Run from source

```
pip install -r requirements.txt
python Studestics.py
```

## Build the .exe

Put `Studestics.py`, `build_exe.bat` and `studestics.ico` in one folder and
double-click `build_exe.bat`. The app appears in `dist\Studestics.exe`.

## Your data

Tasks, goals and settings are stored on your own computer in
`C:\Users\<you>\.studestics`. Your Gemini API key stays there too and is never
uploaded anywhere except to Google when you chat.
