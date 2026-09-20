from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path


def ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def render_smoke(output: Path) -> Path:
    if not ffmpeg_available():
        raise RuntimeError("ffmpeg is not installed or not available on PATH")
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "color=c=black:s=320x180:d=0.5",
        "-an",
        "-c:v",
        "mpeg4",
        "-pix_fmt",
        "yuv420p",
        str(output),
    ]
    subprocess.run(command, check=True)
    if not output.exists() or output.stat().st_size <= 0:
        raise RuntimeError("ffmpeg smoke output was not created")
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", type=Path)
    args = parser.parse_args()
    if args.smoke is None:
        parser.error("--smoke is required")
    output = render_smoke(args.smoke)
    print(f"FFMPEG_SMOKE_OK {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
