#!/usr/bin/env python3
"""Lädt die Abbildungen (Liste aus build.py: <daten>/bilder.json) verkleinert als WebP nach data/bilder/."""
import hashlib, json, os, ssl, sys, time, urllib.request
LISTE = sys.argv[1] if len(sys.argv) > 1 else "app/daten/bilder.json"
ZIEL = sys.argv[2] if len(sys.argv) > 2 else "data/bilder"
ctx = ssl.create_default_context(cafile=os.environ.get("SSL_CERT_FILE") or None)
os.makedirs(ZIEL, exist_ok=True)
urls = json.load(open(LISTE)); neu = 0
for u in urls:
    datei = os.path.join(ZIEL, hashlib.sha1(u.encode()).hexdigest()[:16] + ".webp")
    if os.path.exists(datei): continue
    for i in range(3):
        try:
            req = urllib.request.Request(u + "?w=900&fm=webp&q=70", headers={"User-Agent": "Mozilla/5.0 (privates Archiv)"})
            with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
                open(datei, "wb").write(r.read()); neu += 1; break
        except Exception as e:
            print("Fehler", u, e); time.sleep(3)
    time.sleep(0.5)
print(f"{len(urls)} Bilder, {neu} neu geladen")
