# Vox

A voice assistant that runs your Windows 11 PC. Press a hotkey, say what you
want, and Vox does it and tells you what it did.

- "Open YouTube in Chrome and search for lofi beats"
- "Create a folder on the desktop and move everything not opened in 20 days into it"
- "Organise my desktop"
- "How much disk space is left?"
- "Undo that"

## Why it is fast

Vox tries the cheapest route first:

1. **Instant path.** Everyday commands (open a program or site, search Google
   or YouTube, volume, media keys, lock, screenshot, undo) are recognised on
   the PC in a few milliseconds. No AI call is made.
2. **AI path.** Everything else goes to Gemini or OpenAI in a single request
   over a connection that is kept open. The model returns every action at
   once, and Vox only asks it again when it needs to read a result.

Speech is recognised on the PC by default, so short commands do not wait on
an upload. The window shows, for every command, how long hearing, thinking
and doing each took.

## Install

1. Install [Python 3.11 or newer](https://www.python.org/downloads/) and tick
   "Add python.exe to PATH".
2. Double-click `install.bat` (a few minutes, first time only).
3. Double-click `run.bat`. The Vox window opens and an icon appears in the
   notification area.
4. In **Settings**, pick Gemini or OpenAI, paste your API key and choose a
   model. Press **Test speed** to confirm it works.

Keys are saved in `%APPDATA%\Vox\config.json` on your PC, never in this repo.
OpenAI access needs an API key from platform.openai.com; a ChatGPT
subscription does not include it.

## Using it

- Press **Ctrl + Alt + Space** and speak. Vox stops listening when you stop.
- Or type into the window.
- Vox asks before deleting, shutting down, reorganising a folder or running
  PowerShell. Answer "yes" or "no" by voice or with the buttons.
- Files are moved, never overwritten. "Undo that" puts them back.

## Good to know

- "Not opened in N days" uses the newest of each file's opened, changed and
  created times, because Windows does not reliably record when a file was
  last opened.
- Closing a program asks it to close, so it can still prompt you to save.

## Status

Automated tests (`python -m pytest`) cover the instant router, the planning
engine, file skills, undo, the settings server, and the Gemini and OpenAI
adapters against simulated responses.

Not yet verified on a real Windows PC: microphone capture, the global hotkey,
spoken replies, program launching, volume control, and live calls to Gemini
and OpenAI. These are the first things to check after installing.

## Next

- Browser control: click results, fill forms, read pages aloud.
- Screen control for any desktop program.
- A wake word ("Vox, ...") instead of the hotkey.
- Access from your phone.

## Layout

    vox/router.py    instant command patterns
    vox/engine.py    decides instant vs AI, runs skills, handles yes/no
    vox/llm.py       Gemini and OpenAI
    vox/tools/       skills: files, apps, web, system
    vox/voice.py     microphone, speech-to-text, speaking, hotkey
    vox/server.py    local API behind the window
    vox/ui/          the window
