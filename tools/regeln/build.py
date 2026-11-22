#!/usr/bin/env python3
"""Bereitet die Rohdaten (data/raw) für die App auf.

Ausgabe in <ziel>/:
  index.json        eine Zeile pro Seite: Pfad, Titel, Art, Kapitel, Suchtext
  inhalt/<teil>.json  HTML-Inhalt der Seiten, nach Kapitel aufgeteilt
"""
import base64, glob, hashlib, html, json, os, re, sys, time
from collections import defaultdict

ROH = sys.argv[1] if len(sys.argv) > 1 else "data/raw"
ZIEL = sys.argv[2] if len(sys.argv) > 2 else "app/daten"
BILDER = sys.argv[3] if len(sys.argv) > 3 else "data/bilder"

def bild_daten(url):
    datei = os.path.join(BILDER, hashlib.sha1(url.encode()).hexdigest()[:16] + ".webp")
    if os.path.exists(datei):
        return "data:image/webp;base64," + base64.b64encode(open(datei, "rb").read()).decode()
    return None

seiten = []
for f in sorted(glob.glob(os.path.join(ROH, "**/*.json"), recursive=True)):
    if os.path.basename(f).startswith("_"):
        continue
    d = json.load(open(f))
    if d.get("pageProps"):
        seiten.append(d)

# ---------- Verweise auflösen: Contentful-ID -> Pfad ----------
id_pfad, faq_pfad, titel_pfad = {}, {}, {}
for s in seiten:
    pp, pfad = s["pageProps"], s["pfad"]
    e = pp.get("entry")
    if isinstance(e, dict) and e.get("sys", {}).get("id"):
        id_pfad[e["sys"]["id"]] = pfad
    if pp.get("id") and s["page"] == "/faq/[ruleType]":
        id_pfad.setdefault(pp["id"], pfad)
    if s["page"] == "/faq/[ruleType]":
        for it in pp.get("entries") or []:
            if it.get("fields", {}).get("slug"):
                faq_pfad[it["fields"]["slug"]] = pfad + "#" + it["fields"]["slug"]

einheit_armee = {}
for s_ in seiten:
    if s_["page"] == "/army/[association]":
        an = ((s_["pageProps"].get("entry") or {}).get("fields") or {}).get("name", "")
        for grp in s_["pageProps"].get("unitsByType") or []:
            for u in grp.get("units") or []:
                sl = (u.get("fields") or {}).get("slug")
                if sl:
                    einheit_armee.setdefault("/unit/" + sl, (an, s_["pfad"]))

def pfad_aus_ziel(t):
    if not isinstance(t, dict):
        return None
    sys_ = t.get("sys", {})
    if sys_.get("id") in id_pfad:
        return id_pfad[sys_["id"]]
    f = t.get("fields") or {}
    ct = (sys_.get("contentType") or {}).get("sys", {}).get("id")
    slug = f.get("slug")
    if not slug:
        return None
    if ct == "armyListEntry":
        return "/unit/" + slug
    if ct == "association":
        return "/army/" + slug
    if ct == "ruleType":
        return "/" + slug
    if ct == "faq":
        return faq_pfad.get(slug)
    rt = f.get("ruleType")
    if isinstance(rt, list) and rt and isinstance(rt[0], dict) and (rt[0].get("fields") or {}).get("slug"):
        return "/" + rt[0]["fields"]["slug"] + "/" + slug
    return None

# ---------- Rich Text -> HTML ----------
BLOCK = {"paragraph": "p", "heading-1": "h2", "heading-2": "h2", "heading-3": "h3", "heading-4": "h4",
         "heading-5": "h4", "heading-6": "h4", "unordered-list": "ul", "ordered-list": "ol",
         "list-item": "li", "blockquote": "blockquote", "table-row": "tr", "table-cell": "td",
         "table-header-cell": "th"}
bilder = []

def rt(n):
    if isinstance(n, list):
        return "".join(rt(x) for x in n)
    if not isinstance(n, dict):
        return ""
    t = n.get("nodeType")
    kinder = n.get("content") or []
    if t == "text":
        v = html.escape(n.get("value", "")).replace("\n", "<br>")
        for m in n.get("marks") or []:
            tag = {"bold": "b", "italic": "i", "underline": "u", "code": "code", "superscript": "sup", "subscript": "sub"}.get(m.get("type"))
            if tag:
                v = f"<{tag}>{v}</{tag}>"
        return v
    if t == "document":
        return rt(kinder)
    if t == "" and kinder and all((k or {}).get("nodeType") in ("entry-hyperlink", "embedded-entry-inline") for k in kinder):
        # Liste von Regel-Verweisen (z. B. Sonderregeln einer Einheit) als Chips
        return '<p class="regelchips">' + "".join(rt(k) for k in kinder) + "</p>"
    if t == "hr":
        return "<hr>"
    if t == "table":
        zeilen = [rt(k) for k in kinder]
        return f'<div class="tabelle"><table>{"".join(zeilen)}</table></div>'
    if t in ("table-cell", "table-header-cell"):
        # Absätze in Zellen nicht als <p> umbrechen
        inner = "<br>".join(rt(k.get("content") or []) if k.get("nodeType") == "paragraph" else rt(k) for k in kinder)
        tag = BLOCK[t]
        return f"<{tag}>{inner}</{tag}>"
    if t == "list-item":
        inner = "".join(rt(k.get("content") or []) + "<br>" if k.get("nodeType") == "paragraph" else rt(k) for k in kinder)
        return "<li>" + re.sub(r"(<br>)+$", "", inner) + "</li>"
    if t in BLOCK:
        tag = BLOCK[t]
        inner = rt(kinder)
        if tag == "p" and not inner.strip():
            return ""
        return f"<{tag}>{inner}</{tag}>"
    if t == "hyperlink":
        uri = (n.get("data") or {}).get("uri", "")
        m = re.match(r"https?://tow\.whfb\.app(/[^?#]*)?(#.*)?$", uri)
        if m:
            return f'<a data-p="{html.escape((m.group(1) or "/").rstrip("/") or "/")}">{rt(kinder)}</a>'
        return f'<a href="{html.escape(uri)}" target="_blank" rel="noopener">{rt(kinder)}</a>'
    if t in ("entry-hyperlink", "embedded-entry-inline"):
        ziel = (n.get("data") or {}).get("target")
        p = pfad_aus_ziel(ziel)
        text = rt(kinder) if kinder else html.escape(((ziel or {}).get("fields") or {}).get("name", ""))
        return f'<a data-p="{html.escape(p)}">{text}</a>' if p else f'<span class="kein-link">{text}</span>'
    if t == "asset-hyperlink":
        return rt(kinder)
    if t == "embedded-asset-block":
        ziel = (n.get("data") or {}).get("target") or {}
        f = ziel.get("fields") or {}
        url = (f.get("file") or {}).get("url")
        if url:
            if url.startswith("//"):
                url = "https:" + url
            bilder.append(url)
            alt = html.escape(f.get("description") or f.get("title") or "Abbildung")
            daten = bild_daten(url)
            if daten:
                return f'<figure><img src="{daten}" alt="{alt}" loading="lazy"><figcaption>{alt}</figcaption></figure>'
            return f'<figure><span class="bild-platz">Abbildung: {alt}</span></figure>'
        return ""
    if t == "embedded-entry-block":
        ziel = (n.get("data") or {}).get("target") or {}
        f = ziel.get("fields") or {}
        p = pfad_aus_ziel(ziel)
        teile = []
        if f.get("name"):
            teile.append(f'<h3>{f"<a data-p={chr(34)}{html.escape(p)}{chr(34)}>" if p else ""}{html.escape(f["name"])}{"</a>" if p else ""}</h3>')
        if any(k in f for k in ("range", "strength", "armourPiercing")):
            kopf = "".join(f"<th>{l}</th>" for l in ("Reichweite", "Stärke", "DS", "Sonderregeln"))
            sr = rt(f.get("specialRules")) if isinstance(f.get("specialRules"), dict) else ""
            sr = re.sub(r"^<p>|</p>$", "", sr)
            teile.append(f'<div class="tabelle"><table><tr>{kopf}</tr><tr><td>{html.escape(str(f.get("range", "-")))}</td><td>{html.escape(str(f.get("strength", "-")))}</td><td>{html.escape(str(f.get("armourPiercing", "-")))}</td><td>{sr or "-"}</td></tr></table></div>')
            if teile and teile[0].startswith("<h3>"):
                teile[0] = teile[0].replace(" (Profile)", "")
        for k in ("description", "body", "notes"):
            if isinstance(f.get(k), dict):
                teile.append(rt(f[k]))
        return f'<div class="eingebettet">{"".join(teile)}</div>' if teile else ""
    return rt(kinder)

def text_aus(h):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", h))).strip()

def link(p, name):
    return f'<a data-p="{html.escape(p)}">{html.escape(name)}</a>' if p else html.escape(name)

# ---------- Seiten aufbereiten ----------
PROFIL = ["M", "WS", "BS", "S", "T", "W", "I", "A", "Ld"]
docs = []
def verarbeite(s):
    pp, pfad, page = s["pageProps"], s["pfad"], s["page"]
    e = pp.get("entry") if isinstance(pp.get("entry"), dict) else None
    f = (e or {}).get("fields") or {}
    doc = {"p": pfad, "t": f.get("name") or (pp.get("fields") or {}).get("name") or pfad.strip("/"), "k": "regel", "c": "", "cp": ""}
    teile = []
    if page in ("/", "/metrics") or page.startswith("/sitemap"):
        return
    if page == "/[ruleType]/[rule]":
        rtyp = (f.get("ruleType") or [{}])[0].get("fields") or {}
        doc.update(c=rtyp.get("name", ""), cp="/" + rtyp.get("slug", "") if rtyp.get("slug") else "")
        if isinstance(f.get("description"), dict):
            teile.append(f'<p class="flavour">{text_aus(rt(f["description"]))}</p>')
        if f.get("body"):
            teile.append(rt(f["body"]))
    elif page == "/[ruleType]":
        doc["k"] = "kapitel"
        if f.get("body"):
            teile.append(rt(f["body"]))
        eintraege = pp.get("entries") or []
        if eintraege:
            teile.append("<h2>Inhalt</h2><ul class=\"inhalt\">" + "".join(
                f"<li>{link(pfad + '/' + (x.get('fields') or {}).get('slug', ''), (x.get('fields') or {}).get('name', ''))}</li>"
                for x in eintraege if (x.get('fields') or {}).get('slug')) + "</ul>")
    elif page == "/unit/[armyListEntry]":
        doc["k"] = "einheit"
        ass = (f.get("association") or [{}])[0].get("fields") or {}
        doc.update(c=ass.get("name", ""), cp="/army/" + ass.get("slug", "") if ass.get("slug") else "")
        if pfad in einheit_armee:
            doc["c"], doc["cp"] = einheit_armee[pfad]
        prof = f.get("unitProfile") or []
        if prof:
            kopf = "".join(f"<th>{k}</th>" for k in PROFIL)
            zeilen = "".join("<tr><th class=\"name\">" + html.escape(r.get("Name", "")) + "</th>" + "".join(f"<td>{html.escape(str(r.get(k, '-')))}</td>" for k in PROFIL) + "</tr>" for r in prof)
            teile.append(f'<div class="tabelle profil"><table><tr><th></th>{kopf}</tr>{zeilen}</table></div>')
        infos = []
        tt = (f.get("troopType") or [{}])[0]
        uc = (f.get("unitCategory") or [{}])[0]
        if (tt.get("fields") or {}).get("name"):
            infos.append(("Truppentyp", link(pfad_aus_ziel(tt) or "", tt["fields"]["name"])))
        if (uc.get("fields") or {}).get("name"):
            infos.append(("Kategorie", html.escape(uc["fields"]["name"])))
        for k, l in (("baseSize", "Base"), ("unitSize", "Einheitengröße"), ("armourValue", "Rüstungswurf"), ("cost", "Punkte")):
            if f.get(k) not in (None, ""):
                infos.append((l, html.escape(str(f[k]))))
        if infos:
            teile.append('<dl class="infos">' + "".join(f"<div><dt>{a}</dt><dd>{b}</dd></div>" for a, b in infos) + "</dl>")
        for k, l in (("equipment", "Ausrüstung"), ("options", "Optionen"), ("specialRules", "Sonderregeln"), ("optionalRules", "Optionale Regeln"), ("bodyAfter", "Hinweise")):
            if isinstance(f.get(k), dict):
                h = rt(f[k])
                if text_aus(h):
                    teile.append(f"<h2>{l}</h2>{h}")
    elif page == "/army/[association]":
        doc["k"] = "armee"
        for grp in pp.get("unitsByType") or []:
            sec = (grp.get("section") or {}).get("fields") or {}
            us = [u for u in grp.get("units") or [] if (u.get("fields") or {}).get("slug")]
            if us:
                teile.append(f"<h2>{html.escape(sec.get('name', 'Einheiten'))}</h2><ul class=\"inhalt\">" + "".join(
                    f"<li>{link('/unit/' + u['fields']['slug'], u['fields']['name'])}</li>" for u in us) + "</ul>")
        for grp in pp.get("rulesByType") or []:
            gf = grp.get("fields") or {}
            rs = [r for r in grp.get("rules") or [] if (r.get("fields") or {}).get("slug")]
            if rs:
                teile.append(f"<h2>{html.escape(gf.get('name', 'Regeln'))}</h2><ul class=\"inhalt\">" + "".join(
                    f"<li>{link(pfad_aus_ziel(r) or '', r['fields']['name'])}</li>" for r in rs) + "</ul>")
    elif page in ("/magic-item/[magicItem]", "/spell/[spell]"):
        ist_zauber = page == "/spell/[spell]"
        doc["k"] = "zauber" if ist_zauber else "gegenstand"
        gruppe = (f.get("magicLore" if ist_zauber else "magicItemType") or [{}])[0]
        gf = gruppe.get("fields") or {} if isinstance(gruppe, dict) else {}
        regel = gf.get("rule")
        regel = regel[0] if isinstance(regel, list) and regel else regel
        gp = pfad_aus_ziel(regel) if isinstance(regel, dict) else None
        name = re.sub(r" (Type|Lore)$", "", gf.get("name", "")) if gf.get("name") else ""
        if ist_zauber and name and not name.lower().startswith("lore"):
            name = "Lore of " + name if not name.endswith("Lore") else name
        doc.update(c=gf.get("name", "").removesuffix(" Type") or ("Zauber" if ist_zauber else "Magische Gegenstände"), cp=gp or "")
        infos = []
        if ist_zauber:
            for k, l in (("type", "Art"), ("castingValueOverride", "Zauberwert"), ("range", "Reichweite")):
                v = f.get(k) or (f"{f['castingValue']}+" if k == "castingValueOverride" and f.get("castingValue") else None)
                if k == "type" and str(v).isdigit():
                    l, v = "Nr.", v
                if v:
                    infos.append((l, html.escape(str(v))))
        else:
            for k, l in (("type", "Art"), ("cost", "Punkte")):
                if f.get(k) not in (None, ""):
                    infos.append((l, html.escape(str(f[k]))))
        ass = (f.get("association") or [{}])[0]
        af = ass.get("fields") or {} if isinstance(ass, dict) else {}
        if af.get("name"):
            if af["name"] == "Rulebook":
                af = {**af, "name": "Regelbuch"}
            infos.append(("Quelle" if af["name"] == "Regelbuch" else "Armee", link("/army/" + af["slug"] if af.get("slug") and ("/army/" + af["slug"]) in id_pfad.values() else "", af["name"])))
        if infos:
            teile.append('<dl class="infos">' + "".join(f"<div><dt>{a}</dt><dd>{b}</dd></div>" for a, b in infos) + "</dl>")
        if isinstance(f.get("description"), dict):
            fl = text_aus(rt(f["description"]))
            if fl and fl != "TK":
                teile.append(f'<p class="flavour">{html.escape(fl)}</p>')
        if f.get("body"):
            teile.append(rt(f["body"]))
    elif page == "/cards/[magicLore]":
        doc.update(k="sonstiges", t="Zauberkarten: " + ((pp.get("magicLore") or {}).get("fields") or {}).get("name", doc["t"]), c="Zauberkarten", cp="/cards")
        for sp in pp.get("spells") or []:
            spf = sp.get("fields") or {}
            p = pfad_aus_ziel(sp)
            teile.append(f'<div class="eingebettet"><h3>{link(p or "", spf.get("name", ""))}</h3>{rt(spf.get("body"))}</div>')
    elif page == "/army/[association]/reference":
        doc.update(k="sonstiges", t="Profilübersicht: " + doc["t"], c=doc["t"], cp="/army/" + f.get("slug", ""))
        kopf = "".join(f"<th>{k}</th>" for k in PROFIL)
        zeilen = []
        for u in pp.get("units") or []:
            uf = u.get("fields") or {}
            for i, r in enumerate(uf.get("unitProfile") or []):
                name = link("/unit/" + uf["slug"], r.get("Name", "")) if i == 0 and uf.get("slug") else html.escape(r.get("Name", ""))
                zeilen.append(f'<tr><th class="name">{name}</th>' + "".join(f"<td>{html.escape(str(r.get(k, '-')))}</td>" for k in PROFIL) + "</tr>")
        if zeilen:
            teile.append(f'<div class="tabelle profil"><table><tr><th></th>{kopf}</tr>{"".join(zeilen)}</table></div>')
        if f.get("file"):
            teile.append(f'<p><a href="{html.escape(f["file"])}" target="_blank" rel="noopener">Offizielles PDF der Armee öffnen</a></p>')
    elif page == "/faq/[ruleType]":
        doc.update(k="faq", t="FAQ: " + doc["t"], c="FAQ", cp="/faq")
        for it in pp.get("entries") or []:
            itf = it.get("fields") or {}
            teile.append(f'<details class="faq" id="{html.escape(itf.get("slug", ""))}"><summary>{html.escape(re.sub(chr(10), " ", itf.get("question", "")))}</summary>{rt(itf.get("body"))}</details>')
    else:
        doc["k"] = "sonstiges"
        for k in ("body", "description"):
            if isinstance(f.get(k), dict):
                teile.append(rt(f[k]))
        for k in ("entries",):
            for x in pp.get(k) or []:
                xf = x.get("fields") or {}
                p = pfad_aus_ziel(x)
                if xf.get("name") or xf.get("question"):
                    teile.append(f"<p>{link(p or '', xf.get('name') or xf.get('question'))}</p>")
    # FAQ-Querverweise und Nachbarn
    cr = pp.get("crossReference") or {}
    faqs = [x for x in (cr.get("faq") or []) if (x.get("fields") or {}).get("question")]
    if faqs:
        teile.append('<h2>FAQ zu dieser Regel</h2><ul class="inhalt">' + "".join(
            f"<li>{link(faq_pfad.get(x['fields'].get('slug'), ''), x['fields']['question'])}</li>" for x in faqs) + "</ul>")
    for k in cr:
        if k != "faq" and isinstance(cr[k], list) and cr[k]:
            items = [x for x in cr[k] if (x.get("fields") or {}).get("name")]
            if items:
                teile.append(f'<h2>Siehe auch</h2><ul class="inhalt">' + "".join(f"<li>{link(pfad_aus_ziel(x) or '', x['fields']['name'])}</li>" for x in items) + "</ul>")
    for k, l in (("prev", "v"), ("next", "n")):
        x = pp.get(k)
        if isinstance(x, dict) and (x.get("fields") or {}).get("name"):
            p = pfad_aus_ziel(x)
            if not p and doc["cp"]:
                p = doc["cp"] + "/" + x["fields"].get("slug", "")
            if p:
                doc[l] = [p, x["fields"]["name"]]
    if f.get("pageReference"):
        doc["s"] = f["pageReference"]
    if e and e.get("sys", {}).get("updatedAt"):
        doc["u"] = e["sys"]["updatedAt"][:10]
    doc["h"] = "".join(teile)
    docs.append(doc)

probleme = []
for s in seiten:
    try:
        verarbeite(s)
    except Exception as ex:
        probleme.append(s["pfad"])
        print("Problem bei", s["pfad"], type(ex).__name__, ex)

# Kapitel für Unterseiten ohne ruleType-Name nachtragen
kap_name = {d["p"]: d["t"] for d in docs if d["k"] in ("kapitel", "armee")}
for d in docs:
    if not d["c"]:
        oben = "/" + d["p"].strip("/").split("/")[0]
        if oben != d["p"] and oben in kap_name:
            d["c"], d["cp"] = kap_name[oben], oben

# ---------- Ausgabe ----------
os.makedirs(os.path.join(ZIEL, "inhalt"), exist_ok=True)
teile = defaultdict(dict)
index = []
for d in docs:
    teil = d["p"].strip("/").split("/")[0] or "start"
    if d["k"] == "einheit":
        teil = "einheiten-" + (d["cp"].split("/")[-1] or "andere")
    elif d["k"] in ("gegenstand", "zauber"):
        teil = ("gegenstaende-" if d["k"] == "gegenstand" else "zauber-") + (re.sub(r"[^a-z]", "", d["p"].split("/")[-1][:1]) or "x")
    text = text_aus(d["h"])
    index.append({"p": d["p"], "t": d["t"], "k": d["k"], "c": d["c"], "cp": d["cp"], "f": teil,
                  "x": text[:800]})
    teile[teil][d["p"]] = {k: v for k, v in d.items() if k in ("h", "s", "u", "v", "n")}
for teil, inhalt in teile.items():
    json.dump(inhalt, open(os.path.join(ZIEL, "inhalt", teil + ".json"), "w"), ensure_ascii=False, separators=(",", ":"))
stand = time.strftime("%Y-%m-%d")
try:
    stand = json.load(open(os.path.join(ROH, "_index.json")))["stand"]
except Exception:
    pass
json.dump({"stand": stand, "seiten": index}, open(os.path.join(ZIEL, "index.json"), "w"), ensure_ascii=False, separators=(",", ":"))
json.dump(sorted(set(bilder)), open(os.path.join(ZIEL, "bilder.json"), "w"), indent=0)
fehlende = sum(1 for d in docs for _ in re.finditer(r'data-p=""', d["h"]))
print(f"{len(probleme)} Seiten mit Problemen; {len(docs)} Seiten, {len(teile)} Teildateien, {len(set(bilder))} Bilder, {fehlende} leere Verweise")
