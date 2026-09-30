"""Entry point: python -m winkickoff (the window) or python -m winkickoff --mcp stdio (a headless MCP server).

The headless flags are handled before winkickoff.app is imported, so a stdio server never loads tkinter.
"""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    from winkickoff.mcp.cli import is_headless, parse_args, run_headless

    raw = sys.argv[1:] if argv is None else list(argv)
    try:
        args, extras = parse_args(raw)
    except SystemExit as exc:
        if is_headless(raw):
            return int(exc.code) if isinstance(exc.code, int) else 2  # console use: argparse wrote the message
        from winkickoff.app import fatal  # the window path: show the message in a box

        fatal(f"Arguments not understood: {' '.join(raw)}")
        return 2
    if args.mcp or args.mcp_config or args.version:
        return run_headless(args)
    from winkickoff.app import run  # the only place that imports tkinter

    run(args, extras)
    return 0


if __name__ == "__main__":
    sys.exit(main())
