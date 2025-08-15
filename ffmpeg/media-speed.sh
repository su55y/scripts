#!/bin/sh

INPUT_FILE=
OUTPUT_FILE=
RATIO=
VERBOSE=0

show_help() {
    cat <<EOF
usage: media-speed -i INPUT -o OUTPUT -r RATIO [-h] [-v]

options:
  -h           show this help message and exit
  -i           input file
  -o           output file
  -r           speed ratio (should be in range 0.5 - 2.0)
  -v           verbose output
EOF
}

parse_args() {
    OPTIND=1
    while getopts "i:o:r:hv" opt; do
        case "$opt" in
        h)
            show_help
            exit 0
            ;;
        i) INPUT_FILE=$OPTARG ;;
        r)
            RATIO=$OPTARG
            if [ $(echo "$RATIO >= 0.5 && $RATIO <= 2.0" | bc -l) -ne 1 ]; then
                echo "Invalid ratio '$RATIO', should be in range 0.5-2.0"
                exit 1
            fi
            ;;
        o) OUTPUT_FILE=$OPTARG ;;
        v) VERBOSE=1 ;;
        *)
            show_help
            exit 1
            ;;
        esac
    done

    shift $((OPTIND - 1))
    [ "${1:-}" = "--" ] && shift
}

parse_args "$@"

if [ -z "$INPUT_FILE" ] || [ ! -f "$INPUT_FILE" ]; then
    show_help
    exit 1
fi

probe="$(ffprobe -v quiet -show_streams -of json "$INPUT_FILE")"
if [ $? -ne 0 ]; then
    echo 'Probe failed'
    exit 1
fi

has_video=0
has_audio=0
if echo "$probe" | grep -q '"codec_type": "video"'; then
    has_video=1
fi
if echo "$probe" | grep -q '"codec_type": "audio"'; then
    has_audio=1
fi

verbose='-loglevel warning -stats'
[ $VERBOSE -eq 1 ] && verbose=

if [ $has_video -eq 1 ] && [ $has_audio -eq 1 ]; then
    ffmpeg -hide_banner $verbose -i "$INPUT_FILE" \
        -filter_complex "[0:v]setpts=PTS/${RATIO}[v];[0:a]atempo=${RATIO}[a]" \
        -map [v] -map [a] "$OUTPUT_FILE"
elif [ $has_video -eq 1 ]; then
    ffmpeg -hide_banner $verbose -i "$INPUT_FILE" \
        -filter:v setpts=PTS/$RATIO "$OUTPUT_FILE"
elif [ $has_audio -eq 1 ]; then
    ffmpeg -hide_banner $verbose -i "$INPUT_FILE" \
        -filter:a atempo=$RATIO "$OUTPUT_FILE"
else
    echo "No video or audio streams found in '$INPUT_FILE'"
    exit 1
fi
