"""Print the CHANGELOG.md section for one version:  python release_notes.py 0.2.0"""

import re
import sys
from pathlib import Path

version = sys.argv[1]
text = (Path(__file__).parent.parent / "CHANGELOG.md").read_text("utf-8")
match = re.search(rf"^## {re.escape(version)}\b.*?\n(.*?)(?=^## |\Z)", text, re.S | re.M)
notes = match.group(1).strip() if match else f"Vox {version}"
print(notes + "\n\n**To install:** download `VoxSetup-" + version + ".exe` below and run it. "
      "Windows may show a blue \"Windows protected your PC\" box because the installer is not "
      "code-signed; choose More info, then Run anyway.\n\n"
      "**Already have Vox?** Open Settings, Updates, and press Update now.")
