#!/bin/sh

HISTORY_DB="${XDG_DATA_HOME:-$HOME/.local/share}/playlist_ctl/playlist_ctl.db"

use_history=0
title=
use_title=0
url="$(xclip -o -selection clipboard)"

notify() { notify-send -a clip-play "$1"; }

if [ -z "$url" ]; then
    notify 'no url in clipboard'
    exit 1
fi

show_help() {
    cat <<EOF
usage: $(basename "$0") [-h] [-t] [-H]

this script runs \`mpv "\$(xclip -o -selection clipboard)"\`

options:
  -t  notify with video title instead of url
  -H  log history to playlist-ctl compatible database
EOF
}

parse_args() {
    OPTIND=1
    while getopts "hHt" opt; do
        case "$opt" in
        h)
            show_help
            exit 0
            ;;
        t) use_title=1 ;;
        H) use_history=1 ;;
        *) exit 1 ;;
        esac
    done

    shift $((OPTIND - 1))
    [ "${1:-}" = "--" ] && shift
}

parse_args "$@"

is_twitch=0
if echo "$url" | grep -qP '^(?:https\:\/\/)?(?:www\.)?twitch\.tv\/videos\/[0-9]{10}'; then
    is_twitch=1
else
    url_="$(echo "$url" | grep -oP '^(?:https://)?((?:www\.)?youtu(?:be\.com/watch\?v=|\.be/|be\.com/shorts/))[-_0-9a-zA-z]{11}')"
    if [ -z "$url_" ]; then
        notify "invalid url '$url'"
        exit 1
    fi
    url="$url_"
fi

fetch_title() {
    curl -s "$(printf 'https://youtube.com/oembed?url=%s&format=json' "$url")" \
        -H 'User-Agent: Mozilla/5.0 (X11; Linux x86_64; rv:106.0) Gecko/20100101 Firefox/106.0' \
        -H 'Accept-Language: en-US,en;q=0.5' | jq -r .title
}

if [ $is_twitch -eq 0 ] && [ $use_title -eq 1 ]; then
    title="$(fetch_title)"
fi

if [ -z "$title" ] || [ "$title" = null ]; then
    title="$url"
fi

notify "$title"
setsid -f mpv "$url" >/dev/null 2>&1

if [ "$use_history" -eq 1 ]; then
    if [ ! -f "$HISTORY_DB" ]; then
        notify "DB not found at $HISTORY_DB"
        exit 1
    fi
    sqlite3 "$HISTORY_DB" \
        "INSERT OR IGNORE INTO titles (url, title, created) \
        VALUES ('$url', '$title', '$(date -Ins)');"
fi
