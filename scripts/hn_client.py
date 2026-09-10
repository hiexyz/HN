"""Hacker News Firebase API client."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import httpx

HN_API = "https://hacker-news.firebaseio.com/v0"
HN_ITEM_URL = "https://news.ycombinator.com/item?id={id}"
USER_AGENT = "HN-Nippo/1.0 (+https://github.com/hiexyz/HN)"


async def _get_json(client: httpx.AsyncClient, path: str) -> Any:
    response = await client.get(f"{HN_API}{path}")
    response.raise_for_status()
    return response.json()


def _html_to_text(html: str | None) -> str:
    if not html:
        return ""
    from bs4 import BeautifulSoup

    text = BeautifulSoup(html, "lxml").get_text("\n")
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())


async def fetch_item(client: httpx.AsyncClient, item_id: int) -> dict[str, Any] | None:
    try:
        data = await _get_json(client, f"/item/{item_id}.json")
    except httpx.HTTPError:
        return None
    return data if isinstance(data, dict) else None


async def fetch_top_story_ids(client: httpx.AsyncClient, limit: int = 30) -> list[int]:
    ids = await _get_json(client, "/topstories.json")
    return [int(x) for x in ids[:limit]]


async def fetch_top_comments(
    client: httpx.AsyncClient,
    kid_ids: list[int] | None,
    limit: int = 8,
) -> list[dict[str, Any]]:
    if not kid_ids:
        return []

    comments: list[dict[str, Any]] = []
    for kid_id in kid_ids:
        if len(comments) >= limit:
            break
        item = await fetch_item(client, kid_id)
        if not item or item.get("type") != "comment" or item.get("deleted") or item.get("dead"):
            continue
        text = _html_to_text(item.get("text"))
        if len(text) < 40:
            continue
        comments.append(
            {
                "id": item["id"],
                "author": item.get("by") or "unknown",
                "text": text[:1200],
            }
        )
    return comments


async def fetch_top_stories(limit: int = 30, comment_limit: int = 8) -> list[dict[str, Any]]:
    timeout = httpx.Timeout(30.0, connect=10.0)
    headers = {"User-Agent": USER_AGENT}
    async with httpx.AsyncClient(timeout=timeout, headers=headers) as client:
        ids = await fetch_top_story_ids(client, limit=limit)
        items = await asyncio.gather(*(fetch_item(client, i) for i in ids))

        stories: list[dict[str, Any]] = []
        for rank, item in enumerate(items, start=1):
            if not item or item.get("type") not in {"story", "job"}:
                continue
            if item.get("dead") or item.get("deleted"):
                continue

            comments = await fetch_top_comments(client, item.get("kids"), limit=comment_limit)
            posted = datetime.fromtimestamp(item.get("time", 0), tz=timezone.utc)
            url = item.get("url") or HN_ITEM_URL.format(id=item["id"])
            stories.append(
                {
                    "rank": rank,
                    "id": item["id"],
                    "title_en": item.get("title") or "(no title)",
                    "url": url,
                    "hn_url": HN_ITEM_URL.format(id=item["id"]),
                    "score": int(item.get("score") or 0),
                    "comment_count": int(item.get("descendants") or 0),
                    "posted_at": posted.isoformat(),
                    "comments": comments,
                }
            )
        return stories
