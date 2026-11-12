# Install and first run

## Requirements

- Windows 10 or 11, 64-bit
- A microphone
- A Gemini or OpenAI API key (only needed for commands outside the instant set)

## Install

1. Download `VoxSetup-<version>.exe` from the
   [latest release](https://github.com/nisar87/Vox/releases/latest).
2. Run it. If Windows shows "Windows protected your PC", choose **More info**,
   then **Run anyway**. The installer is not code-signed yet.
3. Choose whether you want a desktop shortcut and whether Vox should start
   with Windows, then finish. Vox opens.

Vox installs to `%LOCALAPPDATA%\Programs\Vox` for your user only. No
administrator rights are needed. Uninstall from Windows Settings, Apps.

## First run

1. Open **Settings**.
2. **AI model.** Pick Gemini or OpenAI and paste the key.
   - Gemini: create a key in Google AI Studio.
   - OpenAI: create a key at platform.openai.com. A ChatGPT subscription does
     not include API access; the API is billed separately.
   Then choose a model from the list and press **Test speed**.
3. **Hearing.** "On this PC" downloads a speech model (about 150 MB) the first
   time it is used, so the first spoken command is slow. Later ones are not.
4. Go to **Talk**, press **Ctrl + Alt + Space** and say "open notepad".

Vox keeps running in the notification area after you close its window.
Right-click the icon to quit.

## If something does not work

- **Check the copy is complete:** run
  `"%LOCALAPPDATA%\Programs\Vox\Vox.exe" -m vox --self-test "%TEMP%\vox-report.json"`
  and open the report.
- **Log file:** `%APPDATA%\Vox\vox.log`
- **Windows Security removed Vox or shows a trojan warning:** see
  "Antivirus warnings" below.
- **Hotkey does nothing:** another program may own the combination. Change it
  in Settings, Hearing.
- **It mishears you:** switch Speech recognition to OpenAI or Gemini, or set
  On-PC accuracy to "Most accurate".

## Antivirus warnings

Vox listens for a global hotkey, runs PowerShell, takes screenshots and
updates itself. Those are also things malware does, so security software
can be suspicious of it, and the installer is not code-signed.

Since 0.2.1 the program itself is the official Python runtime, signed by the
Python Software Foundation, running Vox's readable source code from
`%LOCALAPPDATA%\Programs\Vox\vox`. Version 0.2.0 used a self-extracting
launcher that Microsoft Defender quarantined as `Trojan:Win32/Bearfoos.A!ml`
(a machine-learning guess, not a match to known malware); that launcher is
gone.

If a warning still appears:

1. Open Windows Security, Protection history, and note which file was flagged.
2. You can report it to Microsoft as a false positive at
   https://www.microsoft.com/wdsi/filesubmission
3. Everything Vox runs is in this repository, and each release is built from
   it by GitHub (see the Actions tab), so the build can be inspected.

## Run from source instead

    git clone https://github.com/nisar87/Vox
    cd Vox
    install.bat
    run.bat
