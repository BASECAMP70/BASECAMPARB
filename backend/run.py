"""
Windows-compatible uvicorn launcher.

On Windows, asyncio defaults to SelectorEventLoop which does not support
subprocess creation (needed by Playwright). This script sets
WindowsProactorEventLoopPolicy BEFORE uvicorn creates the event loop,
then hands off to uvicorn programmatically.
"""
import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import uvicorn

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=False)
