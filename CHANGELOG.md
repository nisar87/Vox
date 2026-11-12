# Changelog

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
- **Self-test.** `Vox.exe --self-test report.json` checks every part of the
  installed copy.
- Second launches reuse the running copy instead of starting another.

## 0.1.0

- Instant router for everyday commands, AI planning with Gemini or OpenAI,
  file, program, web and system skills, confirmation and undo, voice input
  and spoken replies, settings window.
