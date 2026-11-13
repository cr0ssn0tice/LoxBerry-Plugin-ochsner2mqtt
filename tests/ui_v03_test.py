#!/usr/bin/env python3
"""Browser-Test v0.3: Anlagenschema (geschlossene Kreise, Puffer, synchrone Animation),
Spaltenausgleich, Konfigurationsseite (Ausrichtung), Loxone-Seite (Gateway V2).

Voraussetzung: tests/dev_env.sh start mit MOCK_ARGS="--profile 208buf" (Gateway V2).
"""
import asyncio
import json
import os
import sys
import urllib.request
from pathlib import Path

from playwright.async_api import async_playwright

BASE = "http://127.0.0.1:18090/index.php?form="
T = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/o2m-dev")
CHROME = os.environ.get("CHROME", "/usr/bin/google-chrome")
ok = True


def check(cond, label):
    global ok
    print(("PASS " if cond else "FAIL ") + label)
    ok &= bool(cond)


def mock_set(**kw):
    urllib.request.urlopen("http://127.0.0.1:18080/_mock/set?" + "&".join(f"{k}={v}" for k, v in kw.items())).read()


PLANT_JS = """() => {
  const root = document.querySelector('ochsner-heatpump-card').shadowRoot;
  const svg = root.querySelector('svg.plant');
  const flows = [...svg.querySelectorAll('path.flowing')];
  const pts = (d) => d.replace(/[ML]/g, ' ').trim().split(/\\s+/).map(Number);
  return {
    text: svg.textContent,
    flows: flows.map(p => ({ d: p.getAttribute('d'), color: p.getAttribute('stroke'), anim: !!p.querySelector('animate'),
                             off: parseFloat(getComputedStyle(p).strokeDashoffset) })),
    narrow: svg.classList.contains('narrow'),
  };
}"""


async def plant(pg):
    return await pg.evaluate(PLANT_JS)


async def main():
    async with async_playwright() as p:
        br = await p.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])
        pg = await br.new_page(viewport={"width": 1280, "height": 1400})
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        await pg.goto(BASE + "app")
        await pg.wait_for_timeout(6000)

        # --- Schema: Heizen, Puffer über Fühler, ein Heizkreis
        s = await plant(pg)
        check("Puffer" in s["text"] and "33,4" in s["text"], "Puffer mit Temperatur im Schema")
        check(len(s["flows"]) >= 4 and all(f["anim"] for f in s["flows"]), "Aktive Leitungen animiert (SMIL)")
        ends = {tuple(map(float, f["d"].replace("M", " ").replace("L", " ").split()[-2:])) for f in s["flows"]}
        starts = {tuple(map(float, f["d"].replace("M", " ").replace("L", " ").split()[:2])) for f in s["flows"]}
        # jeder Rücklauf endet an einem Vorlauf-Anfang (WP oder Puffer): kein loses Leitungsende
        hp_out = min(starts, key=lambda xy: xy[0])
        check(any(abs(e[0] - hp_out[0]) < 0.5 for e in ends), "Rücklauf endet an der Wärmepumpe (geschlossener Kreis)")
        # Phasengleichheit: alle Vorläufe ab derselben Quelle haben dieselbe Strichphase
        by_start = {}
        for f in s["flows"]:
            by_start.setdefault(f["d"].split(" L")[0], set()).add(round(f["off"], 1))
        check(all(len(v) == 1 for v in by_start.values()), "Gleiche Quelle → gleiche Phase (keine Sprünge)")
        a = (await plant(pg))["flows"][0]["off"]
        await pg.wait_for_timeout(400)
        b = (await plant(pg))["flows"][0]["off"]
        check(abs(a - b) > 1, f"Animation läuft ({a:.1f} → {b:.1f})")

        # --- Warmwasserladung: Weg über die Wendel, Heizkreise laufen aus dem Puffer weiter
        mock_set(**{"hp.status": 3, "hp.dhw_valve": 1})
        await pg.wait_for_timeout(17000)
        s = await plant(pg)
        cols = [f["color"] for f in s["flows"]]
        check(any("dhw" in c for c in cols), "WW-Ladung: Leitung zum Speicher aktiv")
        check(any("heat" in c for c in cols), "WW-Ladung: Heizkreis läuft aus dem Puffer weiter")
        check("lädt" in s["text"], "WW-Ladung im Schema beschriftet")
        mock_set(**{"hp.status": 1, "hp.dhw_valve": 0})

        # --- Spaltenausgleich: Energie-Karte steht in der Spalte, die die Gesamthöhe minimiert
        res = await pg.evaluate("""async () => {
          const card = document.querySelector('ochsner-heatpump-card');
          const r = card.shadowRoot;
          const [left, right] = r.querySelectorAll('.bc > .col');
          const energy = r.querySelector('ha-card.card-energy');
          r.querySelector('ha-card.card-schedule').hidden = true;
          card._balance();
          await new Promise(res => setTimeout(res, 50));
          const now = Math.max(left.offsetHeight, right.offsetHeight);
          const other = energy.parentElement === left ? right : left;
          const home = energy.parentElement;
          other.appendChild(energy);
          const alt = Math.max(left.offsetHeight, right.offsetHeight);
          home.appendChild(energy);
          return { now, alt };
        }""")
        check(res["now"] <= res["alt"] + 40, f"Energie-Karte in der günstigeren Spalte ({res['now']} px statt {res['alt']} px)")

        # --- Handy: schmales Layout
        mp = await br.new_page(viewport={"width": 390, "height": 900})
        await mp.goto(BASE + "app")
        await mp.wait_for_timeout(5500)
        s = await plant(mp)
        check(s["narrow"] and "Puffer" in s["text"], "Schmales Schema auf dem Handy")
        await mp.close()

        # --- Konfiguration (LoxBerry-Formularzeilen): Feld und Hinweis bündig, Beschriftung links davon
        await pg.goto(BASE + "settings")
        await pg.wait_for_timeout(1500)
        geo = await pg.evaluate("""() => [...document.querySelectorAll('.o2m-form .lb-form-row')].map(r => {
            const l = r.querySelector('.lb-form-label').getBoundingClientRect();
            const f = r.querySelector('.lb-form-field').getBoundingClientRect();
            const i = r.querySelector('.lb-form-field .lb-input, .lb-form-field .lb-toggle, .lb-form-field .lb-btn');
            const h = r.querySelector('.lb-form-help');
            const hs = h ? parseFloat(getComputedStyle(h).paddingLeft) : 0;
            return { l: l.right, f: f.left, i: i ? i.getBoundingClientRect().left : null,
                     h: h ? h.getBoundingClientRect().left + hs : null };
          })""")
        aligned = all(g["i"] is not None and abs(g["i"] - g["f"]) < 1.5 and (g["h"] is None or abs(g["h"] - g["f"]) < 1.5) and g["l"] <= g["f"]
                      for g in geo)
        check(len(geo) >= 14 and aligned, f"Konfiguration: {len(geo)} Zeilen sauber ausgerichtet")
        check("Puffer wird angezeigt" in await pg.inner_text("#buf-detect"), "Konfiguration zeigt Puffer-Erkennung")
        check(await pg.locator("#cfg-conn .badge").inner_text() in ("● verbunden",), "Verbindungsstatus auf der Konfigurationsseite")

        # --- Loxone: Gateway V2, Basis-Auswahl eintragen
        await pg.goto(BASE + "loxone")
        await pg.wait_for_timeout(2500)
        pg.on("dialog", lambda d: asyncio.ensure_future(d.accept()))
        await pg.click('button:has-text("Basis-Auswahl")')
        n_sel = await pg.locator("input[data-lx]:checked").count()
        await pg.click('button:has-text("Im MQTT Gateway eintragen")')
        await pg.wait_for_timeout(1500)
        subs = json.loads((T / "lbhome/config/system/subscriptions.json").read_text())["Subscriptions"]
        ours = [x["Id"] for x in subs if x["Id"].startswith("ochsner/")]
        check(n_sel >= 10 and len(ours) == n_sel, f"Basis-Auswahl ({n_sel} Topics) im Gateway eingetragen")
        check("ochsner/plant/hc1/room_target" in ours and "shelly/bulb/state" in [x["Id"] for x in subs], "Raumsoll dabei, fremdes Abo erhalten")
        check("Topics werden an den Miniserver gesendet" in await pg.inner_text("#lx-gw"), "Status zeigt eingetragene Topics")

        # --- übrige Seiten ohne JS-Fehler
        for f in ("overview", "values", "edit", "log"):
            await pg.goto(BASE + f)
            await pg.wait_for_timeout(1200)
        check(not errs, f"Keine JavaScript-Fehler {errs[:3]}")
        await br.close()
    print("\nERGEBNIS:", "ALLES OK" if ok else "FEHLER")
    sys.exit(0 if ok else 1)


asyncio.run(main())
