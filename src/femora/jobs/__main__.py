"""Run a packaged workflow from the command line."""

from __future__ import annotations

import argparse

from .bundle import replay
from .backends import TACC


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m femora.jobs")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("replay", help="run a trusted workflow bundle")
    run.add_argument("bundle")
    run.add_argument("--workspace", required=True)
    run.add_argument("--cores", type=int)
    run.add_argument("--backend", choices=("local", "tacc"), default="local")
    args = parser.parse_args()
    if args.command == "replay":
        result = replay(args.bundle, workspace=args.workspace, cores=args.cores,
                        backend=TACC() if args.backend == "tacc" else None)
        print(result.manifest)


if __name__ == "__main__":
    main()
