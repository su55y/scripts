#!/bin/sh

INPUT_FILE=
FRAMES_COUNT=10
DEFAULT_OUTPUT=frames/frame%s.png
OUTPUT=
GENERATE_PREVIEW=0
PREVIEW_OUTPUT=
PREVIEW_TEMPLATE=
VERBOSE=0
YES=0

show_help() {
    cat <<EOF
usage: extract-frames [-i FILE] [-c INT] [-f STR] [-p] [-P PATH] [-t STR] [-v] [-y] [-h]

dependencies: ffmpeg, bc, jq

options:
  -c INT       frames count (default: 10)
  -o STR       frames output (default: frames/frame%d.png), should include %d format specifier
  -h           show this help message and exit
  -i FILE      input file ($(printf '\033[1;31m')required$(printf '\033[0m'))
  -p           generate preview
  -P PATH      preview path (default: frames/preview.png)
  -t STR       preview tiling template (default: '{α}x{count/α}', where 'α' is square root of 'count')
  -v           verbose output
  -y           confirm mkdir -p
EOF
}

die() {
    [ -n "$1" ] && echo "$1"
    exit 1
}

parse_args() {
    OPTIND=1
    while getopts "i:c:o:P:t:hpvy" opt; do
        case "$opt" in
        h)
            show_help
            exit 0
            ;;
        i) INPUT_FILE=$OPTARG ;;
        c)
            FRAMES_COUNT=$OPTARG
            case $FRAMES_COUNT in
            -[[:digit:]]* | 0) die "Invalid count value $FRAMES_COUNT, should be positive number" ;;
            0* | *[!0-9]*) die "Invalid count value $FRAMES_COUNT, should be positive number" ;;
            [[:digit:]]*) ;;
            *) die "Invalid count value $FRAMES_COUNT, should be positive number" ;;
            esac
            ;;
        o)
            OUTPUT=$OPTARG
            if ! echo "$OUTPUT" | grep -qP '^.*%\d*d.+$'; then
                die "Invalid output value '$OUTPUT', should include %d format specifier"
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

if [ -z "$INPUT_FILE" ]; then
    show_help
    exit 1
elif [ ! -f "$INPUT_FILE" ]; then
    die "Input file '$INPUT_FILE' doesn't exist"
fi

for exe in ffmpeg ffprobe bc jq; do
    if ! command -v $exe >/dev/null 2>&1; then
        die "$exe are required"
    fi
done

print_log() { [ $VERBOSE -eq 1 ] && echo "$1"; }

PROBE_FILE="${TEMPDIR:-/tmp}/$(head -c 4096 "$INPUT_FILE" | sha256sum | cut -d' ' -f1).probe.json"
if [ ! -f "$PROBE_FILE" ]; then
    if [ $VERBOSE -eq 1 ]; then
        quiet=
    else
        quiet='-v quiet'
    fi
    ffprobe $quiet -show_format -show_streams \
        -select_streams v:0 -of json "$INPUT_FILE" >"$PROBE_FILE" || exit 1
fi

if [ "$(jq -r .streams\?[0] "$PROBE_FILE" || echo null)" = null ]; then
    die "Input file $INPUT_FILE does not contain video stream"
fi

DURATION=$(jq -r .format\?.duration\? "$PROBE_FILE")
if [ "$DURATION" = null ]; then
    die "Can't get duration from probe $PROBE_FILE"
fi

if [ -z "$OUTPUT" ]; then
    OUTPUT=$(printf "$DEFAULT_OUTPUT" "$(echo "%0${#FRAMES_COUNT}d")")
fi

OUTPUT_DIR_="$(dirname "$OUTPUT")"
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

FPS=$(echo "$FRAMES_COUNT/$DURATION" | bc -l || exit 1)

quiet=
if [ $VERBOSE -eq 0 ]; then
    quiet='-hide_banner -loglevel warning -stats'
fi

print_log "Extracting $FRAMES_COUNT frames..."
print_log "Output fmt: '$OUTPUT'..."
ffmpeg $quiet -i "$INPUT_FILE" -filter:v fps=fps=$FPS \
    -frames:v $FRAMES_COUNT "$OUTPUT" || exit 1

if [ $GENERATE_PREVIEW -eq 0 ]; then
    exit 0
fi

if [ -z "$PREVIEW_OUTPUT" ]; then
    PREVIEW_OUTPUT="$(dirname "$OUTPUT")/preview.png"
fi

if [ -z "$PREVIEW_TEMPLATE" ]; then
    sqrt_count=$(echo "scale=10; sqrt($FRAMES_COUNT)" | bc -l)
    rows=$((FRAMES_COUNT / ${sqrt_count%.*}))
    cols=$((FRAMES_COUNT / rows))

    WIDTH=$(jq -r '.streams[0]?.width?' "$PROBE_FILE" || echo null)
    [ "$WIDTH" = null ] && die "Can't get width from probe $PROBE_FILE"

    HEIGHT=$(jq -r '.streams[0]?.height?' "$PROBE_FILE" || echo null)
    [ "$HEIGHT" = null ] && die "Can't get height from probe $PROBE_FILE"

    PREVIEW_TEMPLATE=${cols}x${rows}
    if [ $WIDTH -lt $HEIGHT ] && [ $cols -lt $rows ]; then
        PREVIEW_TEMPLATE=${rows}x${cols}
    fi

fi

print_log "Generating $PREVIEW_TEMPLATE preview '$PREVIEW_OUTPUT'..."
input_files=
for i in $(seq 1 $FRAMES_COUNT); do
    filename="$(printf "$OUTPUT" $i)"
    [ -f "$filename" ] || die "Frame '$filename' not found"
    input_files="$input_files $filename"
done
[ -n "$input_files" ] || die 'input_files is empty'
montage $input_files -geometry +0+0 -tile "$PREVIEW_TEMPLATE" "$PREVIEW_OUTPUT"
