"""Run the live backend: ``python -m replay_room.api [--host H --port P]``."""

from __future__ import annotations

import argparse


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="replay_room.api", description="Replay Room live backend (HTTP).")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args(argv)
    import uvicorn

    uvicorn.run("replay_room.api.app:app", host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
