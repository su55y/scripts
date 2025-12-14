#!/usr/bin/env -S python -u

import argparse
import os
import json
from pathlib import Path
import re
import subprocess as sp
import sqlite3
import tempfile
import time
from typing import Dict
from urllib.request import urlopen

from requests import HTTPError

APP_NAME = os.path.basename(__file__)
POLLING_TIMEOUT = int(os.environ.get("POLLING_TIMEOUT", 15))
POLLING_INTERVAL = int(os.environ.get("POLLING_INTERVAL", 1))

rx_url = re.compile(
    r".*youtube\.com\/watch\?v=([\w\d_\-]{11})|.*youtu\.be\/([\w\d_\-]{11})|.*twitch\.tv\/videos\/(\d{10})$"
)
rx_yt_url = re.compile(
    r".*youtu(?:be\.com/watch\?v=|\.be/|be\.com/shorts/)[-_0-9a-zA-Z]{11}"
)
rx_yt_dlp_title = re.compile(r".*twitch\.tv\/videos\/\d{10}")


def write_tmp_log(msg: str) -> None:
    temp_dir = Path(tempfile.gettempdir())
    if not temp_dir.exists() or not temp_dir.is_dir():
        return
    log_file_path = temp_dir / f"{APP_NAME}_{time.strftime('%d_%m_%y')}.log"
    with open(log_file_path, "a") as f:
        f.write(f"{time.strftime('%T')} {msg}\n")


def notify(msg: str) -> None:
    try:
        p = sp.run(["notify-send", "-i", "mpv", "-a", APP_NAME, msg])
        if p.returncode != 0:
            raise Exception(f"notify-send exit code {p.returncode}")
    except Exception as e:
        write_tmp_log(f"ERROR: {e} ({msg=!r})")


def read_from_cb() -> str | None:
    try:
        return sp.run(
            ["xclip", "-o", "-selection", "clipboard"],
            capture_output=True,
            text=True,
        ).stdout.strip()
    except Exception as e:
        notify(f"ERROR: {e}")


def run_mpv(url):
    try:
        p = sp.Popen(
            ["mpv", url],
            stdout=sp.DEVNULL,
            stderr=sp.DEVNULL,
            start_new_session=True,
        )
    except Exception as e:
        notify(f"ERROR: {e}")
        exit(1)
    for _ in range(0, POLLING_TIMEOUT, POLLING_INTERVAL):
        time.sleep(POLLING_INTERVAL)
        if p.poll() is not None:
            if p.returncode != 0:
                notify(f"ERROR: mpv exit code {p.returncode}")
            break


def fetch_title(url: str) -> str | None:
    try:
        with urlopen(f"https://youtube.com/oembed?url={url}&format=json") as resp:
            if resp.status != 200:
                raise HTTPError(resp.url, resp.status, resp.reason, resp.headers, None)
            return json.load(resp).get("title")
    except Exception as e:
        notify(f"ERROR: can't fetch title for {url!r}: {e}")


def fetch_title_yt_dlp(url: str) -> str | None:
    try:
        from yt_dlp import YoutubeDL
    except ImportError:
        return
    with YoutubeDL() as ytdl:
        info = ytdl.extract_info(url, download=False)
        if not info or not isinstance(info, Dict):
            notify(f"ERROR: invalid yt-dlp info type {type(info)}")
            return
        return info.get("title")


def update_history(db: Path, url: str, title: str) -> None:
    if not db.expanduser().exists():
        notify(f"{db} not exists")
        return
    try:
        with sqlite3.connect(db) as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT OR IGNORE INTO titles (url, title, created) VALUES (?, ?, ?)",
                (url, title, time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())),
            )
    except Exception as e:
        notify(f"DB ERROR: {e}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(APP_NAME)
    parser.add_argument("url", nargs="?")
    parser.add_argument(
        "-d",
        "--history-database",
        type=Path,
        help="playlist-ctl compatible database path",
    )
    parser.add_argument(
        "-t",
        action="store_true",
        dest="use_title",
        help="notify with video title instead of url",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    url = args.url or read_from_cb()
    if not url:
        notify("ERROR: url not provided")
        exit(1)

    if not rx_url.match(url):
        notify(f"ERROR: invalid url {url!r}")
        exit(1)

    title = url
    if args.use_title:
        if rx_yt_url.match(url):
            title = fetch_title(url) or url
        elif rx_yt_dlp_title.match(url):
            title = fetch_title_yt_dlp(url) or url

    if args.history_database:
        update_history(args.history_database, url, title)

    notify(title or url)
    run_mpv(url)
