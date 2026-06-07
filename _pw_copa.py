import httpx
from playwright.sync_api import sync_playwright

URL = "https://seguiment-lliga-open.vercel.app"
print("status /copa:", httpx.get(URL + "/copa", timeout=20).status_code)

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2)
    errs = []
    pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
    pg.on("pageerror", lambda e: errs.append(f"PAGEERROR: {e}"))
    pg.goto(URL + "/copa", wait_until="networkidle")
    pg.wait_for_timeout(1800)
    print("phase chips + tabs (buttons):", pg.locator("button").count())
    print("group sections:", pg.locator("section").count())
    print("standings rows:", pg.locator("section ul li").count())
    print("nav has Copa:", "Copa" in pg.inner_text("header"))
    pg.screenshot(path="_copa_mobile.png")
    print("console errors:", "none" if not errs else errs[:6])
    b.close()
