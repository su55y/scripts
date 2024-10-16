#!/bin/sh

CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}"
if [ ! -d "$CONFIG_DIR" ]; then
    echo "config dir '$CONFIG_DIR' not found"
    exit 1
fi

choosed_dir="$(find "$CONFIG_DIR" -maxdepth 1 -type d -printf '%f\n' | fzf)"

if [ ! -d "$CONFIG_DIR/$choosed_dir" ]; then
    echo "choosed dir '$choosed_dir' not found"
    exit 1
fi

nvim "$CONFIG_DIR/$choosed_dir"
