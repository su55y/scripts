#!/bin/sh

INPUT_FILE=
FRAMES_COUNT=10
OUTPUT_FMT=frames/frame%02d.png
GENERATE_PREVIEW=0
PREVIEW_OUTPUT=
PREVIEW_TEMPLATE=
VERBOSE=0
YES=0

show_help() {
    cat <<EOF
usage: extract-frames [-i FILE] [-c INT] [-f STR] [-p] [-P PATH] [-t STR] [-v] [-y] [-h]

options:
  -h           show this help message and exit
  -c INT       frames count (default: 10)
  -f STR       output format (default: frames/frame%02d.png), should include %d format specifier
  -p           generate preview
  -P PATH      preview path (default: format based frames_output_dir/preview.png)
  -t STR       preview tiling template (default: '{α}x{count/α}', where 'α' is square root of 'count')
  -v           verbose output
  -y           confirm mkdir -p
EOF
}

parse_args() {
    OPTIND=1
    while getopts "i:c:f:P:t:hpvy" opt; do
        case "$opt" in
        h)
            show_help
            exit 0
            ;;
        i) INPUT_FILE=$OPTARG ;;
        c)
            FRAMES_COUNT=$OPTARG
            case $FRAMES_COUNT in
            -[[:digit:]]* | 0)
                echo "FRAMES_COUNT should be > 0"
                exit 1
                ;;
            0* | *[!0-9]*)
                echo "Invalid FRAMES_COUNT value '$FRAMES_COUNT'"
                exit 1
                ;;
            [[:digit:]]*) ;;
            *)
                echo "Invalid FRAMES_COUNT value '$FRAMES_COUNT'"
                exit 1
                ;;
            esac
            ;;
        f)
            OUTPUT_FMT=$OPTARG
            if ! echo "$OUTPUT_FMT" | grep -qP '^.*%\d*d.+$'; then
                echo "Invalid OUTPUT_FMT '$OUTPUT_FMT'"
                exit 1
            fi
            ;;
        p) GENERATE_PREVIEW=1 ;;
        P) PREVIEW_OUTPUT=$OPTARG ;;
        t) PREVIEW_TEMPLATE=$OPTARG ;;
        v) VERBOSE=1 ;;
        y) YES=1 ;;
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


if [ ! -f "$INPUT_FILE" ]; then
    echo "INPUT_FILE '$INPUT_FILE' not found"
    exit 1
fi

print_log() { [ $VERBOSE -eq 1 ] && echo "$1"; }

print_log "Extracting $FRAMES_COUNT frames..."
print_log "Output fmt: '$OUTPUT_FMT'..."

PROBE_FILE="${TEMPDIR:-/tmp}/$INPUT_FILE.probe.json"
if [ ! -f "$PROBE_FILE" ]; then
    if [ $VERBOSE -eq 1 ]; then
        quiet=
    else
        quiet='-v quiet'
    fi
    ffprobe $quiet -show_format -show_streams \
        -select_streams v:0 -of json "$INPUT_FILE" >"$PROBE_FILE" || exit 1
fi

DURATION=$(jq -r .format\?.duration\? "$PROBE_FILE")
if [ "$DURATION" = null ]; then
    echo "Can't get duration from probe $PROBE_FILE"
    exit 1
fi

OUTPUT_DIR_="$(dirname "$OUTPUT_FMT")"
if [ ! -d "$OUTPUT_DIR_" ]; then
    if [ $YES -eq 0 ]; then
        printf 'Directory %s not found, create? [Y/n]: ' "$OUTPUT_DIR_"
        read -r y_
    else
        y_=y
    fi
    case $y_ in
    n* | N*) exit 0 ;;
    *) mkdir -vp "$OUTPUT_DIR_" || exit 1 ;;
    esac
fi

INTERVAL=$(echo "$DURATION/$FRAMES_COUNT" | bc)

if [ $VERBOSE -eq 1 ]; then
    quiet=
else
    quiet='-loglevel warning -stats'
fi

ffmpeg -hide_banner $quiet -i "$INPUT_FILE" \
    -filter:v "select='not(mod(t,$INTERVAL))',setpts=N/(FRAME_RATE*TB)'" \
    -fps_mode vfr -frames:v $FRAMES_COUNT "$OUTPUT_FMT" || exit 1

if [ $GENERATE_PREVIEW -eq 1 ]; then
    if [ -z "$PREVIEW_OUTPUT" ]; then
        PREVIEW_OUTPUT="$(dirname "$OUTPUT_FMT")/preview.png"
    fi
    if [ -z "$PREVIEW_TEMPLATE" ]; then
        sqrt_count=$(echo "scale=10; sqrt($FRAMES_COUNT)" | bc -l)
        rows=$((FRAMES_COUNT / ${sqrt_count%.*}))
        cols=$((FRAMES_COUNT / rows))

        WIDTH=$(jq -r '.streams[0]?.width?' "$PROBE_FILE")
        if [ "$WIDTH" = null ]; then
            echo "Can't get width from probe $PROBE_FILE"
            exit 1
        fi
        HEIGHT=$(jq -r '.streams[0]?.height?' "$PROBE_FILE")
        if [ "$HEIGHT" = null ]; then
            echo "Can't get height from probe $PROBE_FILE"
            exit 1
        fi

        if [ $WIDTH -lt $HEIGHT ] && [ $cols -lt $rows ]; then
            tmp_cols=$cols
            cols=$rows
            rows=$tmp_cols
        fi

        PREVIEW_TEMPLATE=${cols}x${rows}
    fi

    print_log "Generating $PREVIEW_TEMPLATE preview '$PREVIEW_OUTPUT'..."
    inputs=
    for i in $(seq 1 $FRAMES_COUNT); do
        filename="$(printf "$OUTPUT_FMT" $i)"
        if [ ! -f "$filename" ]; then
            echo "File '$filename' not found"
            exit 1
        fi
        inputs="$inputs $filename"
    done
    montage $inputs -geometry +0+0 -tile "$PREVIEW_TEMPLATE" "$PREVIEW_OUTPUT"
fi
