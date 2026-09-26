#!/usr/bin/env python3
"""Poster rows for the Homepage "Coming Soon" and "Recently Downloaded" cards.

Homepage has no widget that shows images (customapi is text only), so this
serves two small HTML pages that Homepage embeds with its `iframe` widget:

    /coming-soon.html   Sonarr + Radarr calendar, today .. +DAYS_AHEAD
                        (static, regenerated every REFRESH_SECONDS)
    /recent.html        Sonarr + Radarr imports, last DAYS_BACK days
                        (built live on every request, so an import shows up
                        on the next dashboard load)

Both are one horizontal row of posters, a title under each and a short line
("S02E05 · Thu", "Digital · Fri", "3 episodes · Yesterday"). Episodes are
grouped by show, so a binge of eight episodes is one tile, not eight.

Posters come from each app's own /MediaCover cache (the 250px variant, no
auth needed), with the TVDB/TMDB URL as fallback, and are kept on the
media-posters volume so the dashboard never hits the internet for them.
Recently downloaded tiles link into Emby when EMBY_API_KEY is set and Emby
has the item (its web UI, also on phones; the Emby app is not opened);
everything else links to Sonarr/Radarr.

API keys are read from Sonarr's and Radarr's own config.xml (mounted
read-only), so there is nothing to put in 1Password. Standard library only, so it runs on a stock
python:alpine image.
"""

import html
import json
import os
import re
import sys
import threading
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

DOMAIN = os.environ["DOMAIN"]
SONARR_URL = os.environ.get("SONARR_URL", "http://sonarr:8989")
RADARR_URL = os.environ.get("RADARR_URL", "http://radarr:7878")
SONARR_CONFIG = os.environ.get("SONARR_CONFIG", "/arr/sonarr/config.xml")
RADARR_CONFIG = os.environ.get("RADARR_CONFIG", "/arr/radarr/config.xml")
EMBY_URL = os.environ.get("EMBY_URL", "http://emby:8096")
EMBY_API_KEY = os.environ.get("EMBY_API_KEY", "")
DAYS_AHEAD = int(os.environ.get("DAYS_AHEAD", "7"))
DAYS_BACK = int(os.environ.get("DAYS_BACK", "7"))
REFRESH_SECONDS = int(os.environ.get("REFRESH_SECONDS", "3600"))
OUT = Path(os.environ.get("OUT_DIR", "/data"))
PORT = int(os.environ.get("PORT", "8080"))
# Re-download a cached poster after this long, in case the artwork changed.
POSTER_MAX_AGE = 7 * 24 * 3600

POSTERS = OUT / "posters"


def log(msg):
    print(f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}", file=sys.stderr, flush=True)


def api_key(config_path):
    m = re.search(r"<ApiKey>([^<]+)</ApiKey>", Path(config_path).read_text())
    if not m:
        raise RuntimeError(f"no <ApiKey> in {config_path}")
    return m.group(1)


def get_json(base, path, params=None, headers=None):
    url = base + path + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def arr_get(base, config, path, params=None):
    return get_json(base, path, params, {"X-Api-Key": api_key(config)})


def iso(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse(stamp):
    return datetime.fromisoformat(stamp.replace("Z", "+00:00")).astimezone()


def day_label(d, today):
    delta = (d - today).days
    return {-1: "Yesterday", 0: "Today", 1: "Tomorrow"}.get(delta, f"{d:%a}")


def episode_label(eps):
    """(season, episode) pairs -> 'S02E05', 'S02E05–E07' or 'N episodes'."""
    eps = sorted(set(eps))
    if len(eps) == 1:
        return "S%02dE%02d" % eps[0]
    seasons = {s for s, _ in eps}
    nums = [e for _, e in eps]
    if len(seasons) == 1 and nums == list(range(nums[0], nums[-1] + 1)):
        return "S%02dE%02d–E%02d" % (eps[0][0], nums[0], nums[-1])
    return f"{len(eps)} episodes"


def poster(kind, item):
    """Cache the item's poster locally and return its path relative to OUT."""
    name = f"{kind}{item['id']}.jpg"
    dest = POSTERS / name
    if dest.exists() and time.time() - dest.stat().st_mtime < POSTER_MAX_AGE:
        return f"posters/{name}"
    base = SONARR_URL if kind == "s" else RADARR_URL
    remote = next(
        (i.get("remoteUrl") for i in item.get("images", []) if i["coverType"] == "poster"),
        None,
    )
    # TMDB serves any size; 'original' is several MB.
    if remote and "image.tmdb.org" in remote:
        remote = remote.replace("/original/", "/w342/")
    for url in (f"{base}/MediaCover/{item['id']}/poster-250.jpg", remote):
        if not url:
            continue
        try:
            with urllib.request.urlopen(url, timeout=30) as resp:
                data = resp.read()
            tmp = dest.with_suffix(".tmp")
            tmp.write_bytes(data)
            tmp.replace(dest)
            return f"posters/{name}"
        except Exception as e:  # noqa: BLE001 - try the next source
            log(f"poster {url}: {e}")
    return f"posters/{name}" if dest.exists() else None


def sonarr_link(series):
    return f"https://sonarr.{DOMAIN}/series/{series['titleSlug']}"


def radarr_link(movie):
    return f"https://radarr.{DOMAIN}/movie/{movie['titleSlug']}"


# --- Coming soon ------------------------------------------------------------


def coming_tv(start, end, today):
    eps = arr_get(
        SONARR_URL,
        SONARR_CONFIG,
        "/api/v3/calendar",
        {"start": iso(start), "end": iso(end), "includeSeries": "true"},
    )
    shows = {}
    for e in eps:
        if not e.get("airDateUtc"):
            continue
        s = shows.setdefault(e["seriesId"], {"series": e["series"], "eps": [], "when": None, "ready": True})
        s["eps"].append((e["seasonNumber"], e["episodeNumber"]))
        when = parse(e["airDateUtc"])
        s["when"] = min(s["when"] or when, when)
        s["ready"] &= e["hasFile"]
    return [
        {
            "when": s["when"],
            "title": s["series"]["title"],
            "sub": f"{episode_label(s['eps'])} · {day_label(s['when'].date(), today)}",
            "img": poster("s", s["series"]),
            "href": sonarr_link(s["series"]),
            "ready": s["ready"],
        }
        for s in shows.values()
    ]


RELEASES = (("inCinemas", "In cinemas"), ("digitalRelease", "Digital"), ("physicalRelease", "Blu-ray"))


def coming_movies(start, end, today):
    movies = arr_get(
        RADARR_URL,
        RADARR_CONFIG,
        "/api/v3/calendar",
        {"start": iso(start), "end": iso(end)},
    )
    out = []
    for m in movies:
        # A movie is in the calendar if any of its release dates is in range;
        # show the earliest one that is.
        hits = []
        for field, label in RELEASES:
            if m.get(field):
                d = parse(m[field]).date()
                if start.date() <= d < end.date():
                    hits.append((d, label))
        if not hits:
            continue
        d, label = min(hits)
        out.append(
            {
                "when": datetime.combine(d, datetime.min.time()).astimezone(),
                "title": m["title"],
                "sub": f"{label} · {day_label(d, today)}",
                "img": poster("m", m),
                "href": radarr_link(m),
                "ready": m.get("hasFile", False),
            }
        )
    return out


# --- Recently downloaded ----------------------------------------------------


def emby_links(provider_ids):
    """{'tvdb.123': web_url, ...} for items Emby already has."""
    if not EMBY_API_KEY or not provider_ids:
        return {}
    headers = {"X-Emby-Token": EMBY_API_KEY}
    server = get_json(EMBY_URL, "/emby/System/Info/Public")["Id"]
    items = get_json(
        EMBY_URL,
        "/emby/Items",
        {
            "Recursive": "true",
            "IncludeItemTypes": "Series,Movie",
            "AnyProviderIdEquals": ",".join(sorted(provider_ids)),
            "Fields": "ProviderIds",
        },
        headers,
    )["Items"]
    links = {}
    for i in items:
        pids = {k.lower(): v for k, v in i.get("ProviderIds", {}).items()}
        key = f"tvdb.{pids['tvdb']}" if i["Type"] == "Series" and "tvdb" in pids else f"tmdb.{pids.get('tmdb')}"
        links[key] = f"https://emby.{DOMAIN}/web/index.html#!/item?id={i['Id']}&serverId={server}"
    return links


def recent_tv(since, today):
    hist = arr_get(
        SONARR_URL,
        SONARR_CONFIG,
        "/api/v3/history/since",
        {
            "date": iso(since),
            "eventType": "downloadFolderImported",
            "includeSeries": "true",
            "includeEpisode": "true",
        },
    )
    shows = {}
    for h in hist:
        if "series" not in h or "episode" not in h:
            continue
        s = shows.setdefault(h["seriesId"], {"series": h["series"], "eps": [], "when": None})
        s["eps"].append((h["episode"]["seasonNumber"], h["episode"]["episodeNumber"]))
        when = parse(h["date"])
        s["when"] = max(s["when"] or when, when)
    return [
        {
            "when": s["when"],
            "title": s["series"]["title"],
            "sub": f"{episode_label(s['eps'])} · {day_label(s['when'].date(), today)}",
            "img": poster("s", s["series"]),
            "href": sonarr_link(s["series"]),
            "pid": f"tvdb.{s['series']['tvdbId']}",
        }
        for s in shows.values()
    ]


def recent_movies(since, today):
    hist = arr_get(
        RADARR_URL,
        RADARR_CONFIG,
        "/api/v3/history/since",
        {"date": iso(since), "eventType": "downloadFolderImported", "includeMovie": "true"},
    )
    movies = {}
    for h in hist:
        if "movie" not in h:
            continue
        when = parse(h["date"])
        m = movies.setdefault(h["movieId"], {"movie": h["movie"], "when": when})
        m["when"] = max(m["when"], when)
    return [
        {
            "when": m["when"],
            "title": m["movie"]["title"],
            "sub": f"Movie · {day_label(m['when'].date(), today)}",
            "img": poster("m", m["movie"]),
            "href": radarr_link(m["movie"]),
            "pid": f"tmdb.{m['movie']['tmdbId']}",
        }
        for m in movies.values()
    ]


# --- Rendering --------------------------------------------------------------

CSS = """
* { box-sizing: border-box; margin: 0; }
/* Transparent so the Homepage card shows through. No color-scheme here: the
   iframe's parent is scheme-light, and a mismatch paints the frame opaque. */
html, body { background: transparent; }
body {
  font: 12px/1.3 ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
  color: rgb(226 232 240);
  overflow-y: hidden;
}
.row {
  display: flex; gap: 12px; padding: 8px 8px 6px;
  overflow-x: auto; scrollbar-width: thin;
  scrollbar-color: rgb(255 255 255 / .2) transparent;
}
a.tile { flex: 0 0 104px; min-width: 0; color: inherit; text-decoration: none; }
.art {
  position: relative; width: 104px; aspect-ratio: 2 / 3; border-radius: 4px;
  overflow: hidden; background: rgb(255 255 255 / .08);
  box-shadow: 0 1px 3px rgb(0 0 0 / .4); transition: transform .15s;
}
a.tile:hover .art { transform: translateY(-2px); }
.art img { width: 100%; height: 100%; object-fit: cover; display: block; }
.art .none { display: grid; place-items: center; height: 100%; padding: 6px;
  text-align: center; opacity: .6; }
.ready { position: absolute; top: 4px; right: 4px; font-size: 10px;
  padding: 1px 5px; border-radius: 3px; background: rgb(22 163 74 / .9); color: #fff; }
.title { margin-top: 5px; font-weight: 600; overflow: hidden;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }
.sub { margin-top: 1px; opacity: .65; }
.empty { padding: 24px 12px; opacity: .6; }
.err { padding: 0 8px; color: rgb(248 113 113); font-size: 11px; }
"""


def tile(t):
    esc = html.escape
    art = (
        f'<img src="{esc(t["img"])}" alt="" loading="lazy">'
        if t.get("img")
        else f'<div class="none">{esc(t["title"])}</div>'
    )
    ready = '<span class="ready">Ready</span>' if t.get("ready") else ""
    return (
        f'<a class="tile" href="{esc(t["href"])}" target="_blank" rel="noopener" '
        f'title="{esc(t["title"])} — {esc(t["sub"])}">'
        f'<div class="art">{art}{ready}</div>'
        f'<div class="title">{esc(t["title"])}</div>'
        f'<div class="sub">{esc(t["sub"])}</div></a>'
    )


def render_page(name, tiles, empty, errors):
    body = (
        f'<div class="row">{"".join(tile(t) for t in tiles)}</div>'
        if tiles
        else f'<div class="empty">{html.escape(empty)}</div>'
    )
    errs = "".join(f'<div class="err">{html.escape(e)}</div>' for e in errors)
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        f"<title>{html.escape(name)}</title><style>{CSS}</style></head>"
        f"<body>{body}{errs}</body></html>"
    )


def write_page(name, *args):
    tmp = OUT / f".{name}.tmp"
    tmp.write_text(render_page(name, *args))
    tmp.replace(OUT / name)


def collect(sources):
    """Run each source; a failing app becomes an error line, not a blank page."""
    tiles, errors = [], []
    for label, fn in sources:
        try:
            tiles += fn()
        except Exception as e:  # noqa: BLE001
            log(f"{label}: {e}")
            errors.append(f"{label} unavailable: {e}")
    return tiles, errors


def refresh():
    now = datetime.now().astimezone()
    today = now.date()
    midnight = datetime.combine(today, datetime.min.time()).astimezone()
    end = midnight + timedelta(days=DAYS_AHEAD + 1)

    tiles, errors = collect(
        [
            ("Sonarr", lambda: coming_tv(midnight, end, today)),
            ("Radarr", lambda: coming_movies(midnight, end, today)),
        ]
    )
    tiles.sort(key=lambda t: t["when"])
    write_page("coming-soon.html", tiles, f"Nothing scheduled in the next {DAYS_AHEAD} days", errors)
    log(f"refreshed ({date.today()})")


def recent_page():
    """Built per request: two history calls and one Emby lookup, well under a
    second once the posters are cached."""
    now = datetime.now().astimezone()
    today = now.date()
    since = now - timedelta(days=DAYS_BACK)
    tiles, errors = collect(
        [
            ("Sonarr", lambda: recent_tv(since, today)),
            ("Radarr", lambda: recent_movies(since, today)),
        ]
    )
    try:
        links = emby_links({t["pid"] for t in tiles})
        for t in tiles:
            if t["pid"] in links:
                t["href"] = links[t["pid"]]
    except Exception as e:  # noqa: BLE001 - fall back to Sonarr/Radarr links
        log(f"Emby: {e}")
    tiles.sort(key=lambda t: t["when"], reverse=True)
    return render_page("recent.html", tiles, f"Nothing downloaded in the last {DAYS_BACK} days", errors)


def loop():
    while True:
        try:
            refresh()
        except Exception as e:  # noqa: BLE001 - keep serving the last pages
            log(f"refresh failed: {e}")
        time.sleep(REFRESH_SECONDS)


class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path.split("?")[0] == "/recent.html":
            return self.send_recent(head=False)
        return super().do_GET()

    def do_HEAD(self):
        if self.path.split("?")[0] == "/recent.html":
            return self.send_recent(head=True)
        return super().do_HEAD()

    def send_recent(self, head):
        try:
            body = recent_page().encode()
        except Exception as e:  # noqa: BLE001
            log(f"recent.html: {e}")
            self.send_error(502, "recent.html failed")
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if not head:
            self.wfile.write(body)

    def end_headers(self):
        # Pages change every refresh; posters are stable per item.
        if self.path.split("?")[0].endswith(".html"):
            self.send_header("Cache-Control", "no-cache")
        else:
            self.send_header("Cache-Control", "public, max-age=86400")
        super().end_headers()

    def log_message(self, *_):  # keep container logs quiet
        pass


if __name__ == "__main__":
    POSTERS.mkdir(parents=True, exist_ok=True)
    threading.Thread(target=loop, daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", PORT), partial(Handler, directory=str(OUT))).serve_forever()
