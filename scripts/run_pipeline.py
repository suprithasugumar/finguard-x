#!/usr/bin/env python
"""FinGuard-X cross-platform CLI task and pipeline runner."""
import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent


def get_venv_bin(name: str) -> Path:
    """Resolve binary in local .venv cross-platform."""
    if os.name == "nt":
        bin_path = ROOT_DIR / ".venv" / "Scripts" / f"{name}.exe"
    else:
        bin_path = ROOT_DIR / ".venv" / "bin" / name
    if not bin_path.exists():
        # Fallback to system path
        return Path(name)
    return bin_path


def cmd_test(args) -> int:
    """Run pytest suite with optional coverage."""
    pytest_bin = str(get_venv_bin("pytest"))
    cmd = [pytest_bin, "-v"]
    if args.cov:
        cmd.extend(["--cov=backend/app", "--cov-report=term-missing"])
    cmd.append(str(ROOT_DIR / "backend" / "tests"))
    print(f"Running: {' '.join(cmd)}")
    return subprocess.run(cmd, cwd=str(ROOT_DIR)).returncode


def cmd_lint(args) -> int:
    """Run ruff linter check."""
    ruff_bin = str(get_venv_bin("ruff"))
    cmd = [ruff_bin, "check", "backend/"]
    print(f"Running: {' '.join(cmd)}")
    return subprocess.run(cmd, cwd=str(ROOT_DIR)).returncode


def cmd_format(args) -> int:
    """Run ruff formatting and auto-fix."""
    ruff_bin = str(get_venv_bin("ruff"))
    print("Formatting backend with ruff...")
    res = subprocess.run([ruff_bin, "format", "backend/"], cwd=str(ROOT_DIR)).returncode
    if res != 0:
        return res
    return subprocess.run([ruff_bin, "check", "--fix", "backend/"], cwd=str(ROOT_DIR)).returncode


def cmd_migrate(args) -> int:
    """Execute Alembic migrations."""
    alembic_bin = str(get_venv_bin("alembic"))
    action = args.action or "head"
    cmd = [alembic_bin, "upgrade", action]
    print(f"Running: {' '.join(cmd)}")
    return subprocess.run(cmd, cwd=str(ROOT_DIR)).returncode


def cmd_status(args) -> int:
    """Check FinGuard-X environment and service status."""
    sys.path.insert(0, str(ROOT_DIR))
    from backend.app.core.config import get_settings
    from backend.app.core.seed import set_global_seed
    from backend.app.db.session import get_engine
    from sqlalchemy import text

    settings = get_settings()
    print("==================================================")
    print(" FinGuard-X Environment & Pipeline Status")
    print("==================================================")
    print(f"App Name:        {settings.APP_NAME}")
    print(f"Environment:     {settings.APP_ENV}")
    print(f"Global Seed:     {settings.SEED}")
    print(f"Data Raw:        {settings.RAW_DIR} (exists: {settings.RAW_DIR.exists()})")
    print(f"Data Cache:      {settings.CACHE_DIR} (exists: {settings.CACHE_DIR.exists()})")
    print(f"Data Gold:       {settings.GOLD_DIR} (exists: {settings.GOLD_DIR.exists()})")
    print(f"Database URL:    {settings.DATABASE_URL}")
    print(f"Test DB URL:     {settings.TEST_DATABASE_URL}")

    # SEC UA Check
    try:
        ua = settings.validate_sec_user_agent()
        print(f"SEC User-Agent:  {ua} [VALID]")
    except ValueError as e:
        print(f"SEC User-Agent:  [NOT SET / LAZY] ({e})")

    # DB Connection Check
    try:
        engine = get_engine()
        with engine.connect() as conn:
            result = conn.execute(text("SELECT current_database();")).scalar()
            print(f"PostgreSQL DB:   Connected to '{result}' [OK]")
    except Exception as e:
        print(f"PostgreSQL DB:   Connection Failed: {e}")

    set_global_seed(settings.SEED)
    print("Global Seed initialized to 42.")
    print("Status check completed successfully.")
    return 0


def main():
    parser = argparse.ArgumentParser(description="FinGuard-X Cross-Platform CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # test
    p_test = subparsers.add_parser("test", help="Run test suite")
    p_test.add_argument("--cov", action="store_true", default=True, help="Include coverage report")

    # lint
    subparsers.add_parser("lint", help="Run ruff linting")

    # format
    subparsers.add_parser("format", help="Run ruff code formatting")

    # migrate
    p_migrate = subparsers.add_parser("migrate", help="Run Alembic migrations")
    p_migrate.add_argument("action", nargs="?", default="head", help="Migration target (e.g. head)")

    # status
    subparsers.add_parser("status", help="Check pipeline status and DB connectivity")

    args = parser.parse_args()
    actions = {
        "test": cmd_test,
        "lint": cmd_lint,
        "format": cmd_format,
        "migrate": cmd_migrate,
        "status": cmd_status,
    }
    sys.exit(actions[args.command](args))


if __name__ == "__main__":
    main()
