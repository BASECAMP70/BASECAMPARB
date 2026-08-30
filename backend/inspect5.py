"""Final inspection: SI fixture API + Bet365 odds buttons."""
import asyncio, json, sys
from playwright.async_api import async_playwright

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0"
SI_ACCESSID = "OGQ2ZTg0MGYtYjkwNS00ZmI1LTlkN2YtZDVmY2Y0ZDNkYmFl"

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="msedge", headless=True)

        # ── SI: capture ALL api calls on NHL page load ────────────────
        print("=== SI: ALL API calls on NHL page ===")
        ctx = await browser.new_context(user_agent=UA, locale="en-CA")
        page = await ctx.new_page()
        all_calls = []

        async def capture(resp):
            ct = resp.headers.get("content-type", "")
            if "json" in ct and "sportsinteraction" in resp.url:
                try:
                    data = await resp.json()
                    all_calls.append({"url": resp.url[:120], "type": type(data).__name__,
                                      "len": len(data) if isinstance(data, list) else len(data.keys()) if isinstance(data, dict) else 0,
                                      "sample": json.dumps(data)[:300]})
                except:
                    pass

        page.on("response", capture)
        await page.goto("https://www.sportsinteraction.com/en-ca/sports-betting/ice-hockey/nhl/",
                        wait_until="domcontentloaded", timeout=30_000)
        await asyncio.sleep(10)
        await ctx.close()

        print(f"Total JSON API calls: {len(all_calls)}")
        for c in all_calls:
            print(f"\n  URL: {c['url']}")
            print(f"  Type: {c['type']}[{c['len']}]")
            print(f"  Sample: {c['sample'][:200]}")

        # ── Bet365: find odds elements ───────────────────────────────
        print("\n\n=== BET365 ODDS ELEMENTS ===")
        ctx2 = await browser.new_context(user_agent=UA, locale="en-CA")
        page2 = await ctx2.new_page()
        await page2.goto("https://www.bet365.ca", wait_until="domcontentloaded", timeout=25_000)
        await asyncio.sleep(10)

        result = await page2.evaluate("""() => {
            // Find all elements with numeric content that look like odds (1.xx - 9.xx)
            const allEls = document.querySelectorAll('*')
            const oddsEls = []
            for (const el of allEls) {
                if (el.children.length === 0) {  // leaf nodes only
                    const txt = el.textContent.trim()
                    if (txt.match(/^[1-9]\\.[0-9]{2}$/) && el.className) {
                        oddsEls.push({
                            cls: el.className.split(' ').filter(c => !c.includes('_')).join(' ').slice(0,60),
                            fullCls: el.className.slice(0,80),
                            txt
                        })
                    }
                }
            }
            // Group by class
            const groups = {}
            for (const o of oddsEls) {
                groups[o.cls] = groups[o.cls] || []
                groups[o.cls].push(o.txt)
            }
            // Also show parent chain of first odds element
            let parentChain = []
            if (oddsEls.length > 0) {
                // find the actual element
                const allLeafs = [...document.querySelectorAll('*')].filter(el => {
                    const t = el.textContent.trim()
                    return el.children.length === 0 && t.match(/^[1-9]\\.[0-9]{2}$/)
                })
                if (allLeafs[0]) {
                    let el = allLeafs[0]
                    for (let i = 0; i < 6 && el; i++) {
                        parentChain.push(el.className.slice(0,60))
                        el = el.parentElement
                    }
                }
            }
            return {groups: Object.entries(groups).slice(0,10), parentChain, count: oddsEls.length}
        }""")
        print(f"Found {result['count']} odds-like numbers")
        print(f"Parent chain from leaf: {result['parentChain']}")
        print("By class:")
        for cls, vals in result['groups']:
            print(f"  [{cls}]: {vals[:5]}")

        # Get a full fixture+odds row
        row_data = await page2.evaluate("""() => {
            const fixture = document.querySelector('.cpm-ParticipantFixtureDetailsIceHockey')
            if (!fixture) return null
            // Walk up to find market group
            let el = fixture
            for (let i = 0; i < 8; i++) {
                if (!el.parentElement) break
                el = el.parentElement
                const text = el.innerText
                if (text.match(/[1-9]\\.[0-9]{2}/)) {
                    const classes = [...el.querySelectorAll('[class]')].map(e => e.className).join('|').slice(0,200)
                    return {
                        level: i,
                        text: text.slice(0,400),
                        classAtLevel: el.className.slice(0,80),
                        childClasses: classes.slice(0,300)
                    }
                }
            }
            return {error: 'no odds found in parents'}
        }""")
        print(f"\nFixture+odds row: {json.dumps(row_data, indent=2)}")

        await ctx2.close()
        await browser.close()

asyncio.run(main())
