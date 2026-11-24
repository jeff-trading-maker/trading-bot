import json
import math
import os
from datetime import datetime

import yfinance as yf

# =========================================================
# EINSTELLUNGEN
# =========================================================
start_pro_aktie = 1000
kurz = 10
lang = 30
gebuehr = 0.001  # muss zur Gebühr in paper_bot.py passen
turbo_kurz = 5    # Turbo-Bot (Stundenkerzen): muss zu paper_bot.py passen
turbo_lang = 20
# Läuft die Datei bei GitHub, schaltet die App automatisch auf "cloud"
MODUS = "cloud" if os.environ.get("GITHUB_ACTIONS") else "pc"
REPO = os.environ.get("GITHUB_REPOSITORY", "")

# Name, Kürzel im runden Symbol, Hintergrundfarbe, Schriftfarbe, Einheit
STIL = {
    "AAPL": ("Apple", "AP", "#E9E9EE", "#1C1C1E", "Stk"),
    "MSFT": ("Microsoft", "MS", "#0078D4", "#FFFFFF", "Stk"),
    "NVDA": ("Nvidia", "NV", "#76B900", "#0B1A00", "Stk"),
    "GOOGL": ("Google", "GO", "#4285F4", "#FFFFFF", "Stk"),
    "AMZN": ("Amazon", "AM", "#232F3E", "#FF9900", "Stk"),
    "JPM": ("JPMorgan", "JP", "#1F3A5F", "#E9D7B0", "Stk"),
    "KO": ("Coca-Cola", "KO", "#F40009", "#FFFFFF", "Stk"),
    "XOM": ("Exxon", "XO", "#D9252A", "#FFFFFF", "Stk"),
    "GLD": ("Gold", "Au", "#D4A63A", "#2A1E00", "Stk"),
    "BTC-USD": ("Bitcoin", "₿", "#F7931A", "#FFFFFF", "BTC"),
}

ordner = os.path.dirname(os.path.abspath(__file__))
zustand_datei = os.path.join(ordner, "depot.json")
log_datei = os.path.join(ordner, "depot_log.txt")
turbo_zustand_datei = os.path.join(ordner, "turbo_std.json")
turbo_log_datei = os.path.join(ordner, "turbo_std_log.txt")
seite_datei = os.path.join(ordner, "bot_seite.html")

if not os.path.exists(zustand_datei):
    print("Noch kein Depot vorhanden. Starte zuerst paper_bot.py.")
    print("Diese Datei muss im selben Ordner liegen wie depot.json.")
    raise SystemExit

with open(zustand_datei, "r") as f:
    depot = json.load(f)
aktien = list(depot.keys())


def runde(wert, stellen=4):
    if wert is None or (isinstance(wert, float) and math.isnan(wert)):
        return None
    return round(float(wert), stellen)


# =========================================================
# LOG EINLESEN
# =========================================================
def lies_log(datei):
    liste = []
    if os.path.exists(datei):
        with open(datei, "r", encoding="utf-8") as f:
            for zeile in f:
                teile = zeile.strip().split(" | ")
                if len(teile) < 7:
                    continue
                liste.append({
                    "tag": teile[0],
                    "ticker": teile[1],
                    "kurs": float(teile[2].replace("Kurs", "").strip()),
                    "aktion": teile[3],
                    "gesamt": float(teile[6].replace("Gesamtwert", "").strip()),
                })
    liste.sort(key=lambda e: e["tag"])
    return liste


ARTEN = {"GEKAUFT": "Kauf", "VERKAUFT": "Verkauf", "SHORT": "Short", "GEDECKT": "Eindecken"}


def art_von(aktion):
    return "" if aktion == "abwarten" else ARTEN.get(aktion.split()[0], "Verkauf")


def aktionen_aus(liste, t):
    return [[e["tag"], art_von(e["aktion"]), e["kurs"],
             float(e["aktion"].split()[1]) if len(e["aktion"].split()) > 1 else 0]
            for e in liste if e["ticker"] == t and e["aktion"] != "abwarten"]


eintraege = lies_log(log_datei)

# Depotwert pro Tag und Buy-and-Hold zum Vergleich
alle_tage = sorted(set(e["tag"] for e in eintraege))
letzter_wert = {t: float(start_pro_aktie) for t in aktien}
bh_stueck = {}
bh_letzter = {t: float(start_pro_aktie) for t in aktien}
nach_tag = {}
for e in eintraege:
    nach_tag.setdefault(e["tag"], []).append(e)
bot_verlauf, bh_verlauf = [], []
for tag in alle_tage:
    for e in nach_tag[tag]:
        if e["ticker"] not in letzter_wert:
            continue
        letzter_wert[e["ticker"]] = e["gesamt"]
        if e["ticker"] not in bh_stueck:
            bh_stueck[e["ticker"]] = start_pro_aktie / e["kurs"]
        bh_letzter[e["ticker"]] = bh_stueck[e["ticker"]] * e["kurs"]
    bot_verlauf.append(round(sum(letzter_wert.values()), 2))
    bh_verlauf.append(round(sum(bh_letzter.values()), 2))

# Plus/Minus je Aktie und Tag (für das Tagesfenster im Kalender)
pro_tag = {}
letzter_je_aktie = {}
for e in eintraege:
    alt_wert = letzter_je_aktie.get(e["ticker"], float(start_pro_aktie))
    art = art_von(e["aktion"])
    pro_tag.setdefault(e["tag"], []).append([e["ticker"], round(e["gesamt"] - alt_wert, 2), art])
    letzter_je_aktie[e["ticker"]] = e["gesamt"]

aenderung = {}
vorher = start_pro_aktie * len(aktien)
for tag, wert in zip(alle_tage, bot_verlauf):
    aenderung[tag] = round(wert - vorher, 2)
    vorher = wert

# =========================================================
# KURSE LADEN
# =========================================================
print("Lade Kurse für", len(aktien), "Aktien ...")
try:
    roh = yf.download(aktien, period="1y", auto_adjust=True, progress=False)
except Exception as fehler:
    print("Kursdaten nicht geladen:", fehler)
    roh = None

werte = []
for t in aktien:
    name, sym, bg, fg, einheit = STIL.get(t, (t, t[:2], "#22262E", "#C9CDD6", "Stk"))
    s = depot[t]
    tage, kurse, offen, hoch, tief, volumen = [], [], [], [], [], []
    try:
        serie = roh["Close"][t].dropna()
        tage = [str(x.date()) for x in serie.index]
        kurse = [runde(v) for v in serie.values]

        def spalte(feld, ersatz):
            try:
                werte_feld = roh[feld][t].reindex(serie.index).values
            except Exception:
                return list(ersatz)
            return [runde(w) if runde(w) is not None else e for w, e in zip(werte_feld, ersatz)]

        offen = spalte("Open", kurse)
        hoch = [max(x, o, c) for x, o, c in zip(spalte("High", kurse), offen, kurse)]
        tief = [min(x, o, c) for x, o, c in zip(spalte("Low", kurse), offen, kurse)]
        volumen = [int(v) if v else 0 for v in spalte("Volume", [0] * len(kurse))]
    except Exception:
        print(t, ": keine Kursdaten")
    eigene = [e for e in eintraege if e["ticker"] == t]
    preis = kurse[-1] if kurse else (eigene[-1]["kurs"] if eigene else 0)
    aktionen = [[e["tag"], art_von(e["aktion"]), e["kurs"],
                 float(e["aktion"].split()[1]) if len(e["aktion"].split()) > 1 else 0]
                for e in eigene if e["aktion"] != "abwarten"]
    werte.append({
        "t": t, "name": name, "sym": sym, "bg": bg, "fg": fg, "einheit": einheit,
        "stk": s["anteile"], "konto": round(s["konto"], 2), "preis": preis,
        "wert": round(s["konto"] + s["anteile"] * preis, 2),
        "tage": tage, "kurse": kurse, "offen": offen, "hoch": hoch, "tief": tief, "vol": volumen,
        "akt": aktionen,
        "startTag": eigene[0]["tag"] if eigene else "",
        "startKurs": eigene[0]["kurs"] if eigene else preis,
    })

letzter_tag = max((depot[t]["letzter_tag"] for t in aktien if depot[t]["letzter_tag"]), default="")

# Wechselkurs für die Euro-Anzeige (1 € = x $)
eurusd = None
try:
    fx = yf.download("EURUSD=X", period="5d", auto_adjust=True, progress=False)["Close"].dropna()
    eurusd = round(float(fx.values.ravel()[-1]), 4)
except Exception as fehler:
    print("Wechselkurs nicht geladen:", fehler)

# =========================================================
# BEIDE BOTS GLEICH AUSWERTEN (Dein Bot und Turbo-Bot)
# =========================================================
def bot_daten(zustand, liste):
    # Bei Stundenkerzen steht im Log "Tag Uhrzeit", gerechnet wird pro Tag
    tage_bot = sorted(set(e["tag"][:10] for e in liste))
    wert_je = {t: float(start_pro_aktie) for t in aktien}
    bh_st, bh_je = {}, {t: float(start_pro_aktie) for t in aktien}
    je_tag = {}
    for e in liste:
        je_tag.setdefault(e["tag"][:10], []).append(e)
    verlauf, bh = [], []
    for tag in tage_bot:
        for e in je_tag[tag]:
            if e["ticker"] not in wert_je:
                continue
            wert_je[e["ticker"]] = e["gesamt"]
            if e["ticker"] not in bh_st:
                bh_st[e["ticker"]] = start_pro_aktie / e["kurs"]
            bh_je[e["ticker"]] = bh_st[e["ticker"]] * e["kurs"]
        verlauf.append(round(sum(wert_je.values()), 2))
        bh.append(round(sum(bh_je.values()), 2))
    tagliste, letzt = {}, {}
    for e in liste:
        alt_wert = letzt.get(e["ticker"], float(start_pro_aktie))
        art = art_von(e["aktion"])
        tag = tagliste.setdefault(e["tag"][:10], {})
        eintrag = tag.setdefault(e["ticker"], [e["ticker"], 0.0, []])
        eintrag[1] += e["gesamt"] - alt_wert
        if art:
            eintrag[2].append(art)
        letzt[e["ticker"]] = e["gesamt"]
    for tag, je in tagliste.items():
        tagliste[tag] = [[t, round(v, 2), arten[0] if len(arten) == 1 else (f"{len(arten)} Trades" if arten else "")]
                         for t, v, arten in je.values()]
    aend, vor = {}, start_pro_aktie * len(aktien)
    for tag, w in zip(tage_bot, verlauf):
        aend[tag] = round(w - vor, 2)
        vor = w
    je_aktie = {}
    for t in aktien:
        z = zustand.get(t, {"konto": start_pro_aktie, "anteile": 0.0})
        eigene = [e for e in liste if e["ticker"] == t]
        je_aktie[t] = {
            "stk": z["anteile"], "konto": round(z["konto"], 2), "akt": aktionen_aus(liste, t),
            "startTag": eigene[0]["tag"] if eigene else "",
            "startKurs": eigene[0]["kurs"] if eigene else None,
        }
    return {"depot": {"labels": tage_bot, "bot": verlauf, "bh": bh}, "aenderung": aend,
            "proTag": tagliste, "assets": je_aktie}


bots = {"haupt": dict(bot_daten(depot, eintraege), name="Dein Bot", kurz=kurz, lang=lang, trend=False, intervall="1d", richtung="long"),
        "turbo": None, "short": None, "tshort": None}
if os.path.exists(turbo_zustand_datei):
    with open(turbo_zustand_datei, "r") as f:
        turbo_depot = json.load(f)
    bots["turbo"] = dict(bot_daten(turbo_depot, lies_log(turbo_log_datei)),
                         name="Turbo-Bot", kurz=turbo_kurz, lang=turbo_lang, trend=True, intervall="1h", richtung="long")
# Short-Bots (setzen auf fallende Kurse)
for schluessel, datei, logname, name, k, l, iv in [("short", "short.json", "short_log.txt", "Short-Bot", kurz, lang, "1d"),
                                                   ("tshort", "turbo_short.json", "turbo_short_log.txt", "Turbo-Short", turbo_kurz, turbo_lang, "1h")]:
    pfad = os.path.join(ordner, datei)
    if os.path.exists(pfad):
        with open(pfad, "r") as f:
            zustand = json.load(f)
        bots[schluessel] = dict(bot_daten(zustand, lies_log(os.path.join(ordner, logname))),
                                name=name, kurz=k, lang=l, trend=True, intervall=iv, richtung="short")

# Stundenkerzen für die Charts der Stunden-Bots
if bots["turbo"] or bots["tshort"]:
    print("Lade Stundenkurse ...")
    try:
        std = yf.download(aktien, period="60d", interval="1h", auto_adjust=True, progress=False)
    except Exception as fehler:
        print("Stundenkurse nicht geladen:", fehler)
        std = None
    for w in werte:
        try:
            serie = std["Close"][w["t"]].dropna()
            index = serie.index
            index = index.tz_localize("UTC") if index.tz is None else index
            index = index.tz_convert("Europe/Berlin")
            spalte = lambda feld: [runde(x) for x in std[feld][w["t"]].reindex(serie.index).values]
            c = [runde(x) for x in serie.values]
            o, h, l = spalte("Open"), spalte("High"), spalte("Low")
            o = [a if a is not None else b for a, b in zip(o, c)]
            w["std"] = {"z": [d.strftime("%Y-%m-%d %H:%M") for d in index], "c": c, "o": o,
                        "h": [max(x or 0, a, b) for x, a, b in zip(h, o, c)],
                        "l": [min(x or a, a, b) for x, a, b in zip(l, o, c)],
                        "v": [int(x) if x == x and x else 0 for x in std["Volume"][w["t"]].reindex(serie.index).values]}
        except Exception:
            print(w["t"], ": keine Stundenkurse")

daten = {
    "start": start_pro_aktie,
    "kurz": kurz,
    "lang": lang,
    "erzeugt": datetime.now().strftime("%d.%m.%Y, %H:%M"),
    "letzterTag": letzter_tag,
    "assets": werte,
    "depot": {"labels": alle_tage, "bot": bot_verlauf, "bh": bh_verlauf},
    "aenderung": aenderung,
    "proTag": pro_tag,
    "gebuehr": gebuehr,
    "modus": MODUS,
    "vorschau": os.environ.get("VORSCHAU") == "1",
    "eurusd": eurusd,
    "repo": REPO,
    "bots": bots,
}

# =========================================================
# HTML-SEITE (Design wie im Entwurf)
# =========================================================
seite = r"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="Bot">
<meta name="theme-color" content="#0B0B0E">
<link rel="apple-touch-icon" href="apple-touch-icon.png">
<link rel="icon" type="image/png" href="apple-touch-icon.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<title>Bot</title>
<style>
/* ---------- FARBEN: hier kannst du die App umfärben ---------- */
:root {
  --bg: #0B0B0E;
  --karte: #141418;
  --karte2: #1C1C22;
  --linie: #1F1F26;
  --text: #F4F4F6;
  --text2: #9A9AA6;
  --text3: #858592;
  --gruen: #3DDC97;
  --rot: #FF7A7A;
  --gelb: #F5B94A;
  --akzent: #9D8CFF;
  --akzent-hell: #B4A8FF;
}
* { box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
html, body { margin: 0; background: var(--bg); color: var(--text); font-family: Inter, -apple-system, system-ui, sans-serif; -webkit-font-smoothing: antialiased; }
body { padding-top: env(safe-area-inset-top); padding-bottom: calc(100px + env(safe-area-inset-bottom)); }
main { max-width: 520px; margin: 0 auto; }
button { font-family: inherit; color: inherit; border: 0; background: none; cursor: pointer; padding: 0; font-size: inherit; }
.num { font-variant-numeric: tabular-nums; }
.klein { font-size: 12px; color: var(--text2); }
.leise { color: var(--text3); }
.titel { font-size: 30px; font-weight: 700; letter-spacing: -0.8px; margin: 0; }
.abschnitt { display: flex; align-items: baseline; justify-content: space-between; padding: 26px 20px 8px; }
.abschnitt b { font-size: 18px; letter-spacing: -0.3px; }
.karte { background: var(--karte); border-radius: 20px; padding: 16px; margin: 12px 16px 0; }
.karte h3 { font-size: 16px; margin: 0; }
.kachel { background: var(--karte); border-radius: 16px; padding: 12px 12px 13px; }
.kachel2 { background: var(--karte2); border-radius: 14px; padding: 10px 12px; }
.chips { display: flex; justify-content: center; gap: 6px; padding: 10px 20px 0; }
.chip { padding: 8px 16px; border-radius: 12px; font-size: 13px; font-weight: 600; color: var(--text2); }
.chip.aktiv { background: var(--text); color: var(--bg); }
.zeile { display: flex; align-items: center; gap: 12px; padding: 10px 12px; border-radius: 16px; width: 100%; text-align: left; }
.zeile:active { background: #16161C; }
.icon { border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: 700; flex-shrink: 0; }
.punkt { display: inline-block; width: 6px; height: 6px; border-radius: 3px; }
.pill { font-size: 12px; font-weight: 600; padding: 5px 10px; border-radius: 10px; white-space: nowrap; }
.scrollx { display: flex; gap: 6px; overflow-x: auto; scrollbar-width: none; }
.scrollx::-webkit-scrollbar { display: none; }
.chartbox { position: relative; touch-action: pan-y; user-select: none; -webkit-user-select: none; }
.chartbox svg { display: block; }
.tip { position: absolute; top: 4px; display: none; background: rgba(10,10,14,0.95); border: 1px solid #2A2A33; border-radius: 10px; padding: 7px 9px; font-size: 12px; line-height: 1.5; pointer-events: none; white-space: nowrap; z-index: 5; }
.fleck { display: inline-block; width: 8px; height: 8px; border-radius: 4px; margin-right: 5px; }
.legende { display: flex; justify-content: center; flex-wrap: wrap; gap: 14px; margin-top: 10px; font-size: 12px; color: var(--text2); }
.legende span { display: flex; align-items: center; gap: 6px; }
.strich { width: 12px; height: 2px; border-radius: 1px; display: inline-block; }
.leer { text-align: center; color: var(--text3); font-size: 13px; padding: 30px 20px; }
.rund { width: 44px; height: 44px; border-radius: 22px; background: var(--karte); display: flex; align-items: center; justify-content: center; }
.kal { display: grid; grid-template-columns: repeat(7, minmax(0, 1fr)); gap: 4px; margin-top: 14px; }
.kal .wt { text-align: center; font-size: 11px; color: var(--text3); padding-bottom: 4px; }
.kal .tag { height: 44px; border-radius: 10px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 2px; }
.liste-trenner > * + * { border-top: 1px solid var(--linie); }
.tabbar { position: fixed; left: 0; right: 0; bottom: 0; display: flex; justify-content: space-around; padding: 8px 8px calc(10px + env(safe-area-inset-bottom)); background: rgba(11,11,14,0.88); backdrop-filter: blur(18px); -webkit-backdrop-filter: blur(18px); border-top: 1px solid rgba(255,255,255,0.06); z-index: 20; }
.tab { display: flex; flex-direction: column; align-items: center; gap: 4px; flex: 1 1 0; max-width: 76px; min-width: 0; font-size: 11px; font-weight: 600; color: var(--text3); }
.tab.aktiv { color: var(--akzent-hell); }
@keyframes rein { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: none; } }
@keyframes reinRechts { from { opacity: 0; transform: translateX(32px); } to { opacity: 1; transform: none; } }
@keyframes zeichnen { from { stroke-dashoffset: 1; } to { stroke-dashoffset: 0; } }
@keyframes einblenden { from { opacity: 0; } to { opacity: 1; } }
@keyframes toastRein { from { transform: translate(-50%, -140%); } to { transform: translate(-50%, 0); } }
@keyframes toastRaus { from { transform: translate(-50%, 0); opacity: 1; } to { transform: translate(-50%, -140%); opacity: 0; } }
main.anim-tab { animation: rein 0.32s cubic-bezier(.2,.8,.2,1); }
main.live-ruhig *, main.live-ruhig *::after { animation: none !important; }
.chartrahmen.still * { animation: none !important; }
.zoomknopf { width: 26px; height: 22px; border-radius: 7px; background: #1C1C22; color: #C7C7D1; font-size: 15px; font-weight: 700; line-height: 1; display: inline-flex; align-items: center; justify-content: center; }
.live { display: inline-flex; align-items: center; gap: 5px; font-size: 11px; font-weight: 600; color: var(--gruen); white-space: nowrap; }
.live-punkt { width: 6px; height: 6px; border-radius: 3px; background: var(--gruen); animation: puls 1.6s ease-in-out infinite; }
@keyframes puls { 0%, 100% { opacity: 1; } 50% { opacity: .3; } }
main.anim-detail { animation: reinRechts 0.34s cubic-bezier(.2,.8,.2,1); }
.zeichnen { stroke-dasharray: 1; animation: zeichnen 1.1s cubic-bezier(.3,.7,.2,1) both; }
.blende { animation: einblenden 0.6s ease-out both; }
.zeile, .chip, .tab, .rund, .glocke { transition: transform 0.12s ease, background 0.15s ease; }
.zeile:active, .chip:active, .rund:active, .glocke:active { transform: scale(0.97); }
.tab:active { transform: scale(0.92); }
.glocke { position: relative; width: 40px; height: 40px; border-radius: 20px; background: var(--karte); display: flex; align-items: center; justify-content: center; }
.badge { position: absolute; top: -4px; right: -6px; min-width: 16px; height: 16px; border-radius: 8px; animation: einblenden 0.3s ease-out; background: var(--rot); color: #0B0B0E; font-size: 10px; font-weight: 700; display: flex; align-items: center; justify-content: center; padding: 0 4px; border: 2px solid var(--bg); box-sizing: content-box; }
.toast { position: fixed; left: 50%; top: calc(env(safe-area-inset-top) + 10px); transform: translate(-50%, 0); width: min(calc(100% - 24px), 480px); background: rgba(28,28,34,0.96); backdrop-filter: blur(18px); -webkit-backdrop-filter: blur(18px); border: 1px solid #2A2A33; border-radius: 18px; padding: 12px 14px; display: flex; gap: 12px; align-items: center; z-index: 50; box-shadow: 0 12px 30px rgba(0,0,0,0.45); animation: toastRein 0.45s cubic-bezier(.2,.9,.2,1); text-align: left; }
.toast.weg { animation: toastRaus 0.35s ease-in forwards; }
.segment { display: flex; gap: 2px; background: var(--karte); border-radius: 10px; padding: 2px; }
.segment button { padding: 5px 10px; border-radius: 8px; font-size: 12px; font-weight: 600; color: var(--text2); }
.segment button.aktiv { background: var(--karte2); color: var(--text); }
.stat { background: var(--karte2); border-radius: 14px; padding: 10px 12px; }
.stat .w { font-size: 15px; font-weight: 700; margin-top: 4px; }
@keyframes hoch { from { transform: translateY(100%); } to { transform: none; } }
@keyframes runter { from { transform: none; } to { transform: translateY(100%); } }
.sheet-hg { position: fixed; inset: 0; background: rgba(0,0,0,0.55); z-index: 60; animation: einblenden 0.25s ease-out; }
.sheet { position: fixed; left: 0; right: 0; bottom: 0; max-height: 78vh; overflow-y: auto; background: #141418; border-radius: 24px 24px 0 0; z-index: 61; padding: 8px 16px calc(20px + env(safe-area-inset-bottom)); animation: hoch 0.38s cubic-bezier(.2,.9,.2,1); max-width: 520px; margin: 0 auto; border-top: 1px solid #24242C; }
.sheet.weg { animation: runter 0.25s ease-in forwards; }
.griff { width: 40px; height: 5px; border-radius: 3px; background: #3A3A44; margin: 4px auto 12px; }
.kal button.tag { width: 100%; border: 0; font-family: inherit; }
.punkte { display: flex; flex-direction: column; gap: 10px; margin-top: 10px; }
.punkte div { display: flex; gap: 10px; font-size: 13px; line-height: 1.45; color: #C7C7D1; }
.punkte .z { flex-shrink: 0; width: 20px; height: 20px; border-radius: 10px; display: flex; align-items: center; justify-content: center; font-size: 11px; font-weight: 800; color: #0B0B0E; margin-top: 1px; }
.frage { width: 20px; height: 20px; border-radius: 10px; background: #24242C; color: #9A9AA6; font-size: 11px; font-weight: 700; display: inline-flex; align-items: center; justify-content: center; margin-left: 6px; vertical-align: middle; flex-shrink: 0; position: relative; }
.frage::after { content: ""; position: absolute; inset: -12px; }
.vollbild { position: fixed; inset: 0; background: var(--bg); z-index: 80; padding: calc(env(safe-area-inset-top) + 8px) 0 calc(env(safe-area-inset-bottom) + 8px); overflow-y: auto; animation: einblenden 0.25s ease-out; }
.startknopf { background: var(--akzent); color: #0B0B0E; font-weight: 700; font-size: 13px; padding: 10px 14px; border-radius: 12px; white-space: nowrap; display: inline-flex; align-items: center; gap: 6px; }
.startknopf[disabled] { opacity: 0.85; }
@keyframes drehen { to { transform: rotate(360deg); } }
.kreis { width: 12px; height: 12px; border: 2px solid rgba(11,11,14,0.35); border-top-color: #0B0B0E; border-radius: 50%; animation: drehen 0.8s linear infinite; }
.schalter { width: 46px; height: 28px; border-radius: 14px; background: #2A2A33; position: relative; flex-shrink: 0; transition: background 0.2s; }
.schalter::after { content: ""; position: absolute; top: 3px; left: 3px; width: 22px; height: 22px; border-radius: 11px; background: #F4F4F6; transition: transform 0.2s; }
.schalter.an { background: var(--gruen); }
.schalter.an::after { transform: translateX(18px); }
.rang { width: 30px; height: 30px; border-radius: 15px; display: flex; align-items: center; justify-content: center; font-weight: 800; font-size: 13px; flex-shrink: 0; }
@keyframes plopp { 0% { transform: scale(0.55); opacity: 0; } 70% { transform: scale(1.08); opacity: 1; } 100% { transform: scale(1); } }
@keyframes schimmer { 0% { transform: translateX(-130%) skewX(-18deg); } 100% { transform: translateX(230%) skewX(-18deg); } }
@keyframes muenze { 0% { transform: rotateY(0); } 100% { transform: rotateY(360deg); } }
.icon { position: relative; overflow: hidden; transition: transform 0.15s ease; }
.icon::after { content: ""; position: absolute; top: 0; bottom: 0; left: 0; width: 45%; background: linear-gradient(90deg, transparent, rgba(255,255,255,0.45), transparent); transform: translateX(-130%) skewX(-18deg); pointer-events: none; }
main.anim-tab .icon, main.anim-detail .icon { animation: plopp 0.5s cubic-bezier(.2,.9,.3,1.2) both; animation-delay: var(--v, 0ms); }
main.anim-tab .icon::after, main.anim-detail .icon::after { animation: schimmer 0.9s ease-in-out both; animation-delay: calc(var(--v, 0ms) + 450ms); }
main.anim-tab .muenze, main.anim-detail .muenze { display: inline-block; animation: muenze 0.9s cubic-bezier(.3,.7,.3,1) both; animation-delay: calc(var(--v, 0ms) + 350ms); }
.zeile:active .icon, button:active > .icon { transform: scale(0.88); }
@media (prefers-reduced-motion: reduce) { *, *::before, *::after { animation: none !important; transition: none !important; } }
</style>
</head>
<body>
<main id="app"></main>
<nav class="tabbar" id="tabbar"></nav>

<script>
const D = %%DATEN%%;
let KURZ = D.kurz, LANG = D.lang;
const BOTS = D.bots || { haupt: null, turbo: null };
const TURBO_FARBE = "#FF9F5A", SHORT_FARBE = "#F472B6", TSHORT_FARBE = "#22D3EE";
// Alle Bots mit Name, Farbe und Symbol
const BOT_INFO = {
  haupt: { name: "Dein Bot", kurz: "Dein Bot", farbe: "#9D8CFF", bg: "#23202F", pfad: '<rect x="4" y="8" width="16" height="12" rx="3"/><path d="M12 8V4"/><circle cx="12" cy="3" r="1"/><circle cx="9" cy="14" r="1.2"/><circle cx="15" cy="14" r="1.2"/>' },
  turbo: { name: "Turbo-Bot", kurz: "Turbo", farbe: TURBO_FARBE, bg: "#2E2117", pfad: '<path d="M13 2L4.5 13.5H11L10 22l8.5-11.5H12z"/>' },
  short: { name: "Short-Bot", kurz: "Short", farbe: SHORT_FARBE, bg: "#2E1726", pfad: '<path d="M3 6l7 7 4-4 7 7"/><path d="M21 10v6h-6"/>' },
  tshort: { name: "Turbo-Short", kurz: "T-Short", farbe: TSHORT_FARBE, bg: "#10282D", pfad: '<path d="M13 2L4.5 13.5H11L10 22l8.5-11.5H12z"/><path d="M19 15v6M16.5 18.5L19 21l2.5-2.5"/>' },
};
const BOT_IDS = ["haupt", "turbo", "short", "tshort"];
const istEinstieg = (art) => art === "Kauf" || art === "Short";
const rundenProz = (art, k, v) => (art === "Short" ? (1 - v / k) * 100 : (v / k - 1) * 100);
const ART_FARBE = { Kauf: "#6BB6FF", Verkauf: "#F4F4F6", Short: SHORT_FARBE, Eindecken: "#F4F4F6" };
const ART_BG = { Kauf: "rgba(107,182,255,0.13)", Verkauf: "rgba(244,244,246,0.10)", Short: "rgba(244,114,182,0.14)", Eindecken: "rgba(244,244,246,0.10)" };
const ART_WORT = { Kauf: "gekauft", Verkauf: "verkauft", Short: "short gegangen", Eindecken: "eingedeckt" };
const ART_BUCHSTABE = { Kauf: "K", Verkauf: "V", Short: "S", Eindecken: "E" };
let AKTIV = "haupt";
const GRUEN = "#3DDC97", ROT = "#FF7A7A", GELB = "#F5B94A", AKZENT = "#9D8CFF", TEXT = "#F4F4F6";
const BOT_KAUF = "#6BB6FF", BOT_VERKAUF = "#F4F4F6";
const GRUEN_BG = "rgba(61,220,151,0.12)", ROT_BG = "rgba(255,122,122,0.12)", GELB_BG = "rgba(245,185,74,0.12)";

const zahl = (v, d) => Math.abs(v).toLocaleString("de-DE", { minimumFractionDigits: d, maximumFractionDigits: d });
// Kurse und Beträge: in der gewählten Währung (Dollar oder Euro)
const geld = (v) => { const w = v * fx(); return (w < 0 ? "−" : "") + zahl(w, Math.abs(w) >= 10000 ? 0 : 2) + " " + WAEHRUNG; };
// Währung: alles wahlweise in Dollar oder Euro (die Bots selbst rechnen in Dollar)
let WAEHRUNG = "$";
try { if (localStorage.getItem("bot_waehrung") === "€" && D.eurusd) WAEHRUNG = "€"; } catch (e) {}
const fx = () => (WAEHRUNG === "€" && D.eurusd ? 1 / D.eurusd : 1);
const betrag = (v, d) => zahl(v * fx(), d) + " " + WAEHRUNG;
const geldW = (v) => (v < 0 ? "−" : "") + betrag(v, Math.abs(v * fx()) >= 10000 ? 0 : 2);
function wechsleWaehrung() {
  WAEHRUNG = WAEHRUNG === "$" ? "€" : "$";
  try { localStorage.setItem("bot_waehrung", WAEHRUNG); } catch (e) {}
  render(false);
}
const vz = (v) => (v >= 0 ? "+" : "−");
// Zeitpunkte sind "JJJJ-MM-TT" (Tageskerzen) oder "JJJJ-MM-TT HH:MM" (Stundenkerzen)
const datum = (s) => { const t = s.slice(0, 10).split("-"); return t[2] + "." + t[1] + "." + t[0] + (s.length > 10 ? " " + s.slice(11, 16) : ""); };
const kurzDatum = (s) => datum(s.slice(0, 10)).slice(0, 6) + (s.length > 10 ? " " + s.slice(11, 16) : "");
const zeitpunkt = (s) => { const t = s.slice(0, 10).split("-").map(Number), u = s.length > 10 ? s.slice(11, 16).split(":").map(Number) : [0, 0]; return new Date(t[0], t[1] - 1, t[2], u[0], u[1]); };
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const farbe = (v) => (v >= 0 ? GRUEN : ROT);
function tageZurueck(s, n) {
  const t = s.slice(0, 10).split("-").map(Number);
  const d = new Date(t[0], t[1] - 1, t[2] - n);
  return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
}
function stueck(a) {
  const m = Math.abs(a.stk);
  return (a.einheit === "BTC" ? m.toLocaleString("de-DE", { maximumFractionDigits: 6 }) + " BTC" : zahl(m, 2) + " Stk") + (a.stk < 0 ? " short" : "");
}
function schnitt(w, n) {
  const aus = []; let s = 0;
  for (let i = 0; i < w.length; i++) { s += w[i]; if (i >= n) s -= w[i - n]; aus.push(i >= n - 1 ? s / n : null); }
  return aus;
}
function rsiBerechnen(k, n) {
  const aus = new Array(k.length).fill(null);
  if (k.length <= n) return aus;
  let g = 0, l = 0;
  for (let i = 1; i <= n; i++) { const d = k[i] - k[i - 1]; if (d > 0) g += d; else l -= d; }
  g /= n; l /= n;
  aus[n] = l === 0 ? 100 : 100 - 100 / (1 + g / l);
  for (let i = n + 1; i < k.length; i++) {
    const d = k[i] - k[i - 1];
    g = (g * (n - 1) + Math.max(d, 0)) / n;
    l = (l * (n - 1) + Math.max(-d, 0)) / n;
    aus[i] = l === 0 ? 100 : 100 - 100 / (1 + g / l);
  }
  return aus;
}
function kompakt(v) {
  v = v * fx();
  const a = Math.abs(v);
  if (a >= 1e9) return zahl(v / 1e9, 2) + " Mrd " + WAEHRUNG;
  if (a >= 1e6) return zahl(v / 1e6, 2) + " Mio " + WAEHRUNG;
  if (a >= 1e5) return zahl(v / 1e3, 0) + " Tsd " + WAEHRUNG;
  return zahl(v, 0) + " " + WAEHRUNG;
}
function volText(v) {
  if (v >= 1e9) return zahl(v / 1e9, 2) + " Mrd";
  if (v >= 1e6) return zahl(v / 1e6, 2) + " Mio";
  if (v >= 1e3) return zahl(v / 1e3, 1) + " Tsd";
  return zahl(v, 0);
}
function schoeneSchritte(lo, hi, anzahl) {
  const roh = (hi - lo) / anzahl, p = Math.pow(10, Math.floor(Math.log10(roh))), f = roh / p;
  const schritt = (f < 1.5 ? 1 : f < 3 ? 2 : f < 7 ? 5 : 10) * p;
  const werte = [];
  for (let v = Math.ceil(lo / schritt) * schritt; v <= hi; v += schritt) werte.push(v);
  return werte;
}
function wochenKey(s) {
  const t = s.slice(0, 10).split("-").map(Number), d = new Date(t[0], t[1] - 1, t[2]);
  d.setDate(d.getDate() - ((d.getDay() + 6) % 7));
  return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
}
function zuWochen(kerzen) {
  const aus = [];
  kerzen.forEach((k) => {
    const w = wochenKey(k.d), letzte = aus[aus.length - 1];
    if (letzte && letzte.w === w) {
      letzte.h = Math.max(letzte.h, k.h); letzte.l = Math.min(letzte.l, k.l); letzte.c = k.c; letzte.v += k.v;
      letzte.k10 = k.k10; letzte.k30 = k.k30; letzte.rsi = k.rsi; letzte.bis = k.d; letzte.tage.push(k.d);
    } else aus.push({ ...k, w, bis: k.d, tage: [k.d] });
  });
  return aus;
}

// ---------- Auswertung je Aktie ----------
// Bot-unabhängig: Kurse, RSI, Schwankung (immer aus Tageskerzen)
D.assets.forEach((a) => {
  const k = a.kurse, n = k.length;
  a.tagOk = a.ok = n > D.lang + 5;
  if (!a.ok) { a.tagReihe = { tage: a.tage, kurse: a.kurse, offen: a.offen, hoch: a.hoch, tief: a.tief, vol: a.vol, rsi: [] }; return; }
  if (!a.offen || a.offen.length !== n) { a.offen = k.slice(); a.hoch = k.slice(); a.tief = k.slice(); a.vol = k.map(() => 0); }
  a.tagReihe = { tage: a.tage, kurse: a.kurse, offen: a.offen, hoch: a.hoch, tief: a.tief, vol: a.vol, rsi: rsiBerechnen(k, 14) };
  if (a.std && a.std.c.length) a.stdReihe = { tage: a.std.z, kurse: a.std.c, offen: a.std.o, hoch: a.std.h, tief: a.std.l, vol: a.std.v, rsi: rsiBerechnen(a.std.c, 14) };
  const r = [];
  for (let i = Math.max(1, n - 60); i < n; i++) r.push(k[i] / k[i - 1] - 1);
  const m = r.reduce((s, v) => s + v, 0) / r.length;
  a.sigma = Math.sqrt(r.reduce((s, v) => s + (v - m) ** 2, 0) / Math.max(r.length - 1, 1));
  a.tag = k[n - 1] - k[n - 2];
  a.tagProz = a.tag / k[n - 2] * 100;
});

// Bot-abhängig: Bestand, Durchschnitte, Signale, Runden, Kalender
let RUNDEN = [], MONATE = [];
function aktiviere(id) {
  if (!BOTS[id]) id = "haupt";
  if (!BOTS[id]) return;
  const B = BOTS[id];
  const wechsel = AKTIV !== id;
  AKTIV = id; KURZ = B.kurz; LANG = B.lang;
  D.depot = B.depot; D.aenderung = B.aenderung; D.proTag = B.proTag;
  D.assets.forEach((a) => {
    // Kerzen des aktiven Bots: Tag oder Stunde
    const R = B.intervall === "1h" && a.stdReihe ? a.stdReihe : a.tagReihe;
    a.tage = R.tage; a.kurse = R.kurse; a.offen = R.offen; a.hoch = R.hoch; a.tief = R.tief; a.vol = R.vol; a.rsi = R.rsi;
    a.ok = a.tagOk && a.kurse.length > LANG + 5;
    const z = B.assets[a.t] || { stk: 0, konto: D.start, akt: [], startTag: "", startKurs: null };
    a.stk = z.stk; a.konto = z.konto; a.akt = z.akt; a.startTag = z.startTag; a.startKurs = z.startKurs == null ? a.preis : z.startKurs;
    a.wert = Math.round((a.konto + a.stk * a.preis) * 100) / 100;
    a.drin = a.stk !== 0;
    a.letzterKauf = a.akt.filter((x) => istEinstieg(x[1])).slice(-1)[0] || null;
    if (!a.ok) return;
    const k = a.kurse, n = k.length;
    a.k10 = schnitt(k, KURZ); a.k30 = schnitt(k, LANG);
    const jk = a.k10[n - 1], jl = a.k30[n - 1];
    a.auf = jk > jl;
    a.abstand = (jk - jl) / jl * 100;
    let sk = 0, sl = 0;
    for (let i = n - (KURZ - 1); i < n; i++) sk += k[i];
    for (let i = n - (LANG - 1); i < n; i++) sl += k[i];
    a.schwelle = (KURZ * sl - LANG * sk) / (LANG - KURZ);
    a.noetig = a.schwelle > 0 ? (a.schwelle / a.preis - 1) * 100 : null;
  });
  // Abgeschlossene Runden (Kauf + Verkauf)
  RUNDEN = [];
  D.assets.forEach((a) => {
    let kauf = null;
    a.akt.forEach(([tag, art, p]) => {
      if (istEinstieg(art)) kauf = [tag, p, art];
      else if (kauf) { RUNDEN.push({ a, von: kauf[0], bis: tag, k: kauf[1], v: p, art: kauf[2], proz: rundenProz(kauf[2], kauf[1], p) }); kauf = null; }
    });
  });
  RUNDEN.sort((x, y) => (x.bis < y.bis ? 1 : -1));
  MONATE = Array.from(new Set(Object.keys(D.aenderung).map((k) => k.slice(0, 7)))).sort();
  return wechsel;
}
const istTurbo = () => AKTIV === "turbo";
const istHaupt = () => AKTIV === "haupt";
const istShort = () => !!(BOTS[AKTIV] && BOTS[AKTIV].richtung === "short");
const istStunde = () => !!(BOTS[AKTIV] && BOTS[AKTIV].intervall === "1h");
const naechsteKerze = () => (istStunde() ? "in der nächsten Stunde" : "am nächsten Handelstag");
const kerzenWort = () => (istStunde() ? "Stunden" : "Tage");
const botFarbe = () => BOT_INFO[AKTIV].farbe;
const botName = () => BOT_INFO[AKTIV].name;
AKTIV = "";
aktiviere("haupt");
const state = { tab: "depot", depotWahl: liesWahl("bot_wahl_depot", "haupt"), turboWahl: liesWahl("bot_wahl_turbo", "turbo"), sicht: "haupt", detailBot: "haupt", detail: null, mitteilungen: false, markiert: 0, vollbild: false, push: { kauf: true, verkauf: true, bericht: false }, liste: "gesamt", dRange: "Alle", kRangeStd: "1W", kRange: "3M", kIntervall: "T", unten: "vol", monat: Math.max(MONATE.length - 1, 0), nurNah: false };

// ---------- Hilfen für Charts ----------
function pfad(werte, x, y) {
  let d = "", an = false;
  werte.forEach((v, i) => {
    if (v == null) { an = false; return; }
    d += (an ? "L" : "M") + x(i).toFixed(1) + "," + y(v).toFixed(1) + " "; an = true;
  });
  return d;
}
function grenzen(listen) {
  const alle = [].concat(...listen).filter((v) => v != null);
  let lo = Math.min(...alle), hi = Math.max(...alle);
  const pad = (hi - lo) * 0.08 || Math.abs(hi) * 0.01 || 1;
  return [lo - pad, hi + pad];
}
function breite() { return Math.min(document.getElementById("app").clientWidth || 390, 520); }
// Branchen-Symbole (eigene Zeichnungen, keine Firmenlogos)
const SYMBOLE = {
  AAPL: '<rect x="7" y="2.5" width="10" height="19" rx="2.5"/><path d="M11 18.5h2"/>',
  MSFT: '<rect x="4" y="5" width="16" height="11" rx="1.5"/><path d="M2 19h20"/>',
  NVDA: '<rect x="7" y="7" width="10" height="10" rx="1.5"/><path d="M10 10h4v4h-4z"/><path d="M9 3v4M15 3v4M9 17v4M15 17v4M3 9h4M3 15h4M17 9h4M17 15h4"/>',
  GOOGL: '<circle cx="10.5" cy="10.5" r="6"/><path d="M15 15l5.5 5.5"/>',
  AMZN: '<path d="M3.5 7.5L12 3l8.5 4.5v9L12 21l-8.5-4.5z"/><path d="M3.5 7.5L12 12l8.5-4.5M12 12v9"/>',
  JPM: '<path d="M3 9.5L12 4l9 5.5"/><path d="M5 10.5v7.5M9.5 10.5v7.5M14.5 10.5v7.5M19 10.5v7.5M3 20.5h18"/>',
  KO: '<path d="M6 8h12l-1.6 13H7.6z"/><path d="M5 8h14"/><path d="M13 8l2-5h3"/>',
  XOM: '<rect x="4" y="3" width="10" height="18" rx="1.5"/><path d="M4 10h10"/><path d="M14 8h2.5l2.5 3v7a1.5 1.5 0 0 1-3 0v-3h-2"/>',
  GLD: '<path d="M3 20l2-5h6l2 5z"/><path d="M11 20l2-5h6l2 5z"/><path d="M7 15l2-5h6l2 5"/>',
};
let ICON_ZAEHLER = 0;
function icon(a, g) {
  const pfad = SYMBOLE[a.t];
  const inhalt = pfad
    ? `<svg width="${Math.round(g * 0.52)}" height="${Math.round(g * 0.52)}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="${g < 30 ? 2.6 : 2}" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${pfad}</svg>`
    : (a.t === "BTC-USD" ? `<span class="muenze" style="font-size:${Math.round(g * 0.52)}px;font-weight:800;line-height:1">₿</span>` : esc(a.sym));
  const v = Math.min(ICON_ZAEHLER++ * 40, 600);
  return `<span class="icon" role="img" aria-label="${esc(a.name)}" style="width:${g}px;height:${g}px;background:${a.bg};color:${a.fg};font-size:${Math.round(g / 3)}px;--v:${v}ms">${inhalt}</span>`;
}
function tippbar(box, n, xFn, inhalt) {
  const svg = box.querySelector("svg"), tip = box.querySelector(".tip"), kreuz = box.querySelector(".kreuz");
  if (!svg) return;
  const W = svg.viewBox.baseVal.width;
  function zeige(cx) {
    const r = svg.getBoundingClientRect();
    const px = (cx - r.left) * (W / r.width);
    let best = 0, abst = 1e9;
    for (let i = 0; i < n; i++) { const d = Math.abs(xFn(i) - px); if (d < abst) { abst = d; best = i; } }
    const xx = xFn(best);
    kreuz.setAttribute("x1", xx); kreuz.setAttribute("x2", xx); kreuz.setAttribute("opacity", "0.6");
    tip.innerHTML = inhalt(best); tip.style.display = "block";
    const tw = tip.offsetWidth, sx = xx * r.width / W;
    tip.style.left = (sx > r.width / 2 ? Math.max(0, sx - tw - 10) : Math.min(r.width - tw, sx + 10)) + "px";
  }
  svg.addEventListener("pointerdown", (e) => zeige(e.clientX));
  svg.addEventListener("pointermove", (e) => { if (e.pointerType === "mouse" || e.buttons) zeige(e.clientX); });
  svg.addEventListener("pointerleave", (e) => {
    if (e.pointerType !== "mouse") return;
    tip.style.display = "none"; kreuz.setAttribute("opacity", "0");
  });
}

// ---------- Depot ----------
function depotSeite() {
  const startGesamt = D.start * D.assets.length;
  const wert = D.assets.reduce((s, a) => s + a.wert, 0);
  const bargeld = D.assets.reduce((s, a) => s + a.konto, 0);
  const imMarkt = D.assets.filter((a) => a.drin).length;
  const treffer = RUNDEN.length ? Math.round(RUNDEN.filter((r) => r.proz > 0).length / RUNDEN.length * 100) + " %" : "–";
  const v = D.depot, n = v.labels.length;
  const laenge = { "1W": 7, "1M": 30, "3M": 91 };
  let ab = 0;
  if (state.dRange !== "Alle" && n) { const g = tageZurueck(v.labels[n - 1], laenge[state.dRange]); ab = Math.max(0, v.labels.findIndex((d) => d >= g)); }
  const lab = v.labels.slice(ab), bot = v.bot.slice(ab), bh = v.bh.slice(ab);
  let diff, basis, text;
  if (state.dRange === "Alle" || bot.length < 2) { diff = wert - startGesamt; basis = startGesamt; text = "seit Start mit " + zahl(startGesamt, 0) + " $" + (WAEHRUNG === "€" ? " (≈ " + betrag(startGesamt, 0) + ")" : ""); }
  else { diff = bot[bot.length - 1] - bot[0]; basis = bot[0]; text = { "1W": "letzte Woche", "1M": "letzter Monat", "3M": "letzte 3 Monate" }[state.dRange]; }
  const vergleich = n ? v.bot[n - 1] - v.bh[n - 1] : 0;

  let chart = `<div class="leer">Der Verlauf erscheint, sobald der Bot ein paar Tage gelaufen ist.</div>`;
  if (lab.length >= 2) {
    const W = breite(), H = 170;
    const [lo, hi] = grenzen([bot, bh]);
    const x = (i) => 6 + i / (lab.length - 1) * (W - 12), y = (val) => 12 + (hi - val) / (hi - lo) * (H - 22);
    const linie = pfad(bot, x, y);
    chart = `<div class="chartbox" id="depotchart"><svg width="100%" viewBox="0 0 ${W} ${H}" role="img" aria-label="Depotwert gegen Buy-and-Hold">
      <defs><linearGradient id="fuell" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${botFarbe()}" stop-opacity="0.28"/><stop offset="1" stop-color="${botFarbe()}" stop-opacity="0"/></linearGradient></defs>
      <path class="blende" d="${linie}L${x(lab.length - 1)},${H} L${x(0)},${H} Z" fill="url(#fuell)"/>
      <path d="${pfad(bh, x, y)}" fill="none" stroke="#5E5E6B" stroke-width="1.5" stroke-dasharray="3 4"/>
      <path class="zeichnen" pathLength="1" d="${linie}" fill="none" stroke="${botFarbe()}" stroke-width="2.2" stroke-linejoin="round" stroke-linecap="round"/>
      <circle cx="${x(lab.length - 1)}" cy="${y(bot[bot.length - 1])}" r="4.5" fill="${botFarbe()}" stroke="#0B0B0E" stroke-width="2"/>
      <line class="kreuz" x1="0" x2="0" y1="6" y2="${H}" stroke="${TEXT}" stroke-dasharray="3 3" opacity="0"/>
    </svg><div class="tip"></div></div>`;
    setTimeout(() => {
      const box = document.getElementById("depotchart");
      if (box) tippbar(box, lab.length, x, (i) => `<b>${datum(lab[i])}</b><br><span class="fleck" style="background:${botFarbe()}"></span>${botName()}: ${geldW(bot[i])}<br><span class="fleck" style="background:#6E6E7A"></span>Buy-and-Hold: ${geldW(bh[i])}`);
    });
  }

  const sortiert = state.liste === "heute"
    ? D.assets.slice().sort((p, q) => (q.ok ? q.tagProz : -999) - (p.ok ? p.tagProz : -999))
    : D.assets.slice().sort((p, q) => q.wert - p.wert);
  const liste = sortiert.map((a) => {
    const gv = a.wert - D.start;
    const sp = a.tagReihe.kurse.slice(-30);
    let spark = "";
    if (sp.length > 1) {
      const lo = Math.min(...sp), hi = Math.max(...sp) || 1;
      spark = pfad(sp, (i) => i / (sp.length - 1) * 58, (val) => 3 + (hi - val) / ((hi - lo) || 1) * 22);
    }
    return `<button class="zeile" onclick="oeffne('${a.t}')">
      ${icon(a, 42)}
      <span style="flex-grow:1;min-width:0">
        <span style="display:block;font-size:15px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${esc(a.name)}</span>
        <span class="klein" style="display:flex;align-items:center;gap:5px;margin-top:3px;white-space:nowrap;overflow:hidden"><span class="punkt" style="background:${a.drin ? (a.stk < 0 ? SHORT_FARBE : GRUEN) : GELB}" aria-label="${a.drin ? (a.stk < 0 ? "Short" : "Im Markt") : "Wartet"}"></span><span class="num" style="color:#C7C7D1">${geld(a.preis)}</span>${a.ok ? `<span class="num" style="color:${farbe(a.tag)}">${vz(a.tagProz)}${zahl(a.tagProz, 2)} %</span>` : ""}${LIVE.quellen[a.t] ? '<span class="live-punkt" style="margin-left:2px"></span>' : ""}</span>
      </span>
      <svg width="${a.wert >= 100000 ? 44 : 58}" height="28" viewBox="0 0 58 28" preserveAspectRatio="none" aria-hidden="true" style="flex-shrink:0"><path d="${spark}" fill="none" stroke="${farbe(gv)}" stroke-width="1.6" stroke-linejoin="round"/></svg>
      ${state.liste === "heute" ? `<span style="text-align:right;min-width:86px;flex-shrink:0;white-space:nowrap">
        <span class="num" style="display:block;font-size:15px;font-weight:600;color:${a.ok ? farbe(a.tagProz) : TEXT}">${a.ok ? vz(a.tagProz) + zahl(a.tagProz, 2) + " %" : "–"}</span>
        <span class="num leise" style="display:block;font-size:12px;font-weight:600;margin-top:3px">${a.drin && a.ok ? vz(a.tag) + betrag(a.stk * a.tag, 2) : "kein Bestand"}</span>
      </span>` : `<span style="text-align:right;min-width:86px;flex-shrink:0;white-space:nowrap">
        <span class="num" style="display:block;font-size:${a.wert >= 100000 ? 14 : 15}px;font-weight:600">${a.wert >= 100000 ? betrag(a.wert, 0) : betrag(a.wert, 2)}</span>
        <span class="num" style="display:block;font-size:12px;font-weight:600;margin-top:3px;color:${farbe(gv)}">${vz(gv)}${zahl(gv / D.start * 100, 2)} %</span>
      </span>`}
    </button>`;
  }).join("");

  return `
  <div style="display:flex;align-items:center;justify-content:space-between;padding:12px 20px 0">
    <div style="display:flex;align-items:center;gap:10px">
      ${state.botDepot ? `<button class="rund" onclick="zurueck()" aria-label="Zurück" style="width:34px;height:34px"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="${TEXT}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M15 18l-6-6 6-6"/></svg></button>` : ""}
      ${istHaupt() ? `<span class="icon" style="width:34px;height:34px;background:#23202F"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#B4A8FF" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${BOT_INFO.haupt.pfad}</svg></span>` : `<span class="icon" style="width:34px;height:34px;background:${BOT_INFO[AKTIV].bg}"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="${botFarbe()}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${BOT_INFO[AKTIV].pfad}</svg></span>`}
      <div><div style="font-size:15px;font-weight:600;display:flex;align-items:center">${wahlPaar().filter((id) => BOTS[id]).length > 1 && !state.botDepot
        ? `<button onclick="zeigeBotWahl()" aria-label="Bot wechseln" style="display:inline-flex;align-items:center;gap:5px;font-weight:600;white-space:nowrap">${istHaupt() ? "Paper-Depot" : botName()}<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#9A9AA6" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 9l6 6 6-6"/></svg></button>`
        : (istHaupt() ? "Paper-Depot" : botName())}${istHaupt() ? "" : `<button class="frage" onclick="erklaere('${AKTIV}')" aria-label="Was ist der ${botName()}?">?</button>`}</div>
      <div class="klein" style="display:flex;align-items:center;gap:5px"><span class="punkt" style="background:${GRUEN}"></span><span class="jetzt num">${jetztText()}</span></div></div>
    </div>
    <div style="display:flex;align-items:center;gap:8px">
      ${istHaupt() ? `<span class="pill" style="color:#B4A8FF;background:#1E1A2E">Spielgeld</span>` : state.botDepot ? "" : `<span class="pill" style="color:${botFarbe()};background:${BOT_INFO[AKTIV].bg}">${istShort() ? "Short" : istStunde() ? "1 Std" : ""}</span>`}
      ${D.eurusd ? `<button class="glocke" onclick="wechsleWaehrung()" aria-label="Währung wechseln, gerade ${WAEHRUNG === "€" ? "Euro" : "Dollar"}" style="font-size:16px;font-weight:700;color:${WAEHRUNG === "€" ? "#B4A8FF" : TEXT}">${WAEHRUNG}</button>` : ""}
      <button class="glocke" onclick="oeffneMitteilungen()" aria-label="Mitteilungen${ungelesen() ? ", " + ungelesen() + " ungelesen" : ""}">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="${TEXT}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 8a6 6 0 1 1 12 0c0 7 3 8 3 8H3s3-1 3-8"/><path d="M10.3 21a1.9 1.9 0 0 0 3.4 0"/></svg>
        ${ungelesen() ? `<span class="badge num">${badgeText(ungelesen())}</span>` : ""}
      </button>
    </div>
  </div>
  ${istHaupt() ? cloudKarte() + liveKarte() : ""}
  <div style="text-align:center;padding:26px 20px 0">
    <div class="klein" style="font-size:13px;font-weight:500">${istHaupt() ? "Depotwert" : BOT_INFO[AKTIV].kurz + "-Depot"}</div>
    <div class="num" id="depotwert" data-ziel="${wert}" style="font-size:${zahl(wert, 2).length > 12 ? 36 : zahl(wert, 2).length > 9 ? 42 : 46}px;font-weight:700;letter-spacing:-1.6px;margin-top:6px;line-height:1;white-space:nowrap">${betrag(wert, 2)}</div>
    <div class="num pill" style="display:inline-flex;gap:6px;margin-top:14px;font-size:14px;padding:6px 12px;border-radius:12px;color:${farbe(diff)};background:${diff >= 0 ? GRUEN_BG : ROT_BG}">
      <span>${diff >= 0 ? "▲" : "▼"}</span><span>${vz(diff)}${betrag(diff, 2)}</span><span style="opacity:.55">·</span><span>${vz(diff)}${zahl(diff / basis * 100, 2)} %</span>
    </div>
    <div class="leise" style="font-size:12px;margin-top:8px">${text}</div>
    ${LIVE.zeit ? `<div style="margin-top:6px">${liveMarke()}</div>` : ""}
    ${WAEHRUNG === "€" && D.eurusd ? `<div class="leise" style="font-size:11px;margin-top:4px">Alles umgerechnet mit 1 € = ${zahl(D.eurusd, 4)} $</div>` : ""}
  </div>
  ${istHaupt() ? "" : duellKarte(AKTIV)}
  <div style="margin-top:18px">${chart}</div>
  <div class="chips">${["1W", "1M", "3M", "Alle"].map((r) => `<button class="chip ${r === state.dRange ? "aktiv" : ""}" onclick="setze({dRange:'${r}'})">${r}</button>`).join("")}</div>
  <div class="legende"><span><span class="strich" style="background:${botFarbe()}"></span>${botName()}</span><span><span class="strich" style="border-top:2px dashed #6E6E7A;height:0"></span>Buy-and-Hold</span></div>
  <div style="display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;padding:22px 16px 0">
    <div class="kachel"><div class="klein">Im Markt</div><div class="num" style="font-size:18px;font-weight:700;margin-top:6px">${imMarkt}<span class="leise" style="font-weight:500;font-size:14px"> / ${D.assets.length}</span></div></div>
    <div class="kachel"><div class="klein">Bargeld</div><div class="num" style="font-size:18px;font-weight:700;margin-top:6px;white-space:nowrap">${kompakt(bargeld)}</div></div>
    <div class="kachel"><div class="klein" style="display:flex;align-items:center">Treffer<button class="frage" onclick="erklaere('treffer')" aria-label="Was ist die Trefferquote?">?</button></div><div class="num" style="font-size:18px;font-weight:700;margin-top:6px">${treffer}<span class="leise" style="font-weight:500;font-size:13px"> · ${RUNDEN.length}</span></div></div>
  </div>
  ${heuteKarte()}
  ${wocheKarte()}
  <div class="abschnitt" style="align-items:center"><b>Positionen</b>
    <div class="segment"><button class="${state.liste !== "heute" ? "aktiv" : ""}" onclick="setze({liste:'gesamt'})">Gesamt</button><button class="${state.liste === "heute" ? "aktiv" : ""}" onclick="setze({liste:'heute'})">Heute</button></div>
  </div>
  <div style="padding:0 8px">${liste}</div>
  <div class="karte" style="display:flex;align-items:center;justify-content:space-between;border-radius:16px;padding:14px 16px">
    <div><div class="klein" style="font-size:13px;display:flex;align-items:center">Bot gegen Liegenlassen<button class="frage" onclick="erklaere('liegenlassen')" aria-label="Was heißt Liegenlassen?">?</button></div>
    <div class="num" style="font-size:16px;font-weight:700;margin-top:4px;color:${farbe(vergleich)}">${vz(vergleich)}${betrag(vergleich, 2)}</div></div>
    <div class="leise" style="font-size:12px;text-align:right;max-width:170px">Buy-and-Hold aller Werte seit dem ersten Bot-Tag</div>
  </div>`;
}

// Kerzenchart mit Zoom (zwei Finger) und Verschieben (wischen)
const CHART_ARGS = {}, CHART_INFO = {};
function kerzenChart(a, W, H1, H2, boxId) {
  CHART_ARGS[boxId] = { t: a.t, W, H1, H2 };
  setTimeout(() => bindeGesten(boxId));
  return `<div id="${boxId}-rahmen" class="chartrahmen">${kerzenInnen(a, W, H1, H2, boxId)}</div>`;
}
function kerzenInnen(a, W, H1, H2, boxId) {
  const n = a.kurse.length;
  const dez = a.preis >= 10000 ? 0 : 2;
  let ab;
  if (istStunde()) {
    // Stundenkerzen: die letzten 1, 3, 5 oder 21 Handelstage
    const tageListe = Array.from(new Set(a.tage.map((d) => d.slice(0, 10))));
    const anzahl = { "1T": 1, "3T": 3, "1W": a.einheit === "BTC" ? 7 : 5, "1M": a.einheit === "BTC" ? 30 : 21 }[state.kRangeStd] || 5;
    const g = tageListe[Math.max(0, tageListe.length - anzahl)];
    ab = Math.max(0, a.tage.findIndex((d) => d >= g));
  } else {
    const zeitraum = { "1M": 30, "3M": 91, "6M": 182, "1J": 366 };
    const g = tageZurueck(a.tage[n - 1], zeitraum[state.kRange]);
    ab = Math.max(0, a.tage.findIndex((d) => d >= g));
  }
  let alle = [];
  for (let i = 0; i < n; i++) {
    alle.push({ d: a.tage[i], o: a.offen[i], h: a.hoch[i], l: a.tief[i], c: a.kurse[i], v: a.vol[i], k10: a.k10[i], k30: a.k30[i], rsi: a.rsi[i], tage: [a.tage[i]] });
  }
  const woche = state.kIntervall === "W" && !istStunde();
  if (woche) alle = zuWochen(alle);
  const total = alle.length;
  // Standard-Ausschnitt aus dem gewählten Zeitraum (1M, 3M ...), danach eigener Zoom
  const abTag = a.tage[ab];
  const standardN = Math.max(1, alle.filter((k) => (k.bis || k.d) >= abTag).length);
  const key = [a.t, AKTIV, woche ? "W" : istStunde() ? "H" : "T", istStunde() ? state.kRangeStd : state.kRange].join("|");
  const cv = state.cv && state.cv.key === key ? state.cv : null;
  const minN = Math.min(8, total);
  const sichtN = Math.max(minN, Math.min(total, cv ? cv.n : standardN));
  const sichtEnde = Math.max(sichtN, Math.min(total, cv ? (cv.rechts ? total : cv.ende) : total));
  const kerzen = alle.slice(sichtEnde - sichtN, sichtEnde);
  const anz = kerzen.length;
  const gezoomt = !!cv && (sichtEnde < total || sichtN !== Math.min(total, standardN));

  // Maße: Hauptchart oben, Volumen oder RSI darunter
  const RA = 54, LI = 6, OB = 14, ZW = 22, H = H1 + ZW + H2 + 18;
  const schritt = (W - LI - RA) / Math.max(anz, 1);
  const x = (i) => LI + schritt * (i + 0.5);
  const koerper = Math.max(1.4, Math.min(schritt * 0.64, 14));
  const werteY = [];
  kerzen.forEach((k) => { werteY.push(k.h, k.l); if (!woche) { if (k.k10 != null) werteY.push(k.k10); if (k.k30 != null) werteY.push(k.k30); } });
  const kaufLinie = a.drin && a.letzterKauf ? a.letzterKauf[2] : null;
  let lo = Math.min(...werteY), hi = Math.max(...werteY);
  if (kaufLinie && kaufLinie > lo * 0.85 && kaufLinie < hi * 1.15) { lo = Math.min(lo, kaufLinie); hi = Math.max(hi, kaufLinie); }
  const pad = (hi - lo) * 0.07 || hi * 0.01; lo -= pad; hi += pad;
  const y = (v) => OB + (hi - v) / (hi - lo) * (H1 - OB - 6);

  let svg = "";
  const yPreis = y(alle[total - 1].c);
  const fw = fx();
  schoeneSchritte(lo * fw, hi * fw, 4).forEach((vw) => {
    const v = vw / fw;
    svg += `<line x1="${LI}" x2="${W - RA}" y1="${y(v)}" y2="${y(v)}" stroke="#1A1A20"/>`;
    if (Math.abs(y(v) - yPreis) > 13) svg += `<text x="${W - RA + 6}" y="${y(v) + 3.5}" fill="#6E6E7A" font-size="10">${zahl(vw, vw >= 1000 ? 0 : 2)}</text>`;
  });
  const datumsZahl = Math.min(4, anz);
  for (let q = 0; q < datumsZahl; q++) {
    const i = datumsZahl === 1 ? 0 : Math.round(q * (anz - 1) / (datumsZahl - 1));
    svg += `<text x="${x(i)}" y="${H1 + 14}" fill="#6E6E7A" font-size="10" text-anchor="${q === 0 ? "start" : q === datumsZahl - 1 ? "end" : "middle"}">${kurzDatum(kerzen[i].d)}</text>`;
  }
  if (!woche) {
    svg += `<path class="zeichnen" pathLength="1" d="${pfad(kerzen.map((k) => k.k30), x, y)}" fill="none" stroke="${AKZENT}" stroke-width="1.4" stroke-linejoin="round"/>`;
    svg += `<path class="zeichnen" pathLength="1" d="${pfad(kerzen.map((k) => k.k10), x, y)}" fill="none" stroke="${GELB}" stroke-width="1.4" stroke-linejoin="round"/>`;
  }
  kerzen.forEach((k, i) => {
    const hoch = k.c >= k.o, f = hoch ? GRUEN : ROT, xx = x(i);
    const yo = y(Math.max(k.o, k.c)), yu = y(Math.min(k.o, k.c));
    svg += `<line x1="${xx}" x2="${xx}" y1="${y(k.h)}" y2="${y(k.l)}" stroke="${f}" stroke-width="1"/>`;
    svg += `<rect x="${xx - koerper / 2}" y="${yo}" width="${koerper}" height="${Math.max(yu - yo, 1)}" fill="${f}" rx="${koerper > 6 ? 1 : 0}"/>`;
  });
  // Käufe und Verkäufe des Bots
  a.akt.forEach(([t, art]) => {
    const i = kerzen.findIndex((k) => k.tage.includes(t));
    if (i < 0) return;
    const kauf = art === "Kauf" || art === "Eindecken", xx = x(i), f = ART_FARBE[art] || BOT_VERKAUF;
    const ende = kauf ? y(kerzen[i].l) + 3 : y(kerzen[i].h) - 3;
    const yy = Math.max(OB + 9, Math.min(H1 - 10, kauf ? ende + 15 : ende - 15));
    svg += `<line x1="${xx}" x2="${xx}" y1="${ende}" y2="${kauf ? yy - 8 : yy + 8}" stroke="${f}" stroke-width="1.2" opacity="0.9"/>`;
    svg += `<circle cx="${xx}" cy="${yy}" r="8.5" fill="${f}" stroke="#0B0B0E" stroke-width="2"/>`;
    svg += `<text x="${xx}" y="${yy + 3.6}" fill="#0B0B0E" font-size="10" font-weight="800" text-anchor="middle">${ART_BUCHSTABE[art] || "V"}</text>`;
  });
  // Linie mit dem Kaufkurs der offenen Position
  if (kaufLinie && kaufLinie >= lo && kaufLinie <= hi) {
    const yk = y(kaufLinie), text = (a.stk < 0 ? "SHORT " : "KAUF ") + stueck(a).replace(" short", "") + "  " + zahl(kaufLinie * fx(), dez);
    const bw = text.length * 5.6 + 12;
    const lf = a.stk < 0 ? SHORT_FARBE : "#6BB6FF";
    svg += `<line x1="${LI}" x2="${W - RA}" y1="${yk}" y2="${yk}" stroke="${lf}" stroke-dasharray="4 3" opacity="0.8"/>`;
    svg += `<rect x="${LI + 4}" y="${yk - 9}" width="${bw}" height="18" rx="5" fill="${a.stk < 0 ? "#2E1726" : "#13263A"}" stroke="${lf}" stroke-opacity="0.6"/>`;
    svg += `<text x="${LI + 10}" y="${yk + 3.5}" fill="${a.stk < 0 ? "#F9A8D4" : "#9CCBFF"}" font-size="10" font-weight="600">${text}</text>`;
  }
  // Aktueller Kurs mit Schild rechts
  // (zeigt immer den neuesten Kurs, auch wenn du in die Vergangenheit geblättert hast)
  const letzte = kerzen[anz - 1], neueste = alle[total - 1], pf = neueste.c >= neueste.o ? GRUEN : ROT;
  if (neueste.c >= lo && neueste.c <= hi) {
    const yp = y(neueste.c);
    svg += `<line x1="${LI}" x2="${W - RA}" y1="${yp}" y2="${yp}" stroke="${pf}" stroke-dasharray="2 3" opacity="0.7"/>`;
    svg += `<rect x="${W - RA + 2}" y="${yp - 9}" width="${RA - 4}" height="18" rx="5" fill="${pf}"/>`;
    svg += `<text x="${W - RA / 2}" y="${yp + 3.5}" fill="#0B0B0E" font-size="10" font-weight="700" text-anchor="middle">${zahl(neueste.c * fx(), neueste.c * fx() >= 1000 ? 0 : 2)}</text>`;
  }

  // Unteres Feld: Volumen oder RSI
  const y2o = H1 + ZW, y2u = y2o + H2;
  svg += `<line x1="${LI}" x2="${W - RA}" y1="${y2o - 2}" y2="${y2o - 2}" stroke="#1A1A20"/>`;
  let untenText;
  if (state.unten === "rsi") {
    const ry = (v) => y2o + (100 - v) / 100 * H2;
    [70, 30].forEach((v) => {
      svg += `<line x1="${LI}" x2="${W - RA}" y1="${ry(v)}" y2="${ry(v)}" stroke="#3A3A44" stroke-dasharray="3 3"/>`;
      svg += `<text x="${W - RA + 6}" y="${ry(v) + 3.5}" fill="#6E6E7A" font-size="10">${v}</text>`;
    });
    svg += `<path d="${pfad(kerzen.map((k) => k.rsi), x, ry)}" fill="none" stroke="${GELB}" stroke-width="1.5" stroke-linejoin="round"/>`;
    const r = letzte.rsi;
    untenText = `<span style="color:${GELB}">RSI(14): ${r == null ? "–" : zahl(r, 1)}</span>` + (r == null ? "" : r > 70 ? ` <span class="leise">· überkauft</span>` : r < 30 ? ` <span class="leise">· überverkauft</span>` : "") + `<button class="frage" onclick="erklaere('rsi')" aria-label="Was ist der RSI?">?</button>`;
  } else {
    const vmax = Math.max(...kerzen.map((k) => k.v), 1);
    kerzen.forEach((k, i) => {
      const hh = k.v / vmax * (H2 - 4);
      svg += `<rect x="${x(i) - koerper / 2}" y="${y2u - hh}" width="${koerper}" height="${Math.max(hh, 0.5)}" fill="${k.c >= k.o ? GRUEN : ROT}" opacity="0.55"/>`;
    });
    svg += `<text x="${W - RA + 6}" y="${y2o + 10}" fill="#6E6E7A" font-size="10">${volText(vmax)}</text>`;
    untenText = `<span style="color:#C7C7D1">Volumen: ${volText(letzte.v)}</span><button class="frage" onclick="erklaere('volumen')" aria-label="Was ist das Volumen?">?</button>`;
  }
  svg += `<line class="kreuz" x1="0" x2="0" y1="${OB}" y2="${y2u}" stroke="${TEXT}" stroke-dasharray="3 3" opacity="0"/>`;

  const chart = `
  <div class="num" style="display:flex;gap:12px;flex-wrap:wrap;padding:0 20px 6px;font-size:11px;font-weight:600">
    ${istStunde() ? `<span class="leise">1 Std</span>` : ""}${woche ? `<span class="leise">Wochenkerzen</span>` : `<span style="color:${GELB}">Ø${KURZ}: ${letzte.k10 == null ? "–" : zahl(letzte.k10 * fx(), dez)}</span><span style="color:${AKZENT}">Ø${LANG}: ${letzte.k30 == null ? "–" : zahl(letzte.k30 * fx(), dez)}</span><button class="frage" onclick="erklaere('durchschnitt')" aria-label="Was ist Ø${KURZ} und Ø${LANG}?">?</button>`}
    <span style="margin-left:auto;display:inline-flex;align-items:center;gap:4px">
      ${gezoomt ? `<button onclick="zoomeKerzen('${boxId}', 0)" style="color:#B4A8FF;font-size:11px;font-weight:700;padding:2px 8px;border-radius:8px;background:#1E1A2E">Jetzt ⟲</button>` : ""}
      <button onclick="zoomeKerzen('${boxId}', 0.7)" aria-label="Reinzoomen" class="zoomknopf">+</button><button onclick="zoomeKerzen('${boxId}', 1.4)" aria-label="Rauszoomen" class="zoomknopf">−</button>
    </span>
    ${boxId === "kurschart" ? `<button onclick="zeigeVollbild()" aria-label="Chart im Vollbild" style="margin-left:6px;display:flex;align-items:center;gap:5px;color:#9A9AA6;font-size:11px;font-weight:600"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/></svg></button>` : ""}
  </div>
  <div class="chartbox" id="${boxId}"><svg width="100%" viewBox="0 0 ${W} ${H}" role="img" aria-label="Kerzenchart mit Durchschnitten, Bot-Aktionen und ${state.unten === "rsi" ? "RSI" : "Volumen"}">${svg}</svg><div class="tip"></div></div>
  <div class="num" style="padding:0 20px;margin-top:-14px;font-size:11px;font-weight:600">${untenText}</div>`;

  CHART_INFO[boxId] = { key, total, n: sichtN, ende: sichtEnde, standardN, W, LI, RA, anz, x, inhalt: (i) => {
      const k = kerzen[i], ae = (k.c / k.o - 1) * 100;
      let h = `<b>${woche ? "Woche ab " + datum(k.d) : datum(k.d)}</b>`;
      h += `<br>Eröffnung: ${geld(k.o)}<br>Hoch: ${geld(k.h)}<br>Tief: ${geld(k.l)}<br>Schluss: ${geld(k.c)} <span style="color:${farbe(ae)}">${vz(ae)}${zahl(ae, 2)} %</span>`;
      if (!woche && k.k10 != null) h += `<br><span class="fleck" style="background:${GELB}"></span>Ø ${KURZ}: ${geld(k.k10)}`;
      if (!woche && k.k30 != null) h += `<br><span class="fleck" style="background:${AKZENT}"></span>Ø ${LANG}: ${geld(k.k30)}`;
      h += `<br><span class="leise">Volumen ${volText(k.v)}${k.rsi != null ? " · RSI " + zahl(k.rsi, 0) : ""}</span>`;
      a.akt.forEach(([t, art]) => { if (k.tage.includes(t)) h += `<br><b style="color:${ART_FARBE[art]}">Bot: ${art}</b>`; });
      return h;
    } };

  return chart;
}

function zeigeKerzenTip(boxId, cx) {
  const I = CHART_INFO[boxId], box = document.getElementById(boxId);
  if (!I || !box) return;
  const svg = box.querySelector("svg"), tip = box.querySelector(".tip"), kreuz = box.querySelector(".kreuz");
  const rr = svg.getBoundingClientRect(), px = (cx - rr.left) * (I.W / rr.width);
  let best = 0, abst = 1e9;
  for (let i = 0; i < I.anz; i++) { const d = Math.abs(I.x(i) - px); if (d < abst) { abst = d; best = i; } }
  const xx = I.x(best);
  kreuz.setAttribute("x1", xx); kreuz.setAttribute("x2", xx); kreuz.setAttribute("opacity", "0.6");
  tip.innerHTML = I.inhalt(best); tip.style.display = "block";
  const tw = tip.offsetWidth, sx = xx * rr.width / I.W;
  tip.style.left = (sx > rr.width / 2 ? Math.max(0, sx - tw - 10) : Math.min(rr.width - tw, sx + 10)) + "px";
}
function versteckeKerzenTip(boxId) {
  const box = document.getElementById(boxId);
  if (!box) return;
  const tip = box.querySelector(".tip"), k = box.querySelector(".kreuz");
  if (tip) tip.style.display = "none";
  if (k) k.setAttribute("opacity", "0");
}
function zeichneKerzen(boxId) {
  const r = document.getElementById(boxId + "-rahmen"), A = CHART_ARGS[boxId];
  if (!r || !A) return;
  if (r._raf) return;
  r._raf = requestAnimationFrame(() => {
    r._raf = 0;
    const a = D.assets.find((x) => x.t === A.t);
    if (!a) return;
    r.classList.add("still");
    r.innerHTML = kerzenInnen(a, A.W, A.H1, A.H2, boxId);
  });
}
function setzeKerzenSicht(boxId, n, ende) {
  const I = CHART_INFO[boxId];
  if (!I) return;
  n = Math.max(Math.min(8, I.total), Math.min(I.total, Math.round(n)));
  ende = Math.max(n, Math.min(I.total, Math.round(ende)));
  state.cv = { key: I.key, n, ende, rechts: ende >= I.total };
  zeichneKerzen(boxId);
}
// Knöpfe: + / − zoomen um die rechte Kante, "Jetzt" springt zurück
function zoomeKerzen(boxId, faktor) {
  const I = CHART_INFO[boxId];
  if (!I) return;
  if (!faktor) { state.cv = null; zeichneKerzen(boxId); return; }
  const mitte = I.ende - I.n / 2, n = I.n * faktor;
  setzeKerzenSicht(boxId, n, I.ende >= I.total ? I.total : mitte + n / 2);
}
function bindeGesten(boxId) {
  const r = document.getElementById(boxId + "-rahmen");
  if (!r || r._gebunden) return;
  r._gebunden = true;
  r.style.touchAction = "pan-y";
  const zeiger = new Map();
  let modus = null, start = null, timer = null;
  const flaeche = () => { const svg = r.querySelector(".chartbox > svg"), I = CHART_INFO[boxId]; const rr = svg.getBoundingClientRect(); return { links: rr.left + I.LI * rr.width / I.W, breite: (I.W - I.LI - I.RA) * rr.width / I.W }; };
  r.addEventListener("pointerdown", (e) => {
    if (e.target.closest("button")) return;
    zeiger.set(e.pointerId, { x: e.clientX, y: e.clientY });
    try { r.setPointerCapture(e.pointerId); } catch (f) {}
    const I = CHART_INFO[boxId];
    if (zeiger.size === 1) {
      start = { x: e.clientX, y: e.clientY, n: I.n, ende: I.ende, zeit: Date.now() };
      modus = "warte";
      clearTimeout(timer);
      // Gedrückt halten: Fadenkreuz mit allen Werten der Kerze
      if (e.pointerType !== "mouse") timer = setTimeout(() => { if (modus === "warte") { modus = "kreuz"; zeigeKerzenTip(boxId, start.x); } }, 280);
    } else if (zeiger.size === 2) {
      clearTimeout(timer); versteckeKerzenTip(boxId);
      const [p1, p2] = [...zeiger.values()];
      start = { abstand: Math.max(20, Math.abs(p1.x - p2.x)), mitte: (p1.x + p2.x) / 2, n: I.n, ende: I.ende };
      modus = "zoom";
    }
  });
  r.addEventListener("pointermove", (e) => {
    if (!zeiger.has(e.pointerId)) { if (e.pointerType === "mouse" && !e.buttons) zeigeKerzenTip(boxId, e.clientX); return; }
    zeiger.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (modus === "kreuz") { zeigeKerzenTip(boxId, e.clientX); return; }
    if (modus === "zoom" && zeiger.size >= 2) {
      // Zwei Finger: auseinander = reinzoomen, zusammen = rauszoomen
      const [p1, p2] = [...zeiger.values()];
      const f = Math.max(20, Math.abs(p1.x - p2.x)) / start.abstand;
      const F = flaeche(), anteil = Math.max(0, Math.min(1, (start.mitte - F.links) / F.breite));
      const fest = start.ende - start.n + anteil * start.n, n = start.n / f;
      setzeKerzenSicht(boxId, n, fest + (1 - anteil) * n);
      return;
    }
    if (modus === "warte" || modus === "pan") {
      const dx = e.clientX - start.x, dy = e.clientY - start.y;
      if (modus === "warte" && Math.abs(dx) > 8 && Math.abs(dx) > Math.abs(dy)) { modus = "pan"; clearTimeout(timer); versteckeKerzenTip(boxId); }
      if (modus === "pan") {
        // Wischen nach rechts = weiter zurück in die Vergangenheit
        const proKerze = flaeche().breite / start.n;
        setzeKerzenSicht(boxId, start.n, start.ende - dx / proKerze);
      }
    }
  });
  const loslassen = (e) => {
    const war = modus;
    zeiger.delete(e.pointerId);
    clearTimeout(timer);
    if (war === "warte" && start && start.zeit && Date.now() - start.zeit < 280) zeigeKerzenTip(boxId, start.x);
    if (zeiger.size === 0) modus = null;
    else if (zeiger.size === 1 && war === "zoom") {
      const [p] = [...zeiger.values()], I = CHART_INFO[boxId];
      start = { x: p.x, y: p.y, n: I.n, ende: I.ende, zeit: 0 }; modus = "pan";
    }
  };
  r.addEventListener("pointerup", loslassen);
  r.addEventListener("pointercancel", loslassen);
  r.addEventListener("pointerleave", (e) => { if (e.pointerType === "mouse" && !e.buttons) versteckeKerzenTip(boxId); });
}

// ---------- Detail einer Aktie ----------
function detailSeite() {
  const a = D.assets.find((x) => x.t === state.detail) || D.assets[0];
  const chips = D.assets.map((b) => `<button onclick="wechsle('${b.t}')" style="flex-shrink:0;display:flex;align-items:center;gap:6px;padding:6px 12px 6px 6px;border-radius:16px;font-size:13px;font-weight:600;background:${b.t === a.t ? TEXT : "#141418"};color:${b.t === a.t ? "#0B0B0E" : "#C7C7D1"}" id="chip-${b.t}">${icon(b, 22)}${esc(b.name)}</button>`).join("");
  const kopf = `
  <div style="display:flex;align-items:center;justify-content:space-between;padding:8px 12px 0">
    <button class="rund" onclick="zurueck()" aria-label="Zurück"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="${TEXT}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M15 18l-6-6 6-6"/></svg></button>
    <div style="text-align:center"><div style="font-size:16px;font-weight:600">${esc(a.name)}</div><div class="klein" style="display:flex;align-items:center;justify-content:center;gap:5px">${esc(a.t)}${BOT_IDS.filter((id) => BOTS[id]).length > 1 ? ` · <span class="punkt" style="background:${botFarbe()}"></span><span style="color:${botFarbe()};font-weight:600">${BOT_INFO[AKTIV].kurz}${istStunde() ? " · Stunden" : ""}</span>` : ""}</div></div>
    <div style="width:44px"></div>
  </div>
  <div class="scrollx" id="chipleiste" style="padding:14px 16px 0">${chips}</div>`;

  if (!a.ok) return kopf + `<div class="leer">Für ${esc(a.name)} sind gerade keine Kursdaten da.</div>`;

  const n = a.kurse.length;
  const dez = a.preis >= 10000 ? 0 : 2;
  const W = breite();
  const chart = kerzenChart(a, W, 236, 78, "kurschart");
  setTimeout(() => {
    const chip = document.getElementById("chip-" + a.t), leiste = document.getElementById("chipleiste");
    if (chip && leiste) leiste.scrollLeft = chip.offsetLeft - leiste.offsetLeft - (leiste.clientWidth - chip.offsetWidth) / 2;
  });

  const TR = a.tagReihe, tn = TR.kurse.length;
  const tagO = TR.offen[tn - 1], tagH = TR.hoch[tn - 1], tagL = TR.tief[tn - 1], tagV = TR.vol[tn - 1];
  const tageswerte = `
  <div style="display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:6px;padding:16px 16px 0">
    <div class="kachel2" style="padding:8px 10px"><div class="klein" style="font-size:11px">Eröffnung</div><div class="num" style="font-size:13px;font-weight:600;margin-top:3px">${zahl(tagO * fx(), dez)}</div></div>
    <div class="kachel2" style="padding:8px 10px"><div class="klein" style="font-size:11px">Hoch</div><div class="num" style="font-size:13px;font-weight:600;margin-top:3px">${zahl(tagH * fx(), dez)}</div></div>
    <div class="kachel2" style="padding:8px 10px"><div class="klein" style="font-size:11px">Tief</div><div class="num" style="font-size:13px;font-weight:600;margin-top:3px">${zahl(tagL * fx(), dez)}</div></div>
    <div class="kachel2" style="padding:8px 10px"><div class="klein" style="font-size:11px">Volumen</div><div class="num" style="font-size:13px;font-weight:600;margin-top:3px">${volText(tagV)}</div></div>
  </div>`;

  const steuerung = `
  <div style="display:flex;align-items:center;justify-content:space-between;gap:8px;padding:12px 16px 0">
    <div style="display:flex;gap:2px">${istStunde() ? ["1T", "3T", "1W", "1M"].map((r) => `<button class="chip ${r === state.kRangeStd ? "aktiv" : ""}" style="padding:7px 11px" onclick="setze({kRangeStd:'${r}', cv:null})">${r}</button>`).join("") : ["1M", "3M", "6M", "1J"].map((r) => `<button class="chip ${r === state.kRange ? "aktiv" : ""}" style="padding:7px 11px" onclick="setze({kRange:'${r}', cv:null})">${r}</button>`).join("")}</div>
    ${istStunde() ? `<span class="pill" style="color:${TURBO_FARBE};background:rgba(255,159,90,0.12)">Stundenkerzen</span>` : `<div style="display:flex;gap:2px;background:#141418;border-radius:12px;padding:2px">${[["T", "Tag"], ["W", "Woche"]].map(([id, l]) => `<button class="chip ${id === state.kIntervall ? "aktiv" : ""}" style="padding:6px 10px;border-radius:10px" onclick="setze({kIntervall:'${id}', cv:null})">${l}</button>`).join("")}</div>`}
  </div>
  <div style="display:flex;gap:18px;padding:12px 20px 0;font-size:13px;font-weight:600">
    ${[["vol", "Volumen"], ["rsi", "RSI"]].map(([id, l]) => `<button onclick="setze({unten:'${id}'})" style="padding:4px 0;color:${state.unten === id ? TEXT : "#858592"};border-bottom:2px solid ${state.unten === id ? AKZENT : "transparent"}">${l}</button>`).join("")}
    <span class="leise" style="margin-left:auto;font-weight:500;font-size:12px;align-self:center">${(istShort() ? [["Short", "Short"], ["Eindecken", "Eindecken"]] : [["Kauf", "Bot-Kauf"], ["Verkauf", "Verkauf"]]).map(([art, l], i) => `<span style="display:inline-flex;align-items:center;gap:4px;${i ? "margin-left:8px" : ""}"><span style="width:14px;height:14px;border-radius:7px;background:${ART_FARBE[art]};color:#0B0B0E;font-size:8px;font-weight:800;display:inline-flex;align-items:center;justify-content:center">${ART_BUCHSTABE[art]}</span>${l}</span>`).join("")}</span>
  </div>`;

  // Position
  let position;
  if (a.drin && a.letzterKauf) {
    const erg = a.stk * (a.preis - a.letzterKauf[2]), ergP = rundenProz(a.letzterKauf[1], a.letzterKauf[2], a.preis);
    position = `<div style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px 12px;margin-top:14px">
      <div><div class="klein">Bestand</div><div class="num" style="font-size:15px;font-weight:600;margin-top:3px">${stueck(a)}</div></div>
      <div><div class="klein">${a.stk < 0 ? "Short seit" : "Gekauft am"} ${kurzDatum(a.letzterKauf[0])}</div><div class="num" style="font-size:15px;font-weight:600;margin-top:3px">${geld(a.letzterKauf[2])}</div></div>
      <div><div class="klein">Wert</div><div class="num" style="font-size:15px;font-weight:600;margin-top:3px">${geldW(a.wert)}</div></div>
      <div><div class="klein">Ergebnis</div><div class="num" style="font-size:15px;font-weight:600;margin-top:3px;color:${farbe(erg)}">${vz(erg)}${betrag(erg, 2)} · ${vz(ergP)}${zahl(ergP, 1)} %</div></div>
    </div>`;
  } else {
    position = `<div style="font-size:13px;color:#C7C7D1;line-height:1.5;margin-top:10px">Keine Anteile. Der ${istHaupt() ? "Bot" : botName()} hält hier <b class="num">${geldW(a.wert)}</b> Bargeld und wartet auf das nächste ${istShort() ? "Short-Signal" : "Kaufsignal"}.</div>`;
  }

  // Ausblick
  const krypto = a.einheit === "BTC";
  const spanne = (t) => [a.preis * Math.exp(-a.sigma * Math.sqrt(t)), a.preis * Math.exp(a.sigma * Math.sqrt(t))];
  const wo = spanne(krypto ? 7 : 5), mo = spanne(krypto ? 30 : 20);
  let schwelle;
  if (a.noetig == null || Math.abs(a.noetig) > 25) schwelle = `Ein neues Signal ist ${naechsteKerze()} praktisch nicht erreichbar, dafür liegen die beiden Durchschnitte zu weit auseinander.`;
  else if (istShort()) schwelle = a.auf
    ? `Ein <b>Short-Signal</b> käme ${naechsteKerze()} bei einem Schlusskurs unter <b class="num">${geld(a.schwelle)}</b> (${vz(a.noetig)}${zahl(a.noetig, 1)} %). Der Bot würde dann ${a.drin ? "nichts tun, weil er schon short ist" : "short gehen"}.`
    : `<b>Eindecken</b> käme ${naechsteKerze()} bei einem Schlusskurs über <b class="num">${geld(a.schwelle)}</b> (${vz(a.noetig)}${zahl(a.noetig, 1)} %). Der Bot würde dann ${a.drin ? "seine Short-Position schließen" : "nichts tun, weil er gerade nicht short ist"}.`;
  else if (a.auf) schwelle = `Ein <b>Verkaufssignal</b> käme ${naechsteKerze()} bei einem Schlusskurs unter <b class="num">${geld(a.schwelle)}</b> (${vz(a.noetig)}${zahl(a.noetig, 1)} %). Der Bot würde dann ${a.drin ? "verkaufen" : "nichts tun, weil er keine Anteile hat"}.`;
  else schwelle = `Ein <b>Kaufsignal</b> käme ${naechsteKerze()} bei einem Schlusskurs über <b class="num">${geld(a.schwelle)}</b> (${vz(a.noetig)}${zahl(a.noetig, 1)} %). Der Bot würde dann ${a.drin ? "nichts tun, weil er schon Anteile hat" : "kaufen"}.`;
  const alt = a.tagReihe.kurse.slice(-40), zuk = krypto ? 30 : 20, ges = alt.length + zuk;
  const [l2, h2] = spanne(zuk);
  const lo3 = Math.min(l2, ...alt), hi3 = Math.max(h2, ...alt);
  const KW = W - 64, KH = 120;
  const kx = (i) => i / (ges - 1) * KW, ky = (v) => 6 + (hi3 - v) / (hi3 - lo3) * (KH - 12);
  const st = alt.length - 1;
  let oben = "", unten = [];
  for (let t = 0; t <= zuk; t++) {
    const s = a.sigma * Math.sqrt(t), xx = kx(st + t).toFixed(1);
    oben += (t ? "L" : "M") + xx + "," + ky(a.preis * Math.exp(s)).toFixed(1) + " ";
    unten.unshift("L" + xx + "," + ky(a.preis * Math.exp(-s)).toFixed(1));
  }
  const kegel = `<svg width="100%" viewBox="0 0 ${KW} ${KH}" role="img" aria-label="Schwankungsbreite für den nächsten Monat" style="display:block;margin-top:12px">
    <path d="${oben}${unten.join(" ")} Z" fill="${AKZENT}" fill-opacity="0.22"/>
    <path d="M${kx(st)},${ky(a.preis)} L${KW},${ky(a.preis)}" fill="none" stroke="${AKZENT}" stroke-width="1.4" stroke-dasharray="3 4"/>
    <path d="${pfad(alt, kx, ky)}" fill="none" stroke="${TEXT}" stroke-width="1.8" stroke-linejoin="round"/>
  </svg>`;

  const akt = a.akt.slice().reverse();
  const aktionen = akt.length
    ? akt.map(([t, art, p]) => `<div style="display:flex;justify-content:space-between;align-items:center;padding:12px 0">
        <div><div style="font-size:14px;font-weight:600;color:${ART_FARBE[art]}">${art}</div><div class="klein num" style="margin-top:2px">${datum(t)}</div></div>
        <div class="num" style="font-size:14px;font-weight:600">${geld(p)}</div></div>`).join("")
    : `<div class="leise" style="font-size:13px;padding:14px 0">Der Bot hat bei ${esc(a.name)} noch nicht gehandelt.</div>`;

  return kopf + `
  <div style="padding:20px 20px 0;display:flex;align-items:center;gap:14px">
    ${icon(a, 52)}
    <div><div class="num" style="font-size:34px;font-weight:700;letter-spacing:-1px;line-height:1">${geld(a.preis)}</div>
    <div class="num" style="font-size:14px;font-weight:600;margin-top:8px;color:${farbe(a.tag)}">${a.tag >= 0 ? "▲" : "▼"} ${vz(a.tag)}${betrag(a.tag, dez)} · ${vz(a.tag)}${zahl(a.tagProz, 2)} % <span class="leise" style="font-weight:500">${LIVE.quellen[a.t] ? "heute" : "am letzten Tag"}</span></div>${liveMarke(a.t) ? `<div style="margin-top:6px">${liveMarke(a.t)}</div>` : ""}</div>
  </div>
  ${tageswerte}
  <div style="margin-top:14px">${chart}</div>
  <div class="leise" style="font-size:11px;text-align:center;margin-top:8px">Zwei Finger: zoomen · Wischen: zurückblättern · Halten: Details</div>
  ${steuerung}
  <div class="karte" style="margin-top:22px">
    <div style="display:flex;justify-content:space-between;align-items:center"><h3>${istHaupt() ? "Deine Position" : "Position · " + botName()}</h3>
    <span class="pill" style="color:${a.drin ? (a.stk < 0 ? SHORT_FARBE : GRUEN) : GELB};background:${a.drin ? (a.stk < 0 ? "rgba(244,114,182,0.14)" : GRUEN_BG) : GELB_BG}">${a.drin ? (a.stk < 0 ? "Short" : "Im Markt") : "Wartet"}</span></div>
    ${position}
  </div>
  ${bilanzKarte(a)}
  <div class="karte"><h3 style="display:flex;align-items:center">Ausblick<button class="frage" onclick="erklaere('spanne')" aria-label="Was bedeutet die Spanne?">?</button></h3>
    <div style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin-top:12px">
      <div class="kachel2"><div class="klein">Spanne 1 Woche</div><div class="num" style="font-size:14px;font-weight:600;margin-top:4px">${zahl(wo[0] * fx(), dez)} – ${zahl(wo[1] * fx(), dez)} ${WAEHRUNG}</div></div>
      <div class="kachel2"><div class="klein">Spanne 1 Monat</div><div class="num" style="font-size:14px;font-weight:600;margin-top:4px">${zahl(mo[0] * fx(), dez)} – ${zahl(mo[1] * fx(), dez)} ${WAEHRUNG}</div></div>
    </div>
    ${kegel}
    <div style="font-size:13px;color:#C7C7D1;line-height:1.5;margin-top:10px">${schwelle}</div>
    <div class="leise" style="font-size:12px;line-height:1.5;margin-top:8px">Die Fläche zeigt, wie weit der Kurs schwanken könnte, wenn er sich so bewegt wie in den letzten 60 Tagen. Keine Vorhersage.</div>
  </div>
  <div class="karte">
    <div style="display:flex;justify-content:space-between;align-items:center"><h3 style="display:flex;align-items:center">Signal<button class="frage" onclick="erklaere('signal')" aria-label="Wie entsteht ein Signal?">?</button></h3>
    <span class="pill" style="color:${farbe(a.auf ? 1 : -1)};background:${a.auf ? GRUEN_BG : ROT_BG}">${a.auf ? "▲ Aufwärtstrend" : "▼ Abwärtstrend"}</span></div>
    <div style="font-size:13px;color:#C7C7D1;line-height:1.5;margin-top:10px">Ø ${KURZ} liegt ${zahl(a.abstand, 1)} % ${a.auf ? "über" : "unter"} Ø ${LANG}. ${istShort() ? (a.auf ? "Ein Short-Signal kommt, wenn die gelbe Linie unter die violette fällt." : "Eingedeckt wird, wenn die gelbe Linie über die violette steigt.") : a.auf ? "Ein Verkaufssignal kommt, wenn die gelbe Linie unter die violette fällt." : "Ein Kaufsignal kommt, wenn die gelbe Linie über die violette steigt."}</div>
  </div>
  <div class="abschnitt" style="padding-bottom:0"><b style="font-size:16px">${istHaupt() ? "Aktionen des Bots" : "Aktionen · " + botName()}</b></div>
  <div class="karte liste-trenner" style="padding:4px 16px">${aktionen}</div>`;
}

// ---------- Signale ----------
function signaleSeite() {
  const mitDaten = D.assets.filter((a) => a.ok);
  let liste = mitDaten.map((a) => {
    const nah = a.noetig != null && Math.abs(a.noetig) <= 3;
    let naechst, nf;
    if (a.noetig == null || Math.abs(a.noetig) > 25) { naechst = "Signal nicht in Reichweite"; nf = "#858592"; }
    else { naechst = (istShort() ? (a.auf ? "Short unter " : "Eindecken über ") : (a.auf ? "Verkauf unter " : "Kauf über ")) + geld(a.schwelle) + " (" + vz(a.noetig) + zahl(a.noetig, 1) + " %)"; nf = nah ? GELB : "#C7C7D1"; }
    return { a, nah, naechst, nf, sort: a.noetig == null ? 999 : Math.abs(a.noetig) };
  }).sort((p, q) => p.sort - q.sort);
  if (state.nurNah) liste = liste.filter((s) => s.nah);
  const auf = mitDaten.filter((a) => a.auf).length;
  const karten = liste.length ? liste.map(({ a, naechst, nf }) => {
    const b = Math.min(Math.abs(a.abstand) / 6 * 50, 50);
    return `<button class="zeile" onclick="oeffne('${a.t}')" style="display:block;background:#141418;border-radius:18px;padding:14px">
      <span style="display:flex;align-items:center;gap:12px">${icon(a, 38)}
        <span style="flex-grow:1;min-width:0"><span style="display:block;font-size:15px;font-weight:600">${esc(a.name)}</span><span class="klein" style="display:block;margin-top:2px">${a.drin ? (a.stk < 0 ? "Short" : "Im Markt") : (istShort() ? "Wartet auf Short-Signal" : "Wartet auf Kaufsignal")}</span></span>
        <span class="pill num" style="color:${farbe(a.auf ? 1 : -1)};background:${a.auf ? GRUEN_BG : ROT_BG}">${a.auf ? "▲ Aufwärts" : "▼ Abwärts"}</span></span>
      <span style="display:block;margin-top:12px;height:6px;border-radius:3px;background:#22222A;position:relative">
        <span style="position:absolute;left:50%;top:-3px;width:2px;height:12px;background:#5E5E6B;border-radius:1px"></span>
        <span style="position:absolute;top:0;height:6px;border-radius:3px;left:${a.auf ? 50 : 50 - b}%;width:${b}%;background:${farbe(a.auf ? 1 : -1)}"></span></span>
      <span style="display:flex;justify-content:space-between;margin-top:10px;font-size:12px">
        <span class="num klein">Abstand ${vz(a.abstand)}${zahl(a.abstand, 1)} %</span><span class="num" style="color:${nf};font-weight:600">${naechst}</span></span>
    </button>`;
  }).join("") : `<div class="leer">Gerade ist bei keiner Aktie ein Signal nah dran.</div>`;
  return `
  <div style="padding:16px 20px 0"><h1 class="titel">Signale</h1>
  <div class="klein" style="font-size:14px;margin-top:6px;line-height:1.45">Wo ${istHaupt() ? "der Bot" : "der " + botName()} als Nächstes handeln könnte. Ein Signal kommt, wenn sich Ø ${KURZ} und Ø ${LANG} ${istStunde() ? "Stunden" : "Tage"} kreuzen.</div>${botSchalter()}</div>
  <div style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;padding:18px 16px 0">
    <div class="kachel" style="padding:14px"><div class="klein">Aufwärtstrend</div><div class="num" style="font-size:22px;font-weight:700;margin-top:6px;color:${GRUEN}">▲ ${auf}</div></div>
    <div class="kachel" style="padding:14px"><div class="klein">Abwärtstrend</div><div class="num" style="font-size:22px;font-weight:700;margin-top:6px;color:${ROT}">▼ ${mitDaten.length - auf}</div></div>
  </div>
  <div class="chips" style="justify-content:flex-start;padding:18px 20px 4px">
    <button class="chip ${!state.nurNah ? "aktiv" : ""}" onclick="setze({nurNah:false})">Alle</button>
    <button class="chip ${state.nurNah ? "aktiv" : ""}" onclick="setze({nurNah:true})">Nah dran</button>
  </div>
  <div style="padding:6px 16px 0;display:flex;flex-direction:column;gap:8px">${karten}</div>`;
}

// ---------- Aktivität ----------
function aktivitaetSeite() {
  const namen = ["", "Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November", "Dezember"];
  let kalender = `<div class="leer">Der Kalender füllt sich, sobald der Bot läuft.</div>`;
  if (MONATE.length) {
    const ym = MONATE[state.monat], j = +ym.slice(0, 4), m = +ym.slice(5, 7);
    const erster = (new Date(j, m - 1, 1).getDay() + 6) % 7, anzahl = new Date(j, m, 0).getDate();
    let summe = 0, felder = "";
    for (let i = 0; i < erster; i++) felder += `<div></div>`;
    for (let t = 1; t <= anzahl; t++) {
      const key = ym + "-" + String(t).padStart(2, "0");
      if (key in D.aenderung) {
        const v = D.aenderung[key]; summe += v;
        const bg = v > 0.005 ? "rgba(61,220,151,0.14)" : v < -0.005 ? "rgba(255,122,122,0.14)" : "#1C1C22";
        const fc = v > 0.005 ? GRUEN : v < -0.005 ? ROT : "#9A9AA6";
        felder += `<button class="tag" onclick="zeigeTag('${key}')" aria-label="${datum(key)}: ${vz(v)}${betrag(v, 2)}" style="background:${bg}"><span style="font-size:10px;color:#9A9AA6">${t}</span><span class="num" style="font-size:11px;font-weight:600;color:${fc}">${vz(v)}${Math.abs(Math.round(v))}</span></button>`;
      } else felder += `<div class="tag" style="background:#17171C"><span style="font-size:10px;color:#5E5E6B">${t}</span></div>`;
    }
    const pfeil = (r, label, aktiv, ziel) => `<button class="rund" style="background:#1C1C22;opacity:${aktiv ? 1 : 0.35}" ${aktiv ? `onclick="setze({monat:${ziel}})"` : "disabled"} aria-label="${label}"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="${TEXT}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${r}"/></svg></button>`;
    kalender = `<div style="display:flex;align-items:center;justify-content:space-between">
      ${pfeil("M15 18l-6-6 6-6", "Vorheriger Monat", state.monat > 0, state.monat - 1)}
      <div style="text-align:center"><div style="font-size:16px;font-weight:600">${namen[m]} ${j}</div><div class="num" style="font-size:13px;font-weight:600;margin-top:2px;color:${farbe(summe)}">${vz(summe)}${betrag(summe, 2)} im Monat</div></div>
      ${pfeil("M9 18l6-6-6-6", "Nächster Monat", state.monat < MONATE.length - 1, state.monat + 1)}
    </div>
    <div class="kal">${["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"].map((w) => `<div class="wt">${w}</div>`).join("")}${felder}</div>
    <div class="leise" style="display:flex;gap:14px;justify-content:center;margin-top:12px;font-size:11px"><span>Grün: Plus</span><span>Rot: Minus</span><span>Tag antippen für Details</span></div>`;
  }
  const imPlus = RUNDEN.filter((r) => r.proz > 0).length;
  const zeigen = state.alleRunden ? RUNDEN : RUNDEN.slice(0, 25);
  const runden = RUNDEN.length ? zeigen.map((r) => `<button class="zeile" onclick="oeffne('${r.a.t}')" style="padding:12px 8px;border-radius:14px">
      ${icon(r.a, 36)}
      <span style="flex-grow:1;min-width:0"><span style="display:block;font-size:14px;font-weight:600">${esc(r.a.name)}</span><span class="klein num" style="display:block;margin-top:2px">${kurzDatum(r.von)} – ${kurzDatum(r.bis)}</span></span>
      <span style="text-align:right"><span class="num" style="display:block;font-size:14px;font-weight:600;color:${farbe(r.proz)}">${vz(r.proz)}${zahl(r.proz, 1)} %</span>
      <span class="num leise" style="display:block;font-size:12px;margin-top:2px">${zahl(r.k, r.k >= 10000 ? 0 : 2)} → ${zahl(r.v, r.v >= 10000 ? 0 : 2)}</span></span>
    </button>`).join("") : `<div class="leer" style="padding:18px">Noch keine abgeschlossene Runde. Sie erscheint hier, sobald der Bot gekauft und wieder verkauft hat.</div>`;
  return `
  <div style="padding:16px 20px 0"><h1 class="titel">Aktivität</h1>${botSchalter()}</div>
  <div class="karte" style="margin-top:18px;padding:16px 14px 14px">${kalender}</div>
  ${statistikKarte()}
  <div class="abschnitt"><b>Abgeschlossene Runden</b><span class="klein num" style="font-size:13px">${RUNDEN.length ? imPlus + " von " + RUNDEN.length + " im Plus" : ""}</span></div>
  <div class="karte liste-trenner" style="margin-top:0;padding:4px 8px">${runden}${RUNDEN.length > zeigen.length ? `<button onclick="setze({alleRunden:true})" style="width:100%;padding:14px;font-size:14px;font-weight:600;color:${AKZENT}">Alle ${RUNDEN.length} Runden zeigen</button>` : ""}</div>
  <div class="leise" style="font-size:12px;padding:10px 20px 0">Ergebnis in Prozent vom Kaufkurs, ohne Gebühren. Stand erzeugt am ${esc(D.erzeugt)} Uhr.</div>`;
}

// ---------- Tagesfenster im Kalender ----------
function zeigeTag(key) {
  const liste = (D.proTag[key] || []).map(([t, v, art]) => ({ a: D.assets.find((x) => x.t === t), v, art })).filter((x) => x.a);
  const summe = liste.reduce((s, x) => s + x.v, 0);
  const bewegt = liste.filter((x) => Math.abs(x.v) >= 0.005 || x.art).sort((p, q) => q.v - p.v);
  const ruhig = liste.length - bewegt.length;
  const t = key.split("-").map(Number);
  const titel = new Date(t[0], t[1] - 1, t[2]).toLocaleDateString("de-DE", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
  const zeilen = bewegt.map((x) => {
    const p = x.v / D.start * 100;
    return `<button class="zeile" onclick="schliesseTag(); oeffne('${x.a.t}')" style="padding:11px 4px;border-radius:12px">
      ${icon(x.a, 38)}
      <span style="flex-grow:1;min-width:0"><span style="display:block;font-size:15px;font-weight:600">${esc(x.a.name)}</span>
      <span class="klein" style="display:block;margin-top:2px">${x.art ? `<b style="color:${ART_FARBE[x.art] || BOT_VERKAUF}">Bot: ${x.art}</b>` : "Position gehalten"}</span></span>
      <span style="text-align:right;white-space:nowrap"><span class="num" style="display:block;font-size:15px;font-weight:600;color:${farbe(x.v)}">${vz(x.v)}${betrag(x.v, 2)}</span>
      <span class="num leise" style="display:block;font-size:12px;margin-top:2px">${vz(p)}${zahl(p, 2)} %</span></span>
    </button>`;
  }).join("");
  const hg = document.createElement("div"); hg.className = "sheet-hg"; hg.id = "sheethg"; hg.onclick = schliesseTag;
  const sh = document.createElement("div"); sh.className = "sheet"; sh.id = "sheet"; sh.setAttribute("role", "dialog"); sh.setAttribute("aria-label", titel);
  sh.innerHTML = `<div class="griff"></div>
    <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:10px">
      <div><div class="klein" style="font-weight:600">${esc(titel)}</div>
      <div class="num" style="font-size:28px;font-weight:700;margin-top:4px;color:${farbe(summe)}">${vz(summe)}${betrag(summe, 2)}</div>
      <div class="klein">Depot an diesem Tag</div></div>
      <button class="rund" onclick="schliesseTag()" aria-label="Schließen" style="background:#1C1C22;flex-shrink:0"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="${TEXT}" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg></button>
    </div>
    <div class="liste-trenner" style="margin-top:14px">${zeilen || `<div class="leise" style="font-size:13px;padding:14px 0">An diesem Tag hat sich im Depot nichts bewegt.</div>`}</div>
    ${ruhig ? `<div class="leise" style="font-size:12px;margin-top:10px">${ruhig} ${ruhig === 1 ? "Aktie" : "Aktien"} ohne Veränderung, weil der Bot dort nur Bargeld hält.</div>` : ""}`;
  document.body.appendChild(hg); document.body.appendChild(sh);
}
function schliesseTag() {
  const sh = document.getElementById("sheet"), hg = document.getElementById("sheethg");
  if (!sh) return;
  sh.classList.add("weg"); if (hg) hg.style.opacity = "0";
  setTimeout(() => { sh.remove(); if (hg) hg.remove(); }, 260);
}

// ---------- Bot-Bilanz je Aktie ----------
function bewerteAktionen(a) {
  const richtig = [], falsch = [], offen = [];
  const n = a.kurse.length;
  a.akt.forEach(([t, art, p]) => {
    const i = a.tage.indexOf(t);
    if (i < 0) return;
    const j = Math.min(i + 10, n - 1), tageSpaeter = j - i;
    const wann = kurzDatum(t);
    if (tageSpaeter < 3) { offen.push(`${art} am ${wann} bei ${geld(p)}: noch zu frisch, um ihn zu bewerten.`); return; }
    const bew = (a.kurse[j] / p - 1) * 100, txt = `${vz(bew)}${zahl(bew, 1)} %`;
    const zeit = istStunde() ? (tageSpaeter >= 10 ? "in den 10 Handelsstunden danach" : `in den ${tageSpaeter} Stunden danach`) : (tageSpaeter >= 10 ? "in den 10 Handelstagen danach" : `in den ${tageSpaeter} Tagen danach`);
    if (art === "Short") {
      if (bew < 0) richtig.push(`Guter Short am ${wann} bei ${geld(p)}: Der Kurs fiel ${zeit} um ${zahl(bew, 1)} %.`);
      else falsch.push(`Ungünstiger Short am ${wann} bei ${geld(p)}: Der Kurs stieg ${zeit} um ${txt}.`);
    } else if (art === "Eindecken") {
      if (bew > 0) richtig.push(`Rechtzeitig eingedeckt am ${wann} bei ${geld(p)}: Danach stieg der Kurs um ${txt}.`);
      else falsch.push(`Zu früh eingedeckt am ${wann} bei ${geld(p)}: Danach fiel der Kurs noch um ${zahl(bew, 1)} %.`);
    } else if (art === "Kauf") {
      if (bew > 0) richtig.push(`Guter Einstieg am ${wann} bei ${geld(p)}: Der Kurs stieg ${zeit} um ${txt}.`);
      else falsch.push(`Ungünstiger Einstieg am ${wann} bei ${geld(p)}: Der Kurs fiel ${zeit} um ${zahl(bew, 1)} %.`);
    } else {
      if (bew < 0) richtig.push(`Rechtzeitig verkauft am ${wann} bei ${geld(p)}: Danach fiel der Kurs um ${zahl(bew, 1)} %.`);
      else falsch.push(`Zu früh verkauft am ${wann} bei ${geld(p)}: Danach stieg der Kurs noch um ${txt}.`);
    }
  });
  RUNDEN.filter((r) => r.a === a).forEach((r) => {
    if (r.proz > 0) richtig.push(`Runde ${kurzDatum(r.von)} – ${kurzDatum(r.bis)} mit Gewinn abgeschlossen: ${vz(r.proz)}${zahl(r.proz, 1)} %.`);
    else falsch.push(`Runde ${kurzDatum(r.von)} – ${kurzDatum(r.bis)} mit Verlust abgeschlossen: ${zahl(r.proz, 1)} %.`);
  });
  return { richtig, falsch, offen };
}
function bilanzKarte(a) {
  const bot = a.wert - D.start;
  const bh = a.startKurs ? D.start / a.startKurs * a.preis - D.start : 0;
  const besser = bot - bh;
  const b = bewerteAktionen(a);
  const liste = (punkte, zeichen, f) => punkte.slice(-6).map((t) => `<div><span class="z" style="background:${f}">${zeichen}</span><span>${esc(t)}</span></div>`).join("") + (punkte.length > 6 ? `<div class="leise" style="font-size:12px;padding-left:30px">und ${punkte.length - 6} weitere</div>` : "");
  const keineTrades = !a.akt.length;
  return `
  <div class="karte">
    <div style="display:flex;justify-content:space-between;align-items:center;gap:8px"><h3 style="display:flex;align-items:center">Bot-Bilanz<button class="frage" onclick="erklaere('liegenlassen')" aria-label="Was heißt Liegenlassen?">?</button></h3>
      <span class="pill" style="color:${farbe(besser)};background:${besser >= 0 ? GRUEN_BG : ROT_BG}">${besser >= 0 ? "besser als Liegenlassen" : "schlechter als Liegenlassen"}</span></div>
    <div style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin-top:12px">
      <div class="stat"><div class="klein" style="font-size:11px">${istHaupt() ? "Bot" : botName()}</div><div class="w num" style="color:${farbe(bot)}">${vz(bot)}${betrag(bot, 2)}</div></div>
      <div class="stat"><div class="klein" style="font-size:11px">Liegenlassen</div><div class="w num" style="color:${farbe(bh)}">${vz(bh)}${betrag(bh, 2)}</div></div>
    </div>
    <div class="klein" style="margin-top:8px;line-height:1.45">Seit ${a.startTag ? datum(a.startTag) : "dem Start"}. "Liegenlassen" heißt: am ersten Tag für ${zahl(D.start, 0) + " $"} kaufen und nichts mehr tun.</div>
    ${keineTrades ? `<div class="leise" style="font-size:13px;margin-top:14px;line-height:1.5">Der Bot hat bei ${esc(a.name)} noch nicht gehandelt, deshalb gibt es noch nichts zu bewerten.</div>` : `
    ${b.richtig.length ? `<div style="font-size:14px;font-weight:700;margin-top:16px">Was gut lief</div><div class="punkte">${liste(b.richtig, "✓", GRUEN)}</div>` : ""}
    ${b.falsch.length ? `<div style="font-size:14px;font-weight:700;margin-top:16px">Was nicht gut lief</div><div class="punkte">${liste(b.falsch, "✕", ROT)}</div>` : ""}
    ${b.offen.length ? `<div class="punkte" style="margin-top:12px">${liste(b.offen, "…", "#6E6E7A")}</div>` : ""}`}
    <div class="leise" style="font-size:11px;margin-top:14px;line-height:1.45">Bewertet wird, wie sich der Kurs nach jedem Kauf oder Verkauf entwickelt hat. Das ist ein Blick zurück, keine Vorhersage.</div>
  </div>`;
}

// ---------- Aktuelles Datum (vom Handy, bei jedem Öffnen neu) ----------
function jetztText() {
  const d = new Date();
  const tag = d.toLocaleDateString("de-DE", { weekday: "short", day: "2-digit", month: "2-digit" });
  return tag.replace(",", "") + " · " + String(d.getHours()).padStart(2, "0") + ":" + String(d.getMinutes()).padStart(2, "0") + " Uhr";
}
function naechsterLauf() {
  // Die Cloud startet die Bots jede Stunde kurz nach der vollen Stunde
  const d = new Date();
  if (d.getMinutes() >= 5) d.setHours(d.getHours() + 1);
  return "gegen " + String(d.getHours()).padStart(2, "0") + ":05 Uhr";
}
function aktualisiereUhr() {
  document.querySelectorAll(".jetzt").forEach((el) => { el.textContent = jetztText(); });
}
setInterval(aktualisiereUhr, 20000);
const GELADEN = Date.now();
document.addEventListener("visibilitychange", () => {
  if (document.hidden) return;
  // Wer länger weg war, bekommt frische Daten vom Server
  if (Date.now() - GELADEN > 5 * 60 * 1000 && location.protocol.startsWith("http")) location.reload();
  else aktualisiereUhr();
});

// ---------- Cloud-Status und Start-Knopf ----------
function cloudKarte() {
  const uhr = (D.erzeugt.split(", ")[1] || "");
  if (D.modus !== "cloud") return `
  <div class="karte" style="margin-top:16px;display:flex;align-items:center;gap:12px;padding:14px">
    <span class="icon" style="width:40px;height:40px;background:#1E1A2E"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#B4A8FF" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4"/></svg></span>
    <span style="flex-grow:1;min-width:0">
      <span style="display:flex;align-items:center;gap:6px;font-size:14px;font-weight:700"><span class="punkt" style="background:${GRUEN}"></span>Läuft auf deinem PC</span>
      <span class="klein" style="display:block;margin-top:2px">Kurse vom ${D.letzterTag ? kurzDatum(D.letzterTag) : "–"} ✓ · Seite von ${esc(uhr)} Uhr</span>
      <span class="klein" style="display:block">Start-Knopf kommt mit dem Umzug in die Cloud</span>
    </span>
  </div>`;
  return `
  <div class="karte" style="margin-top:16px;display:flex;align-items:center;gap:12px;padding:14px">
    <span class="icon" style="width:40px;height:40px;background:#16233A"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#6BB6FF" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M7 18h10a4 4 0 0 0 .5-7.97A6 6 0 0 0 6.1 9.5 4.3 4.3 0 0 0 7 18z"/></svg></span>
    <span style="flex-grow:1;min-width:0">
      <span style="display:flex;align-items:center;gap:6px;font-size:14px;font-weight:700"><span class="punkt" style="background:${GRUEN}"></span>Läuft in der Cloud</span>
      <span class="klein" style="display:block;margin-top:2px">Kurse vom ${D.letzterTag ? kurzDatum(D.letzterTag) : "–"} ✓</span>
      <span class="klein" style="display:block">Nächster Lauf ${naechsterLauf()}</span>
    </span>
    ${D.repo ? `<a class="startknopf" href="https://github.com/${esc(D.repo)}/actions/workflows/bot.yml" target="_blank" rel="noopener" style="text-decoration:none">Starten<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M7 17L17 7M9 7h8v8"/></svg></a>` : ""}
  </div>`;
}
function botStarten() {
  const k = document.getElementById("startknopf");
  if (!k || k.disabled) return;
  k.disabled = true;
  k.innerHTML = `<span class="kreis"></span>Läuft …`;
  setTimeout(() => {
    k.innerHTML = "Fertig ✓";
    zeigeHinweis("Bot-Lauf fertig", "Keine neuen Käufe oder Verkäufe. (Vorschau: hier nur simuliert)");
    setTimeout(() => { k.disabled = false; k.innerHTML = "Jetzt starten"; }, 2500);
  }, 2600);
}
function zeigeHinweis(titel, text) {
  versteckeToast();
  const t = document.createElement("button");
  t.className = "toast"; t.id = "toast";
  t.innerHTML = `<span class="icon" style="width:38px;height:38px;background:#16233A"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#6BB6FF" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12l5 5L20 7"/></svg></span><span style="flex-grow:1;min-width:0"><span style="display:block;font-size:14px;font-weight:600">${esc(titel)}</span><span style="display:block;font-size:12px;color:#C7C7D1;margin-top:1px">${esc(text)}</span></span>`;
  t.onclick = versteckeToast;
  setTimeout(() => { document.body.appendChild(t); wischbar(t); setTimeout(versteckeToast, 4200); }, 420);
}

// ---------- Wochenrückblick ----------
function wocheKarte() {
  const v = D.depot, n = v.labels.length;
  if (n < 2) return "";
  const ende = v.labels[n - 1], startD = tageZurueck(ende, 7);
  const i0 = v.labels.findIndex((d) => d > startD);
  if (i0 < 0) return "";
  const startGes = D.start * D.assets.length;
  const bBot = i0 > 0 ? v.bot[i0 - 1] : startGes, bBh = i0 > 0 ? v.bh[i0 - 1] : startGes;
  const bot = v.bot[n - 1] - bBot, bh = v.bh[n - 1] - bBh;
  const bewegung = D.assets.filter((a) => a.ok).map((a) => {
    const j = a.tage.findIndex((d) => d > startD);
    const basis = j > 0 ? a.kurse[j - 1] : a.kurse[0];
    return { a, p: (a.preis / basis - 1) * 100 };
  }).sort((x, y) => y.p - x.p);
  const trades = EREIGNISSE.filter((e) => e.bot === AKTIV && e.t > startD);
  const zeile = (x, titel) => `<button class="zeile" onclick="oeffne('${x.a.t}')" style="padding:8px 4px;gap:10px">${icon(x.a, 30)}<span style="flex-grow:1;min-width:0"><span class="klein" style="display:block;font-size:11px">${titel}</span><span style="display:block;font-size:14px;font-weight:600">${esc(x.a.name)}</span></span><span class="num" style="font-size:14px;font-weight:600;color:${farbe(x.p)}">${vz(x.p)}${zahl(x.p, 2)} %</span></button>`;
  return `
  <div class="karte">
    <div style="display:flex;justify-content:space-between;align-items:baseline"><h3>Deine Woche</h3><span class="klein">${kurzDatum(tageZurueck(ende, 6))} – ${kurzDatum(ende)}</span></div>
    <div style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin-top:12px">
      <div class="stat"><div class="klein" style="font-size:11px">${istHaupt() ? "Bot" : botName()}</div><div class="w num" style="color:${farbe(bot)}">${vz(bot)}${betrag(bot, 2)}</div></div>
      <div class="stat"><div class="klein" style="font-size:11px">Liegenlassen</div><div class="w num" style="color:${farbe(bh)}">${vz(bh)}${betrag(bh, 2)}</div></div>
    </div>
    ${bewegung.length ? `<div class="liste-trenner" style="margin-top:8px">${zeile(bewegung[0], "Beste Aktie der Woche")}${zeile(bewegung[bewegung.length - 1], "Schwächste Aktie der Woche")}</div>` : ""}
    <div class="klein" style="margin-top:10px;line-height:1.5">${trades.length ? `${trades.length} ${trades.length === 1 ? "Aktion" : "Aktionen"} diese Woche: ` + trades.slice(0, 4).map((e) => `<b style="color:${ART_FARBE[e.art]}">${esc(e.a.name)} ${ART_WORT[e.art]}</b>`).join(", ") + (trades.length > 4 ? " …" : "") : "Diese Woche hat der Bot nicht gehandelt."}</div>
  </div>`;
}

// ---------- Erklärungen ----------
function zeigeInfo(titel, html) {
  schliesseTag();
  const hg = document.createElement("div"); hg.className = "sheet-hg"; hg.id = "sheethg"; hg.onclick = schliesseTag;
  const sh = document.createElement("div"); sh.className = "sheet"; sh.id = "sheet"; sh.setAttribute("role", "dialog"); sh.setAttribute("aria-label", titel);
  sh.innerHTML = `<div class="griff"></div>
    <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:10px">
      <h3 style="font-size:20px;margin:4px 0 0">${esc(titel)}</h3>
      <button class="rund" onclick="schliesseTag()" aria-label="Schließen" style="background:#1C1C22;flex-shrink:0"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="${TEXT}" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg></button>
    </div>
    <div style="font-size:15px;line-height:1.6;color:#D4D4DC;margin-top:12px">${html}</div>`;
  setTimeout(() => { document.body.appendChild(hg); document.body.appendChild(sh); }, 280);
}
function erklaere(was) {
  const a = D.assets.find((x) => x.t === state.detail);
  const n = a ? a.kurse.length : 0;
  const wert = D.assets.reduce((s, x) => s + x.wert, 0);
  const v = D.depot, m = v.labels.length;
  const texte = {
    durchschnitt: [`Ø${KURZ} und Ø${LANG}`, `<b style="color:${GELB}">Ø${KURZ}</b> ist der Durchschnitt der letzten ${KURZ} ${istStunde() ? "Stunden-" : ""}Schlusskurse, <b style="color:${AKZENT}">Ø${LANG}</b> der Durchschnitt der letzten ${LANG}. Der kurze Durchschnitt reagiert schnell, der lange langsam.<br><br>Steigt die gelbe Linie über die violette, ${istShort() ? `deckt der ${botName()} ein. Fällt sie darunter, geht er short.` : `kauft ${istHaupt() ? "dein Bot" : "der " + botName()}. Fällt sie darunter, verkauft er.`}` + (a && a.ok ? `<br><br>Bei ${esc(a.name)} gerade: Ø${KURZ} = <b>${geld(a.k10[n - 1])}</b>, Ø${LANG} = <b>${geld(a.k30[n - 1])}</b>, also ${a.auf ? "ein Aufwärtstrend" : "ein Abwärtstrend"}.` : "")],
    rsi: ["RSI", `Der <b>RSI</b> (Relative-Stärke-Index) misst auf einer Skala von 0 bis 100, wie stark ein Kurs in den letzten 14 Tagen gestiegen oder gefallen ist.<br><br>Über 70 gilt eine Aktie oft als <b>überkauft</b> (schnell stark gestiegen), unter 30 als <b>überverkauft</b>.` + (a && a.rsi[n - 1] != null ? `<br><br>Bei ${esc(a.name)} liegt er gerade bei <b>${zahl(a.rsi[n - 1], 1)}</b>.` : "") + `<br><br>Dein Bot nutzt den RSI nicht zum Handeln, er dient nur zur Info.`],
    volumen: ["Volumen", `Das <b>Volumen</b> zeigt, wie viele Aktien an einem Tag gehandelt wurden. Hohes Volumen heißt: viele Käufer und Verkäufer waren aktiv, eine Kursbewegung hat also mehr Gewicht.<br><br>Grüne Balken gehören zu Tagen, an denen der Kurs gestiegen ist, rote zu Tagen, an denen er gefallen ist.` + (a ? `<br><br>Bei ${esc(a.name)} am letzten Tag: <b>${volText(a.vol[n - 1])}</b>.` : "")],
    spanne: ["Spanne", `Die <b>Spanne</b> zeigt, wie weit sich der Kurs in einer Woche oder einem Monat typischerweise bewegt. Sie wird aus den Schwankungen der letzten 60 Tage berechnet.<br><br>In etwa 2 von 3 Fällen bleibt der Kurs innerhalb dieser Spanne. Sie sagt aber <b>nichts über die Richtung</b>: ob es eher hoch oder runter geht, weiß niemand vorher.`],
    signal: ["Wie ein Signal entsteht", istShort() ? `Der ${botName()} vergleicht ${istStunde() ? "nach jeder Stunde" : "jeden Abend"} die beiden Durchschnitte:<br><br><b style="color:${SHORT_FARBE}">Short</b>: Ø${KURZ} liegt unter Ø${LANG} und er ist noch nicht short.<br><b>Eindecken</b>: Ø${KURZ} liegt über Ø${LANG} und er ist short.<br><br>Short heißt: Er verkauft geliehene Aktien und kauft sie später zurück. Fällt der Kurs dazwischen, verdient er.` : istTurbo() ? `Der Turbo-Bot vergleicht nach jeder Stunde die beiden Durchschnitte:<br><br><b style="color:${BOT_KAUF}">Kauf</b>: Ø${KURZ} liegt über Ø${LANG} und er hat noch keine Anteile.<br><b>Verkauf</b>: Ø${KURZ} liegt unter Ø${LANG} und er hat Anteile.<br><br>Anders als dein Bot steigt er also auch mitten in einen laufenden Aufwärtstrend ein.` : `Dein Bot vergleicht jeden Abend die beiden Durchschnitte:<br><br><b style="color:${BOT_KAUF}">Kauf</b>: Ø${KURZ} steigt von unten über Ø${LANG}.<br><b>Verkauf</b>: Ø${KURZ} fällt von oben unter Ø${LANG}.<br><br>Er handelt nur am Tag der Kreuzung, nicht mitten in einem laufenden Trend.` + (a && a.ok && a.noetig != null && Math.abs(a.noetig) <= 25 ? `<br><br>Bei ${esc(a.name)} käme das nächste Signal bei einem Schlusskurs ${a.auf ? "unter" : "über"} <b>${geld(a.schwelle)}</b>.` : "")],
    treffer: ["Trefferquote", `Die <b>Trefferquote</b> ist der Anteil der abgeschlossenen Runden (Kauf und Verkauf), die mit Gewinn endeten.` + (RUNDEN.length ? `<br><br>Bei dir: <b>${RUNDEN.filter((r) => r.proz > 0).length} von ${RUNDEN.length}</b> Runden im Plus.` : "") + `<br><br>Wichtig: Auch eine niedrige Trefferquote kann Gewinn bringen, wenn die Gewinne größer sind als die Verluste. Das siehst du in der Bot-Statistik unter Aktivität.`],
    liegenlassen: ["Liegenlassen (Buy-and-Hold)", `<b>Liegenlassen</b> heißt: am ersten Tag kaufen und dann einfach halten, ohne zu handeln.<br><br>Das ist der wichtigste Maßstab für jeden Bot. Nur wenn der Bot <b>mehr</b> schafft als Liegenlassen, lohnt sich das ganze Kaufen und Verkaufen. Sonst wäre einfaches Halten besser und günstiger.` + (m ? `<br><br>Dein Depot gerade: Bot <b>${geldW(v.bot[m - 1])}</b>, Liegenlassen <b>${geldW(v.bh[m - 1])}</b>.` : "")],
    turbo: ["Turbo-Bot", `Der <b style="color:${TURBO_FARBE}">Turbo-Bot</b> ist ein zweiter Bot mit eigenem Spielgeld. Er handelt nach schnelleren Regeln:<br><br>• Er nutzt <b>Stundenkerzen</b> statt Tageskerzen und entscheidet nach jeder abgeschlossenen Stunde.<br>• Er vergleicht <b>Ø5 und Ø20</b>, also die letzten 5 und 20 Stunden.<br>• Er ist <b>im Markt, solange Ø5 über Ø20 liegt</b>, und steigt auch in laufende Trends ein.<br><br>Dafür handelt er viel öfter, zahlt mehr Gebühren und fällt leichter auf kurze Zacken rein. Ob sich das lohnt, zeigt dir das Duell.`],
    short: ["Short-Bot", `Der <b style="color:${SHORT_FARBE}">Short-Bot</b> setzt auf <b>fallende</b> Kurse. Er nutzt dieselben Durchschnitte wie dein Bot (<b>Ø10 und Ø30 Tage</b>), nur andersherum:<br><br>• Liegt Ø10 unter Ø30, geht er <b>short</b>: Er verkauft geliehene Aktien.<br>• Steigt Ø10 wieder über Ø30, <b>deckt er ein</b>: Er kauft sie zurück.<br><br>Fällt der Kurs in der Zwischenzeit, macht er Gewinn. Steigt er, macht er Verlust. Bei echtem Geld ginge das nur über spezielle Produkte wie CFDs, hier ist alles Spielgeld.`],
    tshort: ["Turbo-Short", `Der <b style="color:${TSHORT_FARBE}">Turbo-Short</b> ist das Gegenstück zum Turbo-Bot. Er setzt auf <b>fallende</b> Kurse und nutzt <b>Stundenkerzen mit Ø5 und Ø20</b>:<br><br>• Liegt Ø5 unter Ø20, geht er <b>short</b>.<br>• Steigt Ø5 wieder über Ø20, <b>deckt er ein</b>.<br><br>Er entscheidet nach jeder fertigen Stunde und handelt deshalb sehr oft.`],
    liga: ["Bot-Liga", `In der <b>Bot-Liga</b> treten mehrere Bots mit demselben Spielgeld gegeneinander an.<br><br><b>Echte Bots</b> (Dein Bot, Turbo-Bot) handeln wirklich jeden Tag mit, ihre Ergebnisse sind genau die aus deinem Depot.<br><b>Simulationen</b> zeigen, wie Bots mit anderen Regeln gehandelt hätten, zurückgerechnet mit echten Kursen.<br><b>Liegenlassen</b> ist der Maßstab: am Start kaufen und nichts mehr tun.<br><br>Gezählt wird in Prozent seit dem eigenen Start. Tippe auf einen Bot, um alle Details zu sehen.`],
  };
  const [titel, html] = texte[was] || ["", ""];
  if (titel) zeigeInfo(titel, html);
}

// ---------- Vollbild-Chart ----------
function zeigeVollbild() {
  const a = D.assets.find((x) => x.t === state.detail);
  if (!a || !a.ok) return;
  state.vollbild = true;
  let ov = document.getElementById("vollbild");
  if (!ov) { ov = document.createElement("div"); ov.id = "vollbild"; ov.className = "vollbild"; ov.setAttribute("role", "dialog"); ov.setAttribute("aria-label", "Chart im Vollbild"); document.body.appendChild(ov); }
  const quer = window.innerWidth > window.innerHeight;
  const W = Math.min(window.innerWidth, 1600);
  const H1 = Math.max(150, window.innerHeight - (quer ? 222 : 330)), H2 = quer ? 44 : 90;
  const knopf = (aktiv, text, aufruf) => `<button class="chip ${aktiv ? "aktiv" : ""}" style="padding:7px 11px" onclick="${aufruf}">${text}</button>`;
  ov.innerHTML = `
    <div style="display:flex;align-items:center;gap:10px;padding:0 12px 6px">
      ${icon(a, 32)}
      <div style="min-width:0"><div style="font-size:15px;font-weight:700">${esc(a.name)}</div><div class="num klein">${geld(a.preis)} · <span style="color:${farbe(a.tag)}">${vz(a.tagProz)}${zahl(a.tagProz, 2)} %</span></div></div>
      <span style="flex-grow:1"></span>
      <button class="rund" onclick="schliesseVollbild()" aria-label="Vollbild schließen" style="background:#1C1C22"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="${TEXT}" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg></button>
    </div>
    <div class="scrollx" style="padding:4px 12px 8px;align-items:center">
      ${istStunde() ? ["1T", "3T", "1W", "1M"].map((r) => knopf(r === state.kRangeStd, r, `setzeVoll({kRangeStd:'${r}', cv:null})`)).join("") : ["1M", "3M", "6M", "1J"].map((r) => knopf(r === state.kRange, r, `setzeVoll({kRange:'${r}', cv:null})`)).join("")}
      <span style="width:10px;flex-shrink:0"></span>
      ${istStunde() ? "" : [["T", "Tag"], ["W", "Woche"]].map(([id, l]) => knopf(id === state.kIntervall, l, `setzeVoll({kIntervall:'${id}', cv:null})`)).join("")}
      <span style="width:10px;flex-shrink:0"></span>
      ${[["vol", "Volumen"], ["rsi", "RSI"]].map(([id, l]) => knopf(id === state.unten, l, `setzeVoll({unten:'${id}'})`)).join("")}
    </div>
    ${kerzenChart(a, W, H1, H2, "vollchart")}
    ${quer ? "" : `<div class="leise" style="text-align:center;font-size:12px;margin-top:14px;display:flex;align-items:center;justify-content:center;gap:6px"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="5" y="2" width="14" height="20" rx="3"/><path d="M2 12a10 10 0 0 0 4 8M22 12a10 10 0 0 0-4-8"/></svg>Dreh dein Handy quer für mehr Platz</div>`}`;
}
function setzeVoll(neu) { Object.assign(state, neu); render(false); zeigeVollbild(); }
function schliesseVollbild() {
  state.vollbild = false;
  const ov = document.getElementById("vollbild");
  if (ov) ov.remove();
}

// ---------- Bot-Liga ----------
// Echte Bots (Dein Bot, Turbo-Bot) mit ihren wirklichen Ergebnissen,
// dazu Liegenlassen und zwei Simulationen mit anderen Regeln zum Vergleich.
let LIGA = null;
function wertJetzt(B, a) { const z = B.assets[a.t]; return z ? z.konto + z.stk * a.preis : D.start; }
function rechneLiga() {
  if (LIGA) return LIGA;
  const H = BOTS.haupt, T = BOTS.turbo, S = BOTS.short, TS = BOTS.tshort;
  const mit = D.assets.filter((a) => a.tagOk);
  const startGeld = D.start * D.assets.length;
  const liste = [];
  const ende = mit.map((a) => a.tagReihe.tage[a.tagReihe.tage.length - 1]).sort().pop();
  const ligaStart = (H && H.depot.labels[0]) || (ende ? tageZurueck(ende, 90) : null);

  // Echte Bots
  const echt = (id, B, name, regel, farbe, kerzen) => {
    if (!B || !B.depot.labels.length) return;
    const assets = {};
    D.assets.forEach((a) => { const z = B.assets[a.t] || { akt: [], stk: 0 }; assets[a.t] = { wert: wertJetzt(B, a), akt: z.akt, drin: z.stk !== 0, short: z.stk < 0 }; });
    liste.push({ id, name, regel, farbe, echt: true, kerzen, labels: B.depot.labels, reihe: B.depot.bot, start: startGeld,
      ende: D.assets.reduce((s, a) => s + assets[a.t].wert, 0), assets, kurz: B.kurz, lang: B.lang, trend: B.trend, short: B.richtung === "short" });
  };
  echt("haupt", H, "Dein Bot", `Ø${D.kurz} / Ø${D.lang} Tage`, AKZENT, "Tageskerzen");
  echt("turbo", T, "Turbo-Bot", `Ø${T ? T.kurz : 5} / Ø${T ? T.lang : 20} Stunden`, TURBO_FARBE, "Stundenkerzen");
  echt("short", S, "Short-Bot", `Short · Ø${S ? S.kurz : 10} / Ø${S ? S.lang : 30} Tage`, SHORT_FARBE, "Tageskerzen");
  echt("tshort", TS, "Turbo-Short", `Short · Ø${TS ? TS.kurz : 5} / Ø${TS ? TS.lang : 20} Stunden`, TSHORT_FARBE, "Stundenkerzen");

  // Liegenlassen: am ersten Tag deines Bots kaufen und halten
  if (H && H.depot.labels.length) {
    const assets = {};
    D.assets.forEach((a) => {
      const z = H.assets[a.t], k = z && z.startKurs ? z.startKurs : a.preis;
      const st = D.start / k;
      assets[a.t] = { wert: st * a.preis, akt: z && z.startTag ? [[z.startTag, "Kauf", k, st]] : [], drin: true };
    });
    liste.push({ id: "liegen", name: "Liegenlassen", regel: "Kaufen und halten", farbe: "#9A9AA6", echt: false, kerzen: "Tageskerzen",
      labels: H.depot.labels, reihe: H.depot.bh, start: startGeld, ende: D.assets.reduce((s, a) => s + assets[a.t].wert, 0), assets, liegen: true });
  }

  // Simulationen mit anderen Regeln auf Tageskerzen
  [["schnell", "Schneller Bot", 5, 20, true, BOT_KAUF], ["langsam", "Langsamer Bot", 20, 50, false, "#4FD1C5"]].forEach(([id, name, kurz, lang, trend, farbe]) => {
    const verlauf = {}, assets = {};
    mit.forEach((a) => {
      const k = a.tagReihe.kurse, tage = a.tagReihe.tage, n = k.length;
      const s0 = Math.max(1, tage.findIndex((d) => d >= ligaStart));
      let konto = D.start, stk = 0;
      const akt = [];
      const mk = schnitt(k, kurz), ml = schnitt(k, lang);
      for (let i = s0; i < n; i++) {
        const p = k[i];
        if (mk[i - 1] != null && ml[i - 1] != null) {
          const hoch = trend ? mk[i] > ml[i] : mk[i - 1] <= ml[i - 1] && mk[i] > ml[i];
          const runter = trend ? mk[i] < ml[i] : mk[i - 1] >= ml[i - 1] && mk[i] < ml[i];
          if (hoch && stk === 0) { stk = konto / (p * (1 + D.gebuehr)); konto = 0; akt.push([tage[i], "Kauf", p, stk]); }
          else if (runter && stk > 0) { akt.push([tage[i], "Verkauf", p, stk]); konto = stk * p * (1 - D.gebuehr); stk = 0; }
        }
        (verlauf[tage[i]] = verlauf[tage[i]] || {})[a.t] = konto + stk * p;
      }
      assets[a.t] = { wert: konto + stk * k[n - 1], akt, drin: stk > 0 };
    });
    D.assets.filter((a) => !a.tagOk).forEach((a) => { assets[a.t] = { wert: D.start, akt: [], drin: false }; });
    const labels = Object.keys(verlauf).sort(), letzt = {};
    D.assets.forEach((a) => { letzt[a.t] = D.start; });
    const reihe = labels.map((t) => { Object.assign(letzt, verlauf[t]); return Object.values(letzt).reduce((s, x) => s + x, 0); });
    liste.push({ id, name, regel: `Ø${kurz} / Ø${lang} Tage`, farbe, echt: false, kerzen: "Tageskerzen", labels, reihe, start: startGeld,
      ende: reihe.length ? reihe[reihe.length - 1] : startGeld, assets, kurz, lang, trend });
  });

  // Kennzahlen je Bot
  liste.forEach((b) => {
    b.proz = (b.ende / b.start - 1) * 100;
    b.trades = Object.values(b.assets).reduce((s, x) => s + x.akt.length, 0);
    b.gebuehren = Object.values(b.assets).reduce((s, x) => s + x.akt.reduce((g, [, , p, st]) => g + (st || 0) * p * D.gebuehr, 0), 0);
    b.runden = [];
    D.assets.forEach((a) => {
      let kauf = null;
      b.assets[a.t].akt.forEach(([t, art, p]) => {
        if (istEinstieg(art)) kauf = [t, p, art];
        else if (kauf) { b.runden.push({ a, von: kauf[0], bis: t, k: kauf[1], v: p, proz: rundenProz(kauf[2], kauf[1], p) }); kauf = null; }
      });
    });
    let spitze = b.start, tief = 0;
    b.reihe.concat([b.ende]).forEach((w) => { spitze = Math.max(spitze, w); tief = Math.min(tief, (w / spitze - 1) * 100); });
    b.rueckgang = tief;
    b.imMarkt = Object.values(b.assets).filter((x) => x.drin).length;
    b.seit = b.labels[0] || ligaStart;
    // Liegenlassen über genau denselben Zeitraum wie dieser Bot
    const Q = (b.echt && BOTS[b.id]) || H;
    if (Q) {
      b.bhLabels = Q.depot.labels; b.bhWerte = Q.depot.bh;
      b.bhJetzt = D.assets.reduce((s, a) => { const z = Q.assets[a.t]; return s + (z && z.startKurs ? D.start / z.startKurs * a.preis : D.start); }, 0);
      b.bhProz = (b.bhJetzt / startGeld - 1) * 100;
    }
  });

  // Gemeinsame Zeitachse für das Diagramm (Prozent seit dem eigenen Start)
  const tage = Array.from(new Set(liste.flatMap((b) => b.labels))).sort();
  liste.forEach((b) => {
    let j = -1, w = null;
    b.pReihe = tage.map((d) => {
      while (j + 1 < b.labels.length && b.labels[j + 1] <= d) { j++; w = b.reihe[j]; }
      return w == null ? null : (w / b.start - 1) * 100;
    });
    if (b.pReihe.length) b.pReihe[b.pReihe.length - 1] = b.proz;
    if (b.bhLabels) {
      let k = -1, v = null;
      b.bhP = tage.map((d) => {
        while (k + 1 < b.bhLabels.length && b.bhLabels[k + 1] <= d) { k++; v = b.bhWerte[k]; }
        return v == null || d < b.seit ? null : (v / startGeld - 1) * 100;
      });
      if (b.bhP.length) b.bhP[b.bhP.length - 1] = b.bhProz;
    }
  });
  const rang = liste.slice().sort((x, y) => y.proz - x.proz);
  rang.forEach((b, i) => { b.platz = i + 1; });
  LIGA = { bots: liste, rang, tage, ligaStart };
  return LIGA;
}

function ligaChart(bots, tage, H, boxId, dick) {
  const W = breite();
  const [lo, hi] = grenzen(bots.map((b) => b.pReihe).concat([[0]]));
  const x = (i) => 6 + i / Math.max(tage.length - 1, 1) * (W - 12), y = (v) => 12 + (hi - v) / (hi - lo) * (H - 24);
  const linien = bots.slice().reverse().map((b) => `<path class="zeichnen" pathLength="1" d="${pfad(b.pReihe, x, y)}" fill="none" stroke="${b.farbe}" stroke-width="${b.id === dick ? 2.8 : b.echt ? 2.2 : 1.5}" ${b.liegen ? 'stroke-dasharray="3 4"' : ""} stroke-linejoin="round"/>`).join("");
  setTimeout(() => {
    const box = document.getElementById(boxId);
    if (box) tippbar(box, tage.length, x, (i) => `<b>${datum(tage[i])}</b>` + bots.map((b) => b.pReihe[i] == null ? "" : `<br><span class="fleck" style="background:${b.farbe}"></span>${esc(b.name)}: ${vz(b.pReihe[i])}${zahl(b.pReihe[i], 2)} %`).join(""));
  });
  return `<div class="chartbox" id="${boxId}"><svg width="100%" viewBox="0 0 ${W} ${H}" role="img" aria-label="Verlauf in Prozent">
    <line x1="0" x2="${W}" y1="${y(0)}" y2="${y(0)}" stroke="#2A2A33" stroke-dasharray="2 4"/>${linien}
    <line class="kreuz" x1="0" x2="0" y1="6" y2="${H}" stroke="${TEXT}" stroke-dasharray="3 3" opacity="0"/></svg><div class="tip"></div></div>`;
}

function botMarke(b, g) {
  const pfade = {
    haupt: BOT_INFO.haupt.pfad, turbo: BOT_INFO.turbo.pfad, short: BOT_INFO.short.pfad, tshort: BOT_INFO.tshort.pfad,
    liegen: '<path d="M7 11V7a5 5 0 0 1 10 0v4"/><rect x="4" y="11" width="16" height="10" rx="2"/>',
    schnell: '<path d="M5 12h14M13 6l6 6-6 6"/>',
    langsam: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  };
  return `<span class="icon" style="width:${g}px;height:${g}px;background:${b.farbe}22"><svg width="${Math.round(g * 0.5)}" height="${Math.round(g * 0.5)}" viewBox="0 0 24 24" fill="none" stroke="${b.farbe}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${pfade[b.id] || ""}</svg></span>`;
}

function ligaSeite() {
  const L = rechneLiga();
  if (!L.bots.length) return `<div style="padding:16px 20px 0"><h1 class="titel">Bot-Liga</h1></div><div class="leer">Die Liga startet, sobald Kursdaten da sind.</div>`;
  const medaille = ["#F5C451", "#C9CDD6", "#D08A52"];
  const karten = L.rang.map((b, i) => {
    const gv = b.ende - b.start;
    return `<button class="karte zeile" onclick="oeffneBot('${b.id}')" style="display:flex;align-items:center;gap:12px;padding:14px;width:auto;${b.echt ? `outline:1.5px solid ${b.farbe};` : ""}">
      <span class="rang num" style="background:${i < 3 ? medaille[i] : "#24242C"};color:${i < 3 ? "#0B0B0E" : "#9A9AA6"}">${i + 1}</span>
      <span style="flex-grow:1;min-width:0"><span style="display:flex;align-items:center;gap:6px;font-size:15px;font-weight:700"><span class="strich" style="background:${b.farbe};width:14px"></span>${esc(b.name)}${b.echt ? `<span class="pill" style="padding:2px 7px;font-size:10px;color:${GRUEN};background:${GRUEN_BG}">echt</span>` : b.liegen ? "" : `<span class="pill" style="padding:2px 7px;font-size:10px;color:#9A9AA6;background:#24242C">Simulation</span>`}</span>
      <span class="klein" style="display:block;margin-top:3px">${esc(b.regel)}${b.liegen ? "" : " · " + b.trades + (b.trades === 1 ? " Trade" : " Trades")} · seit ${kurzDatum(b.seit)}</span></span>
      <span style="text-align:right;white-space:nowrap"><span class="num" style="display:block;font-size:15px;font-weight:700">${betrag(b.ende, 2)}</span>
      <span class="num" style="display:block;font-size:12px;font-weight:600;margin-top:2px;color:${farbe(gv)}">${vz(b.proz)}${zahl(b.proz, 2)} %</span></span>
      <svg width="8" height="14" viewBox="0 0 8 14" aria-hidden="true" style="flex-shrink:0;opacity:.4"><path d="M1 1l6 6-6 6" fill="none" stroke="${TEXT}" stroke-width="2" stroke-linecap="round"/></svg>
    </button>`;
  }).join("");
  const deiner = L.rang.find((b) => b.id === "haupt");
  return `
  <div style="padding:16px 20px 0"><h1 class="titel" style="display:flex;align-items:center">Bot-Liga<button class="frage" onclick="erklaere('liga')" aria-label="Was ist die Bot-Liga?" style="width:24px;height:24px;border-radius:12px;font-size:13px">?</button></h1>
  <div class="klein" style="font-size:14px;margin-top:6px;line-height:1.45">Gleiches Spielgeld, verschiedene Regeln.${deiner ? ` Dein Bot liegt auf <b style="color:${TEXT}">Platz ${deiner.platz} von ${L.rang.length}</b>.` : ""} Tippe auf einen Bot für alle Details.</div></div>
  <div style="margin-top:16px">${ligaChart(L.bots, L.tage, 190, "ligachart")}</div>
  <div class="legende">${L.bots.map((b) => `<span><span class="strich" style="background:${b.farbe}"></span>${esc(b.name)}</span>`).join("")}</div>
  ${karten}
  <div class="leise" style="font-size:12px;padding:12px 20px 0;line-height:1.5">Prozent seit dem eigenen Start jedes Bots, mit ${zahl(D.start, 0) + " $"} pro Aktie und ${zahl(D.gebuehr * 100, 1)} % Gebühr. <b style="color:#C7C7D1">Echt</b> heißt: Der Bot handelt wirklich jeden Tag mit. <b style="color:#C7C7D1">Simulation</b> heißt: So hätte ein Bot mit diesen Regeln gehandelt, zurückgerechnet mit echten Kursen.</div>`;
}

function oeffneBotDepot(id) {
  schliesseTag();
  state.botDepot = id;
  history.pushState({ botDepot: id }, "");
  render(true, "detail");
}
function oeffneBot(id) {
  schliesseTag();
  state.ligaBot = id;
  history.pushState({ ligaBot: id }, "");
  render(true, "detail");
}

function botProfilSeite() {
  const L = rechneLiga();
  const b = L.bots.find((x) => x.id === state.ligaBot);
  if (!b) { state.ligaBot = null; return ligaSeite(); }
  const gv = b.ende - b.start;
  const liegen = b.id !== "liegen" && b.bhP ? { id: "bh", name: "Liegenlassen", farbe: "#9A9AA6", liegen: true, pReihe: b.bhP, proz: b.bhProz } : null;
  const vergleich = [b].concat(liegen ? [liegen] : []);
  const r = b.runden, plus = r.filter((x) => x.proz > 0), minus = r.filter((x) => x.proz <= 0);
  const schnittP = (l) => (l.length ? l.reduce((s, x) => s + x.proz, 0) / l.length : null);
  const sP = schnittP(plus), sM = schnittP(minus);
  const kachel = (titel, wert, f, zusatz) => `<div class="stat"><div class="klein" style="font-size:11px">${titel}</div><div class="w num" style="color:${f || TEXT}">${wert}</div>${zusatz ? `<div class="klein" style="font-size:11px;margin-top:2px">${zusatz}</div>` : ""}</div>`;
  const stunde = b.kerzen === "Stundenkerzen";
  const regeln = b.liegen
    ? `Kauft am ersten Tag jede Aktie für ${zahl(D.start, 0) + " $"} und macht danach <b>nichts mehr</b>. Das ist der wichtigste Maßstab: Ein Bot lohnt sich nur, wenn er mehr schafft als einfaches Liegenlassen.`
    : `<b>Kerzen:</b> ${b.kerzen}, entscheidet ${stunde ? "nach jeder fertigen Stunde" : "einmal am Abend nach Börsenschluss"}.<br>
       ${b.short ? `<b style="color:${SHORT_FARBE}">Short:</b> solange Ø${b.kurz} unter Ø${b.lang} liegt. Er verkauft geliehene Aktien und verdient, wenn der Kurs fällt.<br>
       <b>Eindecken:</b> sobald Ø${b.kurz} über Ø${b.lang} steigt. Dann kauft er die Aktien zurück.<br>` : `<b style="color:${BOT_KAUF}">Kauf:</b> ${b.trend ? `solange Ø${b.kurz} über Ø${b.lang} liegt` : `wenn Ø${b.kurz} von unten über Ø${b.lang} steigt`}.<br>
       <b>Verkauf:</b> ${b.trend ? `sobald Ø${b.kurz} unter Ø${b.lang} fällt` : `wenn Ø${b.kurz} von oben unter Ø${b.lang} fällt`}.<br>`}
       <b>Einsatz:</b> ${zahl(D.start, 0) + " $"} pro Aktie, ${zahl(D.gebuehr * 100, 1)} % Gebühr pro Kauf und Verkauf.`;
  const aktien = D.assets.map((a) => ({ a, w: b.assets[a.t] })).filter((x) => x.w).sort((p, q) => q.w.wert - p.w.wert).map(({ a, w }) => {
    const g = w.wert - D.start, p = g / D.start * 100;
    const breiteBalken = Math.min(Math.abs(p) / 20 * 50, 50);
    const klickbar = b.echt;
    return `<${klickbar ? `button class="zeile" onclick="oeffne('${a.t}', '${b.id}')"` : `div class="zeile"`} style="padding:9px 8px">
      ${icon(a, 34)}
      <span style="flex-grow:1;min-width:0"><span style="display:flex;justify-content:space-between;gap:8px"><span style="font-size:14px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${esc(a.name)}</span><span class="num" style="font-size:14px;font-weight:600;color:${farbe(g)};white-space:nowrap">${vz(p)}${zahl(p, 2)} %</span></span>
      <span style="display:block;margin-top:6px;height:5px;border-radius:3px;background:#22222A;position:relative"><span style="position:absolute;left:50%;top:-2px;width:1px;height:9px;background:#5E5E6B"></span><span style="position:absolute;top:0;height:5px;border-radius:3px;left:${g >= 0 ? 50 : 50 - breiteBalken}%;width:${breiteBalken}%;background:${farbe(g)}"></span></span>
      <span class="klein" style="display:block;margin-top:4px">${w.drin ? (w.short ? "Short" : "Im Markt") : "Bargeld"} · ${w.akt.length} ${w.akt.length === 1 ? "Trade" : "Trades"}</span></span>
    </${klickbar ? "button" : "div"}>`;
  }).join("");
  const letzte = D.assets.flatMap((a) => (b.assets[a.t] ? b.assets[a.t].akt : []).map(([t, art, p]) => ({ a, t, art, p }))).sort((x, y) => (x.t < y.t ? 1 : -1)).slice(0, 8);
  const tradeListe = letzte.length ? letzte.map((e) => `<div style="display:flex;align-items:center;gap:10px;padding:10px 0">${icon(e.a, 30)}<span style="flex-grow:1;min-width:0"><span style="display:block;font-size:14px;font-weight:600">${esc(e.a.name)}</span><span class="klein num">${datum(e.t)} · ${geld(e.p)}</span></span><span class="pill" style="color:${ART_FARBE[e.art]};background:${ART_BG[e.art]}">${e.art}</span></div>`).join("") : `<div class="klein" style="padding:10px 0">Noch keine Trades.</div>`;
  const besser = liegen ? b.proz - liegen.proz : null;
  return `
  <div style="display:flex;align-items:center;justify-content:space-between;padding:8px 12px 0">
    <button class="rund" onclick="zurueck()" aria-label="Zurück"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="${TEXT}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M15 18l-6-6 6-6"/></svg></button>
    <span class="pill" style="${b.echt ? `color:${GRUEN};background:${GRUEN_BG}` : `color:#9A9AA6;background:#24242C`}">${b.echt ? "Echter Bot" : b.liegen ? "Maßstab" : "Simulation"}</span>
  </div>
  <div style="text-align:center;padding:14px 20px 0">
    <div style="display:flex;justify-content:center">${botMarke(b, 56)}</div>
    <div style="font-size:22px;font-weight:700;margin-top:10px">${esc(b.name)}</div>
    <div class="klein" style="margin-top:2px">${esc(b.regel)} · seit ${datum(b.seit)}</div>
    <div class="num" style="font-size:40px;font-weight:700;letter-spacing:-1.4px;margin-top:16px;line-height:1">${betrag(b.ende, 2)}</div>
    <div class="num pill" style="display:inline-flex;gap:6px;margin-top:12px;font-size:14px;padding:6px 12px;border-radius:12px;color:${farbe(gv)};background:${gv >= 0 ? GRUEN_BG : ROT_BG}"><span>${gv >= 0 ? "▲" : "▼"}</span><span>${vz(gv)}${betrag(gv, 2)}</span><span style="opacity:.55">·</span><span>${vz(b.proz)}${zahl(b.proz, 2)} %</span></div>
    <div class="leise" style="font-size:12px;margin-top:8px">Platz ${b.platz} von ${L.rang.length} in der Liga</div>
  </div>
  <div style="margin-top:18px">${(() => { const i0 = Math.max(0, b.pReihe.findIndex((v) => v != null)); return ligaChart(vergleich.map((x) => ({ ...x, pReihe: x.pReihe.slice(i0) })), L.tage.slice(i0), 150, "profilchart", b.id); })()}</div>
  <div class="legende">${vergleich.map((x) => `<span><span class="strich" style="background:${x.farbe}"></span>${esc(x.name)}</span>`).join("")}</div>
  ${besser != null ? `<div class="karte" style="display:flex;align-items:center;justify-content:space-between;padding:14px 16px"><span><span class="klein" style="font-size:13px;display:block">Gegen Liegenlassen</span><span class="leise" style="font-size:11px">gleicher Zeitraum, seit ${kurzDatum(b.seit)}</span></span><span class="num" style="font-size:16px;font-weight:700;color:${farbe(besser)}">${vz(besser)}${zahl(besser, 2)} %-Punkte</span></div>` : ""}
  <div class="karte">
    <h3>Kennzahlen</h3>
    <div style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin-top:12px">
      ${kachel("Trades", String(b.trades), null, b.liegen ? "nur die Käufe am Start" : r.length + (r.length === 1 ? " abgeschlossene Runde" : " abgeschlossene Runden"))}
      ${kachel("Trefferquote", r.length ? Math.round(plus.length / r.length * 100) + " %" : "–", null, r.length ? plus.length + " von " + r.length + " im Plus" : "noch keine Runde")}
      ${kachel("Ø Gewinn-Runde", sP == null ? "–" : vz(sP) + zahl(sP, 1) + " %", sP == null ? null : GRUEN)}
      ${kachel("Ø Verlust-Runde", sM == null ? "–" : vz(sM) + zahl(sM, 1) + " %", sM == null ? null : ROT)}
      ${kachel("Größter Rückgang", zahl(b.rueckgang, 1) + " %", b.rueckgang < -0.05 ? ROT : null, "vom Höchststand aus")}
      ${kachel("Gebühren", betrag(b.gebuehren, 2), null, "bezahlt seit Start")}
      ${kachel("Im Markt", b.imMarkt + " / " + D.assets.length, null, "Aktien gerade gehalten")}
      ${kachel("Kerzen", stunde ? "1 Stunde" : "1 Tag", null, b.echt ? "läuft jeden Tag mit" : "zurückgerechnet")}
    </div>
  </div>
  <div class="karte"><h3>So handelt ${b.liegen ? "Liegenlassen" : "dieser Bot"}</h3><div style="font-size:14px;line-height:1.6;color:#D4D4DC;margin-top:10px">${regeln}</div></div>
  <div class="abschnitt"><b>Ergebnis je Aktie</b>${b.echt ? `<span class="klein">Tippen für Chart</span>` : ""}</div>
  <div style="padding:0 8px">${aktien}</div>
  ${b.liegen ? "" : `<div class="karte"><h3>Letzte Trades</h3><div class="liste-trenner" style="margin-top:4px">${tradeListe}</div></div>`}
  ${b.echt ? `<button onclick="zumDepot('${b.id}')" class="karte" style="display:block;width:calc(100% - 32px);text-align:center;font-weight:700;font-size:15px;color:${b.farbe};padding:15px">${b.id === "haupt" ? "Zum Depot deines Bots" : "Zum Depot · " + esc(b.name)}<span class="leise" style="display:block;font-size:11px;font-weight:500;margin-top:3px">im Tab ${b.id === "turbo" || b.id === "tshort" ? "Turbo" : "Depot"}, oben links umschaltbar</span></button>` : ""}`;
}

// ---------- Turbo-Bot ----------
// Duell: beide Bots ab dem Start des Turbo-Bots in Prozent
function duellDaten(id) {
  const T = BOTS[id || "turbo"], H = BOTS.haupt;
  if (!T || !T.depot.labels.length) return null;
  const startGeld = D.start * D.assets.length;
  const labels = T.depot.labels, t0 = labels[0];
  let basis = startGeld;
  H.depot.labels.forEach((d, i) => { if (d < t0) basis = H.depot.bot[i]; });
  let j = -1, letzt = basis;
  const deiner = labels.map((d) => { while (j + 1 < H.depot.labels.length && H.depot.labels[j + 1] <= d) { j++; letzt = H.depot.bot[j]; } return letzt; });
  const jetzt = (B) => D.assets.reduce((s, a) => { const z = B.assets[a.t]; return s + (z ? z.konto + z.stk * a.preis : D.start); }, 0);
  const turboJetzt = jetzt(T), deinerJetzt = jetzt(H);
  return {
    labels, t0, startGeld, basis,
    tp: T.depot.bot.map((w) => (w / startGeld - 1) * 100),
    dp: deiner.map((w) => (w / basis - 1) * 100),
    turboJetzt, deinerJetzt,
    turboProz: (turboJetzt / startGeld - 1) * 100,
    deinerProz: (deinerJetzt / basis - 1) * 100,
    vorsprung: (turboJetzt - startGeld) - (deinerJetzt - basis),
  };
}
function duellKarte(id) {
  id = id || "turbo";
  const d = duellDaten(id), F = BOT_INFO[id].farbe, N = BOT_INFO[id].kurz;
  if (!d) return "";
  const turboVorn = d.vorsprung > 0, gleich = Math.abs(d.vorsprung) < 0.01;
  const anteil = Math.max(8, Math.min(92, 50 + (d.turboProz - d.deinerProz) * 6));
  const seite = (name, f, wert, p, rechts, fuehrt) => `
    <div style="text-align:${rechts ? "right" : "left"};min-width:0">
      <div class="klein" style="display:flex;align-items:center;gap:6px;${rechts ? "justify-content:flex-end" : ""}"><span class="strich" style="background:${f};width:12px"></span>${name}${fuehrt ? ' <span style="color:#F5C451">★</span>' : ""}</div>
      <div class="num" style="font-size:19px;font-weight:700;margin-top:4px;white-space:nowrap">${vz(p)}${zahl(p, 2)} %</div>
      <div class="num leise" style="font-size:12px;margin-top:2px;white-space:nowrap">${betrag(wert, 2)}</div>
    </div>`;
  let mini = "";
  const n = d.labels.length;
  if (n >= 2) {
    const W = breite() - 64, H = 70;
    const [lo, hi] = grenzen([d.tp, d.dp, [0]]);
    const x = (i) => 3 + i / (n - 1) * (W - 6), y = (v) => 5 + (hi - v) / (hi - lo) * (H - 10);
    mini = `<div class="chartbox" id="duellchart" style="margin-top:14px"><svg width="100%" viewBox="0 0 ${W} ${H}" role="img" aria-label="Duell im Verlauf">
      <line x1="0" x2="${W}" y1="${y(0)}" y2="${y(0)}" stroke="#2A2A33" stroke-dasharray="2 4"/>
      <path class="zeichnen" pathLength="1" d="${pfad(d.dp, x, y)}" fill="none" stroke="${AKZENT}" stroke-width="1.8" stroke-linejoin="round"/>
      <path class="zeichnen" pathLength="1" d="${pfad(d.tp, x, y)}" fill="none" stroke="${F}" stroke-width="2.2" stroke-linejoin="round"/>
      <line class="kreuz" x1="0" x2="0" y1="0" y2="${H}" stroke="${TEXT}" stroke-dasharray="3 3" opacity="0"/>
    </svg><div class="tip"></div></div>`;
    setTimeout(() => {
      const box = document.getElementById("duellchart");
      if (box) tippbar(box, n, x, (i) => `<b>${datum(d.labels[i])}</b><br><span class="fleck" style="background:${F}"></span>${N}: ${vz(d.tp[i])}${zahl(d.tp[i], 2)} %<br><span class="fleck" style="background:${AKZENT}"></span>Dein Bot: ${vz(d.dp[i])}${zahl(d.dp[i], 2)} %`);
    });
  }
  return `
  <div class="karte" style="margin-top:22px">
    <div style="display:flex;justify-content:space-between;align-items:baseline"><h3>Duell gegen deinen Bot</h3><span class="klein">seit ${kurzDatum(d.t0)}</span></div>
    <div style="display:grid;grid-template-columns:1fr auto 1fr;align-items:center;gap:8px;margin-top:12px">
      ${seite("Dein Bot", AKZENT, d.deinerJetzt, d.deinerProz, false, !gleich && !turboVorn)}
      <span class="leise" style="font-size:12px;font-weight:700">VS</span>
      ${seite(N, F, d.turboJetzt, d.turboProz, true, !gleich && turboVorn)}
    </div>
    <div style="display:flex;height:8px;border-radius:4px;overflow:hidden;margin-top:14px;background:#24242C">
      <div style="width:${100 - anteil}%;background:${AKZENT}"></div><div style="width:2px;background:#0B0B0E"></div><div style="flex-grow:1;background:${F}"></div>
    </div>
    <div style="font-size:14px;margin-top:12px;line-height:1.45">${gleich ? "Beide liegen gleichauf." : `<b style="color:${turboVorn ? F : AKZENT}">${turboVorn ? N : "Dein Bot"}</b> liegt <b class="num">${betrag(Math.abs(d.vorsprung), 2)}</b> vorne.`}</div>
    ${mini}
  </div>`;
}
function turboSeite() {
  if (BOTS.turbo || BOTS.tshort) return depotSeite();
  return `
  <div style="display:flex;align-items:center;gap:10px;padding:12px 20px 0">
    <span class="icon" style="width:34px;height:34px;background:#2E2117"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="${TURBO_FARBE}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M13 2L4.5 13.5H11L10 22l8.5-11.5H12z"/></svg></span>
    <div><div style="font-size:15px;font-weight:600;display:flex;align-items:center">Turbo-Bot<button class="frage" onclick="erklaere('turbo')" aria-label="Was ist der Turbo-Bot?">?</button></div><div class="klein">Stundenkerzen · Ø5 / Ø20</div></div>
  </div>
  <div class="karte" style="margin-top:22px;text-align:center;padding:28px 20px">
    <div style="font-size:17px;font-weight:700">Startet beim nächsten Lauf</div>
    <div class="klein" style="font-size:14px;line-height:1.55;margin-top:8px">Sobald du <b style="color:${TEXT}">paper_bot.py</b> startest, legt der Turbo-Bot mit ${zahl(D.start, 0) + " $"} pro Aktie los. Danach siehst du hier alles wie bei deinem Bot: Depot, Charts, Kalender und das Duell.</div>
  </div>`;
}
// Umschalter für Signale und Aktivität
function botSchalter() {
  const da = BOT_IDS.filter((id) => BOTS[id]);
  if (da.length < 2) return "";
  return `<div class="scrollx" style="margin-top:12px;gap:6px">${da.map((id) =>
    `<button class="chip ${state.sicht === id ? "aktiv" : ""}" onclick="setze({sicht:'${id}'})" style="display:inline-flex;align-items:center;gap:6px;padding:7px 12px;flex-shrink:0;${state.sicht === id ? "" : "background:#141418"}"><span class="punkt" style="background:${BOT_INFO[id].farbe}"></span>${BOT_INFO[id].kurz}</button>`).join("")}</div>`;
}
// Bot-Wahl oben links: im Depot "Dein Bot" oder "Short-Bot", im Turbo-Tab "Turbo" oder "Turbo-Short"
function liesWahl(k, std) { try { const v = localStorage.getItem(k); return v && BOTS[v] ? v : std; } catch (e) { return std; } }
function wahlPaar() { return state.tab === "turbo" ? ["turbo", "tshort"] : ["haupt", "short"]; }
function zeigeBotWahl() {
  const paar = wahlPaar().filter((id) => BOTS[id]);
  const gewaehlt = state.tab === "turbo" ? state.turboWahl : state.depotWahl;
  const zeilen = paar.map((id) => {
    const B = BOTS[id], I = BOT_INFO[id];
    const wert = D.assets.reduce((s, a) => s + wertJetzt(B, a), 0), gv = wert - D.start * D.assets.length, p = gv / (D.start * D.assets.length) * 100;
    return `<button class="zeile" onclick="waehleBot('${id}')" style="padding:12px 6px;border-radius:14px;${id === gewaehlt ? "background:#1C1C22" : ""}">
      <span class="icon" style="width:42px;height:42px;background:${I.bg}"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="${I.farbe}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${I.pfad}</svg></span>
      <span style="flex-grow:1;min-width:0"><span style="display:block;font-size:15px;font-weight:700;color:${TEXT}">${I.name}</span>
      <span class="klein" style="display:block;margin-top:2px">${B.richtung === "short" ? "Short" : "Long"} · Ø${B.kurz} / Ø${B.lang} ${B.intervall === "1h" ? "Stunden" : "Tage"}</span></span>
      <span style="text-align:right;white-space:nowrap"><span class="num" style="display:block;font-size:14px;font-weight:600;color:${TEXT}">${betrag(wert, 2)}</span>
      <span class="num" style="display:block;font-size:12px;font-weight:600;margin-top:2px;color:${farbe(gv)}">${vz(p)}${zahl(p, 2)} %</span></span>
      <span style="width:22px;flex-shrink:0;display:flex;justify-content:center">${id === gewaehlt ? `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="${I.farbe}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12l5 5 9-10"/></svg>` : ""}</span>
    </button>`;
  }).join("");
  zeigeInfo("Bot wählen", `<div style="margin:-4px -6px 0">${zeilen}</div><div class="leise" style="font-size:12px;margin-top:10px;line-height:1.5">Long-Bots verdienen, wenn Kurse steigen. Short-Bots verdienen, wenn Kurse fallen.</div>`);
}
function waehleBot(id) {
  schliesseTag();
  if (id === "turbo" || id === "tshort") { state.turboWahl = id; try { localStorage.setItem("bot_wahl_turbo", id); } catch (e) {} }
  else { state.depotWahl = id; try { localStorage.setItem("bot_wahl_depot", id); } catch (e) {} }
  render(true, "tab");
}
function zumDepot(id) {
  if (id === "turbo" || id === "tshort") { state.turboWahl = id; tab("turbo"); }
  else { state.depotWahl = id; tab("depot"); }
  try { localStorage.setItem(id === "turbo" || id === "tshort" ? "bot_wahl_turbo" : "bot_wahl_depot", id); } catch (e) {}
}
function botFuer() {
  if (state.mitteilungen) return "haupt";
  if (state.botDepot && !state.detail) return state.botDepot;
  if (state.ligaBot && !state.detail) return BOTS[state.ligaBot] ? state.ligaBot : "haupt";
  if (state.detail) return state.detailBot;
  if (state.tab === "turbo") return BOTS[state.turboWahl] ? state.turboWahl : "turbo";
  if (state.tab === "depot") return BOTS[state.depotWahl] ? state.depotWahl : "haupt";
  if (state.tab === "signale" || state.tab === "aktivitaet") return state.sicht;
  return "haupt";
}

// ---------- Heute ----------
function heuteKarte() {
  const mit = D.assets.filter((a) => a.ok);
  if (!mit.length) return "";
  const tage = Object.keys(D.aenderung).sort();
  const letzter = tage[tage.length - 1];
  const tagGv = letzter ? D.aenderung[letzter] : 0;
  const sortiert = mit.slice().sort((p, q) => q.tagProz - p.tagProz);
  const zeile = (a) => `<button class="zeile" onclick="oeffne('${a.t}')" style="padding:7px 4px;gap:8px">${icon(a, 26)}<span style="flex-grow:1;min-width:0;font-size:13px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${esc(a.name)}</span><span class="num" style="font-size:13px;font-weight:600;white-space:nowrap;color:${farbe(a.tagProz)}">${vz(a.tagProz)}${zahl(a.tagProz, 2)} %</span></button>`;
  return `
  <div class="karte" style="margin-top:22px">
    <div style="display:flex;justify-content:space-between;align-items:baseline">
      <h3>Heute</h3><span class="klein">${letzter ? "Handelstag " + kurzDatum(letzter) : ""}</span>
    </div>
    <div style="display:flex;align-items:baseline;gap:8px;margin-top:10px">
      <span class="num" style="font-size:22px;font-weight:700;color:${farbe(tagGv)}">${vz(tagGv)}${betrag(tagGv, 2)}</span>
      <span class="klein">Depot an diesem Tag</span>
    </div>
    <div style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin-top:12px">
      <div><div class="klein" style="margin-bottom:2px">Gewinner</div>${sortiert.slice(0, 3).map(zeile).join("")}</div>
      <div><div class="klein" style="margin-bottom:2px">Verlierer</div>${sortiert.slice(-3).reverse().map(zeile).join("")}</div>
    </div>
  </div>`;
}

// ---------- Bot-Statistik ----------
function statistikKarte() {
  const r = RUNDEN.slice().sort((p, q) => (p.bis < q.bis ? -1 : 1));
  let gebuehren = 0;
  D.assets.forEach((a) => a.akt.forEach(([, , p, st]) => { gebuehren += (st || 0) * p * D.gebuehr; }));
  if (!r.length) {
    return `<div class="karte"><h3>Bot-Statistik</h3><div class="klein" style="margin-top:8px;line-height:1.5">Erscheint nach der ersten abgeschlossenen Runde. Gebühren bisher: <b class="num" style="color:${TEXT}">${betrag(gebuehren, 2)}</b></div></div>`;
  }
  const gewinner = r.filter((x) => x.proz > 0), verlierer = r.filter((x) => x.proz <= 0);
  const schnittP = (l) => l.length ? l.reduce((s, x) => s + x.proz, 0) / l.length : null;
  const stundenZw = (a, b) => (zeitpunkt(b) - zeitpunkt(a)) / 3600000;
  const haltenStd = r.reduce((s, x) => s + stundenZw(x.von, x.bis), 0) / r.length;
  const halten = haltenStd / 24;
  let serieG = 0, serieV = 0, g = 0, v = 0;
  r.forEach((x) => { if (x.proz > 0) { g++; v = 0; } else { v++; g = 0; } serieG = Math.max(serieG, g); serieV = Math.max(serieV, v); });
  const beste = r.reduce((m, x) => (x.proz > m.proz ? x : m)), schlechteste = r.reduce((m, x) => (x.proz < m.proz ? x : m));
  const sG = schnittP(gewinner), sV = schnittP(verlierer);
  const kachel = (titel, wert, f, zusatz) => `<div class="stat"><div class="klein" style="font-size:11px">${titel}</div><div class="w num" style="color:${f || TEXT}">${wert}</div>${zusatz ? `<div class="klein" style="font-size:11px;margin-top:2px">${zusatz}</div>` : ""}</div>`;
  return `
  <div class="karte">
    <div style="display:flex;justify-content:space-between;align-items:baseline"><h3>Bot-Statistik</h3><span class="klein">${r.length} Runden</span></div>
    <div style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;margin-top:12px">
      ${kachel("Ø Gewinn-Runde", sG == null ? "–" : vz(sG) + zahl(sG, 1) + " %", sG == null ? null : GRUEN)}
      ${kachel("Ø Verlust-Runde", sV == null ? "–" : vz(sV) + zahl(sV, 1) + " %", sV == null ? null : ROT)}
      ${kachel("Beste Runde", vz(beste.proz) + zahl(beste.proz, 1) + " %", farbe(beste.proz), esc(beste.a.name))}
      ${kachel("Schlechteste Runde", vz(schlechteste.proz) + zahl(schlechteste.proz, 1) + " %", farbe(schlechteste.proz), esc(schlechteste.a.name))}
      ${kachel("Längste Gewinnserie", serieG + (serieG === 1 ? " Runde" : " Runden"))}
      ${kachel("Längste Verlustserie", serieV + (serieV === 1 ? " Runde" : " Runden"))}
      ${kachel("Ø Haltedauer", istStunde() && haltenStd < 48 ? zahl(haltenStd, 0) + " Std" : zahl(halten, istStunde() ? 1 : 0) + " Tage")}
      ${kachel("Gebühren gesamt", betrag(gebuehren, 2), null, "bei " + zahl(D.gebuehr * 100, 1) + " % pro Kauf/Verkauf")}
    </div>
  </div>`;
}

// ---------- Mitteilungen ----------
const EREIGNISSE = [];
BOT_IDS.forEach((bot) => {
  const B = BOTS[bot];
  if (!B) return;
  D.assets.forEach((a) => {
    const z = B.assets[a.t];
    if (!z) return;
    let kauf = null;
    z.akt.forEach(([t, art, p, st]) => {
      let extra = null;
      if (istEinstieg(art)) kauf = [p, art];
      else if (kauf) { extra = rundenProz(kauf[1], kauf[0], p); kauf = null; }
      EREIGNISSE.push({ a, t, art, p, st, extra, bot });
    });
  });
});
EREIGNISSE.sort((x, y) => (x.t < y.t ? 1 : x.t > y.t ? -1 : 0));
// Gelesene Mitteilungen merkt sich die App auf dem Handy
function liesGelesen() { try { return parseInt(localStorage.getItem("bot_gelesen") || "0", 10) || 0; } catch (e) { return 0; } }
function merkeGelesen(n) { try { localStorage.setItem("bot_gelesen", String(n)); } catch (e) {} }
let GELESEN = liesGelesen();
if (GELESEN > EREIGNISSE.length) { GELESEN = 0; merkeGelesen(0); }
function ungelesen() { return Math.max(0, EREIGNISSE.length - GELESEN); }
function badgeText(n) { return n > 99 ? "99+" : String(n); }
const NEU = EREIGNISSE.slice(0, ungelesen());
function ereignisText(e) {
  const menge = e.a.einheit === "BTC" ? (e.st || 0).toLocaleString("de-DE", { maximumFractionDigits: 6 }) + " BTC" : zahl(e.st || 0, 2) + " Stk";
  return {
    titel: `${e.bot !== "haupt" ? BOT_INFO[e.bot].kurz + ": " : ""}${e.a.name} ${ART_WORT[e.art]}`,
    text: `${menge} zu ${geld(e.p)}` + (e.t.length > 10 ? ` · ${e.t.slice(11, 16)} Uhr` : "") + (e.extra != null ? ` · Runde ${vz(e.extra)}${zahl(e.extra, 1)} %` : ""),
  };
}
function mitteilungenSeite() {
  const gruppen = {};
  EREIGNISSE.forEach((e, i) => { e.neu = i < (state.markiert || 0); const tag = e.t.slice(0, 10); (gruppen[tag] = gruppen[tag] || []).push(e); });
  const inhalt = EREIGNISSE.length ? Object.keys(gruppen).map((t) => `
    <div class="klein" style="padding:18px 20px 6px;font-weight:600">${t === D.letzterTag ? "Letzter Handelstag · " : ""}${datum(t)}</div>
    <div class="karte liste-trenner" style="margin-top:0;padding:4px 14px">${gruppen[t].map((e) => {
      const tx = ereignisText(e);
      return `<button class="zeile" onclick="oeffne('${e.a.t}', '${e.bot}')" style="padding:12px 0;border-radius:0">
        ${icon(e.a, 36)}
        <span style="flex-grow:1;min-width:0"><span style="display:flex;align-items:center;gap:6px;font-size:14px;font-weight:600">${e.neu ? `<span class="punkt" style="background:${BOT_KAUF};width:8px;height:8px;border-radius:4px" aria-label="neu"></span>` : ""}${esc(tx.titel)}</span><span class="klein num" style="display:block;margin-top:2px">${tx.text}</span></span>
        <span class="pill" style="color:${ART_FARBE[e.art]};background:${ART_BG[e.art]}">${e.art}</span>
      </button>`;
    }).join("")}</div>`).join("") : `<div class="leer">Noch keine Mitteilungen. Sobald der Bot kauft oder verkauft, steht es hier.</div>`;
  return `
  <div style="display:flex;align-items:center;gap:12px;padding:8px 12px 0">
    <button class="rund" onclick="zurueck()" aria-label="Zurück"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="${TEXT}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M15 18l-6-6 6-6"/></svg></button>
  </div>
  <div style="padding:10px 20px 0"><h1 class="titel">Mitteilungen</h1>
  <div class="klein" style="font-size:14px;margin-top:6px;line-height:1.45">${BOT_IDS.filter((id) => BOTS[id]).length > 1 ? "Alle Trades von allen deinen Bots." : "Alle Käufe und Verkäufe des Bots."}</div></div>
  <div class="karte">
    <h3>Push-Nachrichten aufs iPhone</h3>
    ${D.modus !== "cloud" ? `<div class="klein" style="font-size:13px;margin-top:8px;line-height:1.5">Kommen mit dem Umzug in die Cloud. Bis dahin siehst du neue Käufe und Verkäufe hier und an der Zahl an der Glocke.</div>` : `<div class="klein" style="font-size:13px;margin-top:8px;line-height:1.5">Kommen über die App <b style="color:${TEXT}">ntfy</b>: Sobald einer deiner Bots kauft oder verkauft, bekommst du eine Nachricht. Klappt ein Lauf nicht, zum Beispiel weil keine Kurse kamen, meldet er sich auch.</div>`}
  </div>
  ${inhalt}`;
}
function oeffneMitteilungen() {
  versteckeToast();
  state.markiert = ungelesen();
  GELESEN = EREIGNISSE.length;
  merkeGelesen(GELESEN);
  state.mitteilungen = true;
  history.pushState({ mitteilungen: true }, "");
  render(true, "detail");
}
function zeigeToast() {
  if (!NEU.length) return;
  const tx = ereignisText(NEU[0]);
  const t = document.createElement("button");
  t.className = "toast"; t.id = "toast";
  t.innerHTML = `${icon(NEU[0].a, 38)}<span style="flex-grow:1;min-width:0"><span style="display:block;font-size:11px;color:#9A9AA6;font-weight:600;letter-spacing:.3px">BOT · NEU</span><span style="display:block;font-size:14px;font-weight:600;margin-top:1px">${esc(tx.titel)}</span><span class="num" style="display:block;font-size:12px;color:#C7C7D1;margin-top:1px">${tx.text}${NEU.length > 1 ? " · +" + (NEU.length - 1) + " weitere" : ""}</span></span>`;
  t.onclick = oeffneMitteilungen;
  document.body.appendChild(t);
  wischbar(t);
  setTimeout(versteckeToast, 5200);
}
// Nachricht nach oben wischen = sofort weg (der Timer bleibt trotzdem als Sicherheit)
function wischbar(t) {
  let y0 = null, dy = 0, gewischt = false;
  t.style.touchAction = "none";
  t.addEventListener("pointerdown", (e) => {
    y0 = e.clientY; dy = 0; gewischt = false;
    t.style.animation = "none"; t.style.transition = "none";
    try { t.setPointerCapture(e.pointerId); } catch (f) {}
  });
  t.addEventListener("pointermove", (e) => {
    if (y0 == null) return;
    dy = Math.min(0, e.clientY - y0);
    if (dy < -6) gewischt = true;
    t.style.transform = `translate(-50%, ${dy}px)`;
    t.style.opacity = String(Math.max(0.3, 1 + dy / 160));
  });
  const ende = () => {
    if (y0 == null) return;
    y0 = null;
    if (dy < -35) {
      t.style.transition = "transform .22s ease-in, opacity .22s";
      t.style.transform = "translate(-50%, -160%)"; t.style.opacity = "0";
      t.id = ""; setTimeout(() => t.remove(), 240);
    } else {
      t.style.transition = "transform .2s ease-out, opacity .2s";
      t.style.transform = "translate(-50%, 0)"; t.style.opacity = "1";
    }
  };
  t.addEventListener("pointerup", ende);
  t.addEventListener("pointercancel", ende);
  // Nach einem Wisch nicht gleichzeitig die Mitteilungen öffnen
  t.addEventListener("click", (e) => { if (gewischt) { e.stopImmediatePropagation(); e.preventDefault(); } }, true);
}
function versteckeToast() {
  const t = document.getElementById("toast");
  if (!t || t.classList.contains("weg")) return;
  t.classList.add("weg");
  setTimeout(() => t.remove(), 400);
}
function zaehle(el) {
  const ziel = parseFloat(el.dataset.ziel), start = ziel * 0.985, t0 = performance.now(), dauer = 750;
  if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  function schritt(t) {
    const f = Math.min((t - t0) / dauer, 1), e = 1 - Math.pow(1 - f, 3);
    el.textContent = betrag(start + (ziel - start) * e, 2);
    if (f < 1) requestAnimationFrame(schritt);
  }
  requestAnimationFrame(schritt);
}

// ---------- Steuerung ----------
const ICONS = {
  depot: '<path d="M21 12a9 9 0 1 1-9-9v9z"/><path d="M15 3.5A9 9 0 0 1 20.5 9H15z"/>',
  signale: '<path d="M3 12h4l3-8 4 16 3-8h4"/>',
  aktivitaet: '<rect x="3" y="5" width="18" height="16" rx="3"/><path d="M3 10h18M8 3v4M16 3v4"/>',
  turbo: '<path d="M13 2L4.5 13.5H11L10 22l8.5-11.5H12z"/>',
  liga: '<path d="M8 21h8M12 17v4M7 4h10v5a5 5 0 0 1-10 0V4z"/><path d="M17 6h3v1a4 4 0 0 1-3 3.9M7 6H4v1a4 4 0 0 0 3 3.9"/>',
};
function render(nachOben, anim) {
  ICON_ZAEHLER = 0;
  if (aktiviere(botFuer())) state.monat = Math.max(MONATE.length - 1, 0);
  let html;
  if (state.mitteilungen) html = mitteilungenSeite();
  else if (state.botDepot && !state.detail) html = depotSeite();
  else if (state.ligaBot && !state.detail) html = botProfilSeite();
  else if (state.detail) html = detailSeite();
  else if (state.tab === "signale") html = signaleSeite();
  else if (state.tab === "aktivitaet") html = aktivitaetSeite();
  else if (state.tab === "liga") html = ligaSeite();
  else if (state.tab === "turbo") html = turboSeite();
  else html = depotSeite();
  document.getElementById("app").innerHTML = html;
  document.getElementById("tabbar").innerHTML = [["depot", "Depot"], ["signale", "Signale"], ["turbo", "Turbo"], ["liga", "Liga"], ["aktivitaet", "Aktivität"]].map(([id, label]) =>
    `<button class="tab ${state.tab === id ? "aktiv" : ""}" onclick="tab('${id}')"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[id]}</svg>${label}</button>`).join("");
  if (nachOben) window.scrollTo(0, 0);
  const main = document.getElementById("app");
  if (anim) { main.className = ""; void main.offsetWidth; main.className = anim === "detail" ? "anim-detail" : "anim-tab"; LIVE.animBis = Date.now() + 1200; }
  else main.className = "";
  const dw = document.getElementById("depotwert");
  if (dw && anim) zaehle(dw);
}
function setze(neu) { Object.assign(state, neu); render(false); }
document.addEventListener("keydown", (e) => { if (e.key === "Escape") { schliesseTag(); schliesseVollbild(); } });
function tab(id) {
  schliesseVollbild(); schliesseTag();
  if (history.state && (history.state.detail || history.state.mitteilungen || history.state.ligaBot || history.state.botDepot)) history.replaceState(null, "");
  state.ligaBot = null; state.botDepot = null;
  state.tab = id; state.detail = null; state.mitteilungen = false; render(true, "tab");
}
function oeffne(t, bot) { schliesseTag(); state.detailBot = bot || botFuer(); state.detail = t; state.mitteilungen = false; history.pushState({ detail: t, bot: state.detailBot }, ""); render(true, "detail"); }
function wechsle(t) { state.detail = t; history.replaceState({ detail: t, bot: state.detailBot }, ""); render(false); }
function zurueck() {
  if (history.state && (history.state.detail || history.state.mitteilungen || history.state.ligaBot || history.state.botDepot)) history.back();
  else { state.detail = null; state.mitteilungen = false; render(true, "tab"); }
}
window.addEventListener("popstate", (e) => {
  schliesseVollbild();
  state.detail = (e.state && e.state.detail) || null;
  if (e.state && e.state.bot) state.detailBot = e.state.bot;
  state.ligaBot = (e.state && e.state.ligaBot) || (state.detail || (e.state && e.state.botDepot) ? state.ligaBot : null);
  state.botDepot = (e.state && e.state.botDepot) || (state.detail ? state.botDepot : null);
  state.mitteilungen = !!(e.state && e.state.mitteilungen);
  render(true, "tab");
});
let letzteBreite = window.innerWidth;
window.addEventListener("resize", () => { if (window.innerWidth !== letzteBreite) { letzteBreite = window.innerWidth; render(false); if (state.vollbild) zeigeVollbild(); } });
// ---------- Live-Kurse ----------
// Solange die App offen ist, holt sie alle paar Sekunden aktuelle Preise.
// Bitcoin: Coinbase (ohne Anmeldung). Aktien und Gold: Finnhub (kostenloser Schlüssel, nur auf dem Handy gespeichert).
// Die Bots handeln davon unabhängig weiter nur nach fertigen Kerzen.
const LIVE = { zeit: null, quellen: {}, fehler: false, beruehrt: 0, animBis: 0, gezeigt: false };
function liveSchluessel() { try { return localStorage.getItem("finnhub_key") || ""; } catch (e) { return ""; } }
function heuteText() { const d = new Date(); return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0"); }
document.addEventListener("pointerdown", () => { LIVE.beruehrt = Date.now(); }, true);
async function holeJson(url) {
  const r = await fetch(url, { cache: "no-store" });
  if (!r.ok) throw new Error("HTTP " + r.status);
  return r.json();
}
let LIVE_RUNDE = 0;
async function holeLive() {
  if (document.hidden) return;
  const neu = {};
  const aktienRunde = LIVE_RUNDE++ % 3 === 0;
  if (D.vorschau) {
    // Vorschau: Preise bewegen sich ein bisschen, damit man den Effekt sieht
    D.assets.forEach((a) => { if (a.tagOk) neu[a.t] = a.preis * (1 + (Math.random() - 0.5) * 0.004); });
  } else {
    const btc = D.assets.find((a) => a.t === "BTC-USD");
    if (btc) {
      try { const j = await holeJson("https://api.coinbase.com/v2/prices/BTC-USD/spot"); const p = parseFloat(j.data.amount); if (p > 0) neu["BTC-USD"] = p; }
      catch (e) { try { const j = await holeJson("https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT"); const p = parseFloat(j.price); if (p > 0) neu["BTC-USD"] = p; } catch (f) {} }
    }
    const key = liveSchluessel();
    if (key && aktienRunde) {
      await Promise.all(D.assets.filter((a) => a.t !== "BTC-USD").map(async (a) => {
        try { const j = await holeJson(`https://finnhub.io/api/v1/quote?symbol=${encodeURIComponent(a.t)}&token=${encodeURIComponent(key)}`); if (j && j.c > 0) neu[a.t] = j.c; } catch (e) {}
      }));
    }
  }
  if (aktienRunde) LIVE.fehler = !Object.keys(neu).some((t) => t !== "BTC-USD") && !!liveSchluessel();
  if (!Object.keys(neu).length) return;
  let geaendert = false;
  const heute = heuteText(), jetzt = Date.now();
  const stundeText = (d) => d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0") + " " + String(d.getHours()).padStart(2, "0") + ":" + String(d.getMinutes()).padStart(2, "0");
  const setze = (R, i, p) => { R.kurse[i] = p; R.hoch[i] = Math.max(R.hoch[i], p); R.tief[i] = Math.min(R.tief[i], p); };
  const anhaengen = (R, zeit, p) => { const vor = R.kurse[R.kurse.length - 1]; R.tage.push(zeit); R.offen.push(vor); R.hoch.push(Math.max(vor, p)); R.tief.push(Math.min(vor, p)); R.kurse.push(p); R.vol.push(0); };
  D.assets.forEach((a) => {
    const p = neu[a.t];
    if (p == null || !a.tagOk) return;
    LIVE.quellen[a.t] = true;
    if (Math.abs(p - a.preis) > 1e-9) geaendert = true;
    a.preis = p;
    // Tageskerze von heute: mitbewegen oder neu anfangen
    const T = a.tagReihe, n = T.kurse.length;
    if (D.vorschau || T.tage[n - 1] === heute) setze(T, n - 1, p);
    else if (T.tage[n - 1] < heute && Math.abs(p / T.kurse[n - 1] - 1) > 1e-6) anhaengen(T, heute, p);
    const m = T.kurse.length, vorher = T.tage[m - 1] === heute || D.vorschau ? T.kurse[m - 2] : T.kurse[m - 1];
    a.tag = p - vorher; a.tagProz = a.tag / vorher * 100;
    T.rsi = rsiBerechnen(T.kurse, 14);
    // Stundenkerze: laufende Stunde mitbewegen oder neue Stunde anfangen
    const S = a.stdReihe;
    if (S && S.tage.length) {
      const k = S.tage.length, start = zeitpunkt(S.tage[k - 1]).getTime();
      if (D.vorschau || (jetzt >= start && jetzt - start < 3600000)) setze(S, k - 1, p);
      else if (jetzt - start >= 3600000 && Math.abs(p / S.kurse[k - 1] - 1) > 1e-6) {
        const schritte = Math.floor((jetzt - start) / 3600000);
        anhaengen(S, stundeText(new Date(start + schritte * 3600000)), p);
      }
      S.rsi = rsiBerechnen(S.kurse, 14);
    }
  });
  LIVE.zeit = new Date();
  LIGA = null;
  // Neu zeichnen, aber nicht während du gerade tippst, wischst oder ein Fenster offen ist
  const ruhig = Date.now() - LIVE.beruehrt > 4000 && Date.now() > LIVE.animBis && !document.getElementById("sheet");
  // Beim ersten Mal immer zeichnen, damit der Live-Timer sofort erscheint
  const erstesMal = !LIVE.gezeigt;
  if ((geaendert || erstesMal) && ruhig && state.vollbild) { zeigeVollbild(); LIVE.gezeigt = true; return; }
  if (geaendert || erstesMal) {
    if (!ruhig) { if (erstesMal && !LIVE.wartet) { LIVE.wartet = true; setTimeout(holeLiveAnzeigen, 1500); } aktualisiereLiveText(); return; }
    LIVE.gezeigt = true;
    const y = window.scrollY;
    document.getElementById("app").classList.add("live-ruhig");
    render(false);
    document.getElementById("app").classList.add("live-ruhig");
    window.scrollTo(0, y);
  } else aktualisiereLiveText();
}
// Wenn gerade nicht gezeichnet werden durfte: kurz danach nachholen
function holeLiveAnzeigen() {
  const ruhig = Date.now() - LIVE.beruehrt > 4000 && Date.now() > LIVE.animBis && !document.getElementById("sheet");
  if (!ruhig) { setTimeout(holeLiveAnzeigen, 1500); return; }
  LIVE.wartet = false;
  if (LIVE.gezeigt) return;
  const y = window.scrollY;
  render(false);
  document.getElementById("app").classList.add("live-ruhig");
  window.scrollTo(0, y);
  LIVE.gezeigt = true;
}
function liveText() {
  if (!LIVE.zeit) return "";
  // Läuft die Verbindung, tickt die Uhr jede Sekunde mit. Kommt länger nichts, steht dort die letzte Zeit.
  const frisch = Date.now() - LIVE.zeit.getTime() < 60000;
  const z = frisch ? new Date() : LIVE.zeit;
  return (frisch ? "" : "zuletzt ") + String(z.getHours()).padStart(2, "0") + ":" + String(z.getMinutes()).padStart(2, "0") + ":" + String(z.getSeconds()).padStart(2, "0");
}
setInterval(aktualisiereLiveText, 1000);
function liveMarke(t) {
  if (!LIVE.zeit || (t && !LIVE.quellen[t])) return "";
  return `<span class="live"><span class="live-punkt"></span>Live · <span class="live-zeit">${liveText()}</span></span>`;
}
function aktualisiereLiveText() { document.querySelectorAll(".live-zeit").forEach((el) => { el.textContent = liveText(); }); }
function liveKarte() {
  const key = liveSchluessel();
  const aktien = D.assets.filter((a) => a.t !== "BTC-USD").length;
  const mitLive = Object.keys(LIVE.quellen).length;
  return `
  <button class="karte zeile" onclick="zeigeLiveEinstellung()" style="display:flex;align-items:center;gap:12px;padding:14px;width:calc(100% - 32px)">
    <span class="icon" style="width:40px;height:40px;background:#13261E"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="${GRUEN}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 12h4l3-8 4 16 3-8h4"/></svg></span>
    <span style="flex-grow:1;min-width:0">
      <span style="display:flex;align-items:center;gap:6px;font-size:14px;font-weight:700">Live-Kurse ${LIVE.zeit ? liveMarke() : ""}</span>
      <span class="klein" style="display:block;margin-top:2px">${D.vorschau ? "Vorschau: Preise werden simuliert" : key ? (LIVE.fehler ? "Keine Antwort von Finnhub, Schlüssel prüfen" : `${mitLive} von ${D.assets.length} Werten live`) : `Bitcoin live · für die ${aktien} Aktien Schlüssel eintragen`}</span>
    </span>
    <svg width="8" height="14" viewBox="0 0 8 14" aria-hidden="true" style="flex-shrink:0;opacity:.4"><path d="M1 1l6 6-6 6" fill="none" stroke="${TEXT}" stroke-width="2" stroke-linecap="round"/></svg>
  </button>`;
}
function zeigeLiveEinstellung() {
  const key = liveSchluessel();
  zeigeInfo("Live-Kurse", `Solange die App offen ist, holt sie alle paar Sekunden die aktuellen Preise. Depotwert, Positionen und die laufende Kerze im Chart bewegen sich mit.<br><br>
    <b>Bitcoin</b> kommt ohne Anmeldung von Coinbase.<br>
    <b>Aktien und Gold</b> brauchen einen kostenlosen Schlüssel von <b>finnhub.io</b>. Er bleibt nur auf diesem iPhone gespeichert.<br><br>
    <input id="livekey" type="text" inputmode="latin" autocomplete="off" autocapitalize="off" spellcheck="false" placeholder="Finnhub-Schlüssel einfügen" value="${esc(key)}" style="width:100%;padding:13px 14px;border-radius:12px;border:1px solid #2A2A33;background:#0F0F13;color:${TEXT};font-size:15px;font-family:inherit">
    <button onclick="speichereLiveSchluessel()" style="margin-top:10px;width:100%;padding:13px;border-radius:12px;background:${GRUEN};color:#0B0B0E;font-weight:700;font-size:15px">Speichern</button>
    ${key ? `<button onclick="document.getElementById('livekey').value='';speichereLiveSchluessel()" style="margin-top:8px;width:100%;padding:11px;border-radius:12px;background:#1C1C22;font-weight:600;font-size:14px">Schlüssel entfernen</button>` : ""}
    <div class="leise" style="font-size:12px;margin-top:12px;line-height:1.5">US-Aktien bewegen sich nur, während die Börse offen ist (etwa 15:30 bis 22:00 Uhr). Die Bots handeln weiter nur nach fertigen Kerzen, die Live-Preise sind zum Zuschauen.</div>`);
}
function speichereLiveSchluessel() {
  const el = document.getElementById("livekey");
  const v = el ? el.value.trim() : "";
  try { if (v) localStorage.setItem("finnhub_key", v); else localStorage.removeItem("finnhub_key"); } catch (e) {}
  schliesseTag();
  zeigeHinweis(v ? "Schlüssel gespeichert" : "Schlüssel entfernt", v ? "Die Aktien werden ab jetzt live aktualisiert." : "Nur Bitcoin wird noch live aktualisiert.");
  setTimeout(holeLive, 300);
}
setInterval(holeLive, 5000);
setTimeout(holeLive, 1200);
document.addEventListener("visibilitychange", () => { if (!document.hidden) setTimeout(holeLive, 400); });

render(true, "tab");
setTimeout(zeigeToast, 700);
</script>
</body>
</html>"""

seite = seite.replace("%%DATEN%%", json.dumps(daten, ensure_ascii=False).replace("</", "<\\/"))

with open(seite_datei, "w", encoding="utf-8") as f:
    f.write(seite)
print("Seite gespeichert:", seite_datei)
