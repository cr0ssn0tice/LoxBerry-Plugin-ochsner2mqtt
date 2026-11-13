#!/usr/bin/env python3
"""Erzeugt die Screenshots für README und docs/ aus der Testumgebung (simulierte Anlage).

Voraussetzung: laufende Umgebung, z. B.
  O2M_SEED=1 LBSRC=<LoxBerry-Quellcode> tests/dev_env.sh start                     (Dashboard, Seiten)
  O2M_SEED=1 LBSRC=... ALARM_AFTER=4 tests/dev_env.sh start  + Aufruf mit "alarm"  (Störungsseite)
Aufruf: screenshots.py <zielordner> [all|alarm]
"""
import asyncio
import io
import sys
import time
import urllib.request
from pathlib import Path

from PIL import Image
from playwright.async_api import async_playwright

OUT = Path(sys.argv[1])
MODE = sys.argv[2] if len(sys.argv) > 2 else "all"
WEB = "http://127.0.0.1:18090/index.php?form="
OUT.mkdir(parents=True, exist_ok=True)


def save(png: bytes, name: str, max_w: int = 0) -> None:
    im = Image.open(io.BytesIO(png)).convert("RGB")
    if max_w and im.width > max_w:
        im = im.resize((max_w, round(im.height * max_w / im.width)), Image.LANCZOS)
    im.save(OUT / name, optimize=True)
    print(f"{name:28s} {im.width}x{im.height}  {(OUT / name).stat().st_size // 1024} KB")


async def page(br, width, height, dark=False, scale=2, lang=None):
    ctx = await br.new_context(viewport={"width": width, "height": height}, device_scale_factor=scale,
                               color_scheme="dark" if dark else "light", locale="de-DE")
    await ctx.add_init_script("try{localStorage.setItem('o2m-dark','%s')}catch(e){}" % ("1" if dark else "0"))
    pg = await ctx.new_page()
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.errors = errors
    pg.lang = f"&lang={lang}" if lang else ""
    return ctx, pg


async def go(pg, form, wait=5500):
    await pg.goto(WEB + form + pg.lang)
    await pg.wait_for_timeout(wait)


async def plant_gif(pg, name, frames=20, dur=1.25):
    """Fließanimation des Anlagenschemas als nahtlose Schleife (SMIL-Zeit gezielt gesetzt)."""
    card = pg.locator("ha-card.card-plant")
    imgs = []
    for i in range(frames):
        await pg.evaluate("""(t) => {
            const svg = document.querySelector('ochsner-heatpump-card').shadowRoot.querySelector('ha-card.card-plant svg');
            svg.pauseAnimations(); svg.setCurrentTime(t); }""", 100 + i * dur / frames)
        await pg.wait_for_timeout(40)
        imgs.append(Image.open(io.BytesIO(await card.screenshot())).convert("RGB"))
    w = 900
    imgs = [im.resize((w, round(im.height * w / im.width)), Image.LANCZOS) for im in imgs]
    pal = imgs[0].quantize(colors=128, method=Image.MEDIANCUT)
    frames_p = [im.quantize(palette=pal, dither=Image.NONE) for im in imgs]
    frames_p[0].save(OUT / name, save_all=True, append_images=frames_p[1:], duration=round(dur * 1000 / frames),
                     loop=0, optimize=True, disposal=1)
    print(f"{name:28s} {w}x{imgs[0].height}  {(OUT / name).stat().st_size // 1024} KB (GIF, {frames} Bilder)")


# Novembertag statt der Rohwerte der Simulation (sonst z. B. COP 9,7 bei 12 °C)
REALISTIC = {"hp.outdoor": 3.4, "hp.heat_output": 6.1, "hp.el_power": 1.58, "hp.flow": 34.6, "hp.return": 30.1,
             "hp.buffer_top": 33.8, "dhw.temp": 48.6, "hc1.flow_actual": 29.6, "hc1.flow_target": 29.4,
             "hc2.flow_actual": 32.4, "hc2.flow_target": 32.6}


def realistic():
    q = "&".join(f"{k}={v}" for k, v in REALISTIC.items())
    try:
        urllib.request.urlopen(f"http://127.0.0.1:18080/_mock/set?{q}", timeout=5).read()
        time.sleep(12)   # eine Abfrage des Dienstes abwarten
    except OSError as exc:
        print("Simulation nicht erreichbar:", exc)


async def main():
    realistic()
    async with async_playwright() as p:
        br = await p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
        if MODE == "alarm":
            ctx, pg = await page(br, 1280, 1000)
            await go(pg, "overview", 7000)
            save(await pg.locator("#o2m").screenshot(), "stoerungen.png", 2000)
            await ctx.close()
            await br.close()
            return

        # Dashboard (hell) – ganzes Plugin und einzelne Karten
        ctx, pg = await page(br, 1440, 1000)
        await go(pg, "app")
        save(await pg.locator("#o2m-app").screenshot(), "dashboard.png", 2200)
        for card, name in (("card-plant", "anlagenschema.png"), ("card-controls", "bedienung.png"),
                           ("card-schedule", "zeitprogramm.png"), ("card-curve", "heizkurve.png"),
                           ("card-energy", "energie.png")):
            save(await pg.locator(f"ha-card.{card}").screenshot(), name, 1400)
        await plant_gif(pg, "anlagenschema.gif")
        await ctx.close()

        # Einbettung in LoxBerry (Kopf, Menü, Seitenleiste) – Bildschirmausschnitt
        ctx, pg = await page(br, 1440, 900, scale=1.5)
        await go(pg, "app")
        save(await pg.screenshot(), "loxberry-integration.png", 2000)
        await ctx.close()

        # Handy, dunkel: zwei Bildschirme nebeneinander
        ctx, pg = await page(br, 390, 844, dark=True, scale=2)
        await go(pg, "app")
        shots = [await pg.screenshot()]
        await pg.evaluate("window.scrollTo(0, document.querySelector('ochsner-heatpump-card').getBoundingClientRect().top + window.scrollY + 1040)")
        await pg.wait_for_timeout(600)
        shots.append(await pg.screenshot())
        ims = [Image.open(io.BytesIO(s)).convert("RGB") for s in shots]
        gap = 60
        canvas = Image.new("RGB", (ims[0].width * 2 + gap * 3, ims[0].height + gap * 2), (240, 242, 245))
        for i, im in enumerate(ims):
            canvas.paste(im, (gap + i * (im.width + gap), gap))
        buf = io.BytesIO()
        canvas.save(buf, "PNG")
        save(buf.getvalue(), "handy-dunkel.png", 1300)
        await ctx.close()

        # Plugin-Seiten
        ctx, pg = await page(br, 1280, 1000)
        for form, name, clip_h in (("settings", "konfiguration.png", 0), ("log", "log.png", 0),
                                   ("loxone", "loxone.png", 1650), ("values", "alle-werte.png", 1100),
                                   ("edit", "experten-editor.png", 1100)):
            await go(pg, form, 5000)
            el = pg.locator("#o2m")
            if clip_h:
                box = await el.bounding_box()
                png = await pg.screenshot(full_page=True, clip={"x": box["x"], "y": box["y"], "width": box["width"],
                                                                 "height": min(box["height"], clip_h)})
            else:
                png = await el.screenshot()
            save(png, name, 2000)
        await ctx.close()

        # Englische Oberfläche (LoxBerry-Sprache Englisch)
        ctx, pg = await page(br, 1280, 900, scale=1.5, lang="en")
        await go(pg, "app")
        save(await pg.screenshot(), "english.png", 1600)
        print("Fehler im Browser:", pg.errors or "keine")
        await ctx.close()
        await br.close()

asyncio.run(main())
