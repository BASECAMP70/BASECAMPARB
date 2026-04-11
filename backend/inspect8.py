"""
Quick diagnostic: check what bet365 and SI actually show in headless Playwright.
Run: .venv/Scripts/python.exe inspect8.py
"""
import asyncio, sys
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import json

ACCESS_ID = "OGQ2ZTg0MGYtYjkwNS00ZmI1LTlkN2YtZDVmY2Y0ZDNkYmFl"

async def main():
    from playwright.async_api import async_playwright
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(channel="msedge", headless=True)

    # ── Bet365 ──────────────────────────────────────────────────────────
    print("\n=== BET365 ===")
    ctx365 = await browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        locale="en-CA",
        geolocation={"latitude": 53.5461, "longitude": -113.4938, "accuracy": 50},
        permissions=["geolocation"],
    )
    page365 = await ctx365.new_page()
    await page365.goto("https://www.bet365.ca/en/sports/ice-hockey/", wait_until="domcontentloaded", timeout=30_000)
    await asyncio.sleep(5)
    title = await page365.title()
    print(f"Title: {title}")

    # Count key elements
    for sel in [
        '[class*="cpm-ParticipantFixtureDetailsIceHockey"]',
        '[class*="gl-MarketGroup"]',
        '[class*="cpm-ParticipantOdds"]',
        '[class*="cookie"]',
        '[class*="Cookie"]',
        '[class*="consent"]',
        'button',
    ]:
        count = await page365.locator(sel).count()
        print(f"  {sel}: {count}")

    # Grab first 500 chars of body text
    body_text = await page365.evaluate("() => document.body.innerText.slice(0, 600)")
    print(f"Body text:\n{body_text}")
    await ctx365.close()

    # ── Sports Interaction ─────────────────────────────────────────────
    print("\n=== SPORTS INTERACTION ===")
    ctxsi = await browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        locale="en-CA",
    )
    pagesi = await ctxsi.new_page()

    # Navigate to SI hockey page to get cookies, then call API from within the page
    await pagesi.goto("https://www.sportsinteraction.com/en-ca/sports-betting/ice-hockey/",
                      wait_until="domcontentloaded", timeout=30_000)
    await asyncio.sleep(6)
    title_si = await pagesi.title()
    print(f"Title: {title_si}")

    # Try CDS API from within page context (will have cookies)
    for sport_id in [4, 11, 13]:
        url = (f"https://www.sportsinteraction.com/cds-api/bettingoffer/fixtures"
               f"?x-bwin-accessid={ACCESS_ID}&lang=en-ca&country=CA&userCountry=CA"
               f"&fixtureTypes=Standard&state=PreMatch&count=20&sportId={sport_id}")
        result = await pagesi.evaluate(f"""async () => {{
            const r = await fetch({json.dumps(url)});
            const text = await r.text();
            return {{ status: r.status, body: text.slice(0, 500) }};
        }}""")
        fixtures_count = result['body'].count('"name"')
        print(f"  sportId={sport_id}: HTTP {result['status']} - body[:200]={result['body'][:200]!r}")

    # DOM check on SI
    for sel in ['[class*="ms-event"]', 'ms-event', '[class*="event-row"]', '[class*="EventRow"]']:
        count = await pagesi.locator(sel).count()
        print(f"  {sel}: {count}")

    body_si = await pagesi.evaluate("() => document.body.innerText.slice(0, 400)")
    print(f"Body text:\n{body_si}")
    await ctxsi.close()

    await browser.close()
    await pw.stop()

asyncio.run(main())
