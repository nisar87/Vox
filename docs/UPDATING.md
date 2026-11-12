# Updating

## From inside Vox

Vox checks GitHub for a newer release each time it starts. When there is one:

- A bar appears on the Talk screen with **Update now**.
- Settings, Updates shows the new version and the same button.

Pressing it downloads the installer, checks it against the checksum published
with the release, installs it silently and restarts Vox. Your settings,
learned commands and undo history are kept; they live in `%APPDATA%\Vox`,
outside the program folder.

To check on demand: Settings, Updates, **Check for updates**. To stop the
automatic check, switch off "Look for a new version when Vox starts".

## By hand

Download the newest `VoxSetup-<version>.exe` from the
[releases page](https://github.com/nisar87/Vox/releases/latest) and run it
over the existing installation.

## If you run from source

The update button only works for the installed program. From source:

    git pull
    install.bat
