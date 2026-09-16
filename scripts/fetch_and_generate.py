"""Fetch HN top stories, enrich in Japanese, and render the static site."""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

from scripts.hn_client import fetch_top_stories
from scripts.render import render_site, write_snapshot
from scripts.translate import enrich_story

JST = ZoneInfo("Asia/Tokyo")
ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="HN日報を生成する")
    parser.add_argument("--slot", choices=["07", "12", "23"])
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument("--skip-enrich", action="store_true", help="翻訳・要約をスキップ（デバッグ用）")
    parser.add_argument(
        "--render-only",
        action="store_true",
        help="HN を取得せず、docs/data の既存スナップショットからページを作り直す",
    )
    args = parser.parse_args()
    if not args.render_only and not args.slot:
        parser.error("--slot is required unless --render-only is given")
    return args


async def build(slot: str, limit: int, skip_enrich: bool) -> dict:
    metrics = {
        "translate_requests": 0,
        "translate_failures": 0,
        "summarize_requests": 0,
        "summaries_success": 0,
        "slot": slot,
        "started_at": datetime.now(JST).isoformat(),
    }

    stories = await fetch_top_stories(limit=limit, comment_limit=8)
    enriched = []
    for story in stories:
        if skip_enrich:
            enriched.append(
                {
                    **story,
                    "title_ja": story["title_en"],
                    "summary_ja": "",
                    "editor_note": "",
                    "category": "Other",
                }
            )
        else:
            enriched.append(enrich_story(story, metrics))

    metrics["finished_at"] = datetime.now(JST).isoformat()
    metrics["story_count"] = len(enriched)

    payload = {
        "date": datetime.now(JST).replace(hour=int(slot), minute=0, second=0, microsecond=0).isoformat(),
        "slot": slot,
        "stories": enriched,
        "metrics": metrics,
    }
    return payload


def rerender_from_snapshots() -> None:
    """Rebuild every page from the stored JSON snapshots, oldest first."""
    snapshots = sorted((ROOT / "docs" / "data").glob("*.json"))
    if not snapshots:
        raise SystemExit("docs/data にスナップショットがありません")
    for path in snapshots:
        payload = json.loads(path.read_text(encoding="utf-8"))
        slot = payload.get("slot") or path.stem.rsplit("_", 1)[-1]
        render_site(payload, slot)
    print(f"re-rendered {len(snapshots)} snapshots")


def main() -> None:
    load_dotenv(ROOT / ".env")
    args = parse_args()
    if args.render_only:
        rerender_from_snapshots()
        return
    payload = asyncio.run(build(args.slot, args.limit, args.skip_enrich))
    write_snapshot(payload, args.slot)
    render_site(payload, args.slot)
    print(json.dumps(payload["metrics"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
