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
  `"%LOCALAPPDATA%\Programs\Vox\Vox.exe" --self-test "%TEMP%\vox-report.json"`
  and open the report.
- **Log file:** `%APPDATA%\Vox\vox.log`
- **Hotkey does nothing:** another program may own the combination. Change it
  in Settings, Hearing.
- **It mishears you:** switch Speech recognition to OpenAI or Gemini, or set
  On-PC accuracy to "Most accurate".

## Run from source instead

    git clone https://github.com/nisar87/Vox
    cd Vox
    install.bat
    run.bat
