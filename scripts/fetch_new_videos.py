#!/usr/bin/env python3
"""YouTube RSS 피드에서 새 영상을 가져오고 키워드로 필터링하는 스크립트."""

import json
import os
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, "config", "channels.json")
PROCESSED_PATH = os.path.join(BASE_DIR, "data", "processed_videos.json")
RSS_URL_TEMPLATE = "https://www.youtube.com/feeds/videos.xml?channel_id={}"

NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "yt": "http://www.youtube.com/xml/schemas/2015",
    "media": "http://search.yahoo.com/mrss/",
}


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def load_processed():
    if not os.path.exists(PROCESSED_PATH):
        return {"video_ids": []}
    with open(PROCESSED_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_processed(data):
    os.makedirs(os.path.dirname(PROCESSED_PATH), exist_ok=True)
    with open(PROCESSED_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def fetch_rss(channel_id):
    url = RSS_URL_TEMPLATE.format(channel_id)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    resp = urllib.request.urlopen(req, timeout=15)
    return ET.fromstring(resp.read().decode("utf-8"))


def parse_entries(root, channel_name):
    entries = []
    for entry in root.findall("atom:entry", NS):
        video_id_el = entry.find("yt:videoId", NS)
        title_el = entry.find("atom:title", NS)
        published_el = entry.find("atom:published", NS)
        media_group = entry.find("media:group", NS)
        desc_el = media_group.find("media:description", NS) if media_group is not None else None

        video_id = video_id_el.text if video_id_el is not None else None
        if not video_id:
            continue

        entries.append({
            "video_id": video_id,
            "title": title_el.text if title_el is not None else "",
            "published": published_el.text if published_el is not None else "",
            "description": (desc_el.text or "")[:500] if desc_el is not None else "",
            "url": f"https://www.youtube.com/watch?v={video_id}",
            "channel_name": channel_name,
        })
    return entries


def matches_keywords(entry, keywords):
    text = (entry["title"] + " " + entry["description"]).lower()
    return any(kw.lower() in text for kw in keywords)


def mark_processed(video_id):
    data = load_processed()
    if video_id not in data["video_ids"]:
        data["video_ids"].append(video_id)
        # 최근 500개만 유지
        if len(data["video_ids"]) > 500:
            data["video_ids"] = data["video_ids"][-500:]
        save_processed(data)


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--mark-processed":
        if len(sys.argv) < 3:
            print("Usage: --mark-processed <video_id>", file=sys.stderr)
            sys.exit(1)
        mark_processed(sys.argv[2])
        print(json.dumps({"marked": sys.argv[2]}))
        return

    config = load_config()
    processed = load_processed()
    processed_ids = set(processed.get("video_ids", []))
    keywords = config.get("keywords", [])
    max_videos = config.get("max_videos_per_run", 5)

    new_videos = []

    for channel in config["channels"]:
        try:
            root = fetch_rss(channel["channel_id"])
            entries = parse_entries(root, channel["name"])
            for entry in entries:
                if entry["video_id"] in processed_ids:
                    continue
                if not matches_keywords(entry, keywords):
                    continue
                new_videos.append(entry)
        except Exception as e:
            print(f"[WARN] {channel['name']} RSS 조회 실패: {e}", file=sys.stderr)

    # 최신순 정렬, 최대 개수 제한
    new_videos.sort(key=lambda x: x.get("published", ""), reverse=True)
    new_videos = new_videos[:max_videos]

    print(json.dumps(new_videos, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
