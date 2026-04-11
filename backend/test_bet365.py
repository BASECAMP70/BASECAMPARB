"""
Quick test of the updated Bet365Scraper.
Run: .venv/Scripts/python.exe test_bet365.py
"""
import asyncio
import sys
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())


async def main():
    from playwright.async_api import async_playwright
    from playwright_stealth import stealth_async
    from scrapers.base import UA_LIST
    import random

    pw = await async_playwright().start()
    browser = await pw.chromium.launch(channel="msedge", headless=True)
    ctx = await browser.new_context(
        user_agent=random.choice(UA_LIST),
        locale="en-CA",
        geolocation={"latitude": 53.5461, "longitude": -113.4938, "accuracy": 50},
        permissions=["geolocation"],
    )
    await stealth_async(ctx)
    page = await ctx.new_page()
    print("Navigating to bet365 NHL page...")
    await page.goto("https://www.bet365.ca/en/sports/ice-hockey/nhl/",
                    wait_until="domcontentloaded", timeout=30_000)
    await page.wait_for_selector(
        '[class*="cpm-ParticipantFixtureDetailsIceHockey"]:not([class*="Hidden"])',
        timeout=20_000
    )
    import asyncio as _a
    await _a.sleep(4)

    raw = await page.evaluate("""() => {
        const FIXTURE_SEL = '[class*="cpm-ParticipantFixtureDetailsIceHockey"]:not([class*="Hidden"])';
        const ML_ODDS_SEL  = '[class*="cpm-ParticipantOdds"][class*="gl-Participant_General"]';

        const oddsText = (el) => {
            const span = el && el.querySelector('[class*="cpm-ParticipantOdds_Odds"]');
            return (span || el) ? (span || el).textContent.trim() : '';
        };

        const results = [];
        const containers = document.querySelectorAll('[class*="gl-MarketGroupContainer"]');

        for (const container of containers) {
            const fixRows = [...container.querySelectorAll(FIXTURE_SEL)];
            if (!fixRows.length) continue;

            // Find the "Money" market column
            const oddsColumns = container.querySelectorAll('[class*="cpm-MarketOdds"]');
            let moneyCol = null;
            for (const col of oddsColumns) {
                const hdr = col.querySelector('[class*="cpm-MarketOddsHeader"]');
                if (hdr && /money/i.test(hdr.textContent)) {
                    moneyCol = col;
                    break;
                }
            }
            if (!moneyCol) {
                results.push({ debug: 'no money col', fixtures: fixRows.length });
                continue;
            }

            const mlOdds = [...moneyCol.querySelectorAll(ML_ODDS_SEL)];
            const gameCount = Math.floor(mlOdds.length / 2);
            if (!gameCount) continue;

            const seen = new Set();
            const uniqueGames = [];
            for (const fix of fixRows) {
                const teamEls = fix.querySelectorAll('.cpm-ParticipantFixtureDetailsIceHockey_Team');
                if (teamEls.length < 2) continue;
                const home = teamEls[0].textContent.trim();
                const away = teamEls[1].textContent.trim();
                if (!home || !away) continue;
                const key = home + '|' + away;
                if (!seen.has(key)) {
                    seen.add(key);
                    uniqueGames.push({ home, away });
                }
                if (uniqueGames.length >= gameCount) break;
            }

            for (let i = 0; i < uniqueGames.length; i++) {
                const { home, away } = uniqueGames[i];
                results.push({
                    home, away,
                    homeOdds: oddsText(mlOdds[i * 2]),
                    awayOdds: oddsText(mlOdds[i * 2 + 1]),
                });
            }
        }
        return results;
    }""")

    print(f"Extracted {len(raw)} events:")
    for ev in raw[:20]:
        if 'debug' in ev:
            print(f"  [DEBUG] {ev}")
        else:
            print(f"  {ev.get('home','?'):25s} vs {ev.get('away','?'):25s} | home={ev.get('homeOdds','?'):8s} away={ev.get('awayOdds','?'):8s}")

    await ctx.close()
    await browser.close()
    await pw.stop()


asyncio.run(main())
