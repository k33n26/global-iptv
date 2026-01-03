import requests
import os
import json
from collections import defaultdict

IPTV_URL = "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/iptv.m3u"

OUTPUT = "playlist.m3u"
TEMP = "playlist.tmp"
STATS = "stats.json"

TIMEOUT = 6

def check_stream(url):
    """
    return: alive, geo_blocked
    """
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

print("[2] Stream kontrolü + GEO analiz...")
i = 0
while i < len(lines):
    line = lines[i]

    if not line.startswith("#EXTINF"):
        i += 1
        continue

    url = lines[i + 1] if i + 1 < len(lines) else ""
    alive, geo = check_stream(url)

    if alive or geo:
        out_line = line

        # GEO etiketi ekle
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

        if 'tvg-country="' in out_line:
            c = out_line.split('tvg-country="')[1].split('"')[0]
            stats["by_country"][c] += 1

        if 'group-title="' in out_line:
            g = out_line.split('group-title="')[1].split('"')[0]
            stats["by_category"][g] += 1

    else:
        print("❌ Silindi:", line.split(",")[-1])

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

with open(STATS, "w", encoding="utf-8") as f:
    json.dump(
        {
            "total_channels": stats["total_channels"],
            "geo_blocked": stats["geo_blocked"],
            "countries": dict(stats["by_country"]),
            "categories": dict(stats["by_category"])
        },
        f,
        indent=2,
        ensure_ascii=False
    )

print("✅ playlist.m3u + stats.json güncellendi")
