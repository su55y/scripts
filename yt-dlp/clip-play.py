#!/usr/bin/env -S python -u

import argparse
import os
from pathlib import Path
import re
import requests
import subprocess as sp
import sqlite3
import tempfile
import time
from typing import Dict

APP_NAME = os.path.basename(__file__)
rx_url = re.compile(
    r".*youtube\.com\/watch\?v=([\w\d_\-]{11})|.*youtu\.be\/([\w\d_\-]{11})|.*twitch\.tv\/videos\/(\d{10})$"
)
rx_yt_url = re.compile(
    r".*youtu(?:be\.com/watch\?v=|\.be/|be\.com/shorts/)[-_0-9a-zA-Z]{11}"
)
rx_yt_dlp_title = re.compile(r".*twitch\.tv\/videos\/\d{10}")


def write_tmp_log(msg):
    temp_dir = Path(tempfile.gettempdir())
    if not temp_dir.exists() or not temp_dir.is_dir():
        return
    log_file_path = temp_dir / f"{APP_NAME}_{time.strftime('%d_%m_%y')}.log"
    with open(log_file_path, "a") as f:
        f.write("%s: %s\n" % (time.strftime("%T"), msg))


def notify(msg):
    try:
        if (c := sp.run(["notify-send", "-a", APP_NAME, msg]).returncode) != 0:
            raise Exception("notify-send exit code %d" % c)
    except Exception as e:
        write_tmp_log("ERROR: can't notify with msg: %r, error: %s" % (msg, e))


def read_from_cb():
    try:
        return sp.run(
            ["xclip", "-o", "-selection", "clipboard"],
            capture_output=True,
            text=True,
        ).stdout.strip()
    except Exception as e:
        notify("ERROR: %s" % e)


def run_mpv(url):
    try:
        p = sp.Popen(
            ["mpv", url],
            stdout=sp.DEVNULL,
            stderr=sp.DEVNULL,
            start_new_session=True,
        )
    except Exception as e:
        notify("ERROR: %s" % e)
        exit(1)
    else:
        for _ in range(25):
            time.sleep(1)
            if isinstance(p.poll(), int) and p.returncode != 0:
                notify("ERROR: mpv return status %d" % p.returncode)
                exit(1)


def fetch_title(url):
    try:
        resp = requests.get("https://youtube.com/oembed?url=%s&format=json" % url)
        resp.raise_for_status()
        return resp.json().get("title")
    except Exception as e:
        notify("ERROR: can't fetch title for %r: %s" % (url, e))


def fetch_title_yt_dlp(url):
    try:
        from yt_dlp import YoutubeDL
    except ImportError:
        return
    with YoutubeDL() as ytdl:
        info = ytdl.extract_info(url, download=False)
        if not info or not isinstance(info, Dict):
            notify("invalid yt-dlp info type %s" % type(info))
            return
        return info.get("title")


def get_title(url):
    if rx_yt_url.match(url):
        return fetch_title(url)
    if rx_yt_dlp_title.match(url):
        return fetch_title_yt_dlp(url)


def update_history(db, url, title):
    try:
        with sqlite3.connect(db) as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT OR IGNORE INTO titles (url, title, created) VALUES (?, ?, ?)",
                (url, title, time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())),
            )
    except Exception as e:
        notify("DB ERROR: %s" % e)


def parse_args():
    parser = argparse.ArgumentParser(APP_NAME)
    parser.add_argument("url", nargs="?")
    parser.add_argument(
        "-d",
        "--history-database",
        type=Path,
        help="playlist-ctl compatible database path",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    url = args.url or read_from_cb()
    if not url:
        notify("ERROR: url not provided")
        exit(1)

    if not rx_url.match(url):
        notify("ERROR: invalid url %r" % url)
        exit(1)

    title = ""
    if args.history_database:
        if not args.history_database.expanduser().exists():
            notify(f"{args.history_database} not exists")
            exit(1)
        title = get_title(url) or url
        update_history(str(args.history_database), url, title)

    notify(title or url)
    run_mpv(url)
