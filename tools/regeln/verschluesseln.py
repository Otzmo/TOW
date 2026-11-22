#!/usr/bin/env python3
"""Verschlüsselt die aufbereiteten Regeldaten für die Veröffentlichung.

  python3 verschluesseln.py <klartext-ordner> <ziel-ordner>

Das Passwort kommt aus der Umgebungsvariable REGELN_PASSWORT.
Jede JSON-Datei wird gzip-komprimiert, mit AES-256-GCM verschlüsselt und als Base64-Text
gespeichert (Inhalt: IV + Chiffretext, Endung .txt).
Der Schlüssel wird mit PBKDF2-SHA256 aus dem Passwort abgeleitet. Das Salz bleibt erhalten,
solange das Passwort gleich bleibt, damit gemerkte Geräte nach einem Update angemeldet bleiben.
"""
import base64, glob, gzip, json, os, sys
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

QUELLE, ZIEL = sys.argv[1], sys.argv[2]
PW = os.environ.get("REGELN_PASSWORT")
if not PW:
    sys.exit("REGELN_PASSWORT fehlt.")
RUNDEN = 600_000
PRUEF = b"OTZMO-TOW Regelindex"

def schluessel(salz):
    return PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salz, iterations=RUNDEN).derive(PW.encode())

def verschluessle(aes, daten):
    iv = os.urandom(12)
    return iv + aes.encrypt(iv, daten, None)

# Salz wiederverwenden, wenn das Passwort gleich geblieben ist
salz, info_datei = None, os.path.join(ZIEL, "schluessel.json")
if os.path.exists(info_datei):
    try:
        alt = json.load(open(info_datei))
        s = base64.b64decode(alt["salz"]); roh = base64.b64decode(alt["pruefung"])
        if alt.get("runden") == RUNDEN and AESGCM(schluessel(s)).decrypt(roh[:12], roh[12:], None) == PRUEF:
            salz = s
    except Exception:
        pass
salz = salz or os.urandom(16)
aes = AESGCM(schluessel(salz))

def alter_inhalt(datei):
    """Klartext der bisherigen Datei, falls sie mit demselben Schlüssel lesbar ist."""
    try:
        roh = base64.b64decode(open(datei, "rb").read())
        return gzip.decompress(aes.decrypt(roh[:12], roh[12:], None))
    except Exception:
        return None

def vergleichbar(rel, daten):
    # Im Index ändert sich das Datum bei jedem Abruf; das allein ist keine Änderung.
    if rel == "index.json":
        try:
            d = json.loads(daten); d.pop("stand", None); return json.dumps(d, sort_keys=True).encode()
        except Exception:
            return daten
    return daten

os.makedirs(os.path.join(ZIEL, "inhalt"), exist_ok=True)
vorhanden = {os.path.relpath(f, ZIEL) for f in glob.glob(os.path.join(ZIEL, "**/*.txt"), recursive=True)}
geschrieben, anzahl, neu = set(), 0, 0
for f in glob.glob(os.path.join(QUELLE, "**/*.json"), recursive=True):
    rel = os.path.relpath(f, QUELLE)
    if rel == "bilder.json":
        continue
    ziel = os.path.join(ZIEL, rel[:-5] + ".txt")
    geschrieben.add(os.path.relpath(ziel, ZIEL))
    os.makedirs(os.path.dirname(ziel), exist_ok=True)
    daten = open(f, "rb").read()
    alt = alter_inhalt(ziel) if os.path.exists(ziel) else None
    anzahl += 1
    if alt is not None and vergleichbar(rel, alt) == vergleichbar(rel, daten):
        continue   # unverändert: alte Datei behalten, damit Git keine Änderung sieht
    open(ziel, "wb").write(base64.b64encode(verschluessle(aes, gzip.compress(daten, 9, mtime=0))))
    neu += 1
for weg in vorhanden - geschrieben:
    os.remove(os.path.join(ZIEL, weg)); neu += 1
if os.path.exists(info_datei) and salz == base64.b64decode(json.load(open(info_datei))["salz"]):
    pass   # Schlüsseldatei unverändert lassen
else:
  json.dump({"verfahren": "PBKDF2-SHA256 / AES-256-GCM / gzip", "runden": RUNDEN,
           "salz": base64.b64encode(salz).decode(),
           "pruefung": base64.b64encode(verschluessle(aes, PRUEF)).decode()},
          open(info_datei, "w"), indent=1)
print(f"{anzahl} Dateien geprüft, {neu} neu verschlüsselt oder entfernt ({ZIEL})")
