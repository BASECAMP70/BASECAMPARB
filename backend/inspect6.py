"""Inspector 6: SI fixture API + remaining sites (BetMGM, FanDuel, Betway, Bet365 sports page)."""
import asyncio, json, sys, re
from playwright.async_api import async_playwright

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0"
SI_ACCESSID = "OGQ2ZTg0MGYtYjkwNS00ZmI1LTlkN2YtZDVmY2Y0ZDNkYmFl"
GEO = {"latitude": 53.5461, "longitude": -113.4938, "accuracy": 50}


async def try_si_cds_endpoints(browser):
    """Try known bwin/GVC CDS endpoint patterns for SI fixture odds."""
    print("\n=== SI: TRYING CDS FIXTURE ENDPOINTS ===")
    import urllib.request

    base_params = f"x-bwin-accessid={SI_ACCESSID}&lang=en-ca&country=CA&userCountry=CA"
    endpoints = [
        f"https://www.sportsinteraction.com/cds-api/bettingoffer/fixture-view?{base_params}&fixtureTypes=Standard&state=Latest&sportIds=11&count=30",
        f"https://www.sportsinteraction.com/cds-api/bettingoffer/fixture-view?{base_params}&sportIds=11&count=20",
        f"https://www.sportsinteraction.com/cds-api/events?{base_params}&sportIds=11",
        f"https://www.sportsinteraction.com/cds-api/offer-grouping/fixture-view/sport/11?{base_params}",
        f"https://www.sportsinteraction.com/cds-api/offer-grouping/fixture-view/all?{base_params}&sportIds=11",
        f"https://www.sportsinteraction.com/en-ca/sports/api/competitions?sportId=11",
        f"https://www.sportsinteraction.com/cds-api/bettingoffer/fixtures?{base_params}&sportId=11&count=30",
        f"https://www.sportsinteraction.com/cds-api/bettingoffer/event-card?{base_params}&sportIds=11&count=20",
    ]

    ctx = await browser.new_context(user_agent=UA, locale="en-CA")
    page = await ctx.new_page()

    for url in endpoints:
        try:
            resp = await page.evaluate(f"""async () => {{
                const r = await fetch({json.dumps(url)}, {{
                    headers: {{'Accept': 'application/json', 'x-bwin-accessid': '{SI_ACCESSID}'}}
                }})
                const txt = await r.text()
                return {{status: r.status, body: txt.slice(0, 600)}}
            }}""")
            short_url = url[50:120]
            print(f"\n  {short_url}")
            print(f"  Status: {resp['status']}")
            body = resp.get('body', '')
            if resp['status'] == 200 and len(body) > 50:
                print(f"  FOUND DATA: {body[:400]}")
            else:
                print(f"  Body: {body[:100]}")
        except Exception as e:
            print(f"  ERROR: {e}")

    await ctx.close()


async def check_si_dom(browser):
    """Load SI hockey page and extract DOM odds."""
    print("\n\n=== SI: DOM ODDS EXTRACTION ===")
    ctx = await browser.new_context(user_agent=UA, locale="en-CA")
    page = await ctx.new_page()

    captured_fixture_urls = []

    async def on_response(resp):
        if "sportsinteraction" in resp.url and "cds-api" in resp.url:
            ct = resp.headers.get("content-type", "")
            if "json" in ct:
                try:
                    data = await resp.json()
                    captured_fixture_urls.append({
                        "url": resp.url[:150],
                        "sample": json.dumps(data)[:500] if data else ""
                    })
                except:
                    pass

    page.on("response", on_response)
    await page.goto("https://www.sportsinteraction.com/en-ca/sports-betting/ice-hockey/nhl/",
                    wait_until="networkidle", timeout=40_000)
    await asyncio.sleep(8)

    print(f"CDS API calls captured: {len(captured_fixture_urls)}")
    for c in captured_fixture_urls:
        print(f"  {c['url']}")
        print(f"  {c['sample'][:200]}\n")

    # Try to extract DOM structure
    dom_info = await page.evaluate("""() => {
        // Look for event rows - bwin/GVC uses ms-grid patterns
        const selectors = [
            '.ms-event', '.ms-event-row', 'ms-grid-event',
            '[class*="event-row"]', '[class*="fixture"]',
            '.gl-MarketGroup', '.sc-fzoLsD',
            '[data-event-id]', '[data-fixture-id]',
            '.sgl-MarketGroup', '.rcm-ClassificationModule'
        ]
        const found = {}
        for (const sel of selectors) {
            const els = document.querySelectorAll(sel)
            if (els.length > 0) {
                found[sel] = {
                    count: els.length,
                    sample: els[0].textContent.slice(0, 150).trim()
                }
            }
        }

        // Also look for any element containing team names + decimal odds
        const textSamples = []
        const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT)
        let node
        while ((node = walker.nextNode()) && textSamples.length < 5) {
            const txt = node.textContent.trim()
            if (txt.match(/[1-9]\\.\\d{2}/) && txt.length < 500 && txt.length > 20) {
                if (node.children.length < 5) {
                    textSamples.push({
                        tag: node.tagName,
                        cls: node.className.slice(0, 60),
                        txt: txt.slice(0, 200)
                    })
                }
            }
        }

        return {found, textSamples, title: document.title, url: location.href}
    }""")

    print(f"Page title: {dom_info.get('title')}")
    print(f"URL: {dom_info.get('url')}")
    print("Found selectors:", json.dumps(dom_info.get('found', {}), indent=2))
    print("Text samples with odds:")
    for s in dom_info.get('textSamples', []):
        print(f"  [{s['cls']}]: {s['txt'][:150]}")

    await ctx.close()


async def check_betmgm(browser):
    """Find working BetMGM Alberta URL and selectors."""
    print("\n\n=== BETMGM: URL SEARCH ===")
    urls_to_try = [
        "https://sports.ab.betmgm.ca/en/sports",
        "https://ca.betmgm.ca/en/sports",
        "https://sports.on.betmgm.ca/en/sports",  # Ontario - might work for structure
        "https://betmgm.ca/en/sports",
        "https://www.betmgm.ca",
        "https://sports.betmgm.ca/en/sports",
    ]

    ctx = await browser.new_context(
        user_agent=UA, locale="en-CA",
        geolocation=GEO, permissions=["geolocation"]
    )
    page = await ctx.new_page()

    for url in urls_to_try:
        try:
            resp = await page.goto(url, wait_until="domcontentloaded", timeout=15_000)
            await asyncio.sleep(3)
            final_url = page.url
            title = await page.title()
            print(f"\n  Tried: {url}")
            print(f"  Status: {resp.status if resp else 'None'}, Final: {final_url}")
            print(f"  Title: {title[:80]}")

            # Check if it's usable
            if "betmgm" in final_url.lower() and resp and resp.status == 200:
                # Look for event selectors
                info = await page.evaluate("""() => {
                    const selectors = [
                        '[class*="event"]', '[class*="Event"]',
                        '.KambiBC-event-item', '.KambiBC-bet-offer__participant',
                        'ms-event', '[data-event-id]',
                        '.mod-participant', '.mod-state'
                    ]
                    const found = {}
                    for (const s of selectors) {
                        const els = document.querySelectorAll(s)
                        if (els.length) found[s] = {n: els.length, txt: els[0]?.textContent?.slice(0,100)}
                    }
                    return {found, bodySnip: document.body.textContent.slice(0,300)}
                }""")
                print(f"  Found elements: {list(info.get('found', {}).keys())[:5]}")
                print(f"  Body snippet: {info.get('bodySnip', '')[:150]}")
                if info.get('found'):
                    break
        except Exception as e:
            print(f"  {url} -> ERROR: {str(e)[:80]}")

    await ctx.close()


async def check_fanduel(browser):
    """Find working FanDuel Canada URL."""
    print("\n\n=== FANDUEL CANADA: URL SEARCH ===")
    urls_to_try = [
        "https://www.fanduel.com/sports/hockey",
        "https://sportsbook.fanduel.com",
        "https://www.fanduel.ca",
        "https://can.fanduel.com",
        "https://www.fanduelsportsbook.ca",
        "https://www.fanduel.com/sports/alberta",
    ]

    ctx = await browser.new_context(
        user_agent=UA, locale="en-CA",
        geolocation=GEO, permissions=["geolocation"]
    )
    page = await ctx.new_page()

    for url in urls_to_try:
        try:
            resp = await page.goto(url, wait_until="domcontentloaded", timeout=12_000)
            await asyncio.sleep(2)
            final_url = page.url
            title = await page.title()
            print(f"\n  Tried: {url}")
            print(f"  Status: {resp.status if resp else 'None'}, Final: {final_url}")
            print(f"  Title: {title[:80]}")
        except Exception as e:
            print(f"  {url} -> ERROR: {str(e)[:80]}")

    await ctx.close()


async def check_betway(browser):
    """Find working Betway Canada URL."""
    print("\n\n=== BETWAY CANADA: URL SEARCH ===")
    urls_to_try = [
        "https://www.betway.com/en-ca/sport/",
        "https://betway.ca",
        "https://www.betway.ca",
        "https://www.betway.com/sport/ice-hockey/",
        "https://casino.betway.com/en-ca/",
        "https://www.betway.com/en-ca/",
    ]

    ctx = await browser.new_context(
        user_agent=UA, locale="en-CA",
        geolocation=GEO, permissions=["geolocation"]
    )
    page = await ctx.new_page()

    for url in urls_to_try:
        try:
            resp = await page.goto(url, wait_until="domcontentloaded", timeout=12_000)
            await asyncio.sleep(2)
            final_url = page.url
            title = await page.title()
            print(f"\n  Tried: {url}")
            print(f"  Status: {resp.status if resp else 'None'}, Final: {final_url}")
            print(f"  Title: {title[:80]}")
        except Exception as e:
            print(f"  {url} -> ERROR: {str(e)[:80]}")

    await ctx.close()


async def check_bet365_sports(browser):
    """Check Bet365 actual sports betting page (not homepage) for odds selectors."""
    print("\n\n=== BET365: SPORTS PAGE ODDS ===")
    urls = [
        "https://www.bet365.ca/en/sports/ice-hockey/#/IP/",
        "https://www.bet365.ca/#/IP/",
        "https://www.bet365.com/#/AC/B13/C20604387/D48/E1453/F10/",  # NHL moneyline URL pattern
    ]

    ctx = await browser.new_context(
        user_agent=UA, locale="en-CA",
        geolocation=GEO, permissions=["geolocation"]
    )
    page = await ctx.new_page()

    captured = []
    async def on_resp(resp):
        ct = resp.headers.get("content-type", "")
        if ("json" in ct or "javascript" in ct) and "bet365" in resp.url:
            if any(k in resp.url for k in ["api", "sports", "odds", "market", "event"]):
                try:
                    data = await resp.json()
                    captured.append({"url": resp.url[:120], "sample": json.dumps(data)[:300]})
                except:
                    pass

    page.on("response", on_resp)

    for url in urls:
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=20_000)
            await asyncio.sleep(8)
            final_url = page.url
            title = await page.title()
            print(f"\n  URL: {url}")
            print(f"  Final: {final_url}, Title: {title[:60]}")

            # Look for odds in data attributes
            info = await page.evaluate("""() => {
                // Bet365 typically uses data-* attributes for odds
                const withData = document.querySelectorAll('[data-*]')

                // Try common Bet365 class patterns (they obfuscate but structure is consistent)
                const selectors = [
                    '[class*="Participant"]', '[class*="participant"]',
                    '[class*="Fixture"]', '[class*="fixture"]',
                    '[class*="Coupon"]', '[class*="coupon"]',
                    '[class*="Price"]', '[class*="price"]',
                    '[class*="odds"]', '[class*="Odds"]',
                    '[class*="MarketRow"]',
                    '.gll-MarketGroupButton',
                    '[aria-label]',
                ]
                const found = {}
                for (const s of selectors) {
                    const els = document.querySelectorAll(s)
                    if (els.length > 0) {
                        found[s] = {
                            n: els.length,
                            sample: els[0]?.textContent?.trim()?.slice(0,100) || '',
                            cls: els[0]?.className?.slice(0,60) || ''
                        }
                    }
                }

                // Find decimal-looking odds
                const allText = document.body.innerText
                const oddsMatches = allText.match(/[1-9]\\.\\d{2}/g) || []

                // Find elements with aria-labels that have odds
                const ariaEls = [...document.querySelectorAll('[aria-label]')]
                    .filter(el => el.getAttribute('aria-label').match(/[1-9]\\.\\d{2}/))
                    .slice(0, 5)
                    .map(el => ({
                        aria: el.getAttribute('aria-label').slice(0,60),
                        cls: el.className.slice(0,60),
                        tag: el.tagName
                    }))

                return {found, oddsInPage: oddsMatches.slice(0,20), ariaWithOdds: ariaEls,
                        bodyLen: allText.length}
            }""")

            print(f"  Body length: {info.get('bodyLen', 0)}")
            print(f"  Decimal odds in page: {info.get('oddsInPage', [])[:10]}")
            print(f"  Aria elements with odds: {info.get('ariaWithOdds', [])}")
            print(f"  Found selectors: {list(info.get('found', {}).keys())}")
            for sel, data in list(info.get('found', {}).items())[:5]:
                print(f"    {sel}: n={data['n']}, cls={data['cls'][:50]}")
                print(f"      sample: {data['sample'][:100]}")

        except Exception as e:
            print(f"  ERROR: {str(e)[:100]}")

    print(f"\nCapured API calls: {len(captured)}")
    for c in captured[:5]:
        print(f"  {c['url']}: {c['sample'][:200]}")

    await ctx.close()


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="msedge", headless=True)

        await try_si_cds_endpoints(browser)
        await check_si_dom(browser)
        await check_betmgm(browser)
        await check_fanduel(browser)
        await check_betway(browser)
        await check_bet365_sports(browser)

        await browser.close()


asyncio.run(main())
