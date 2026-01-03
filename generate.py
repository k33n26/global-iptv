import requests
import os
import json
from collections import defaultdict
from datetime import datetime

IPTV_URL = "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/iptv.m3u"

OUTPUT = "playlist.m3u"
TEMP = "playlist.tmp"
STATS = "stats.json"
DIFF = "diff_stats.json"

TIMEOUT = 6

# Önceki stats varsa oku
prev_stats = {}
if os.path.exists(STATS):
    with open(STATS, "r", encoding="utf-8") as f:
        prev_stats = json.load(f)

def check_stream(url):
    """return: alive, geo_blocked"""
    try:
        r = requests.get(
            url,
            timeout=TIMEOUT,
            headers={"User-Agent": "Mozilla/5.0"}
        )
        if r.status_code in (401, 403, 451):
            return False, True
        if r.status_code != 200:
            return False, False
        txt = r.text
        if "#EXTM3U" in txt or "#EXT-X-STREAM-INF" in txt:
            return True, False
        return False, False
    except requests.exceptions.Timeout:
        return False, True
    except:
        return False, False

print("[1] IPTV list indiriliyor...")
r = requests.get(IPTV_URL, headers={"User-Agent": "Mozilla/5.0"})
lines = r.text.splitlines()

playlist = ["#EXTM3U"]

stats = {
    "total_channels": 0,
    "geo_blocked": 0,
    "by_country": defaultdict(int),
    "by_category": defaultdict(int)
}

current_channels = set()

print("[2] Stream kontrolü + GEO analiz...")
i = 0
while i < len(lines):
    line = lines[i]
    if not line.startswith("#EXTINF"):
        i += 1
        continue

    url = lines[i + 1] if i + 1 < len(lines) else ""
    alive, geo = check_stream(url)
    channel_name = line.split(",")[-1]

    if alive or geo:
        out_line = line
        if geo:
            stats["geo_blocked"] += 1
            if 'group-title="' in out_line:
                grp = out_line.split('group-title="')[1].split('"')[0]
                out_line = out_line.replace(
                    f'group-title="{grp}"',
                    f'group-title="{grp} [GEO]"'
                )
            else:
                out_line = out_line.replace(
                    "#EXTINF:-1",
                    '#EXTINF:-1 group-title="[GEO]"'
                )

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

    i += 2

if len(playlist) <= 1:
    print("❌ Playlist boş → eski liste korunuyor")
    exit(0)

print("[3] Dosyalar yazılıyor...")
with open(TEMP, "w", encoding="utf-8") as f:
    f.write("\n".join(playlist))
if os.path.exists(OUTPUT):
    os.replace(OUTPUT, OUTPUT + ".bak")
os.replace(TEMP, OUTPUT)

# stats.json yaz
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

# diff_stats.json yaz
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

    # ülke farkları
    diff["by_country"] = {}
    for c in set(list(stats["by_country"].keys()) + list(prev_stats.get("by_country", {}).keys())):
        prev_count = prev_stats.get("by_country", {}).get(c, 0)
        cur_count = stats["by_country"].get(c, 0)
        diff["by_country"][c] = cur_count - prev_count

    # kategori farkları
    diff["by_category"] = {}
    for cat in set(list(stats["by_category"].keys()) + list(prev_stats.get("by_category", {}).keys())):
        prev_count = prev_stats.get("by_category", {}).get(cat, 0)
        cur_count = stats["by_category"].get(cat, 0)
        diff["by_category"][cat] = cur_count - prev_count

with open(DIFF, "w", encoding="utf-8") as f:
    json.dump(diff, f, indent=2, ensure_ascii=False)

print("✅ playlist.m3u + stats.json + diff_stats.json güncellendi")
