"""`uv run python -m app.library <명령>` (app/library/cli.py)."""

from app.library.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
