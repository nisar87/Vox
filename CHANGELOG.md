# Changelog

## 0.3.1

Fixes from the first real use: Vox misheard speech, took up to 15 seconds to
answer, and its voice was poor.

- **Understands speech far better.** Hearing is now "Automatic": your AI
  provider transcribes what you say, which copes with accents and names such
  as Notepad++. The small on-PC model that heard "Hi Vox" as "Hiles" is now
  only the offline fallback. Existing installs are switched over.
- **Much faster AI answers.** The Gemini model was spending 6 to 14 seconds
  "thinking" about simple commands. Vox now asks for minimal thinking and
  defaults to the fastest model (Gemini 3.5 Flash-Lite).
- **Natural voice.** Replies use your provider's AI voice instead of the
  robotic Windows one. Common sentences are kept on disk so they play
  instantly. If the AI voice fails, Vox says why and falls back to Windows.
  Choose the voice in Settings, Voice, and press "Hear it".
- **Teach Vox your "Hi Vox".** Standby listens on the PC only, so it can
  still mishear the wake phrase. Settings, Hearing, "Teach Vox my Hi Vox"
  records you saying it and learns what your voice sounds like to it.
- **"Open Notepad++ and write a few lines about education"** now goes to the
  AI, which writes the text and types it. "Type hello world" still types
  exactly what you said. "Notepad plus plus" is recognised.
- "Hello" and "thank you" are answered instantly, without the AI.

## 0.3.0

- **Standby: say "Hi Vox".** Switch it on in Settings, Hearing (or from the
  tray icon) and Vox listens in the background with its window closed. Say
  "Hi Vox" and it answers "Yes <your name>, I'm listening", or say it in one
  go: "Hi Vox, open Notepad". What it hears stays on the PC and is discarded
  unless it starts with "Hi Vox".
- **Quiet during calls.** Standby pauses while another program is using the
  microphone (Teams, WhatsApp, Zoom, a browser call) and resumes afterwards.
- **Your name.** Settings, Voice, "Your name". Filled in from your Windows
  account to start with.
- **Dictation.** "Open Notepad and keep writing what I say" opens the program
  and types everything you say, silently, until you say "stop dictation".
  "Open Notepad and write hello world" types one line.
- **More natural phrasing.** "I want to see Pakistan vs Sri Lanka match
  highlights on YouTube", "show me ... on YouTube", "I'd like to watch ...".
- **Yes/no by voice.** When Vox asks a question it now listens for your
  answer straight away.
- **Fixed: "Unable to open file 'model.bin'".** The speech model is now kept
  in Vox's own folder and is downloaded again automatically if it is damaged
  or incomplete.

## 0.2.2

- **API key could not be saved.** The key box in Settings shared an internal
  name with another element, so a pasted key was never stored and Vox kept
  saying "Enter the API key first". Fixed, with a test that prevents a repeat.
- Pasting a key now saves it at once, and "Load models" and "Test speed"
  save whatever is in the box before running.
- The model list shows only Gemini models that can plan commands.

## 0.2.1

Fixes the two problems found installing 0.2.0.

- **Antivirus quarantine.** Microsoft Defender quarantined 0.2.0's `Vox.exe`
  as `Trojan:Win32/Bearfoos.A!ml`, a machine-learning false positive common
  with self-extracting Python launchers. Vox no longer uses one. `Vox.exe` is
  now the official Python runtime, digitally signed by the Python Software
  Foundation, running Vox's plain source code.
- **"Internal Server Error" in the window.** Caused by the same quarantine:
  Vox could no longer read parts of itself from the blocked file. With no
  packed file this cannot recur, and the window now explains the problem if
  Windows ever blocks a Vox file.
- If another program is using Vox's port, Vox picks a free one instead of
  showing that program's page.
- Self-test command is now `Vox.exe -m vox --self-test report.json`.

## 0.2.0

First installable release.

- **Installer.** `VoxSetup-0.2.0.exe` installs Vox for the current user, with
  optional desktop shortcut and start-with-Windows. No Python needed.
- **Updates.** Vox checks GitHub for a newer release when it starts. Settings,
  Updates, "Update now" downloads the installer, verifies its checksum,
  installs it and restarts Vox.
- **Self-learning.** When the AI plans a command, Vox remembers the plan. The
  same sentence next time runs with no AI request, and after two similar
  examples Vox handles new variations too. The Learned screen lists
  everything remembered and lets you forget any of it.
- **Self-test.** `--self-test report.json` checks every part of the
  installed copy.
- Second launches reuse the running copy instead of starting another.

## 0.1.0

- Instant router for everyday commands, AI planning with Gemini or OpenAI,
  file, program, web and system skills, confirmation and undo, voice input
  and spoken replies, settings window.
