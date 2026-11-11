"""Start Vox:  python -m vox"""

from __future__ import annotations

import argparse
import os
import subprocess
import threading
import time
import webbrowser

import uvicorn

from . import app as app_module
from . import server


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
        pystray.MenuItem("Quit", lambda: (stop.set(), icon.stop())),
    ))
    icon.run()
    return True


def main() -> None:
    parser = argparse.ArgumentParser(prog="vox", description="Voice assistant for your PC")
    parser.add_argument("--no-window", action="store_true", help="start in the background only")
    args = parser.parse_args()

    vox = app_module.VoxApp()
    port = int(vox.config["port"])
    url = f"http://127.0.0.1:{port}"
    web = uvicorn.Server(uvicorn.Config(server.create(vox), host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=web.run, daemon=True).start()
    vox.start()
    time.sleep(0.6)
    print(f"Vox is running at {url}  (hotkey: {vox.config['hotkey']})")
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
