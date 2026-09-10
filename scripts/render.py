"""HTML / RSS rendering for HN日報."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from jinja2 import Environment, FileSystemLoader, select_autoescape

JST = ZoneInfo("Asia/Tokyo")
ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"
DOCS = ROOT / "docs"


def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES)),
        autoescape=select_autoescape(["html", "xml"]),
    )


def slot_label(slot: str) -> str:
    return f"{int(slot):02d}:00"


def format_jst_heading(date_iso: str, slot: str) -> str:
    dt = datetime.fromisoformat(date_iso)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=JST)
    local = dt.astimezone(JST)
    return f"{local.year}年{local.month}月{local.day}日"


def ensure_dirs() -> None:
    for path in [
        DOCS,
        DOCS / "assets",
        DOCS / "archive",
        DOCS / "data",
    ]:
        path.mkdir(parents=True, exist_ok=True)


def list_archives() -> list[dict[str, str]]:
    archives: list[dict[str, str]] = []
    for path in sorted((DOCS / "data").glob("*.json"), reverse=True):
        stem = path.stem  # YYYY-MM-DD_HH
        if "_" not in stem:
            continue
        date_part, slot = stem.rsplit("_", 1)
        archives.append(
            {
                "stem": stem,
                "href": f"/archive/{stem}.html",
                "label": f"{date_part} {slot}:00",
            }
        )
    return archives


def write_snapshot(payload: dict, slot: str) -> Path:
    ensure_dirs()
    date_local = datetime.now(JST).strftime("%Y-%m-%d")
    stem = f"{date_local}_{slot}"
    data_path = DOCS / "data" / f"{stem}.json"
    data_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return data_path


def render_site(payload: dict, slot: str) -> None:
    ensure_dirs()
    env = _env()
    archives = list_archives()
    date_iso = payload.get("date") or datetime.now(JST).isoformat()
    heading_date = format_jst_heading(date_iso, slot)
    context = {
        "site_name": "HN日報",
        "site_tagline": "Hacker News を、日本語でさっと追う",
        "stories": payload.get("stories") or [],
        "slot": slot,
        "slot_label": slot_label(slot),
        "heading_date": heading_date,
        "generated_at": datetime.now(JST).isoformat(),
        "archives": archives[:60],
        "is_home": True,
    }

    index_html = env.get_template("index.html").render(**context)
    (DOCS / "index.html").write_text(index_html, encoding="utf-8")

    date_local = datetime.fromisoformat(date_iso).astimezone(JST).strftime("%Y-%m-%d")
    stem = f"{date_local}_{slot}"
    archive_context = {**context, "is_home": False, "archive_stem": stem}
    archive_html = env.get_template("index.html").render(**archive_context)
    (DOCS / "archive" / f"{stem}.html").write_text(archive_html, encoding="utf-8")

    archive_index = env.get_template("archive.html").render(
        site_name="HN日報",
        archives=archives,
        generated_at=context["generated_at"],
    )
    (DOCS / "archive" / "index.html").write_text(archive_index, encoding="utf-8")

    about = env.get_template("about.html").render(
        site_name="HN日報",
        generated_at=context["generated_at"],
    )
    (DOCS / "about.html").write_text(about, encoding="utf-8")

    feed = env.get_template("feed.xml").render(
        site_name="HN日報",
        site_tagline=context["site_tagline"],
        stories=context["stories"][:20],
        heading_date=heading_date,
        slot_label=context["slot_label"],
        generated_at=context["generated_at"],
    )
    (DOCS / "feed.xml").write_text(feed, encoding="utf-8")

    metrics_path = DOCS / "run-metrics.json"
    metrics_path.write_text(
        json.dumps(payload.get("metrics") or {}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
