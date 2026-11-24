import json
import math
import os
from datetime import datetime

import pandas as pd
import yfinance as yf

# =========================================================
# EINSTELLUNGEN
# =========================================================
aktien = ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "JPM", "KO", "XOM", "GLD", "BTC-USD"]
start_pro_aktie = 1000
gebuehr = 0.001

# Zwei Bots mit eigenem Spielgeld:
# - "Dein Bot":  Tageskerzen, Ø10 / Ø30, handelt nur am Tag der Kreuzung
# - "Turbo-Bot": Stundenkerzen, Ø5 / Ø20, ist im Markt, solange Ø5 über Ø20 liegt
BOTS = [
    {"name": "Dein Bot", "kerzen": "1d", "kurz": 10, "lang": 30, "trend": False,
     "zustand": "depot.json", "log": "depot_log.txt"},
    {"name": "Turbo-Bot", "kerzen": "1h", "kurz": 5, "lang": 20, "trend": True,
     "zustand": "turbo_std.json", "log": "turbo_std_log.txt"},
]

ordner = os.path.dirname(os.path.abspath(__file__))
BERLIN = "Europe/Berlin"


def schnitt(liste, ende, laenge):
    return sum(liste[ende - laenge + 1:ende + 1]) / laenge


def stueck_text(anzahl):
    return f"{anzahl:.6f}".rstrip("0").rstrip(".")


# Welche Kerzen sind schon abgeschlossen?
# Tageskerzen: Aktien ab 22:30 Uhr, Bitcoin erst am Folgetag.
# Stundenkerzen: sobald die Stunde vorbei ist.
jetzt = datetime.now()
heute = jetzt.strftime("%Y-%m-%d")
nach_boersenschluss = jetzt.hour * 60 + jetzt.minute >= 22 * 60 + 30
jetzt_berlin = pd.Timestamp.now(tz=BERLIN)

print("Lade Tageskurse für", len(aktien), "Aktien ...")
daten = {"1d": yf.download(aktien, period="6mo", auto_adjust=True, progress=False)}
if daten["1d"] is None or daten["1d"].empty:
    print("FEHLER: Keine Kursdaten bekommen. Versuch es später noch einmal.")
    raise SystemExit(1)
if any(b["kerzen"] == "1h" for b in BOTS):
    print("Lade Stundenkurse ...")
    try:
        daten["1h"] = yf.download(aktien, period="60d", interval="1h", auto_adjust=True, progress=False)
    except Exception as fehler:
        print("Stundenkurse nicht geladen:", fehler)
        daten["1h"] = None


def reihe(kerzen, t):
    """Liefert (Zeitpunkte, Schlusskurse, fertig?) für eine Aktie."""
    tabelle = daten.get(kerzen)
    if tabelle is None or tabelle.empty:
        return None
    try:
        serie = tabelle["Close"][t].dropna()
    except KeyError:
        return None
    kurse = [float(v) for v in serie.values]
    if kerzen == "1d":
        krypto = t.endswith("-USD")
        tage = [str(d.date()) for d in serie.index]
        fertig = [tag < heute or (tag == heute and nach_boersenschluss and not krypto) for tag in tage]
        return tage, kurse, fertig
    index = serie.index
    index = index.tz_localize("UTC") if index.tz is None else index
    index = index.tz_convert(BERLIN)
    zeiten = [d.strftime("%Y-%m-%d %H:%M") for d in index]
    fertig = [d + pd.Timedelta(hours=1) <= jetzt_berlin for d in index]
    return zeiten, kurse, fertig


def bot_laufen(bot):
    kurz, lang, trend = bot["kurz"], bot["lang"], bot["trend"]
    zustand_datei = os.path.join(ordner, bot["zustand"])
    log_datei = os.path.join(ordner, bot["log"])
    einheit = "Stunden" if bot["kerzen"] == "1h" else "Tages"

    # Stand laden oder neu anlegen
    if os.path.exists(zustand_datei):
        with open(zustand_datei, "r") as f:
            depot = json.load(f)
    else:
        depot = {}
    for t in aktien:
        if t not in depot:
            depot[t] = {"konto": start_pro_aktie, "anteile": 0.0, "letzter_tag": ""}

    print()
    print("=== " + bot["name"] + f" ({einheit}kerzen, Ø{kurz} / Ø{lang}) ===")
    neue_zeilen = []
    for t in aktien:
        r = reihe(bot["kerzen"], t)
        if r is None:
            print(t, ": keine Kursdaten bekommen, wird übersprungen")
            continue
        tage, kurse, fertig = r
        if len(kurse) <= lang:
            print(t, ": zu wenig Kursdaten, wird übersprungen")
            continue

        s = depot[t]
        if s["letzter_tag"] == "":
            # Erster Start: nur die letzte abgeschlossene Kerze verarbeiten
            zu_tun = [i for i in range(len(tage)) if fertig[i]][-1:]
        else:
            # Alle Kerzen seit dem letzten Start nachholen
            zu_tun = [i for i in range(len(tage)) if tage[i] > s["letzter_tag"] and fertig[i]]

        for i in zu_tun:
            if i < lang:
                continue
            preis = kurse[i]
            kurz_heute = schnitt(kurse, i, kurz)
            lang_heute = schnitt(kurse, i, lang)
            kurz_gestern = schnitt(kurse, i - 1, kurz)
            lang_gestern = schnitt(kurse, i - 1, lang)

            if trend:
                # Turbo: drin, solange der kurze Schnitt über dem langen liegt
                kaufen = kurz_heute > lang_heute
                verkaufen = kurz_heute < lang_heute
            else:
                # Dein Bot: nur am Tag der Kreuzung
                kaufen = kurz_gestern <= lang_gestern and kurz_heute > lang_heute
                verkaufen = kurz_gestern >= lang_gestern and kurz_heute < lang_heute

            aktion = "abwarten"
            if kaufen and s["anteile"] == 0:
                # Auch Bruchstücke kaufen (wie bei vielen Neobrokern), sonst wäre Bitcoin mit 1000 nicht möglich
                anzahl = math.floor(s["konto"] / (preis * (1 + gebuehr)) * 1e6) / 1e6
                if anzahl > 0:
                    s["konto"] = s["konto"] - anzahl * preis * (1 + gebuehr)
                    s["anteile"] = anzahl
                    aktion = "GEKAUFT " + stueck_text(anzahl)
            elif verkaufen and s["anteile"] > 0:
                s["konto"] = s["konto"] + s["anteile"] * preis * (1 - gebuehr)
                aktion = "VERKAUFT " + stueck_text(s["anteile"])
                s["anteile"] = 0.0

            s["letzter_tag"] = tage[i]
            gesamt = s["konto"] + s["anteile"] * preis
            zeile = (f"{tage[i]} | {t} | Kurs {preis:.2f} | {aktion} | Konto {s['konto']:.2f} | "
                     f"Anteile {stueck_text(s['anteile'])} | Gesamtwert {gesamt:.2f}")
            neue_zeilen.append(zeile)
            if aktion != "abwarten":
                print(">>>", zeile)

    with open(zustand_datei, "w") as f:
        json.dump(depot, f, indent=1)
    if neue_zeilen:
        with open(log_datei, "a", encoding="utf-8") as f:
            f.write("\n".join(neue_zeilen) + "\n")

    print(len(neue_zeilen), "neue Einträge verarbeitet.")
    if not neue_zeilen:
        print("Es gab keine neue abgeschlossene Kerze.")


for bot in BOTS:
    bot_laufen(bot)

print()
print("Jetzt seite_bauen.py starten, damit die Handy-Seite aktuell ist.")
