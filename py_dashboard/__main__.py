"""CLI entrypoint for `python -m py_dashboard`."""

from __future__ import annotations

import argparse

from .app import create_app
from .data_access import ensure_db_ready


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Run the Python-only GB VTP Settlement Forensics Dash dashboard."
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host interface to bind (default: 127.0.0.1).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8050,
        help="Port to serve the dashboard on (default: 8050).",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable Dash debug / hot-reload mode.",
    )
    args = parser.parse_args(argv)

    db_path = ensure_db_ready()
    print(f"Using SQLite database: {db_path}")
    print(f"Starting GB VTP Settlement Forensics dashboard at http://{args.host}:{args.port}")

    app = create_app()
    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
