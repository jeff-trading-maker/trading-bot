# Schickt Push-Nachrichten aufs Handy (über die kostenlose App ntfy).
# "python melden.py vorher"  merkt sich, wie lang die Logs sind
# "python melden.py nachher" meldet alle neuen Käufe und Verkäufe
# "python melden.py fehler"  meldet, dass der Lauf nicht geklappt hat
import json
import os
import sys
import urllib.request

LOGS = {"depot_log.txt": "Dein Bot", "turbo_std_log.txt": "Turbo"}
NAMEN = {"AAPL": "Apple", "MSFT": "Microsoft", "NVDA": "Nvidia", "GOOGL": "Google", "AMZN": "Amazon",
         "JPM": "JPMorgan", "KO": "Coca-Cola", "XOM": "Exxon", "GLD": "Gold", "BTC-USD": "Bitcoin"}
STAND = "log_stand.tmp"
ordner = os.path.dirname(os.path.abspath(__file__))


def zeilen(datei):
    pfad = os.path.join(ordner, datei)
    if not os.path.exists(pfad):
        return []
    with open(pfad, encoding="utf-8") as f:
        return [z.strip() for z in f if z.strip()]


def senden(titel, text, tags):
    thema = os.environ.get("NTFY_TOPIC", "").strip()
    if not thema:
        print("Kein NTFY_TOPIC eingerichtet, keine Push-Nachricht:", titel)
        return
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    daten = {"topic": thema, "title": titel, "message": text, "tags": tags}
    if "/" in repo:
        besitzer, name = repo.split("/", 1)
        daten["click"] = f"https://{besitzer.lower()}.github.io/{name}/"
    anfrage = urllib.request.Request("https://ntfy.sh/", data=json.dumps(daten).encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(anfrage, timeout=20)
        print("Push gesendet:", titel)
    except Exception as fehler:
        print("Push nicht gesendet:", fehler)


def zahl(text):
    return text.replace(",", "X").replace(".", ",").replace("X", ".")


modus = sys.argv[1] if len(sys.argv) > 1 else ""
if modus == "vorher":
    with open(os.path.join(ordner, STAND), "w") as f:
        json.dump({d: len(zeilen(d)) for d in LOGS}, f)
elif modus == "nachher":
    try:
        with open(os.path.join(ordner, STAND)) as f:
            alt = json.load(f)
    except Exception:
        alt = {}
    for datei, bot in LOGS.items():
        for zeile in zeilen(datei)[alt.get(datei, 0):]:
            teile = zeile.split(" | ")
            if len(teile) < 7 or teile[3] == "abwarten":
                continue
            art, stueck = teile[3].split()[0], teile[3].split()[1]
            name = NAMEN.get(teile[1], teile[1])
            kurs = float(teile[2].replace("Kurs", "").strip())
            kauf = art == "GEKAUFT"
            senden(f"{bot}: {name} {'gekauft' if kauf else 'verkauft'}",
                   f"{zahl(stueck)} Stück zu {zahl(f'{kurs:,.2f}')} $ ({teile[0][8:10]}.{teile[0][5:7]}."
                   + (f" {teile[0][11:16]} Uhr)" if len(teile[0]) > 10 else ")"),
                   ["chart_with_upwards_trend" if kauf else "money_with_wings"])
elif modus == "fehler":
    senden("Bot-Lauf hat nicht geklappt",
           "Heute Abend ist beim Bot etwas schiefgegangen, zum Beispiel weil keine Kurse geladen werden konnten. "
           "Dein Depot ist unverändert. Der nächste Lauf holt alles nach.", ["warning"])
