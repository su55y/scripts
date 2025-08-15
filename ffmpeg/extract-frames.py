#!/usr/bin/env -S python -u

import argparse
from dataclasses import dataclass
import json
import math
import re
import subprocess as sp
from pathlib import Path
from sys import argv
from typing import Any


SILENCE_OPTS = "-hide_banner -loglevel warning -stats"
MONTAGE_CMD = "montage -geometry +0+0 -tile %s %s %s"

DEFAULT_COUNT = 10
DEFAULT_FMT = "frames/frame%02d.png"
DEFAULT_PREVIEW = "preview.png"


def parse_args():
    def check_count(arg: str) -> int:
        try:
            num = int(arg)
            if num < 1:
                raise argparse.ArgumentTypeError("count should be positive number")
        except:
            raise argparse.ArgumentTypeError("invalid count '%s'" % arg)
        else:
            return num

    def check_format(arg: str) -> Path:
        try:
            path = Path(arg)
            if not re.match(r"^.*%(?:0\d)?d\..+$", path.name):
                raise argparse.ArgumentTypeError(f"invalid format '{path.name}'")
            if not path.parent.exists():
                if "-y" not in argv[1:]:
                    resp = input(
                        "path '%s' not exists, create? [Y/n]: " % path.parent.absolute()
                    )
                    if resp.lower().startswith("n"):
                        exit(0)
                path.parent.mkdir(parents=True, exist_ok=True)
        except KeyboardInterrupt:
            exit(0)
        except Exception as e:
            raise argparse.ArgumentTypeError(f"parse format error: {e}")
        else:
            return path

    parser = argparse.ArgumentParser()
    parser.add_argument("file", help="input file")
    parser.add_argument(
        "-c",
        "--count",
        type=check_count,
        default=DEFAULT_COUNT,
        metavar="INT",
        help="frames count (default: %(default)s)",
    )
    parser.add_argument(
        "-f",
        "--format",
        type=check_format,
        default=DEFAULT_FMT,
        metavar="STR",
        help="output format (default: %(default)s), should include %%d format specifier",
    )
    parser.add_argument("-p", "--preview", action="store_true", help="generate preview")
    parser.add_argument(
        "-P",
        "--preview-output",
        metavar="PATH",
        help="preview path (default: format based frames_output_dir/preview.png)",
    )
    parser.add_argument(
        "-t",
        "--preview-template",
        metavar="STR",
        help="preview tiling template (default: '{α}x{count/α}', where 'α' is square root of 'count')",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="verbose output")
    parser.add_argument("-y", action="store_true", help="confirm mkdir -p")

    return parser.parse_args()


class InvalidProbeFormat(Exception):
    pass


@dataclass(slots=True)
class Probe:
    width: int
    height: int
    duration: float


def parse_probe(s: dict[str, Any]) -> Probe:
    format = s.get("format", dict())
    if not format or "duration" not in format:
        raise InvalidProbeFormat(f"{format=!r}")
    streams = s.get("streams", list())
    if not streams or len(streams) != 1:
        raise InvalidProbeFormat(f"{streams=!r}")
    match streams[0]:
        case {
            "width": int(),
            "height": int(),
        }:
            return Probe(
                width=int(streams[0]["width"]),
                height=int(streams[0]["height"]),
                duration=float(format["duration"]),
            )
    raise InvalidProbeFormat(f"{streams[0]=!r}")


def generate_preview(args: argparse.Namespace, probe: Probe):
    rx_num = re.compile(r"(\d+)")

    def find_num(s: str) -> int:
        try:
            if match := rx_num.search(s):
                return int(match.group())
        except:
            pass
        return 0

    output = args.preview_output or args.format.parent.joinpath(DEFAULT_PREVIEW)
    rows = args.count // int(math.sqrt(args.count))
    cols = args.count // rows
    # swap cols and rows for vertical aspect ratio
    if (probe.width / probe.height) < 1 and cols < rows:
        cols, rows = rows, cols

    template = args.preview_template or f"{cols}x{rows}"
    files = " ".join(
        str(p)
        for p in sorted(
            args.format.parent.glob(f"*{args.format.suffix}"),
            key=lambda f: find_num(f.stem),
        )[: cols * rows]
    )
    cmd = MONTAGE_CMD % (template, files, output)
    print(cmd)
    sp.run(cmd.split())


if __name__ == "__main__":
    args = parse_args()

    probe_cmd = [
        "ffprobe",
        "-v",
        "quiet",
        "-show_format",
        "-show_streams",
        "-select_streams",
        "v:0",
        "-of",
        "json",
        args.file,
    ]
    if args.verbose:
        print(" ".join(probe_cmd))
    probe_out = sp.check_output(probe_cmd, stderr=sp.DEVNULL, timeout=10)
    if not probe_out:
        raise Exception("can't get output from cmd '%s'" % probe_cmd)
    raw_probe = json.loads(probe_out)
    probe = parse_probe(raw_probe)
    interval = int(probe.duration / args.count)
    verbosity = "" if args.verbose else SILENCE_OPTS

    cmd = [
        "ffmpeg",
        *verbosity.split(),
        "-i",
        args.file,
        "-filter:v",
        f"select='not(mod(t,{interval}))',setpts=N/(FRAME_RATE*TB)",
        "-fps_mode",
        "vfr",
        "-frames:v",
        str(args.count),
        str(args.format),
    ]
    if args.verbose:
        print(" ".join(cmd))
    if sp.run(cmd).returncode == 0 and args.preview:
        generate_preview(args, probe)
