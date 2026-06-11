from __future__ import annotations

import sys

import run


if __name__ == "__main__":
    raise SystemExit(run.main(["--setup", *sys.argv[1:]]))

