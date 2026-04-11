"""
Deep-dive into bet365 and SI extraction.
Run: .venv/Scripts/python.exe inspect9.py
"""
import asyncio, sys, json
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

ACCESS_ID = "OGQ2ZTg0MGYtYjkwNS00ZmI1LTlkN2YtZDVmY2Y0ZDNkYmFl"

async def main():
    from playwright.async_api import async_playwright
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(channel="msedge", headless=True)

    # ── Bet365: inspect actual DOM structure ─────────────────────────────
    print("\n=== BET365 DOM STRUCTURE ===")
    ctx = await browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        locale="en-CA",
        geolocation={"latitude": 53.5461, "longitude": -113.4938, "accuracy": 50},
        permissions=["geolocation"],
    )
    page = await ctx.new_page()
    await page.goto("https://www.bet365.ca/en/sports/ice-hockey/", wait_until="domcontentloaded", timeout=30_000)
    await asyncio.sleep(5)

    # Look at the first fixture's full HTML
    result = await page.evaluate("""() => {
        const fixtures = document.querySelectorAll('[class*="cpm-ParticipantFixtureDetailsIceHockey"]');
        if (!fixtures.length) return {count: 0, html: ''};

        const f = fixtures[0];
        // Get the parent container row
        let container = f.parentElement;
        for (let i = 0; i < 5; i++) {
            const odds = container.querySelectorAll('[class*="cpm-ParticipantOdds"]');
            if (odds.length >= 2) break;
            container = container.parentElement;
        }

        return {
            count: fixtures.length,
            fixtureClasses: f.className,
            fixtureText: f.textContent.trim().slice(0, 200),
            // Check what team name elements look like
            nameEls: [...f.querySelectorAll('*')].slice(0, 20).map(e => ({
                tag: e.tagName, cls: e.className.slice(0, 60), text: e.textContent.trim().slice(0, 40)
            })),
            // odds in container
            oddsEls: [...container.querySelectorAll('[class*="cpm-ParticipantOdds"]')].slice(0, 4).map(e => ({
                cls: e.className.slice(0, 80),
                text: e.textContent.trim().slice(0, 20),
            })),
            containerClass: container.className.slice(0, 80),
        };
    }""")

    print(f"Fixture count: {result['count']}")
    print(f"First fixture classes: {result['fixtureClasses'][:100]}")
    print(f"First fixture text: {result['fixtureText']}")
    print(f"\nChildren of first fixture:")
    for el in result.get('nameEls', [])[:15]:
        if el['text']:
            print(f"  <{el['tag']}> cls='{el['cls']}' text='{el['text']}'")

    print(f"\nContainer class: {result['containerClass']}")
    print(f"Odds elements in container:")
    for o in result.get('oddsEls', []):
        print(f"  cls='{o['cls']}' text='{o['text']}'")

    # Try extracting with a fixed approach
    results = await page.evaluate("""() => {
        const out = [];
        const fixtures = document.querySelectorAll('[class*="cpm-ParticipantFixtureDetailsIceHockey"]');
        for (const f of Array.from(fixtures).slice(0, 3)) {
            // Get all text nodes / spans within fixture
            const allEls = [...f.querySelectorAll('*')].filter(e => e.children.length === 0 && e.textContent.trim());
            const texts = allEls.map(e => e.textContent.trim()).filter(Boolean);

            // Find adjacent odds element (sibling in parent)
            const parent = f.parentElement;
            const oddsInParent = [...parent.querySelectorAll('[class*="ParticipantOdds"], [class*="gl-Participant"]')]
                .map(e => e.textContent.trim());

            out.push({ fixtureTexts: texts.slice(0, 8), oddsInParent: oddsInParent.slice(0, 4) });
        }
        return out;
    }""")

    print("\n\nExtraction attempt on first 3 fixtures:")
    for i, r in enumerate(results):
        print(f"\nFixture {i+1}:")
        print(f"  texts: {r['fixtureTexts']}")
        print(f"  odds in parent: {r['oddsInParent']}")

    await ctx.close()

    # ── SI: find the correct sport ID ──────────────────────────────────
    print("\n\n=== SPORTS INTERACTION: Find NHL ===")
    ctxsi = await browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        locale="en-CA",
    )
    pagesi = await ctxsi.new_page()

    # Navigate to SI main sports page
    await pagesi.goto("https://www.sportsinteraction.com/en-ca/sports/", wait_until="domcontentloaded", timeout=25_000)
    await asyncio.sleep(4)
    body = await pagesi.evaluate("() => document.body.innerText.slice(0, 500)")
    print(f"SI sports page body:\n{body}")

    # Try the grid-view API to find hockey
    result2 = await pagesi.evaluate(f"""async () => {{
        const url = 'https://www.sportsinteraction.com/cds-api/bettingoffer/grid-view/all?x-bwin-accessid={ACCESS_ID}&lang=en-ca&country=CA&userCountry=CA&state=PreMatch&count=5&fixtureTypes=Standard';
        const r = await fetch(url);
        const text = await r.text();
        return {{ status: r.status, body: text.slice(0, 1000) }};
    }}""")
    print(f"\nGrid-view API: HTTP {result2['status']}")
    print(f"Body: {result2['body']}")

    # Try NHL-specific URL
    await pagesi.goto("https://www.sportsinteraction.com/en-ca/sports/nhl/", wait_until="domcontentloaded", timeout=25_000)
    await asyncio.sleep(6)
    title_nhl = await pagesi.title()
    print(f"\nNHL page title: {title_nhl}")
    body_nhl = await pagesi.evaluate("() => document.body.innerText.slice(0, 300)")
    print(f"NHL page body: {body_nhl}")

    # Intercept any API calls the NHL page makes
    result3 = await pagesi.evaluate(f"""async () => {{
        // Try various sport IDs for NHL
        const results = [];
        for (const sportId of [3, 4, 5, 6, 7, 8, 9, 10, 14, 15, 16]) {{
            const url = `https://www.sportsinteraction.com/cds-api/bettingoffer/fixtures?x-bwin-accessid={ACCESS_ID}&lang=en-ca&country=CA&userCountry=CA&fixtureTypes=Standard&state=PreMatch&count=5&sportId=${{sportId}}`;
            const r = await fetch(url);
            if (r.ok) {{
                const d = await r.json();
                const fixtures = d.fixtures || [];
                if (fixtures.length > 0) {{
                    const firstName = fixtures[0].name?.value || '';
                    results.push({{sportId, count: fixtures.length, firstName, hasOdds: (fixtures[0].optionMarkets?.length || 0) > 0}});
                }}
            }}
        }}
        return results;
    }}""")
    print(f"\nSport IDs with data:")
    for r in result3:
        print(f"  sportId={r['sportId']}: {r['count']} fixtures, first='{r['firstName']}', hasOdds={r['hasOdds']}")

    await ctxsi.close()
    await browser.close()
    await pw.stop()

asyncio.run(main())
