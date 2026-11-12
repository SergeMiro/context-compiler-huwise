"""End-to-end check of the showcase in a real browser (local Chrome via Playwright, browser: local).
Usage: python3 scripts/e2e_site.py https://context-preprod.smiro.dev/   -> exit 1 on any failure."""
import asyncio
import sys

from playwright.async_api import async_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8799/"


async def main():
    bad = []
    async with async_playwright() as p:
        b = await p.chromium.launch(channel="chrome")
        for w, h in [(1440, 900), (1920, 1080), (390, 844)]:
            pg = await b.new_page(viewport={"width": w, "height": h})
            errs = []
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
            for path in ("", "en/"):
                await pg.goto(URL + path, wait_until="networkidle")
                sw, iw = await pg.evaluate("[document.documentElement.scrollWidth, innerWidth]")
                if sw > iw:
                    bad.append(f"{w}px {path or 'fr'}: horizontal scroll {sw} > {iw}")
            await pg.goto(URL, wait_until="networkidle")
            hidden = await pg.locator(".node.ours.hidden").count()
            await pg.click("[data-mode=ours]")
            shown = await pg.locator(".node.ours:not(.hidden)").count()
            if not (hidden == 2 and shown == 2):
                bad.append(f"{w}px: modes today/ours hidden={hidden} shown={shown}")
            await pg.click("[data-mode=trace]")
            if await pg.locator("#tsteps .tstep").count() == 0:
                bad.append(f"{w}px: no trace steps")
            await pg.locator("#architecture .node").first.focus()
            await pg.keyboard.press("Enter")
            if "Sources" not in await pg.inner_text("#panel"):
                bad.append(f"{w}px: keyboard selection did not open the panel")
            if errs:
                bad.append(f"{w}px console: {errs[:3]}")
        await b.close()
    print("browser: local ·", "OK" if not bad else "\n".join(bad))
    sys.exit(1 if bad else 0)

asyncio.run(main())
