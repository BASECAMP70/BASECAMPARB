"""Get SI API fixture+odds structure and Bet365 actual odds DOM."""
import asyncio, json, sys, urllib.request
from playwright.async_api import async_playwright

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0"
SI_ACCESS_ID = "OGQ2ZTg0MGYtYjkwNS00ZmI1LTlkN2YtZDVmY2Y0ZDNkYmFl"

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="msedge", headless=True)

        # ── Sports Interaction: call API for NHL fixtures ─────────────
        print("=== SI CDS API — NHL fixtures ===")
        # Try sport-specific endpoint
        for endpoint in [
            f"https://www.sportsinteraction.com/cds-api/bettingoffer/fixture-view?x-bwin-accessid={SI_ACCESS_ID}&lang=en-ca&country=CA&usercountry=CA&fixtureTypes=Standard&state=Latest&offerMapping=Filtered&offerCategories=Gridable&categoryIDs=1000093862&subcategoryIDs=35&q=filters&sortBy=StartDate&fixtureCount=20",
            f"https://www.sportsinteraction.com/cds-api/offer-grouping/grid-view?x-bwin-accessid={SI_ACCESS_ID}&lang=en-ca&country=CA&usercountry=CA&sportId=35",
            f"https://www.sportsinteraction.com/cds-api/bettingoffer/grid-view?x-bwin-accessid={SI_ACCESS_ID}&lang=en-ca&country=CA&usercountry=CA&sportid=400&count=20",
        ]:
            ctx = await browser.new_context(user_agent=UA)
            page = await ctx.new_page()
            try:
                resp = await page.goto(endpoint, timeout=15_000)
                text = await page.content()
                # Extract json from <body>
                import re
                m = re.search(r'<body[^>]*>(.*)</body>', text, re.DOTALL)
                body = m.group(1).strip() if m else text
                data = json.loads(body)
                print(f"\nEndpoint: {endpoint[:80]}")
                if isinstance(data, list):
                    print(f"  List of {len(data)} items")
                    if data:
                        item = data[0]
                        print(f"  Item keys: {list(item.keys()) if isinstance(item, dict) else type(item)}")
                        print(f"  Sample: {json.dumps(item)[:500]}")
                elif isinstance(data, dict):
                    print(f"  Dict keys: {list(data.keys())}")
                    print(f"  Sample: {json.dumps(data)[:500]}")
            except Exception as e:
                print(f"  ERROR: {e}")
            finally:
                await ctx.close()

        # ── SI: Get full response from the working endpoint ──────────
        print("\n=== SI full grid-view all (sportId=400/hockey?) ===")
        ctx = await browser.new_context(user_agent=UA)
        page = await ctx.new_page()
        full_data = []
        async def capture(resp):
            if "cds-api" in resp.url and "grid-view/all" in resp.url:
                try:
                    full_data.append(await resp.json())
                except: pass
        page.on("response", capture)
        await page.goto("https://www.sportsinteraction.com/en-ca/sports-betting/ice-hockey/nhl/", wait_until="domcontentloaded", timeout=25_000)
        await asyncio.sleep(8)
        await ctx.close()

        if full_data:
            data = full_data[0]
            print(f"Sports in response: {len(data)}")
            # Find hockey (NHL)
            for sport in data:
                if isinstance(sport, dict):
                    sid = sport.get('sportId')
                    groups = sport.get('groups', [])
                    six_pack = sport.get('sixPackGroups', [])
                    print(f"  sportId={sid}: {len(groups)} groups, {len(six_pack)} sixPacks")
                    if six_pack:
                        sg = six_pack[0]
                        print(f"    sixPack[0]: {json.dumps(sg)[:400]}")

        # ── Bet365 — get actual odds values ─────────────────────────
        print("\n\n=== BET365 ODDS DOM ===")
        ctx2 = await browser.new_context(user_agent=UA, locale="en-CA")
        page2 = await ctx2.new_page()
        await page2.goto("https://www.bet365.ca", wait_until="domcontentloaded", timeout=25_000)
        await asyncio.sleep(8)

        result = await page2.evaluate("""() => {
            // Find fixture + odds in one hockey event
            const fixture = document.querySelector('.cpm-ParticipantFixtureDetailsIceHockey')
            if (!fixture) return {error: 'no fixture'}
            // The parent market row should have odds
            const row = fixture.closest('[class*="MarketGroup"], [class*="MarketRow"], [class*="Coupon"], .gl-Market_General')
            if (!row) return {error: 'no row', fixture: fixture.outerHTML.slice(0,300)}

            const teams = Array.from(row.querySelectorAll('[class*="Team"],[class*="team"],[class*="Participant"]'))
                .map(e => e.innerText.trim()).filter(t => t.length > 0 && t.length < 50).slice(0,4)
            const prices = Array.from(row.querySelectorAll('[class*="Price"],[class*="price"],[class*="odds"],[class*="Odds"],[class*="Btn"],[class*="btn"]'))
                .map(e => ({cls: e.className.slice(0,40), txt: e.innerText.trim().slice(0,15)}))
                .filter(e => e.txt.match(/\\d/)).slice(0,10)

            return {
                rowClass: row.className.slice(0,80),
                teams,
                prices,
                rowText: row.innerText.slice(0,300)
            }
        }""")
        print("Bet365 fixture row data:")
        print(json.dumps(result, indent=2))

        # Also try to find all fixtures with their odds
        all_fixtures = await page2.evaluate("""() => {
            const fixtures = document.querySelectorAll('.cpm-ParticipantFixtureDetailsIceHockey')
            return Array.from(fixtures).slice(0,5).map(f => {
                const teams = f.innerText.trim().split('\\n').filter(t => t.trim())
                const parent = f.parentElement
                // Look for odds buttons in the parent
                const btns = parent ? Array.from(parent.querySelectorAll('[class*="gl-Participant"],[class*="gl-Market"],[class*="Btn"]'))
                    .map(b => ({cls: b.className.split(' ').pop(), txt: b.innerText.trim().slice(0,10)}))
                    .filter(b => b.txt.match(/^\\d/)).slice(0,8) : []
                return {teams, btns}
            })
        }""")
        print("\nAll fixtures sample:")
        for f in all_fixtures:
            print(f"  Teams: {f['teams'][:4]}  |  Odds: {[b['txt'] for b in f['btns']]}")

        await ctx2.close()
        await browser.close()

asyncio.run(main())
