#!/usr/bin/env -S python -u

import argparse
from dataclasses import dataclass
import hashlib
import json
import math
import os
import re
import subprocess as sp
from pathlib import Path
from sys import argv
from typing import Any


SILENCE_OPTS = "-hide_banner -loglevel warning -stats"
MONTAGE_CMD = "montage -geometry +0+0 -tile %s %s %s"

DEFAULT_COUNT = 10
DEFAULT_OUTPUT = "frames/frame%02d.png"
DEFAULT_PREVIEW = "preview.png"


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("input", help="input file")
    parser.add_argument(
        "-c",
        "--count",
        metavar="INT",
        help=f"frames count (default: {DEFAULT_COUNT})",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=DEFAULT_OUTPUT,
        metavar="STR",
        help="frames output (default: %(default)s), should include %%d format specifier",
    )
    parser.add_argument("-p", "--preview", action="store_true", help="generate preview")
    parser.add_argument(
        "-P",
        "--preview-output",
        metavar="PATH",
        help="preview output (default: format based frames_output_dir/preview.png)",
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


def get_probe(input_file: Path, verbose: bool = False) -> Probe:
    probe_file = Path(os.environ.get("TEMPDIR", "/tmp"))
    hash_obj = hashlib.sha256()
    with open(input_file, "rb") as f:
        hash_obj.update(f.read(4096))
        probe_file = probe_file.joinpath(f"{hash_obj.hexdigest()}.probe.json")

    if probe_file.exists():
        with open(probe_file) as pf:
            print("reading probe from cache")
            raw_probe = json.load(pf)
    else:
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
            input_file,
        ]
        if verbose:
            print(" ".join(probe_cmd))
        probe_out = sp.check_output(probe_cmd, stderr=sp.DEVNULL, timeout=10)
        if not probe_out:
            raise Exception("can't get output from cmd '%s'" % probe_cmd)
        with open(probe_file, "w") as pf:
            print("writing probe cache")
            pf.write(probe_out.decode())
        raw_probe = json.loads(probe_out)
    format = raw_probe.get("format", dict())
    if not format or "duration" not in format:
        raise InvalidProbeFormat(f"{format=!r}")
    streams = raw_probe.get("streams", list())
    if not streams or len(streams) != 1:
        raise InvalidProbeFormat(f"{streams=!r}")
    try:
        return Probe(
            width=int(streams[0]["width"]),
            height=int(streams[0]["height"]),
            duration=float(format["duration"]),
        )
    except:
        raise InvalidProbeFormat(f"{streams[0]=!r}")


def generate_preview(
    *,
    probe: Probe,
    count: int,
    output: Path,
    preview_template: str,
    preview_output: str,
):
    rx_num = re.compile(r"(\d+)")

    def find_num(s: str) -> int:
        try:
            if match := rx_num.search(s):
                return int(match.group())
        except:
            pass
        return 0

    p_output = preview_output or output.parent.joinpath(DEFAULT_PREVIEW)
    rows = count // int(math.sqrt(count))
    cols = count // rows
    # swap cols and rows for vertical aspect ratio
    if (probe.width / probe.height) < 1 and cols < rows:
        cols, rows = rows, cols

    template = preview_template or f"{cols}x{rows}"
    files = " ".join(
        str(p)
        for p in sorted(
            output.parent.glob(f"*{output.suffix}"),
            key=lambda f: find_num(f.stem),
        )[: cols * rows]
    )
    cmd = MONTAGE_CMD % (template, files, p_output)
    print(cmd)
    sp.run(cmd.split())


def validate_output(v: str) -> Path:
    try:
        path = Path(v)
        if not re.match(r"^.*%(?:0\d)?d\..+$", path.name):
            raise argparse.ArgumentTypeError(
                f"invalid output value '{path.name}', should include %d format specifier"
            )
        if not path.parent.exists():
            if "-y" not in argv[1:]:
                resp = input(
                    "directory '%s' not exists, create? [Y/n]: "
                    % path.parent.absolute()
                )
                if resp.lower().startswith("n"):
                    exit(0)
            path.parent.mkdir(parents=True, exist_ok=True)
    except KeyboardInterrupt:
        exit(0)
    except Exception as e:
        raise e
    else:
        return path


if __name__ == "__main__":
    args = parse_args()
    count = int(args.count)
    if count < 1:
        raise argparse.ArgumentTypeError("count should be positive number")

    output = validate_output(args.output)

    input_file = Path(args.input).expanduser()
    if not input_file.exists():
        print(f"File {input_file} doesn't exist")
        exit(1)

    probe = get_probe(input_file, args.verbose)
    fps = round(count / probe.duration, 3)
    verbosity = "" if args.verbose else SILENCE_OPTS

    cmd = [
        "ffmpeg",
        *verbosity.split(),
        "-i",
        args.input,
        "-filter:v",
        f"fps=fps={fps}",
        "-frames:v",
        str(count),
        str(output),
    ]
    if args.verbose:
        print(" ".join(cmd))
    if sp.run(cmd).returncode == 0 and args.preview:
        generate_preview(
            probe=probe,
            count=count,
            output=output,
            preview_template=args.preview_template,
            preview_output=args.preview_output,
        )
