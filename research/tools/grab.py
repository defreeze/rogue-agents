"""Fetch an archived page via the Wayback Machine and print passages around keywords."""
import html
import re
import subprocess
import sys

import os
TS = os.environ.get("TS", "2025")
name, url, *keys = sys.argv[1:]
out = f"../raw/{name}.html"
code = subprocess.run(
    ["curl", "-sL", "-m", "60", "-A", "Mozilla/5.0", "-o", out, "-w", "%{http_code}", f"https://web.archive.org/web/{TS}id_/{url}"],
    capture_output=True, text=True,
).stdout
t = open(out, encoding="utf-8", errors="ignore").read()
t = re.sub(r"(?s)<(script|style).*?</\1>", "", t)
t = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", t)))
open(f"../raw/{name}.txt", "w").write(t)
print(f"== {name} [{code}] {len(t)} chars")
for k in keys:
    for m in list(re.finditer(re.escape(k), t))[:2]:
        print("  ...", t[max(0, m.start() - 350):m.end() + 250])
