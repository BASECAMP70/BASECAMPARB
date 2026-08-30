"""
One-shot inspector: visits each sportsbook, intercepts XHR/fetch calls,
and dumps enough DOM info to write real scrapers.
Run from backend/ with the venv active.
"""
import asyncio, json, sys, re
from playwright.async_api import async_playwright

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

SITES = [
    ("playalberta",        "https://www.playalberta.ca/sports"),
    ("betmgm",             "https://sports.betmgm.ca/en/sports"),
    ("fanduel",            "https://www.fanduel.com/sports/hockey"),
    ("bet365",             "https://www.bet365.ca/en/sports"),
    ("sportsinteraction",  "https://www.sportsinteraction.com/sports-betting/hockey/nhl"),
    ("betway",             "https://www.betway.com/en-ca/sport/ice-hockey/"),
]

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0"

async def inspect(p, name, url):
    print(f"\n{'='*60}")
    print(f"INSPECTING: {name}  →  {url}")
    print('='*60)

    api_calls = []
    ctx = await p.chromium.launch(channel="msedge", headless=True)
    context = await ctx.new_context(user_agent=UA)
    page = await context.new_page()

    async def on_response(resp):
        ct = resp.headers.get("content-type", "")
        if "json" in ct and any(kw in resp.url for kw in ["odds","events","market","fixture","sport","price"]):
            try:
                body = await resp.json()
                api_calls.append({"url": resp.url[:120], "keys": list(body.keys()) if isinstance(body, dict) else f"list[{len(body)}]"})
            except:
                pass

    page.on("response", on_response)

    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        await asyncio.sleep(5)

        # Find all unique classes that look odds-related
        classes = await page.evaluate("""() => {
            const all = [...document.querySelectorAll('[class]')]
                .map(e => e.className)
                .filter(c => typeof c === 'string')
                .flatMap(c => c.split(' '))
                .filter(c => c.match(/event|match|game|odds|market|bet|price|participant|competitor|team|fixture/i))
            return [...new Set(all)].slice(0, 50)
        }""")
        print(f"Odds-related classes: {', '.join(classes[:30])}")

        # Get sample text from likely odds containers
        sample = await page.evaluate("""() => {
            const selectors = [
                '[class*="event-item"]', '[class*="event-row"]', '[class*="fixture"]',
                '[class*="match-row"]', '[class*="bet-item"]', '[class*="market-row"]',
                'ms-event', 'ms-six-pack-event', '[data-testid*="event"]'
            ]
            for (const sel of selectors) {
                const el = document.querySelector(sel)
                if (el) return { selector: sel, text: el.innerText.slice(0,300) }
            }
            return { selector: 'none', text: document.body.innerText.slice(0, 300) }
        }""")
        print(f"Sample ({sample['selector']}): {repr(sample['text'][:200])}")

        if api_calls:
            print(f"API calls ({len(api_calls)}):")
            for c in api_calls[:5]:
                print(f"  {c['url']} → {c['keys']}")
        else:
            print("No JSON API calls intercepted")

    except Exception as e:
        print(f"ERROR: {e}")
    finally:
        await context.close()
        await ctx.close()

async def main():
    async with async_playwright() as p:
        for name, url in SITES:
            await inspect(p, name, url)

asyncio.run(main())
