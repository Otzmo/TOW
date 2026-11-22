#!/usr/bin/env python3
"""Lädt alle Seiten von tow.whfb.app (Breitensuche über interne Links) und speichert
die Seitendaten (Next.js pageProps) als JSON. Höflich: eine Anfrage nach der anderen."""
import json, os, re, ssl, sys, threading, time, urllib.request
from collections import deque
from concurrent.futures import ThreadPoolExecutor

BASIS = "https://tow.whfb.app"
ZIEL = sys.argv[1] if len(sys.argv) > 1 else "data/raw"
PAUSE = float(os.environ.get("PAUSE", "0.5"))
AUSSCHLUSS = re.compile(r"^/(_next|icons|api|apps|public|regenerate)")
ctx = ssl.create_default_context(cafile=os.environ.get("SSL_CERT_FILE") or None)

def lade(pfad, versuche=4):
    for i in range(versuche):
        try:
            req = urllib.request.Request(BASIS + pfad, headers={"User-Agent": "Mozilla/5.0 (privates Archiv)"})
            with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
                return r.status, r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code == 404: return 404, ""
            time.sleep(2 ** i * 2)
        except Exception:
            time.sleep(2 ** i * 2)
    return None, ""

def links(html):
    out = set()
    for h in re.findall(r'href="(/[^"#?]*)', html):
        h = h.rstrip("/") or "/"
        if not AUSSCHLUSS.match(h) and not re.search(r"\.(png|ico|svg|css|js|webmanifest|xml|txt)$", h):
            out.add(h)
    return out

def datei_fuer(pfad):
    return os.path.join(ZIEL, ("index" if pfad == "/" else pfad.strip("/")) + ".json")

def hole(pfad):
    """Gibt (eintrag, links, fehler) zurück. Bereits gespeicherte Seiten werden nicht neu geladen."""
    datei = datei_fuer(pfad)
    if os.path.exists(datei):
        try:
            d = json.load(open(datei))
            if "links" in d:
                return {"pfad": pfad, "titel": d.get("titel", ""), "page": d.get("page")}, set(d["links"]), None
        except Exception:
            pass
    status, html = lade(pfad)
    time.sleep(PAUSE)
    if status != 200:
        return None, set(), {"pfad": pfad, "status": status}
    ls = links(html)
    m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.S)
    titel = re.search(r"<title>([^<|]*)", html)
    titel = titel.group(1).strip() if titel else ""
    if not m:
        return None, ls, {"pfad": pfad, "status": "keine Daten"}
    nd = json.loads(m.group(1))
    os.makedirs(os.path.dirname(datei), exist_ok=True)
    with open(datei, "w") as f:
        json.dump({"pfad": pfad, "titel": titel, "page": nd.get("page"), "links": sorted(ls),
                   "pageProps": nd.get("props", {}).get("pageProps")}, f, ensure_ascii=False)
    return {"pfad": pfad, "titel": titel, "page": nd.get("page")}, ls, None

def main():
    os.makedirs(ZIEL, exist_ok=True)
    gesehen, index, fehler = {"/"}, [], []
    welle = ["/"]
    with ThreadPoolExecutor(max_workers=int(os.environ.get("PARALLEL", "3"))) as pool:
        while welle:
            neu = []
            for eintrag, ls, err in pool.map(hole, welle):
                if err: fehler.append(err); print("FEHLER", err, flush=True)
                if eintrag: index.append(eintrag)
                for l in ls - gesehen:
                    gesehen.add(l); neu.append(l)
            print(f"{len(index):4d} ok  {len(neu):4d} neu entdeckt", flush=True)
            welle = neu
    with open(os.path.join(ZIEL, "_index.json"), "w") as f:
        json.dump({"stand": time.strftime("%Y-%m-%d"), "seiten": index, "fehler": fehler}, f, ensure_ascii=False, indent=1)
    print("FERTIG", len(index), "Seiten,", len(fehler), "Fehler", flush=True)

main()
