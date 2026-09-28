"""Screenshot dashboard pages in light and dark mode and report console errors.

    .venv/bin/python .agents/skills/test-trackio/scripts/ui_check.py \\
        --url http://127.0.0.1:7862 --project my-project \\
        --pages overview,metrics,traces --out /tmp/ui-check [--token TOKEN] \\
        [--width 1400 --height 900] [--selector ".alert-panel"]

Writes <out>/<page>-<theme>.png (or an element screenshot with --selector),
collapses the floating alert panel so it does not cover the page, prints each
page's console errors, and exits 1 if there were any. Look at every screenshot:
this checks that pages render, not that they look right.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from urllib.parse import urlencode

from playwright.async_api import async_playwright


async def capture(args: argparse.Namespace) -> int:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    failures = 0
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        for theme in args.themes.split(","):
            context = await browser.new_context(
                viewport={"width": args.width, "height": args.height}
            )
            page = await context.new_page()
            errors: list[str] = []
            page.on(
                "console",
                lambda m: errors.append(m.text[:200]) if m.type == "error" else None,
            )
            page.on("pageerror", lambda e: errors.append(str(e)[:200]))
            if args.token:
                await page.goto(f"{args.url}/?write_token={args.token}")
                await page.wait_for_timeout(1500)
            for name in args.pages.split(","):
                errors.clear()
                query = {"__theme": theme}
                if args.project:
                    query["project"] = args.project
                await page.goto(f"{args.url}/{name}?{urlencode(query)}")
                await page.wait_for_timeout(args.wait)
                chevron = page.locator(".alert-header .collapse-icon")
                if (
                    await chevron.count()
                    and not await page.locator(".alert-panel.collapsed").count()
                ):
                    await chevron.first.click()
                    await page.wait_for_timeout(200)
                path = out / f"{name}-{theme}.png"
                if args.selector:
                    await page.locator(args.selector).first.screenshot(path=str(path))
                else:
                    await page.screenshot(path=str(path), full_page=args.full_page)
                status = "ok" if not errors else f"{len(errors)} console error(s)"
                print(f"{name:<12} {theme:<5} {status:<20} {path}")
                for error in errors:
                    print(f"    {error}")
                failures += len(errors)
            await context.close()
        await browser.close()
    return failures


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--url", default="http://127.0.0.1:7860")
    parser.add_argument("--project")
    parser.add_argument(
        "--pages",
        default="overview,metrics,system,traces,media,reports,files,artifacts",
    )
    parser.add_argument("--themes", default="light,dark")
    parser.add_argument("--out", default="ui-check")
    parser.add_argument("--token", help="write_token, for pages that need write access")
    parser.add_argument("--selector", help="Screenshot only this element")
    parser.add_argument("--width", type=int, default=1400)
    parser.add_argument("--height", type=int, default=900)
    parser.add_argument("--wait", type=int, default=2500, help="ms to wait per page")
    parser.add_argument("--full-page", action="store_true")
    args = parser.parse_args()
    sys.exit(1 if asyncio.run(capture(args)) else 0)


if __name__ == "__main__":
    main()
