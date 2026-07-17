"""Bootstrap the local Python environment for first-time users.

This script installs project dependencies and runs a small smoke test. It is
intended for skill onboarding, where users should not need to know which Python
packages are required before using the project.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS_PATH = PROJECT_ROOT / "requirements.txt"


class BootstrapError(RuntimeError):
    """Raised when environment bootstrap fails."""


def run_command(command: list[str]) -> None:
    try:
        subprocess.run(command, cwd=PROJECT_ROOT, check=True)
    except subprocess.CalledProcessError as exc:
        raise BootstrapError(f"Command failed: {' '.join(command)}") from exc


def install_dependencies() -> None:
    if not REQUIREMENTS_PATH.exists():
        raise BootstrapError(f"Missing requirements file: {REQUIREMENTS_PATH}")

    run_command(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "-r",
            str(REQUIREMENTS_PATH),
        ]
    )


def run_smoke_test() -> None:
    run_command(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_extractor_router.py",
        ]
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Install dependencies and validate the local environment."
    )
    parser.add_argument(
        "--skip-tests",
        action="store_true",
        help="Install dependencies without running the router smoke test.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        print("Installing project dependencies...")
        install_dependencies()

        if not args.skip_tests:
            print("Running environment smoke test...")
            run_smoke_test()

        print("Environment bootstrap complete.")
    except BootstrapError as exc:
        print(f"Environment bootstrap failed: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
