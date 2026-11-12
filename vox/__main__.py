"""Start Vox:  python -m vox"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import threading
import time
import webbrowser


def _prepare_output() -> None:
    """The installed exe has no console, so send all output to a log file."""
    if sys.stdout is None or sys.stderr is None:
        from . import config

        log = open(config.home() / "vox.log", "a", buffering=1, encoding="utf-8", errors="replace")
        sys.stdout = sys.stderr = log


def _is_vox(port: int) -> bool:
    import httpx

    try:
        return "<title>Vox</title>" in httpx.get(f"http://127.0.0.1:{port}/", timeout=1.5).text
    except httpx.HTTPError:
        return False


def _running_port(preferred: int) -> int | None:
    """Port of a Vox that is already running, if any."""
    from . import config

    candidates = [preferred]
    try:
        candidates.insert(0, int((config.home() / "port.txt").read_text()))
    except (OSError, ValueError):
        pass
    return next((port for port in dict.fromkeys(candidates) if _is_vox(port)), None)


def _free_port(preferred: int) -> int:
    """The preferred port, or another free one if some other program holds it."""
    import socket

    for port in (preferred, 0):
        with socket.socket() as sock:
            try:
                sock.bind(("127.0.0.1", port))
                return sock.getsockname()[1]
            except OSError:
                continue
    return preferred


def open_window(url: str) -> None:
    """Show the UI as its own window (Edge app mode), else in the default browser."""
    if os.name == "nt":
        try:
            subprocess.Popen(["cmd", "/c", "start", "", "msedge", f"--app={url}", "--window-size=1080,760"],
                             creationflags=0x08000000)
            return
        except OSError:
            pass
    webbrowser.open(url)


def tray(vox, url: str, stop) -> bool:
    """Notification-area icon so Vox keeps running after the window closes."""
    try:
        import pystray
        from PIL import Image, ImageDraw
    except Exception:
        return False
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((4, 4, 60, 60), radius=16, fill=(52, 46, 204))
    for x, height in ((20, 14), (28, 26), (36, 34), (44, 18)):
        draw.rounded_rectangle((x - 3, 32 - height // 2, x + 3, 32 + height // 2), radius=3, fill="white")
    icon = pystray.Icon("Vox", image, "Vox", menu=pystray.Menu(
        pystray.MenuItem("Open Vox", lambda: open_window(url), default=True),
        pystray.MenuItem("Listen now", lambda: vox.listen()),
        pystray.MenuItem('Standby: listen for "Hi Vox"',
                         lambda: vox.apply_settings({"standby": not vox.config["standby"]}),
                         checked=lambda item: bool(vox.config["standby"])),
        pystray.MenuItem("Quit", lambda: (stop.set(), icon.stop())),
    ))
    icon.run()
    return True


def main() -> None:
    parser = argparse.ArgumentParser(prog="vox", description="Voice assistant for your PC")
    parser.add_argument("--no-window", action="store_true", help="start in the background only")
    parser.add_argument("--self-test", metavar="REPORT", nargs="?", const="",
                        help="check this copy of Vox works, write a JSON report, and exit")
    parser.add_argument("--version", action="store_true")
    args = parser.parse_args()
    _prepare_output()

    from . import __version__

    if args.version:
        print(__version__)
        return
    if args.self_test is not None:
        from . import selftest

        sys.exit(selftest.run_all(args.self_test or None))

    import uvicorn

    from . import app as app_module
    from . import server

    from . import config as config_module

    vox = app_module.VoxApp()
    running = _running_port(int(vox.config["port"]))
    if running:  # second launch: just show the window of the first
        if not args.no_window:
            open_window(f"http://127.0.0.1:{running}")
        return
    port = _free_port(int(vox.config["port"]))
    (config_module.home() / "port.txt").write_text(str(port))
    url = f"http://127.0.0.1:{port}"
    web = uvicorn.Server(uvicorn.Config(server.create(vox), host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=web.run, daemon=True).start()
    vox.start()
    time.sleep(0.6)
    print(f"Vox {__version__} is running at {url}  (hotkey: {vox.config['hotkey']})")
    if not args.no_window:
        open_window(url)

    stop = threading.Event()
    if not tray(vox, url, stop):
        try:
            while not stop.is_set():
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
    web.should_exit = True


if __name__ == "__main__":
    main()
