"""
Quick test of bet365 extraction logic.
Run: .venv/Scripts/python.exe test_bet365.py
"""
import asyncio, sys
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

async def main():
    from playwright.async_api import async_playwright
    pw = await async_playwright().start()
    browser = await pw.chromium.launch(channel="msedge", headless=True)
    ctx = await browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        locale="en-CA",
        geolocation={"latitude": 53.5461, "longitude": -113.4938, "accuracy": 50},
        permissions=["geolocation"],
    )
    page = await ctx.new_page()
    print("Navigating to bet365 NHL page...")
    await page.goto("https://www.bet365.ca/en/sports/ice-hockey/", wait_until="domcontentloaded", timeout=30_000)
    await page.wait_for_selector('[class*="cpm-ParticipantFixtureDetailsIceHockey"]', timeout=20_000)
    import asyncio as _a
    await _a.sleep(4)

    raw = await page.evaluate("""() => {
        const results = [];
        const containers = document.querySelectorAll('[class*="gl-MarketGroupContainer"]');
        for (const container of containers) {
            const allOddsEls = [...container.querySelectorAll('[class*="cpm-ParticipantOdds"][class*="gl-Participant_General"]')];
            if (!allOddsEls.length) continue;
            if (allOddsEls.some(el => el.className.includes('Handicap'))) continue;
            const firstOddsTxt = allOddsEls[0].textContent.trim();
            if (/^[OU]\\s+[0-9]/.test(firstOddsTxt)) continue;
            const fixtures = [...container.querySelectorAll('[class*="cpm-ParticipantFixtureDetailsIceHockey"]')];
            if (!fixtures.length) continue;
            for (let i = 0; i < fixtures.length; i++) {
                const fix = fixtures[i];
                const teamEls = fix.querySelectorAll('[class*="_TeamContainer"]');
                let home = '', away = '';
                if (teamEls.length >= 2) {
                    home = teamEls[0].textContent.trim();
                    away = teamEls[1].textContent.trim();
                } else {
                    const raw = fix.textContent.replace(/\\d+:\\d+\\s*(AM|PM).*/i, '').trim();
                    const m = raw.match(/^(.{4,30}?)([A-Z].{4,30})$/);
                    if (m) { home = m[1].trim(); away = m[2].trim(); }
                    else home = raw;
                }
                if (!home) continue;
                const homeEl = allOddsEls[i * 2];
                const awayEl = allOddsEls[i * 2 + 1];
                if (!homeEl || !awayEl) continue;
                const oddsText = (el) => {
                    const inner = el.querySelector('[class*="_Odds"]');
                    return (inner || el).textContent.trim();
                };
                results.push({home, away, homeOdds: oddsText(homeEl), awayOdds: oddsText(awayEl)});
            }
        }
        return results;
    }""")

    print(f"Extracted {len(raw)} events:")
    for ev in raw[:10]:
        print(f"  {ev['home']} vs {ev['away']} | home={ev['homeOdds']} away={ev['awayOdds']}")

    await ctx.close()
    await browser.close()
    await pw.stop()

asyncio.run(main())
