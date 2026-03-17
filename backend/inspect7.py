"""Inspector 7: Simple URL checks and SI response interception."""
import asyncio, json, sys
from playwright.async_api import async_playwright

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0"
SI_ACCESSID = "OGQ2ZTg0MGYtYjkwNS00ZmI1LTlkN2YtZDVmY2Y0ZDNkYmFl"
GEO = {"latitude": 53.5461, "longitude": -113.4938, "accuracy": 50}


async def check_si(browser):
    """Load SI hockey page via response interception."""
    print("=== SI: RESPONSE INTERCEPTION ===")
    ctx = await browser.new_context(user_agent=UA, locale="en-CA")
    page = await ctx.new_page()
    captured = []

    async def on_resp(resp):
        ct = resp.headers.get("content-type", "")
        if "json" in ct and "sportsinteraction" in resp.url:
            if "cds-api" in resp.url:
                try:
                    data = await resp.json()
                    captured.append({"url": resp.url[:150], "sample": json.dumps(data)[:600]})
                except:
                    pass

    page.on("response", on_resp)
    try:
        await page.goto("https://www.sportsinteraction.com/en-ca/sports-betting/ice-hockey/nhl/",
                        wait_until="domcontentloaded", timeout=30_000)
    except Exception as e:
        print(f"  goto error: {e}")

    await asyncio.sleep(12)

    print(f"CDS calls: {len(captured)}")
    for c in captured:
        print(f"\n  {c['url']}")
        print(f"  {c['sample'][:300]}")

    # Extract DOM structure for odds
    dom = await page.evaluate("""() => {
        const title = document.title
        const url = location.href
        // Look for common bwin selectors
        const sels = [
            'ms-event', 'ms-event-row', '[class*="ms-event"]',
            '[class*="event-item"]', '[class*="EventRow"]',
            'mspart', '[data-event]', '[class*="KambiBC"]',
            'option-indicator', '[class*="option"]',
            '.gl-Market', '.gl-Participant',
        ]
        const found = {}
        for (const s of sels) {
            const els = document.querySelectorAll(s)
            if (els.length) found[s] = {n: els.length, txt: els[0]?.textContent?.trim()?.slice(0,120)}
        }
        // Any decimal-looking number in page
        const decimals = (document.body.innerText.match(/[1-9]\\.[0-9]{2}/g) || []).slice(0,20)
        // Get a snapshot of visible text
        const visibleText = document.body.innerText.slice(0, 1000)
        return {title, url, found, decimals, visibleText}
    }""")

    print(f"\nTitle: {dom['title']}")
    print(f"URL: {dom['url']}")
    print(f"Decimal-like numbers: {dom['decimals']}")
    print(f"Found selectors: {list(dom['found'].keys())}")
    print(f"Visible text (first 800 chars):\n{dom['visibleText'][:800]}")

    # Try CDS API endpoints from SI domain context
    print("\n--- Trying CDS endpoints from page context ---")
    base = f"x-bwin-accessid={SI_ACCESSID}&lang=en-ca&country=CA&userCountry=CA"
    endpoints = [
        f"/cds-api/bettingoffer/fixture-view?{base}&fixtureTypes=Standard&state=Latest&sportIds=11&count=30",
        f"/cds-api/bettingoffer/fixtures?{base}&sportId=11&count=30",
        f"/cds-api/events/by-sport?{base}&sportId=11",
        f"/cds-api/offer-grouping/fixture-view?{base}&sportId=11",
    ]
    for ep in endpoints:
        result = await page.evaluate(f"""async () => {{
            try {{
                const r = await fetch('https://www.sportsinteraction.com' + {json.dumps(ep)}, {{
                    headers: {{'Accept': 'application/json'}}
                }})
                const txt = await r.text()
                return {{ok: r.ok, status: r.status, body: txt.slice(0,500)}}
            }} catch(e) {{ return {{error: e.message}} }}
        }}""")
        short = ep[:80]
        print(f"\n  {short}")
        if result.get('ok'):
            print(f"  STATUS 200! Body: {result.get('body','')[:400]}")
        else:
            print(f"  {result.get('status', result.get('error',''))}: {result.get('body','')[:100]}")

    await ctx.close()


async def url_probe(browser, name, urls):
    """Quick URL probe for a sportsbook."""
    print(f"\n\n=== {name}: URL PROBE ===")
    ctx = await browser.new_context(
        user_agent=UA, locale="en-CA",
        geolocation=GEO, permissions=["geolocation"]
    )
    page = await ctx.new_page()

    for url in urls:
        try:
            resp = await page.goto(url, wait_until="domcontentloaded", timeout=15_000)
            await asyncio.sleep(2)
            status = resp.status if resp else "?"
            final = page.url
            title = await page.title()
            body_snip = await page.evaluate("() => document.body?.innerText?.slice(0,200) || ''")
            print(f"\n  {url}")
            print(f"  -> {status} | {final[:80]}")
            print(f"  Title: {title[:70]}")
            print(f"  Body: {body_snip[:150]}")
        except Exception as e:
            print(f"\n  {url} -> {str(e)[:100]}")

    await ctx.close()


async def check_bet365_direct(browser):
    """Try Bet365 directly with better URL."""
    print("\n\n=== BET365: DIRECT ODDS SCRAPE ===")
    ctx = await browser.new_context(
        user_agent=UA, locale="en-CA",
        geolocation=GEO, permissions=["geolocation"]
    )
    page = await ctx.new_page()

    captured = []
    async def on_resp(resp):
        ct = resp.headers.get("content-type", "")
        url = resp.url
        if "bet365" in url and (any(k in url for k in ["api/", "/odds", "/markets", "/events"])):
            try:
                data = await resp.json()
                captured.append({"url": url[:120], "sample": json.dumps(data)[:400]})
            except:
                pass

    page.on("response", on_resp)

    urls = [
        "https://www.bet365.ca/en/sports/ice-hockey/",
        "https://www.bet365.ca/#/AC/B13/C20604387/D48/E1453/F10/",
    ]
    for url in urls:
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=20_000)
            await asyncio.sleep(8)
            title = await page.title()
            print(f"\n  URL: {url}")
            print(f"  Title: {title}")

            info = await page.evaluate("""() => {
                // Bet365 uses class names like 'cpm-*', 'cpm2-*', 'gll-*', 'gl-*'
                const sels = [
                    '[class*="cpm-Participant"]', '[class*="cpm2-Participant"]',
                    '[class*="gll-Participant"]', '[class*="gl-Participant"]',
                    '[class*="Coupon"]', '[class*="MarketGroup"]',
                    '[class*="Price"]', '[class*="Odds"]',
                    '[aria-label*="odds"]', '[data-odds]',
                    '.gll-CouponParticipantDetail', '.gll-MarketGroupButton__odds',
                ]
                const found = {}
                for (const s of sels) {
                    const els = document.querySelectorAll(s)
                    if (els.length) {
                        found[s] = {n: els.length,
                                    cls: els[0]?.className?.slice(0,60),
                                    txt: els[0]?.textContent?.trim()?.slice(0,80)}
                    }
                }
                // Get decimal odds
                const decimals = (document.body.innerText.match(/[1-9]\\.[0-9]{2}/g) || [])
                const bodyLen = document.body.innerText.length
                const bodyStart = document.body.innerText.slice(0, 2000)
                return {found, decimals: decimals.slice(0,20), bodyLen, bodyStart}
            }""")

            print(f"  Body length: {info['bodyLen']}, Decimals: {info['decimals'][:10]}")
            print(f"  Found selectors: {list(info['found'].keys())[:8]}")
            for s, d in list(info['found'].items())[:5]:
                print(f"    {s}: n={d['n']}, cls={d['cls'][:50]}")
                print(f"      txt: {d['txt'][:80]}")
            print(f"  Body (first 1000):\n{info.get('bodyStart','')[:1000]}")

        except Exception as e:
            print(f"  ERROR: {str(e)[:100]}")

    print(f"\nAPI calls captured: {len(captured)}")
    for c in captured[:3]:
        print(f"  {c['url']}: {c['sample'][:200]}")

    await ctx.close()


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="msedge", headless=True)

        await check_si(browser)

        await url_probe(browser, "BETMGM", [
            "https://sports.ab.betmgm.ca/en/sports",
            "https://ca.betmgm.ca/en/sports",
            "https://sports.betmgm.ca/en/sports",
            "https://www.betmgm.ca",
        ])

        await url_probe(browser, "FANDUEL CANADA", [
            "https://www.fanduel.com/sports/hockey",
            "https://www.fanduel.ca",
            "https://can.fanduel.com",
        ])

        await url_probe(browser, "BETWAY CANADA", [
            "https://www.betway.com/en-ca/sport/",
            "https://betway.ca",
            "https://www.betway.ca",
        ])

        await check_bet365_direct(browser)

        await browser.close()


asyncio.run(main())
