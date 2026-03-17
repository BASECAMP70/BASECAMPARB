"""
Deep inspection of the sites that loaded + better URLs for others.
"""
import asyncio, json, sys
from playwright.async_api import async_playwright

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0"

SITES = [
    # Better URLs based on first pass
    ("betmgm_ab",    "https://sports.ab.betmgm.ca/en/sports"),
    ("fanduel",      "https://www.fanduel.com/sports"),
    ("bet365_full",  "https://www.bet365.ca/en/sports/ice-hockey/#/IP/"),
    ("si_hockey",    "https://www.sportsinteraction.com/en-ca/sports-betting/ice-hockey/nhl/"),
    ("betway",       "https://www.betway.com/en-ca/sport/"),
]

async def deep_inspect(p, name, url):
    print(f"\n{'='*60}\n{name}: {url}\n{'='*60}")
    api_calls = []
    browser = await p.chromium.launch(channel="msedge", headless=True)
    context = await browser.new_context(
        user_agent=UA,
        geolocation={"latitude": 53.5461, "longitude": -113.4938},  # Edmonton, AB
        permissions=["geolocation"],
        locale="en-CA",
    )
    page = await context.new_page()

    async def on_response(resp):
        ct = resp.headers.get("content-type", "")
        url_lower = resp.url.lower()
        if "json" in ct and any(kw in url_lower for kw in ["odds","event","market","fixture","sport","price","offer","coupon","cds"]):
            try:
                body = await resp.json()
                snippet = json.dumps(body)[:300]
                api_calls.append({"url": resp.url[:100], "snippet": snippet})
            except:
                pass

    page.on("response", on_response)
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=25_000)
        await asyncio.sleep(6)

        # Get all unique odds-related classes
        classes = await page.evaluate("""() => [...new Set(
            [...document.querySelectorAll('[class]')]
                .map(e => e.className)
                .filter(c => typeof c === 'string')
                .flatMap(c => c.split(' '))
                .filter(c => c.match(/event|match|odds|market|bet|price|participant|team|fixture|coupon/i))
        )].slice(0,30)""")
        print("Classes:", ", ".join(classes[:25]))

        # Try to find odds
        sample = await page.evaluate("""() => {
            const sels = [
                '[class*="event-item"]','[class*="fixture"]','[class*="event-row"]',
                '[class*="market-row"]','ms-event','[class*="EventCell"]',
                '[class*="participant"]','[class*="coupon"]','[class*="BetRow"]'
            ]
            for (const s of sels) {
                const el = document.querySelector(s)
                if (el && el.innerText.trim().length > 20)
                    return {sel: s, txt: el.innerText.slice(0,400)}
            }
            return {sel:'body', txt: document.body.innerText.slice(0,300)}
        }""")
        print(f"Sample ({sample['sel']}): {repr(sample['txt'][:300])}")

        print(f"API calls ({len(api_calls)}):")
        for c in api_calls[:8]:
            print(f"  URL: {c['url']}")
            print(f"  Data: {c['snippet'][:200]}")

    except Exception as e:
        print(f"ERROR: {e}")
    finally:
        await context.close()
        await browser.close()

async def main():
    async with async_playwright() as p:
        for name, url in SITES:
            await deep_inspect(p, name, url)

asyncio.run(main())
