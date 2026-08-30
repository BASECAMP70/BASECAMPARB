"""Capture full SI CDS API URL + Bet365 DOM structure."""
import asyncio, json, sys
from playwright.async_api import async_playwright

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0"

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="msedge", headless=True)

        # ── Sports Interaction CDS API ───────────────────────────────
        print("\n=== SPORTS INTERACTION ===")
        ctx = await browser.new_context(user_agent=UA, locale="en-CA")
        page = await ctx.new_page()
        cds_responses = []

        async def si_resp(resp):
            if "cds-api" in resp.url:
                try:
                    data = await resp.json()
                    cds_responses.append({"url": resp.url, "data": data})
                except:
                    pass

        page.on("response", si_resp)
        await page.goto("https://www.sportsinteraction.com/en-ca/sports-betting/ice-hockey/nhl/",
                        wait_until="domcontentloaded", timeout=25_000)
        await asyncio.sleep(7)

        print(f"CDS calls captured: {len(cds_responses)}")
        for r in cds_responses[:3]:
            print(f"\nURL: {r['url']}")
            # Show first item structure
            data = r['data']
            if isinstance(data, list) and data:
                item = data[0]
                print("First item keys:", list(item.keys()) if isinstance(item, dict) else type(item))
                if isinstance(item, dict):
                    # Show markets/groups
                    if 'groups' in item:
                        g = item['groups'][0] if item['groups'] else {}
                        print("Group sample:", json.dumps(g)[:400])
                    elif 'markets' in item:
                        print("Markets sample:", json.dumps(item['markets'])[:400])
                    else:
                        print("Item sample:", json.dumps(item)[:400])
            elif isinstance(data, dict):
                print("Keys:", list(data.keys()))
                print("Sample:", json.dumps(data)[:400])

        await ctx.close()

        # ── Bet365 DOM ───────────────────────────────────────────────
        print("\n\n=== BET365 DOM ===")
        ctx2 = await browser.new_context(user_agent=UA, locale="en-CA")
        page2 = await ctx2.new_page()
        await page2.goto("https://www.bet365.ca", wait_until="domcontentloaded", timeout=25_000)
        await asyncio.sleep(8)

        result = await page2.evaluate("""() => {
            // Try to find actual game rows
            const selectors = [
                '.cpm-ParticipantFixtureDetailsIceHockey',
                '.gl-MarketRow',
                '.gl-Market_General',
                '[class*="Fixture"]',
                '[class*="Participant"]',
                '[class*="EventRow"]',
            ]
            const found = []
            for (const sel of selectors) {
                const els = document.querySelectorAll(sel)
                if (els.length > 0) {
                    found.push({
                        sel,
                        count: els.length,
                        sample: els[0].innerText.slice(0, 200)
                    })
                }
            }
            return found
        }""")
        print("Bet365 selectors found:")
        for f in result:
            print(f"  {f['sel']}: {f['count']} els → {repr(f['sample'][:100])}")

        # Also try hockey page
        await page2.goto("https://www.bet365.ca/en/sports/ice-hockey/", wait_until="domcontentloaded", timeout=25_000)
        await asyncio.sleep(6)
        result2 = await page2.evaluate("""() => {
            const body = document.body.innerText.slice(0, 500)
            const fixtures = document.querySelectorAll('[class*="Fixture"], [class*="fixture"]')
            const markets = document.querySelectorAll('[class*="Market"], [class*="market"]')
            return {body: body.slice(0,200), fixtures: fixtures.length, markets: markets.length,
                    url: window.location.href}
        }""")
        print(f"\nBet365 hockey page: {result2}")

        await ctx2.close()
        await browser.close()

asyncio.run(main())
