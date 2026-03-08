"""
(C) 2026 Joseph Tingiris (joseph.tingiris@gmail.com)

VS Code Keyboard Navigation common cli functions.
"""

from __future__ import annotations

import argparse
import sys

from typing import Callable

#
# globals & constants
#


#
# functions
#


def _flag_present(raw_argv: list[str], names: list[str]) -> bool:
    """Return True if any of the flag names are present in the raw argv list."""

    for name in names:
        if name in raw_argv:
            return True

    return False


def _make_common_parser(prog: str | None = None) -> argparse.ArgumentParser:
    """Create and return a common ArgumentParser preconfigured with standard options."""

    p = argparse.ArgumentParser(prog=prog)

    # p.add_argument("-i", "--input", help="input file (defaults to stdin)", default="-")
    # p.add_argument("-o", "--output", help="output file (defaults to stdout)", default="-")
    # p.add_argument("--encoding", help="file encoding", default="utf-8")

    p.add_argument("--dry-run", action="store_true", help="don't write output")
    p.add_argument("-v", "--verbose", action="count", default=0, help="increase verbosity")

    # p.add_argument("--add-context", action="store_true", help="add feature-gate context when generating corpus")

    return p


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse and return CLI arguments using the common parser."""

    parser = _make_common_parser()

    return parser.parse_args(argv)


def _run_main(main_fn: Callable[[argparse.Namespace], int] | Callable[[argparse.Namespace], None], argv: list[str] | None = None) -> int:
    """Run a CLI main function with parsed args and convert exceptions into exit codes."""

    args = _parse_args(argv)

    try:
        res = main_fn(args)
        if res is None:
            return 0
        return int(res)
    except KeyboardInterrupt:
        return 130
    except SystemExit as e:
        # allow deliberate exits
        code = int(getattr(e, 'code', 1) or 0)
        return code
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
