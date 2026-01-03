import asyncio
import aiohttp
import os
import json
from collections import defaultdict
from datetime import datetime

BASE_DIR = "/app"
IPTV_URL = "https://iptv-org.github.io/iptv/index.m3u"

OUTPUT = os.path.join(BASE_DIR, "playlist.m3u")
TEMP = os.path.join(BASE_DIR, "playlist.tmp")
STATS = os.path.join(BASE_DIR, "stats.json")
DIFF = os.path.join(BASE_DIR, "diff_stats.json")

TIMEOUT = 5  # saniye
MAX_CONCURRENT = 50  # aynı anda kaç kanal kontrol edilsin

prev_stats = {}
if os.path.exists(STATS):
    with open(STATS, "r", encoding="utf-8") as f:
        prev_stats = json.load(f)

print("[1] IPTV list indiriliyor...")
import requests
lines = requests.get(IPTV_URL, headers={"User-Agent": "Mozilla/5.0"}).text.splitlines()

playlist = ["#EXTM3U"]
playlist.append("#EXTINF:-1,tv-test")  # dummy
playlist.append("https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8")

stats = {
    "total_channels": 1,
    "geo_blocked": 0,
    "by_country": defaultdict(int),
    "by_category": defaultdict(int)
}

current_channels = {"tv-test"}

# async kontrol fonksiyonu
async def check_stream(session, line, url):
    channel_name = line.split(",")[-1]
    try:
        async with session.get(url, timeout=TIMEOUT) as resp:
            text = await resp.text()
            alive = resp.status == 200 and ("#EXTM3U" in text or "#EXT-X-STREAM-INF" in text)
            geo = resp.status in (401, 403, 451)
            return line, url, alive, geo, channel_name
    except:
        return line, url, False, True, channel_name

async def main():
    tasks = []
    async with aiohttp.ClientSession(headers={"User-Agent": "Mozilla/5.0"}) as session:
        for i in range(0, len(lines), 2):
            line = lines[i]
            if not line.startswith("#EXTINF"):
                continue
            url = lines[i + 1] if i + 1 < len(lines) else ""
            tasks.append(check_stream(session, line, url))

        sem = asyncio.Semaphore(MAX_CONCURRENT)
        async def sem_task(task):
            async with sem:
                return await task

        results = await asyncio.gather(*[sem_task(t) for t in tasks])

        for line, url, alive, geo, channel_name in results:
            if alive or geo:
                out_line = line
                if geo:
                    stats["geo_blocked"] += 1
                    if 'group-title="' in out_line:
                        grp = out_line.split('group-title="')[1].split('"')[0]
                        out_line = out_line.replace(f'group-title="{grp}"', f'group-title="{grp} [GEO]"')
                    else:
                        out_line = out_line.replace("#EXTINF:-1", '#EXTINF:-1 group-title="[GEO]"')

                playlist.append(out_line)
                playlist.append(url)
                stats["total_channels"] += 1
                current_channels.add(channel_name)

                if 'tvg-country="' in out_line:
                    c = out_line.split('tvg-country="')[1].split('"')[0]
                    stats["by_country"][c] += 1
                if 'group-title="' in out_line:
                    g = out_line.split('group-title="')[1].split('"')[0]
                    stats["by_category"][g] += 1
            else:
                print("❌ Silindi:", channel_name)

asyncio.run(main())

# Dosyaları yaz
with open(TEMP, "w", encoding="utf-8") as f:
    f.write("\n".join(playlist))

if os.path.exists(OUTPUT):
    os.replace(OUTPUT, OUTPUT + ".bak")
os.replace(TEMP, OUTPUT)

with open(STATS, "w", encoding="utf-8") as f:
    json.dump(
        {
            "total_channels": stats["total_channels"],
            "geo_blocked": stats["geo_blocked"],
            "countries": dict(stats["by_country"]),
            "categories": dict(stats["by_category"]),
            "channels_set": list(current_channels)
        },
        f,
        indent=2,
        ensure_ascii=False
    )

diff = {
    "run_time": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
    "added": 0,
    "removed": 0,
    "geo_added": 0,
    "geo_removed": 0,
    "added_channels": [],
    "removed_channels": [],
    "by_country": {},
    "by_category": {}
}

if prev_stats:
    prev_set = set(prev_stats.get("channels_set", []))
    added = current_channels - prev_set
    removed = prev_set - current_channels
    diff["added"] = len(added)
    diff["removed"] = len(removed)
    diff["added_channels"] = list(added)
    diff["removed_channels"] = list(removed)

    diff["geo_added"] = sum(1 for ch in added if "[GEO]" in ch)
    diff["geo_removed"] = sum(1 for ch in removed if "[GEO]" in ch)

    diff["by_country"] = {}
    for c in set(list(stats["by_country"].keys()) + list(prev_stats.get("by_country", {}).keys())):
        prev_count = prev_stats.get("by_country", {}).get(c, 0)
        cur_count = stats["by_country"].get(c, 0)
        diff["by_country"][c] = cur_count - prev_count

    diff["by_category"] = {}
    for cat in set(list(stats["by_category"].keys()) + list(prev_stats.get("by_category", {}).keys())):
        prev_count = prev_stats.get("by_category", {}).get(cat, 0)
        cur_count = stats["by_category"].get(cat, 0)
        diff["by_category"][cat] = cur_count - prev_count

with open(DIFF, "w", encoding="utf-8") as f:
    json.dump(diff, f, indent=2, ensure_ascii=False)

print("✅ playlist.m3u + stats.json + diff_stats.json güncellendi")
