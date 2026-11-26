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

# Zehn Bots mit eigenem Spielgeld (je einmal mit Tageskerzen und einmal mit Stundenkerzen):
# - "Dein Bot":    Long, Tageskerzen, Ø10 / Ø30, handelt nur am Tag der Kreuzung
# - "Turbo-Bot":   Long, Stundenkerzen, Ø5 / Ø20, im Markt, solange Ø5 über Ø20 liegt
# - "Short-Bot":   Short, Tageskerzen, Ø10 / Ø30, short, solange Ø10 unter Ø30 liegt
# - "Turbo-Short": Short, Stundenkerzen, Ø5 / Ø20, short, solange Ø5 unter Ø20 liegt
# - "Stop-Loss-Bot" / "Turbo-Stop": wie der Trend-Bot, verkauft aber sofort, wenn der Kurs
#   zu weit unter den Kaufkurs fällt (Tag 5 %, Stunde 2 %), und wartet dann auf einen neuen Trend
# - "Long-Short-Bot" / "Turbo-L/S": immer im Markt, long bei Aufwärtstrend, short bei Abwärtstrend
# - "Lern-Bot" / "Turbo-Lern": lernt aus seinen Fehlern und hat dafür zwei Stellschrauben:
#   1. Vorsicht: Nach einem Fehlkauf braucht er einen größeren Abstand zwischen den Durchschnitten,
#      nach Gewinnen wird er wieder mutiger.
#   2. Gewinn sichern: Hat er einen Gewinn wieder verschenkt, verkauft er beim nächsten Mal, sobald der Kurs
#      um den "Nachzug" vom Höchststand fällt. War das zu früh (Kurs steigt danach weiter), lockert er ihn wieder.
# Short heißt: Der Bot verkauft Aktien, die er sich leiht, und kauft sie später zurück.
# Fällt der Kurs dazwischen, macht er Gewinn, steigt er, macht er Verlust.
BOTS = [
    {"name": "Dein Bot", "kerzen": "1d", "kurz": 10, "lang": 30, "trend": False, "richtung": "long",
     "zustand": "depot.json", "log": "depot_log.txt"},
    {"name": "Turbo-Bot", "kerzen": "1h", "kurz": 5, "lang": 20, "trend": True, "richtung": "long",
     "zustand": "turbo_std.json", "log": "turbo_std_log.txt"},
    {"name": "Short-Bot", "kerzen": "1d", "kurz": 10, "lang": 30, "trend": True, "richtung": "short",
     "zustand": "short.json", "log": "short_log.txt"},
    {"name": "Turbo-Short", "kerzen": "1h", "kurz": 5, "lang": 20, "trend": True, "richtung": "short",
     "zustand": "turbo_short.json", "log": "turbo_short_log.txt"},
    {"name": "Stop-Loss-Bot", "kerzen": "1d", "kurz": 10, "lang": 30, "trend": True, "richtung": "long", "stop": 0.05,
     "zustand": "stop.json", "log": "stop_log.txt"},
    {"name": "Turbo-Stop", "kerzen": "1h", "kurz": 5, "lang": 20, "trend": True, "richtung": "long", "stop": 0.02,
     "zustand": "turbo_stop.json", "log": "turbo_stop_log.txt"},
    {"name": "Long-Short-Bot", "kerzen": "1d", "kurz": 10, "lang": 30, "trend": True, "richtung": "beide",
     "zustand": "ls.json", "log": "ls_log.txt"},
    {"name": "Turbo-L/S", "kerzen": "1h", "kurz": 5, "lang": 20, "trend": True, "richtung": "beide",
     "zustand": "turbo_ls.json", "log": "turbo_ls_log.txt"},
    {"name": "Lern-Bot", "kerzen": "1d", "kurz": 10, "lang": 30, "trend": True, "richtung": "long",
     "lernen": {"schritt": 0.5, "max": 3.0, "nachzug_start": 4.0, "nachzug_schritt": 0.5, "nachzug_min": 2.0, "nachzug_max": 6.0},
     "zustand": "lern.json", "log": "lern_log.txt"},
    {"name": "Turbo-Lern", "kerzen": "1h", "kurz": 5, "lang": 20, "trend": True, "richtung": "long",
     "lernen": {"schritt": 0.1, "max": 1.0, "nachzug_start": 1.0, "nachzug_schritt": 0.2, "nachzug_min": 0.4, "nachzug_max": 2.0},
     "zustand": "turbo_lern.json", "log": "turbo_lern_log.txt"},
]

ordner = os.path.dirname(os.path.abspath(__file__))
BERLIN = "Europe/Berlin"


def schnitt(liste, ende, laenge):
    return sum(liste[ende - laenge + 1:ende + 1]) / laenge


def komma(wert):
    return f"{wert:.2f}".rstrip("0").rstrip(".").replace(".", ",") if abs(wert) < 1 else f"{wert:.1f}".replace(".", ",")


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
    richtung = bot.get("richtung", "long")
    stop, lernen = bot.get("stop"), bot.get("lernen")
    print("=== " + bot["name"] + f" ({einheit}kerzen, Ø{kurz} / Ø{lang}, {richtung}) ===")
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
            ab = os.environ.get("NACHHOLEN_AB_" + bot["kerzen"].upper(), "")
            zu_tun = ([i for i in range(len(tage)) if fertig[i] and tage[i] >= ab] if ab
                      else [i for i in range(len(tage)) if fertig[i]][-1:])
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

            aktionen = []

            def kauf():
                anzahl = math.floor(s["konto"] / (preis * (1 + gebuehr)) * 1e6) / 1e6
                if anzahl > 0:
                    s["konto"] -= anzahl * preis * (1 + gebuehr)
                    s["anteile"] = anzahl
                    s["einstieg"] = preis
                    # Für den Lern-Bot merken, wie die Lage beim Kauf war
                    s["einstieg_tag"] = tage[i]
                    s["einstieg_abstand"] = round(abstand, 2)
                    s["hoechst"] = preis
                    aktionen.append("GEKAUFT " + stueck_text(anzahl))

            def verkauf(wort="VERKAUFT"):
                anzahl = s["anteile"]
                s["konto"] += anzahl * preis * (1 - gebuehr)
                s["anteile"] = 0.0
                aktionen.append(wort + " " + stueck_text(anzahl))
                if lernen:
                    lerne((preis * (1 - gebuehr)) / (s.get("einstieg") or preis) / (1 + gebuehr) - 1, wort)

            def short_rein():
                # Short: rein, wenn der Trend nach unten zeigt
                anzahl = math.floor(s["konto"] / (preis * (1 + gebuehr)) * 1e6) / 1e6
                if anzahl > 0:
                    s["konto"] += anzahl * preis * (1 - gebuehr)
                    s["anteile"] = -anzahl
                    s["einstieg"] = preis
                    aktionen.append("SHORT " + stueck_text(anzahl))

            def eindecken():
                anzahl = -s["anteile"]
                s["konto"] -= anzahl * preis * (1 + gebuehr)
                s["anteile"] = 0.0
                aktionen.append("GEDECKT " + stueck_text(anzahl))

            def mit_nachzug(n, j):
                # Wie wäre diese Runde mit einem Nachzug von n % ausgegangen?
                hoch_n = kurse[j]
                for m in range(j + 1, i + 1):
                    hoch_n = max(hoch_n, kurse[m])
                    if hoch_n / kurse[j] - 1 >= 2 * n / 100 and kurse[m] <= hoch_n * (1 - n / 100):
                        return (kurse[m] / kurse[j] - 1) * 100
                return None

            def lektion_merken(eintrag):
                s["lektionen"] = (s.get("lektionen", []) + [eintrag])[-25:]

            def lerne(ergebnis, wort="VERKAUFT"):
                # Aus Fehlern lernen: jede abgeschlossene Runde auswerten und je nach Fehlerart
                # die passende Stellschraube drehen
                stunden = bot["kerzen"] == "1h"
                einheit = "Stunden" if stunden else "Tage"
                alt, nz_alt = s.get("vorsicht", 0.0), s.get("nachzug")
                neu, nz_neu = alt, nz_alt
                einstieg = s.get("einstieg") or preis
                e_tag = s.get("einstieg_tag", tage[i])
                j = tage.index(e_tag) if e_tag in tage else i
                dauer = i - j
                spanne = kurse[j:i + 1] or [preis]
                hoch = (max(spanne) / einstieg - 1) * 100
                tief = (min(spanne) / einstieg - 1) * 100
                abst = s.get("einstieg_abstand", 0.0)
                erg = ergebnis * 100
                hebel, vermieden = "vorsicht", False
                if ergebnis < 0 and wort != "GESICHERT":
                    s["fehler"] = s.get("fehler", 0) + 1
                    if hoch >= max(abs(erg), 0.4 if stunden else 1.5):
                        # Gewinn verschenkt: Gewinne früher sichern
                        typ, hebel = "Gewinn verschenkt", "nachzug"
                        nz_neu = (lernen["nachzug_start"] if nz_alt is None
                                  else round(max(lernen["nachzug_min"], nz_alt - lernen["nachzug_schritt"]), 2))
                        warum = (f"Er lag zwischendurch {komma(hoch)} % im Plus, hat aber nicht verkauft. "
                                 f"Bis Ø{kurz} unter Ø{lang} gefallen war, war der Gewinn wieder weg.")
                        gelernt = (f"Er sichert Gewinne jetzt: War er {komma(2 * nz_neu)} % im Plus und fällt der Kurs danach {komma(nz_neu)} % unter den Höchststand, verkauft er."
                                   if nz_alt is None else
                                   f"Er sichert Gewinne jetzt früher: Nachzug {komma(nz_alt)} % → {komma(nz_neu)} %."
                                   if nz_neu < nz_alt else f"Sein Nachzug ist schon am engsten ({komma(nz_neu)} %).")
                        sim = mit_nachzug(nz_neu, j)
                        vermieden = sim is not None and sim > erg
                        gelernt += (f" Mit dieser Regel hätte er bei {'+' if sim >= 0 else ''}{komma(sim)} % verkauft statt {komma(erg)} %."
                                    if vermieden else " In dieser Runde hätte auch das nicht geholfen.")
                    else:
                        neu = round(min(lernen["max"], alt + lernen["schritt"]), 2)
                        if abs(erg) < (0.25 if stunden else 0.5):
                            typ = "Seitwärts"
                            warum = (f"Der Kurs kam kaum vom Fleck ({komma(erg)} %). Den Verlust haben vor allem "
                                     f"die Gebühren für Kauf und Verkauf gemacht.")
                        elif dauer <= 3 and abst < (0.3 if stunden else 1.5):
                            typ = "Fehlsignal"
                            warum = (f"Er hat gekauft, obwohl Ø{kurz} nur {komma(abst)} % über Ø{lang} lag. Der Aufwärtstrend "
                                     f"war also kaum zu erkennen und drehte schon nach {dauer} {einheit} wieder.")
                        else:
                            typ = "Trend zu Ende"
                            warum = (f"Der Kurs fiel nach dem Kauf um bis zu {komma(-tief)} % und kam nicht mehr über den "
                                     f"Kaufkurs. Als er gekauft hat, war der Aufwärtstrend schon fast vorbei.")
                        gelernt = (f"Er kauft diese Aktie jetzt erst ab {komma(neu)} % Abstand statt {komma(alt)} %."
                                   if neu > alt else f"Er ist bei dieser Aktie schon maximal vorsichtig ({komma(neu)} %).")
                        vermieden = abst <= neu
                        gelernt += (" Mit dieser Regel hätte er den Kauf nicht gemacht." if vermieden
                                    else " Diesen Kauf hätte er auch mit der neuen Regel gemacht.")
                else:
                    neu = round(max(0.0, alt - lernen["schritt"] / 2), 2)
                    s["treffer"] = s.get("treffer", 0) + 1
                    if wort == "GESICHERT":
                        typ = "Gewinn gesichert"
                        warum = (f"Er lag bis zu {komma(hoch)} % im Plus. Als der Kurs {komma(nz_alt)} % unter den Höchststand "
                                 f"fiel, hat er verkauft und {komma(erg)} % behalten.")
                    else:
                        typ = "Gewinn"
                        warum = f"Der Trend hat gehalten, er lag zwischendurch sogar {komma(hoch)} % im Plus."
                    gelernt = (f"Etwas mutiger: Er kauft jetzt schon ab {komma(neu)} % Abstand." if neu < alt
                               else "Regeln bleiben gleich.")
                    if wort == "GESICHERT" and ergebnis < 0:
                        neu = alt
                        gelernt = "Regeln bleiben gleich. Den kleinen Rest haben die Gebühren gefressen."
                s["vorsicht"], s["nachzug"] = neu, nz_neu
                lektion_merken({
                    "von": e_tag, "bis": tage[i], "kauf": round(einstieg, 4), "verkauf": round(preis, 4),
                    "erg": round(erg, 2), "dauer": dauer, "hoch": round(hoch, 2), "tief": round(tief, 2),
                    "abstand": abst, "vorher": alt, "nachher": neu, "nz_vorher": nz_alt, "nz_nachher": nz_neu,
                    "hebel": hebel, "typ": typ, "warum": warum, "gelernt": gelernt, "vermieden": vermieden})

            abstand = (kurz_heute - lang_heute) / lang_heute * 100
            if richtung == "short":
                if verkaufen and s["anteile"] == 0:
                    short_rein()
                elif kaufen and s["anteile"] < 0:
                    eindecken()
            elif richtung == "beide":
                # Long-Short: immer auf der Seite des Trends
                if kaufen and s["anteile"] <= 0:
                    if s["anteile"] < 0:
                        eindecken()
                    kauf()
                elif verkaufen and s["anteile"] >= 0:
                    if s["anteile"] > 0:
                        verkauf()
                    short_rein()
            else:
                nz = s.get("nachzug") if lernen else None
                if s["anteile"] > 0:
                    s["hoechst"] = max(s.get("hoechst", s.get("einstieg", preis)), preis)
                g = s.get("gesichert") if lernen else None
                if g and s["anteile"] == 0 and nz and preis >= g["preis"] * (1 + nz / 100) and kaufen:
                    # Zu früh gesichert: Der Kurs ist danach deutlich weiter gestiegen -> Nachzug lockern
                    nz_neu = round(min(lernen["nachzug_max"], nz + lernen["nachzug_schritt"]), 2)
                    weiter = (preis / g["preis"] - 1) * 100
                    s["fehler"] = s.get("fehler", 0) + 1
                    lektion_merken({
                        "von": g["tag"], "bis": tage[i], "kauf": g["preis"], "verkauf": round(preis, 4),
                        "erg": round(-weiter, 2), "dauer": i - tage.index(g["tag"]) if g["tag"] in tage else 0,
                        "hoch": round(weiter, 2), "tief": 0.0, "abstand": round(abstand, 2),
                        "vorher": s.get("vorsicht", 0.0), "nachher": s.get("vorsicht", 0.0),
                        "nz_vorher": nz, "nz_nachher": nz_neu, "hebel": "nachzug", "typ": "Zu früh gesichert",
                        "warum": (f"Er hat den Gewinn gesichert, aber der Trend lief weiter. "
                                  f"Der Kurs stieg danach noch um {komma(weiter)} %, das hat er verpasst."),
                        "gelernt": (f"Er lässt Gewinnen jetzt mehr Luft: Nachzug {komma(nz)} % → {komma(nz_neu)} %. "
                                    f"Weil der Trend noch läuft, steigt er wieder ein." if nz_neu > nz else
                                    f"Sein Nachzug ist schon am weitesten ({komma(nz)} %). Er steigt wieder ein."),
                        "vermieden": False})
                    s["nachzug"] = nz = nz_neu
                    s["gesperrt"] = False
                    s.pop("gesichert", None)
                if stop and s["anteile"] > 0 and preis <= s.get("einstieg", preis) * (1 - stop):
                    # Stop-Loss: Verlust begrenzen und erst beim nächsten neuen Aufwärtstrend wieder rein
                    verkauf("STOPP")
                    s["gesperrt"] = True
                elif (nz and s["anteile"] > 0 and s["hoechst"] / s["einstieg"] - 1 >= 2 * nz / 100
                      and preis <= s["hoechst"] * (1 - nz / 100)):
                    # Gewinn sichern: Kurs ist um den Nachzug vom Höchststand gefallen
                    verkauf("GESICHERT")
                    s["gesperrt"] = True
                    s["gesichert"] = {"tag": tage[i], "preis": round(preis, 4)}
                elif verkaufen and s["anteile"] > 0:
                    verkauf()
                elif kaufen and s["anteile"] == 0 and not s.get("gesperrt") and (not lernen or abstand > s.get("vorsicht", 0.0)):
                    kauf()
                if verkaufen:
                    s["gesperrt"] = False
                    s.pop("gesichert", None)

            s["letzter_tag"] = tage[i]
            anteile_text = ("-" if s["anteile"] < 0 else "") + stueck_text(abs(s["anteile"]))
            gesamt = s["konto"] + s["anteile"] * preis
            for aktion in aktionen or ["abwarten"]:
                zeile = (f"{tage[i]} | {t} | Kurs {preis:.2f} | {aktion} | Konto {s['konto']:.2f} | "
                         f"Anteile {anteile_text} | Gesamtwert {gesamt:.2f}")
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
