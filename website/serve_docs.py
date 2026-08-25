"""Serve Femora documentation locally, with an optional Concepts-only mode."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def main() -> None:
    """Run MkDocs with either the full or fast local configuration."""
    parser = argparse.ArgumentParser(description="Serve Femora documentation locally.")
    parser.add_argument(
        "--skip-api-reference",
        action="store_true",
        help="Serve documentation without generating or rendering API reference pages.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Local HTTP port (default: 8000).",
    )
    args = parser.parse_args()

    website_dir = Path(__file__).parent
    config_name = "mkdocs.fast.yml" if args.skip_api_reference else "mkdocs.yml"
    command = [
        sys.executable,
        "-m",
        "mkdocs",
        "serve",
        "--config-file",
        str(website_dir / config_name),
        "--dirtyreload",
        "--dev-addr",
        f"127.0.0.1:{args.port}",
    ]
    subprocess.run(command, check=True, cwd=website_dir)


if __name__ == "__main__":
    main()
