import io

import pytest

from replay_room.replay.__main__ import main


def test_cli_instant_window(fixture_dir):
    out = io.StringIO()
    assert main([str(fixture_dir), "--start", "p1:40", "--end", "p1:50", "--instant"], out=out) == 0
    lines = out.getvalue().splitlines()
    assert lines[0].startswith("SYN-0007")
    body = lines[2:]
    assert body and all(line.startswith("[1 00:4") or line.startswith("[1 00:50") for line in body)
    assert any(" ACTION " in line for line in body)
    assert sum(" FRAME " in line for line in body) == 11  # 1 Hz over 40..50 s inclusive


def test_cli_rejects_unknown_period(fixture_dir):
    with pytest.raises(SystemExit):
        main([str(fixture_dir), "--start", "p9:0", "--instant"], out=io.StringIO())
