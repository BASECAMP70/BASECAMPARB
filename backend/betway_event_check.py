"""Quick one-shot script to dump raw Betway event data so we can find the URL/CName field."""
import asyncio, json, uuid, random
import aiohttp

_API_BASE = "https://betway.com/g/services/api"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"

def _base():
    return {"BrandId":3,"LanguageId":25,"TerritoryId":38,"TerritoryCode":"CA",
            "ClientTypeId":2,"JurisdictionId":2,"ClientIntegratorId":1,
            "CorrelationId":str(uuid.uuid4())}

async def main():
    hdrs = {"User-Agent": UA, "Accept":"application/json","Content-Type":"application/json",
            "Origin":"https://betway.com","Referer":"https://betway.com/g/en-ca/sports/"}
    async with aiohttp.ClientSession(headers=hdrs) as s:
        # Step 1: get event IDs for NHL
        p = _base()
        p.update({"GroupCName":"nhl","CategoryCName":"ice-hockey",
                   "SubCategoryCName":"north-america","PremiumOnly":False})
        async with s.post(f"{_API_BASE}/events/v2/GetGroup", json=p) as r:
            grp = await r.json(content_type=None)
        summaries = grp.get("EventSummaries",[])
        print(f"=== EventSummary keys: {list(summaries[0].keys()) if summaries else 'NONE'}")
        if summaries:
            print(f"=== Sample EventSummary: {json.dumps(summaries[0], indent=2)}")

        # Step 2: get event details
        ids = [s2["EventId"] for s2 in summaries[:3] if not s2.get("IsOutright",True)]
        p2 = _base()
        p2.update({"EventMarketSets":[{"EventIds":ids,"MarketCNames":["money-line"]}],
                   "ScoreboardRequest":{"IncidentRequest":{},"ScoreboardType":3}})
        async with s.post(f"{_API_BASE}/events/v2/GetEventsWithMultipleMarkets", json=p2) as r:
            detail = await r.json(content_type=None)
        events = detail.get("Events",[])
        print(f"\n=== Event keys: {list(events[0].keys()) if events else 'NONE'}")
        if events:
            print(f"=== Sample Event: {json.dumps(events[0], indent=2)}")

asyncio.run(main())
