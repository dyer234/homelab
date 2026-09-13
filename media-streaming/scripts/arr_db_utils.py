#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["rich>=13"]
# ///
"""Bulk maintenance for the Radarr/Sonarr libraries in this homelab stack.

Radarr and Sonarr keep the library and the configuration in one SQLite database, but
behind separate API surfaces. Every command here touches only the library, so indexers,
download clients, quality/release profiles and root folders always survive.

Media files on disk are never removed: every delete sends deleteFiles=false.

Libraries are addressed as `all`, `movies` (Radarr) or `tv` (Sonarr).

Every command is a dry run by default; changes need --apply, and purge additionally
requires typing a confirmation phrase.

Commands:
  status [all|movies|tv]    read-only overview of libraries, monitoring and settings
  purge  <all|movies|tv>    delete library entries, keeping settings and files on disk
  monitor                   re-apply a monitoring policy to TV series (Sonarr only)

Examples:
  ./arr_db_utils.py status                     # what is there right now
  ./arr_db_utils.py purge movies               # dry run: what clearing movies would do
  ./arr_db_utils.py purge movies --apply       # clear Radarr only
  ./arr_db_utils.py purge all --apply          # clear both libraries
  ./arr_db_utils.py monitor                    # dry run: switch TV to Future Episodes
  ./arr_db_utils.py monitor --apply            # stop hunting the back catalogue
  ./arr_db_utils.py monitor --monitor all --apply          # undo: monitor everything
  ./arr_db_utils.py monitor --series 6 21 --apply          # only these series ids
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.prompt import Confirm, Prompt
from rich.table import Table

CONFIRM_PHRASE = "delete me"
COMMAND_TIMEOUT = 180
MEDIA_STREAMING = Path(__file__).resolve().parent.parent
CONFIG_DIR = MEDIA_STREAMING / "config"

# Sonarr MonitorTypes, as accepted by POST /api/v3/seasonpass. "future" is the UI's
# "Future Episodes": only episodes that have not aired yet stay monitored.
MONITOR_TYPES = (
    "future",
    "missing",
    "existing",
    "all",
    "none",
    "firstSeason",
    "lastSeason",
    "latestSeason",
    "pilot",
    "recent",
    "monitorSpecials",
    "unmonitorSpecials",
)

console = Console()


class ApiError(RuntimeError):
    pass


@dataclass
class App:
    """One *arr instance. Radarr and Sonarr name the same concepts differently, so that is data."""

    name: str  # container name, also the config/<name> directory
    port: int
    resource: str  # "movie" / "series" — the library endpoint and editor prefix
    label: str  # human word for one library entry
    plural: str
    ids_field: str  # editor payload key holding the id list
    exclusion_field: str  # editor payload key for the list-exclusion flag
    title_of: object  # item -> display title
    settings_endpoints: tuple[str, ...]
    has_episodes: bool  # only Sonarr has per-episode monitoring
    api_key: str = ""
    library: list[dict] = field(default_factory=list)
    settings_before: dict[str, int] = field(default_factory=dict)
    stats_before: dict[str, int] = field(default_factory=dict)
    total_entries: int = 0


APPS = {
    "radarr": App(
        name="radarr",
        port=7878,
        resource="movie",
        label="movie",
        plural="movies",
        ids_field="movieIds",
        exclusion_field="addImportExclusion",
        title_of=lambda m: f"{m.get('title', '?')} ({m.get('year') or '?'})",
        settings_endpoints=(
            "indexer",
            "downloadclient",
            "qualityprofile",
            "rootfolder",
            "importlist",
            "notification",
            "customformat",
        ),
        has_episodes=False,
    ),
    "sonarr": App(
        name="sonarr",
        port=8989,
        resource="series",
        label="series",
        plural="series",
        ids_field="seriesIds",
        exclusion_field="addImportListExclusion",
        title_of=lambda s: s.get("title", "?"),
        settings_endpoints=(
            "indexer",
            "downloadclient",
            "qualityprofile",
            "rootfolder",
            "importlist",
            "notification",
            "customformat",
            "releaseprofile",
        ),
        has_episodes=True,
    ),
}


# Libraries are addressed the way they are talked about, not by container name.
TARGETS = {"all": ("radarr", "sonarr"), "movies": ("radarr",), "tv": ("sonarr",)}


# --------------------------------------------------------------------------- api


def read_api_key(app: App) -> str:
    """Pull <ApiKey> out of the app's config.xml so no secret lives in this file."""
    config_xml = CONFIG_DIR / app.name / "config.xml"
    if not config_xml.is_file():
        raise ApiError(f"no config.xml at {config_xml}")
    key = ET.parse(config_xml).getroot().findtext("ApiKey")
    if not key:
        raise ApiError(f"no <ApiKey> in {config_xml}")
    return key.strip()


def api(app: App, path: str, method: str = "GET", body: dict | None = None):
    """Call the app's v3 API.

    Neither container publishes a host port — only Traefik fronts them — so requests go
    in through `docker exec <container> curl` rather than over the host network.
    """
    cmd = [
        "docker", "exec", app.name,
        "curl", "-sS", "-m", "120",
        "-w", "\n%{http_code}",
        "-X", method,
        "-H", f"X-Api-Key: {app.api_key}",
        "-H", "Content-Type: application/json",
    ]
    if body is not None:
        cmd += ["-d", json.dumps(body)]
    cmd.append(f"http://localhost:{app.port}/api/v3/{path}")

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise ApiError(f"{app.name}: {method} {path} failed: {proc.stderr.strip() or proc.returncode}")

    payload, _, status = proc.stdout.rpartition("\n")
    status = status.strip()
    if not status.isdigit():
        raise ApiError(f"{app.name}: {method} {path} gave no status code")
    code = int(status)
    if code >= 400:
        raise ApiError(f"{app.name}: {method} {path} -> HTTP {code} {payload.strip()[:200]}")
    if not payload.strip():
        return None
    try:
        return json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ApiError(f"{app.name}: {method} {path} returned non-JSON: {exc}") from exc


def count(value) -> int:
    return len(value) if isinstance(value, list) else 0


def load(app: App) -> None:
    """Fetch everything needed to describe the app, before anything is changed."""
    app.api_key = read_api_key(app)
    status = api(app, "system/status")
    console.print(f"  [green]connected[/] {status.get('appName')} {status.get('version')}")
    app.library = api(app, app.resource) or []
    app.settings_before = {ep: count(api(app, ep)) for ep in app.settings_endpoints}


def queue_size(app: App) -> int:
    return (api(app, "queue") or {}).get("totalRecords", 0)


def run_command(app: App, name: str, wait: bool) -> None:
    """Fire an *arr command, optionally blocking until it reports completion."""
    command = api(app, "command", "POST", {"name": name})
    if not wait:
        return
    command_id = (command or {}).get("id")
    if command_id is None:
        raise ApiError(f"{app.name}: {name} command returned no id")
    deadline = time.monotonic() + COMMAND_TIMEOUT
    while time.monotonic() < deadline:
        state = api(app, f"command/{command_id}") or {}
        if state.get("status") == "completed":
            return
        if state.get("status") in {"failed", "aborted"}:
            raise ApiError(f"{app.name}: {name} {state.get('status')}: {str(state.get('exception', ''))[:200]}")
        time.sleep(2)
    raise ApiError(f"{app.name}: {name} did not finish within {COMMAND_TIMEOUT}s")


def backup(apps: list[App], skip: bool) -> None:
    if skip:
        console.print("[yellow]Skipping backup as requested.[/]")
        return
    console.print("\n[bold]Backing up[/]")
    for app in apps:
        run_command(app, "Backup", wait=True)
        console.print(f"  [green]backup written[/] to config/{app.name}/Backups/manual/")


# ------------------------------------------------------------------- inspection


def episode_stats(app: App) -> dict[str, int]:
    """Count monitored episodes, split by whether they have already aired.

    Aired-and-monitored is the number Sonarr actively hunts for; switching to Future
    Episodes is exactly the operation that drives it to zero.
    """
    now = datetime.now(timezone.utc).isoformat()
    stats = {"total": 0, "unaired": 0, "monitored": 0, "monitored_aired": 0, "monitored_future": 0}
    with Progress(
        SpinnerColumn(), TextColumn("[dim]scanning episodes"), BarColumn(), TextColumn("{task.completed}/{task.total}"),
        console=console, transient=True,
    ) as progress:
        task = progress.add_task("", total=len(app.library))
        for series in app.library:
            for episode in api(app, f"episode?seriesId={series['id']}") or []:
                stats["total"] += 1
                has_aired = (episode.get("airDateUtc") or "9999") < now
                if not has_aired:
                    stats["unaired"] += 1
                if not episode.get("monitored"):
                    continue
                stats["monitored"] += 1
                if has_aired:
                    stats["monitored_aired"] += 1
                else:
                    stats["monitored_future"] += 1
            progress.advance(task)
    return stats


def media_counts() -> dict[str, int]:
    """Count top-level entries in the media dirs, so we can prove files were kept."""
    media_host = "./media"
    env = MEDIA_STREAMING / ".env"
    if env.is_file():
        for line in env.read_text().splitlines():
            if line.startswith("MEDIA_HOST="):
                media_host = line.split("=", 1)[1].strip()
    root = (MEDIA_STREAMING / media_host).resolve() if media_host.startswith(".") else Path(media_host)
    counts = {}
    for sub in ("movies", "tv"):
        path = root / sub
        counts[sub] = len([p for p in path.iterdir() if not p.name.startswith(".")]) if path.is_dir() else -1
    return counts


def settings_table(apps: list[App], title: str) -> Table:
    table = Table(title=title, header_style="bold")
    table.add_column("Setting")
    for app in apps:
        table.add_column(app.name, justify="right")
    for endpoint in sorted({ep for app in apps for ep in app.settings_endpoints}):
        table.add_row(endpoint, *[str(app.settings_before.get(endpoint, "—")) for app in apps])
    return table


# ---------------------------------------------------------------- verification


class Checks:
    """Collects pass/fail rows so a command can report everything before exiting."""

    def __init__(self, title: str) -> None:
        self.table = Table(title=title, header_style="bold")
        self.table.add_column("Check")
        self.table.add_column("Expected", justify="right")
        self.table.add_column("Actual", justify="right")
        self.table.add_column("Result")
        self.ok = True

    def add(self, check: str, expected, actual) -> None:
        passed = expected == actual
        self.ok = self.ok and passed
        self.table.add_row(check, str(expected), str(actual), "[green]pass[/]" if passed else "[bold red]FAIL[/]")

    def info(self, check: str, expected, actual) -> None:
        """Report a value without gating the exit code on it."""
        self.table.add_row(check, str(expected), str(actual), "[dim]info[/]")

    def settings_preserved(self, apps: list[App]) -> None:
        for app in apps:
            for endpoint, before in app.settings_before.items():
                self.add(f"{app.name} {endpoint} preserved", before, count(api(app, endpoint)))

    def report(self) -> bool:
        console.print(self.table)
        return self.ok


# -------------------------------------------------------------------- commands


def cmd_status(apps: list[App], args) -> int:
    table = Table(title="Library", header_style="bold")
    table.add_column("App")
    table.add_column("Entries", justify="right")
    table.add_column("Queue", justify="right")
    for app in apps:
        table.add_row(app.name, str(len(app.library)), str(queue_size(app)))
    console.print(table)

    for app in apps:
        if not app.has_episodes or not app.library:
            continue
        stats = episode_stats(app)
        episodes = Table(title=f"{app.name} episode monitoring", header_style="bold")
        episodes.add_column("Metric")
        episodes.add_column("Count", justify="right")
        episodes.add_row("total episodes", str(stats["total"]))
        episodes.add_row("monitored", str(stats["monitored"]))
        episodes.add_row("monitored, already aired", f"[yellow]{stats['monitored_aired']}[/]")
        episodes.add_row("monitored, not yet aired", str(stats["monitored_future"]))
        console.print(episodes)

    console.print(settings_table(apps, "Settings"))
    media = media_counts()
    console.print(f"On disk: media/movies={media['movies']} entries, media/tv={media['tv']} entries.")
    return 0


def cmd_purge(apps: list[App], args) -> int:
    media_before = media_counts()

    for app in apps:
        table = Table(
            title=f"{app.name}: {len(app.library)} {app.plural} would be removed",
            header_style="bold",
        )
        table.add_column("#", justify="right", style="dim")
        table.add_column("Title")
        for index, item in enumerate(app.library, start=1):
            table.add_row(str(index), str(app.title_of(item)))
        if not app.library:
            table.add_row("", "[dim]nothing to delete[/]")
        console.print(table)

    console.print(settings_table(apps, "Settings that must survive unchanged"))
    console.print(
        f"On disk now: media/movies={media_before['movies']} entries, "
        f"media/tv={media_before['tv']} entries — these are [bold]kept[/]."
    )

    if not args.apply:
        console.print("\n[bold cyan]Dry run — nothing was changed.[/] Re-run with --apply to delete.")
        return 0

    if not check_queues(apps, args.force):
        return 1

    summary = ", ".join(f"{len(app.library)} {app.plural} from {app.name}" for app in apps)
    console.print()
    console.print(
        Panel(
            f"About to delete [bold red]{summary}[/].\n\n"
            "Settings (indexers, download clients, quality/release profiles, root folders) are kept.\n"
            "Media files on disk are [bold]kept[/] — every delete sends deleteFiles=false.",
            title="[bold red]Confirm deletion[/]",
            border_style="red",
        )
    )
    if not sys.stdin.isatty():
        console.print("[red]Not a terminal — cannot take confirmation. Aborting.[/]")
        return 1
    if Prompt.ask(f"Type [bold]{CONFIRM_PHRASE}[/] to proceed").strip() != CONFIRM_PHRASE:
        console.print("[yellow]Confirmation did not match. Nothing was changed.[/]")
        return 1

    backup(apps, args.skip_backup)

    console.print("\n[bold]Deleting library entries[/]")
    for app in apps:
        delete_library(app)

    console.print("\n[bold]Housekeeping[/]")
    for app in apps:
        run_command(app, "Housekeeping", wait=False)
        console.print(f"  [green]queued[/] housekeeping on {app.name}")

    console.print()
    checks = Checks("Verification")
    for app in apps:
        checks.add(f"{app.name} library empty", 0, count(api(app, app.resource)))
    checks.settings_preserved(apps)
    media_after = media_counts()
    for sub, before in media_before.items():
        checks.add(f"media/{sub} files kept", before, media_after[sub])
    return finish(checks, "Libraries cleared; settings and media files intact.")


def delete_library(app: App) -> None:
    """Bulk-delete via the editor endpoint, falling back to one call per id.

    deleteFiles=false is what keeps the media on disk. It must stay false in both paths.
    """
    ids = [item["id"] for item in app.library]
    if not ids:
        console.print(f"  [dim]{app.name}: library already empty[/]")
        return

    payload = {app.ids_field: ids, "deleteFiles": False, app.exclusion_field: False}
    try:
        api(app, f"{app.resource}/editor", "DELETE", payload)
        console.print(f"  [green]deleted[/] {len(ids)} {app.plural} via bulk editor")
        return
    except ApiError as exc:
        if "HTTP 404" not in str(exc) and "HTTP 405" not in str(exc):
            raise
        console.print("  [yellow]bulk editor unavailable, falling back to per-id deletes[/]")

    query = f"deleteFiles=false&{app.exclusion_field}=false"
    for done, item_id in enumerate(ids, start=1):
        api(app, f"{app.resource}/{item_id}?{query}", "DELETE")
        if done % 10 == 0 or done == len(ids):
            console.print(f"  [dim]deleted {done}/{len(ids)}[/]")


def cmd_monitor(apps: list[App], args) -> int:
    """Re-apply a monitoring policy to existing series via Sonarr's Season Pass.

    This is what Series -> Season Pass -> Monitor does in the UI. With --monitor future
    only episodes that have not aired yet stay monitored, so Sonarr stops hunting the
    back catalogue but still grabs new episodes as they air.
    """
    targets = [app for app in apps if app.has_episodes]
    if not targets:
        console.print("[red]Monitoring applies to TV only; movies have no episodes.[/]")
        return 1

    for app in targets:
        if args.series:
            wanted = set(args.series)
            app.library = [s for s in app.library if s["id"] in wanted]
            missing = wanted - {s["id"] for s in app.library}
            if missing:
                console.print(f"[red]{app.name}: no such series id(s): {sorted(missing)}[/]")
                return 1
        if not app.library:
            console.print(f"[yellow]{app.name}: no series to act on.[/]")
            return 0

        app.total_entries = len(api(app, app.resource) or [])
        before = episode_stats(app)
        table = Table(
            title=f"{app.name}: apply monitor='{args.monitor}' to {len(app.library)} series",
            header_style="bold",
        )
        table.add_column("Metric")
        table.add_column("Now", justify="right")
        table.add_column("After", justify="right")
        expected = expected_after(args.monitor, before)
        table.add_row("total episodes", str(before["total"]), str(before["total"]))
        table.add_row("monitored", str(before["monitored"]), expected["monitored"])
        table.add_row("monitored, already aired", str(before["monitored_aired"]), expected["monitored_aired"])
        table.add_row("monitored, not yet aired", str(before["monitored_future"]), expected["monitored_future"])
        console.print(table)
        app.stats_before = before

    console.print(
        "[dim]Series entries, files on disk and all settings are untouched; only the "
        "monitored flag on episodes and seasons changes.[/]"
    )

    if not args.apply:
        console.print(f"\n[bold cyan]Dry run — nothing was changed.[/] Re-run with --apply to set monitor='{args.monitor}'.")
        return 0

    console.print()
    console.print(
        Panel(
            f"About to set monitoring to [bold]{args.monitor}[/] on "
            f"[bold]{sum(len(app.library) for app in targets)}[/] series.\n\n"
            "This is reversible — re-run with a different --monitor value to change it back.\n"
            "No series, files or settings are removed.",
            title="[bold yellow]Confirm monitoring change[/]",
            border_style="yellow",
        )
    )
    if not sys.stdin.isatty():
        console.print("[red]Not a terminal — cannot take confirmation. Aborting.[/]")
        return 1
    if not Confirm.ask("Apply this monitoring change?", default=False):
        console.print("[yellow]Aborted. Nothing was changed.[/]")
        return 1

    backup(targets, args.skip_backup)

    console.print("\n[bold]Applying monitoring[/]")
    for app in targets:
        # Full series resources are sent back unmodified so each series keeps its own
        # `monitored` flag; monitoringOptions is what rewrites the episode/season flags.
        api(app, "seasonpass", "POST", {
            "series": app.library,
            "monitoringOptions": {"monitor": args.monitor},
        })
        console.print(f"  [green]applied[/] monitor='{args.monitor}' to {len(app.library)} series on {app.name}")

    console.print()
    checks = Checks("Verification")
    for app in targets:
        after = episode_stats(app)
        expected = expected_after(args.monitor, app.stats_before)
        checks.add(f"{app.name} series count unchanged", app.total_entries, count(api(app, app.resource)))
        checks.add(f"{app.name} total episodes unchanged", app.stats_before["total"], after["total"])
        if expected["monitored_aired"] != "?":
            checks.add(f"{app.name} monitored aired episodes", int(expected["monitored_aired"]), after["monitored_aired"])
        checks.info(f"{app.name} monitored episodes", expected["monitored"], after["monitored"])
        checks.info(f"{app.name} monitored future episodes", expected["monitored_future"], after["monitored_future"])
    checks.settings_preserved(apps)
    return finish(checks, f"Monitoring set to '{args.monitor}'; series, files and settings intact.")


def expected_after(monitor: str, before: dict[str, int]) -> dict[str, str]:
    """What the episode counts should look like afterwards, where it is predictable."""
    if monitor == "future":
        return {
            "monitored": str(before["unaired"]),
            "monitored_aired": "0",
            "monitored_future": str(before["unaired"]),
        }
    if monitor == "none":
        return {"monitored": "0", "monitored_aired": "0", "monitored_future": "0"}
    return {"monitored": "?", "monitored_aired": "?", "monitored_future": "?"}


# ------------------------------------------------------------------------ glue


def check_queues(apps: list[App], force: bool) -> bool:
    busy = [(app.name, size) for app in apps if (size := queue_size(app)) > 0]
    if not busy:
        return True
    detail = ", ".join(f"{name}: {size} queued" for name, size in busy)
    if not force:
        console.print(f"[bold red]Download queue is not empty ({detail}). Aborting; use --force to override.[/]")
        return False
    console.print(f"[yellow]Proceeding with a non-empty queue ({detail}) because --force was given.[/]")
    return True


def finish(checks: Checks, success_message: str) -> int:
    if checks.report():
        console.print(f"\n[bold green]Done.[/] {success_message}")
        return 0
    console.print(
        "\n[bold red]Verification failed.[/] Restore from the backup via "
        "System → Backups in the web UI before changing anything else."
    )
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="arr_db_utils.py",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        allow_abbrev=False,
    )
    subparsers = parser.add_subparsers(dest="command", required=True, metavar="<command>")

    def add_common(sub, backup_note: str) -> None:
        sub.add_argument("--apply", action="store_true", help="actually make changes (default is a dry run)")
        sub.add_argument("--skip-backup", action="store_true", help=backup_note)

    status = subparsers.add_parser(
        "status",
        help="read-only overview of libraries, monitoring and settings",
        description="Show library sizes, download queues, TV episode monitoring and\n"
                    "settings counts. Changes nothing.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        allow_abbrev=False,
    )
    status.add_argument(
        "target", nargs="?", choices=list(TARGETS), default="all", metavar="<all|movies|tv>",
        help="which library to report on (default: all)",
    )

    purge = subparsers.add_parser(
        "purge",
        help="delete library entries, keeping settings and files on disk",
        description="Delete every entry from a library.\n\n"
                    "Settings (indexers, download clients, quality/release profiles, root\n"
                    "folders) are kept. Media files on disk are kept too - every delete\n"
                    "sends deleteFiles=false.\n\n"
                    f"Requires --apply plus typing \"{CONFIRM_PHRASE}\" at the prompt. A backup is\n"
                    "taken first unless --skip-backup is given.",
        epilog="Examples:\n"
               "  arr_db_utils.py purge movies            dry run over Radarr\n"
               "  arr_db_utils.py purge movies --apply    clear Radarr only\n"
               "  arr_db_utils.py purge tv --apply        clear Sonarr only\n"
               "  arr_db_utils.py purge all --apply       clear both\n",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        allow_abbrev=False,
    )
    purge.add_argument(
        "target", choices=list(TARGETS), metavar="<all|movies|tv>",
        help="which library to clear: all, movies (Radarr) or tv (Sonarr)",
    )
    add_common(purge, "do not trigger a backup before deleting")
    purge.add_argument("--force", action="store_true", help="proceed even if a download queue is non-empty")

    monitor = subparsers.add_parser(
        "monitor",
        help="re-apply a monitoring policy to TV series (Sonarr only)",
        description="Re-apply a monitoring policy to existing series via Sonarr's Season\n"
                    "Pass. With the default 'future', only episodes that have not aired stay\n"
                    "monitored, so Sonarr stops hunting the back catalogue but still grabs\n"
                    "new episodes as they air.\n\n"
                    "Nothing is deleted and this is reversible - re-run with a different\n"
                    "--monitor value. Movies have no per-episode monitoring, so this command\n"
                    "is TV-only.",
        epilog="Examples:\n"
               "  arr_db_utils.py monitor                       dry run, monitor=future\n"
               "  arr_db_utils.py monitor --apply               stop hunting aired episodes\n"
               "  arr_db_utils.py monitor --monitor all --apply undo, monitor everything\n"
               "  arr_db_utils.py monitor --series 6 21 --apply limit to these series ids\n",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        allow_abbrev=False,
    )
    add_common(monitor, "do not trigger a backup before changing monitoring")
    monitor.add_argument(
        "--monitor", choices=MONITOR_TYPES, default="future", metavar="<policy>",
        help="policy to apply (default: future). One of: " + ", ".join(MONITOR_TYPES),
    )
    monitor.add_argument(
        "--series", type=int, nargs="+", metavar="ID",
        help="limit to these series ids (default: all series)",
    )
    args = parser.parse_args()

    # monitor is inherently TV; everything else takes its scope from the target word.
    names = ("sonarr",) if args.command == "monitor" else TARGETS[args.target]
    apps = [APPS[name] for name in names]

    console.print("[bold]Reading current state[/]")
    try:
        for app in apps:
            load(app)
        console.print()
        handler = {"status": cmd_status, "purge": cmd_purge, "monitor": cmd_monitor}[args.command]
        return handler(apps, args)
    except ApiError as exc:
        console.print(f"[bold red]{exc}[/]")
        return 1
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted. Nothing further was changed.[/]")
        return 1


if __name__ == "__main__":
    sys.exit(main())
