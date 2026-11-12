# How Vox is built and released

## Layout

    vox/router.py     instant command patterns
    vox/learning.py   remembered AI plans
    vox/engine.py     picks the route, runs skills, handles yes/no
    vox/llm.py        Gemini and OpenAI
    vox/tools/        skills: files, apps, web, system
    vox/voice.py      microphone, speech-to-text, speaking, hotkey
    vox/updater.py    GitHub Releases updater
    vox/selftest.py   --self-test
    vox/server.py     local API behind the window
    vox/ui/           the window
    packaging/        icon, build script, Inno Setup script
    tests/            automated tests

## The pipeline

`.github/workflows/build.yml` runs on every push to `main`:

1. **Logic tests on Linux.**
2. **On Windows:** the full test suite, including real-program and
   spoken-command tests.
3. **Build** the program folder and `VoxSetup-<version>.exe` with Inno Setup.
4. **Self-test the built program.**
5. **Install with the installer**, confirm the installed Vox starts and
   serves its window, and self-test the installed copy.
6. **Publish.** If `vox/__init__.py` names a version with no GitHub release
   yet, a release `v<version>` is created with the installer and its
   checksum. Otherwise nothing is published.

A release therefore only exists if every step before it passed.

## How the program is packaged

`packaging/build.ps1` assembles `dist\Vox`:

- the official embeddable Python runtime from python.org. `Vox.exe` is its
  `pythonw.exe` under another name, so it keeps the Python Software
  Foundation's digital signature; the build fails if that signature is not valid
- the libraries from `requirements.txt` in `Lib\site-packages`
- the `vox` package as plain source

Shortcuts run `Vox.exe -m vox`. Nothing is packed into a self-extracting
executable, because antivirus tools distrust those (0.2.0 was quarantined
for it).

The pipeline also scans the result with Microsoft Defender. That scan is
informational: the hosted machine cannot run the cloud-based checks a home
PC does.

## Releasing a new version

1. Change `__version__` in `vox/__init__.py`.
2. Add a `## <version>` section at the top of `CHANGELOG.md`. It becomes the
   release notes.
3. Push to `main`.

Installed copies see the new release the next time they start.

## Building on your own PC

    pip install -r requirements-dev.txt
    python -m pytest
    powershell -ExecutionPolicy Bypass -File packaging\build.ps1

The installer step needs [Inno Setup 6](https://jrsoftware.org/isinfo.php).
Output goes to `dist\`.

## Optional: live AI tests

The cloud tests use simulated AI replies because the repository holds no API
keys. To test against the real services, run Vox locally with your keys and
use Settings, **Test speed**.
