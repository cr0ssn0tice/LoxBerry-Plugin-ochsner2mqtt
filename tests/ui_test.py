#!/usr/bin/env python3
"""Browser-Test der App-Oberfläche (Playwright + Chrome) gegen tests/dev_env.sh.

Klickt Bedienelemente wie ein Nutzer und prüft, welche Schreibzugriffe beim
simulierten Regler ankommen. Screenshots landen in $SHOTS (Standard /tmp/o2m-shots).
"""

import asyncio
import json
import os
import sys
import urllib.request
from pathlib import Path

from playwright.async_api import async_playwright

URL = "http://127.0.0.1:18090/index.php?form=app"
T = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/o2m-dev")
SHOTS = Path(os.environ.get("SHOTS", "/tmp/o2m-shots"))
SHOTS.mkdir(parents=True, exist_ok=True)
CHROME = os.environ.get("CHROME", "/usr/bin/google-chrome")
ok = True


def check(cond, label):
    global ok
    print(("PASS " if cond else "FAIL ") + label)
    ok &= bool(cond)


def writes():
    return json.loads(urllib.request.urlopen("http://127.0.0.1:18080/_mock/writes").read())


async def main():
    async with async_playwright() as p:
        br = await p.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])
        pg = await br.new_page(viewport={"width": 1280, "height": 1500})
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        await pg.goto(URL)
        await pg.wait_for_timeout(6000)
        await pg.screenshot(path=str(SHOTS / "app_desktop.png"), full_page=True)
        check(await pg.locator("svg.plant").count() >= 1, "Anlagenschema gerendert")
        check(await pg.locator(".circuit[data-key=hc1]").count() == 1, "Heizkreis-Kacheln gerendert")

        async def act(label, sel, clicks=1, wait=4500, expect=1):
            before = len(writes())
            for _ in range(clicks):
                await pg.locator(sel).first.click()
                await pg.wait_for_timeout(300)
            await pg.wait_for_timeout(wait)
            new = writes()[before:]
            check(len(new) == expect, f"{label}: {len(new)} Schreibzugriff(e) {new}")

        await act("HK1 Eco", 'button[data-act=preset][data-c="1"][data-v="eco"]')
        check("Eco" in await pg.locator(".circuit[data-key=hc1] .sub").first.inner_text(), "HK1 zeigt Eco")
        await act("Nacht-Soll 2× + (zusammengefasst)",
                  'button[data-act=spstep][data-c="1"][data-k=setpoint_reduced_heat][data-s="1"]', clicks=2)
        await act("HK1 Komfort", 'button[data-act=preset][data-c="1"][data-v="comfort"]')
        await act("Warmwasser Eco", 'button[data-act=dhwmode][data-v="eco"]')
        await act("Warmwasser Boost", 'button[data-act=boost]')
        await act("Wärmepumpe Aus – erster Klick nur scharf", 'button[data-act=hp][data-v="3"]', wait=600, expect=0)
        await act("Wärmepumpe Aus – Bestätigung", 'button[data-act=hp][data-v="3"]')
        await act("Wärmepumpe Auto", 'button[data-act=hp][data-v="0"]')

        # Zeitprogramm: Montag Ende 22:00 -> 21:30
        before = len(writes())
        await pg.locator('.drow[data-act=tprow][data-d="0"]').first.click()
        await pg.wait_for_timeout(800)
        inp = pg.locator('input[data-act=tptime][data-i="0"][data-edge="e"]').first
        await inp.fill("21:30")
        await inp.dispatch_event("change")
        await pg.wait_for_timeout(400)
        await pg.locator("button[data-act=tpapply]").first.click()
        await pg.wait_for_timeout(5000)
        new = writes()[before:]
        check(len(new) == 1 and new[0]["value"] == str(21 | (30 << 8)), f"Zeitprogramm: genau ein geänderter Schaltpunkt {new}")

        # Heizkurve: Heizgrenze per Tastatur verschieben und übernehmen
        before = len(writes())
        await pg.locator('svg g[data-h="heat_limit"]').first.focus()
        await pg.keyboard.press("ArrowLeft")
        await pg.keyboard.press("ArrowLeft")
        await pg.wait_for_timeout(500)
        await pg.locator("button[data-cact=apply]").first.click()
        await pg.wait_for_timeout(5000)
        new = writes()[before:]
        check(len(new) == 1, f"Heizkurve: Heizgrenze geschrieben {new}")

        # Detaildialog
        await pg.locator(".circuit[data-key=hc1] button.hcname").first.click()
        await pg.wait_for_timeout(1200)
        check(await pg.locator("dialog.o2m-more[open]").count() == 1, "Detaildialog öffnet")
        await pg.screenshot(path=str(SHOTS / "dialog.png"))
        await pg.keyboard.press("Escape")

        # Schreibsperre: Klick zeigt verständlichen Fehler
        cfgp = T / "cfg/ochsner2mqtt.json"
        cfg = json.loads(cfgp.read_text())
        cfg["writes_enabled"] = False
        cfgp.write_text(json.dumps(cfg))
        await pg.wait_for_timeout(7000)
        check("Bedienung gesperrt" in await pg.locator("[data-o2m=status]").inner_text(), "Statusleiste zeigt Sperre")
        before = len(writes())
        await pg.locator('button[data-act=preset][data-c="2"][data-v="eco"]').first.click()
        await pg.wait_for_timeout(2500)
        toasts = await pg.locator(".o2m-toast").all_inner_texts()
        check(len(writes()) == before and any("gesperrt" in t for t in toasts), "Gesperrt: nichts geschrieben, Hinweis angezeigt")
        cfg["writes_enabled"] = True
        cfgp.write_text(json.dumps(cfg))

        # Mobil, dunkel
        ctx = await br.new_context(viewport={"width": 400, "height": 900}, color_scheme="dark")
        mp = await ctx.new_page()
        await mp.goto(URL)
        await mp.wait_for_timeout(6000)
        await mp.screenshot(path=str(SHOTS / "app_mobile_dark.png"), full_page=True)
        check(await mp.locator("#o2m-app.o2m-dark").count() == 1, "Dunkle Darstellung auf dem Handy")
        await ctx.close()
        check(not errs, f"Keine JavaScript-Fehler {errs}")
        await br.close()


asyncio.run(main())
print("\nERGEBNIS:", "ALLES OK" if ok else "FEHLER")
sys.exit(0 if ok else 1)
