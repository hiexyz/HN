"""Translation and summarization helpers."""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any

import httpx

USER_AGENT = "HN-Nippo/1.0 (+https://github.com/hiexyz/HN)"

CATEGORIES = [
    "AI/ML",
    "Startup/Business",
    "Security",
    "Programming",
    "Science",
    "Hardware",
    "Crypto",
    "Culture",
    "Other",
]


def _client() -> httpx.Client:
    return httpx.Client(timeout=httpx.Timeout(60.0, connect=15.0), headers={"User-Agent": USER_AGENT})


def translate_text(text: str, source: str = "en", target: str = "ja") -> str:
    """Translate text using free public endpoints (no API key)."""
    text = (text or "").strip()
    if not text:
        return ""
    # Already mostly Japanese
    if re.search(r"[\u3040-\u30ff\u4e00-\u9fff]", text) and not re.search(r"[A-Za-z]{4,}", text):
        return text

    with _client() as client:
        # 1) MyMemory
        try:
            response = client.get(
                "https://api.mymemory.translated.net/get",
                params={"q": text[:450], "langpair": f"{source}|{target}"},
            )
            if response.status_code < 400:
                data = response.json()
                translated = (data.get("responseData") or {}).get("translatedText") or ""
                # MyMemory returns INVALID QUERY / QUOTA messages as "translation"
                if (
                    translated
                    and "MYMEMORY WARNING" not in translated.upper()
                    and "INVALID" not in translated.upper()
                ):
                    return translated.strip()
        except Exception:
            pass

        # 2) Google gtx fallback
        params = {
            "client": "gtx",
            "sl": source,
            "tl": target,
            "dt": "t",
            "q": text[:4500],
        }
        response = client.get(
            "https://translate.googleapis.com/translate_a/single",
            params=params,
        )
        response.raise_for_status()
        data = response.json()
    parts = [chunk[0] for chunk in data[0] if chunk and chunk[0]]
    return "".join(parts).strip() or text


def _openrouter_chat(messages: list[dict[str, str]], max_tokens: int = 900) -> str | None:
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        return None
    model = os.getenv("OPENROUTER_MODEL", "openrouter/auto").strip() or "openrouter/auto"
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.3,
        "max_tokens": max_tokens,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/hiexyz/HN",
        "X-Title": "HN Nippo",
    }
    with _client() as client:
        response = client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=payload,
        )
        if response.status_code >= 400:
            return None
        data = response.json()
    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError, AttributeError):
        return None


def guess_category(title: str, url: str) -> str:
    blob = f"{title} {url}".lower()
    rules = [
        ("AI/ML", ["ai", "llm", "gpt", "model", "openai", "anthropic", "machine learning", "neural"]),
        ("Security", ["security", "cve", "malware", "ransomware", "hack", "breach", "vuln"]),
        ("Crypto", ["bitcoin", "crypto", "ethereum", "blockchain", "web3"]),
        ("Hardware", ["chip", "cpu", "gpu", "raspberry", "hardware", "fpga", "semiconductor"]),
        ("Science", ["nasa", "physics", "biology", "climate", "space", "research", "paper"]),
        ("Startup/Business", ["startup", "funding", "ipo", "acquires", "shopify", "layoff", "market"]),
        ("Programming", ["rust", "python", "javascript", "linux", "git", "compiler", "database", "api"]),
        ("Culture", ["book", "game", "music", "film", "essay", "history"]),
    ]
    for category, keywords in rules:
        if any(k in blob for k in keywords):
            return category
    return "Other"


def enrich_story(story: dict[str, Any], metrics: dict[str, int]) -> dict[str, Any]:
    title_en = story["title_en"]
    metrics["translate_requests"] += 1
    try:
        title_ja = translate_text(title_en)
        if not title_ja:
            raise ValueError("empty translation")
    except Exception:
        metrics["translate_failures"] += 1
        title_ja = title_en

    category = guess_category(title_en, story.get("url") or "")
    comments = story.get("comments") or []
    comment_blob = "\n\n".join(
        f"- {c['author']}: {c['text'][:500]}" for c in comments[:6]
    )

    summary_ja = ""
    editor_note = ""
    metrics["summarize_requests"] += 1

    prompt = f"""あなたはHacker Newsの日本語ダイジェスト編集者です。
次の記事について JSON だけを返してください（前後に説明文やコードフェンスを付けない）。

スキーマ:
{{
  "editor_note": "日本の読者向けに、この話題の意義を1文で",
  "summary_ja": "コメント欄の主な議論点・賛否・注目コメントを3段落程度で日本語要約",
  "category": "AI/ML|Startup/Business|Security|Programming|Science|Hardware|Crypto|Culture|Other のいずれか"
}}

タイトル: {title_en}
URL: {story.get("url")}
スコア: {story.get("score")} / コメント数: {story.get("comment_count")}

上位コメント:
{comment_blob or "(コメントなし)"}
"""
    raw = _openrouter_chat(
        [
            {"role": "system", "content": "Return only valid JSON. Language: Japanese."},
            {"role": "user", "content": prompt},
        ]
    )

    if raw:
        try:
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
                cleaned = re.sub(r"\s*```$", "", cleaned)
            parsed = json.loads(cleaned)
            summary_ja = str(parsed.get("summary_ja") or "").strip()
            editor_note = str(parsed.get("editor_note") or "").strip()
            cat = str(parsed.get("category") or "").strip()
            if cat in CATEGORIES:
                category = cat
            if summary_ja:
                metrics["summaries_success"] += 1
        except json.JSONDecodeError:
            pass

    if not summary_ja:
        # Fallback: translate a short English digest of comments
        if comments:
            english = "Discussion highlights: " + " / ".join(
                c["text"].split(". ")[0][:180] for c in comments[:3]
            )
            try:
                summary_ja = translate_text(english)
                if summary_ja:
                    metrics["summaries_success"] += 1
            except Exception:
                summary_ja = ""
        if not summary_ja:
            summary_ja = "コメント要約は現在利用できません。HNのスレッドを直接ご覧ください。"

    if not editor_note:
        editor_note = f"「{title_ja}」について、開発者コミュニティで注目が集まっています。"

    # Be gentle with the free translate endpoint across 30 stories.
    time.sleep(0.25)

    return {
        **story,
        "title_ja": title_ja,
        "summary_ja": summary_ja,
        "editor_note": editor_note,
        "category": category,
    }
