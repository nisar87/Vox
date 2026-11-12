# Changelog

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
