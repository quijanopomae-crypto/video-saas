import shutil

import pytest

from src.workers.render import render_smoke


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed locally")
def test_ffmpeg_smoke_creates_nonempty_mp4(tmp_path):
    output = render_smoke(tmp_path / "smoke.mp4")
    assert output.exists()
    assert output.stat().st_size > 0
