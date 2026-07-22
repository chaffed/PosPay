#!/usr/bin/env python3
"""One-click local launcher for PosPay (SQLite, zero external services).

Run this directly (`python3 scripts/launcher.py`) or via the platform wrapper
(run_pospay.command on macOS): it creates a virtual environment if needed, installs the
project into it, runs database migrations, prompts for first-run setup info if the
database is empty, then starts the server and opens your browser.

Everything this script creates — the virtual environment, the SQLite database, uploaded
check images, and trained ML model files — lives under .pospay-run/ next to this project,
never inside the source tree itself. To fully reset (wipe the database, uploads, trained
models, and installed dependencies) and start over, just delete that one folder:

    rm -rf .pospay-run

Safe to re-run any time otherwise — every step is idempotent and skips whatever's
already done.

Deliberately stdlib-only until AFTER the re-exec into the venv's own interpreter (see
_create_venv_and_install/_reexec_under_venv below): this script must run under whatever
bare Python the user has, before any of PosPay's dependencies exist anywhere.
"""

import os
import shutil
import subprocess
import sys
import venv
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RUN_DIR = PROJECT_ROOT / ".pospay-run"  # delete this one folder to fully reset — see module docstring
VENV_DIR = RUN_DIR / "venv"
# Written only after a fully successful install — an interrupted first run (Ctrl+C
# mid-`pip install`) leaves a venv directory behind but no marker, so the next run
# recreates it from scratch rather than trusting a half-installed environment.
VENV_MARKER = VENV_DIR / ".pospay-setup-complete"

HOST = "127.0.0.1"  # never a LAN IP: WebAuthn requires a secure context, and this is a
PORT = 8000  # local single-user tool, not something that should be network-reachable.


def _venv_python() -> Path:
    if os.name == "nt":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def _is_running_under_venv() -> bool:
    # NOT `Path(sys.executable).resolve() == _venv_python().resolve()`: venv-created
    # interpreters are frequently symlinks back to the base Python (common on macOS/
    # Linux), so resolving symlinks makes the venv's python compare equal to the system
    # python too. sys.prefix is the standard, symlink-proof way to detect which
    # environment is actually active (it points at the venv root either way).
    return Path(sys.prefix).resolve() == VENV_DIR.resolve()


def _create_venv_and_install() -> None:
    if VENV_MARKER.exists():
        return

    print("Setting up PosPay for the first time — this can take a minute...\n")
    if VENV_DIR.exists():
        print(f"  Removing incomplete virtual environment at {VENV_DIR}")
        shutil.rmtree(VENV_DIR)

    print(f"  Creating virtual environment at {VENV_DIR}")
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    venv.create(str(VENV_DIR), with_pip=True)

    venv_python = str(_venv_python())
    print("  Upgrading pip...")
    subprocess.run([venv_python, "-m", "pip", "install", "--quiet", "--upgrade", "pip"], check=True)

    print("  Installing PosPay and its dependencies (this is the slow part)...")
    subprocess.run([venv_python, "-m", "pip", "install", "--quiet", "-e", str(PROJECT_ROOT)], check=True)

    VENV_MARKER.write_text("ok")
    print("  Setup complete.\n")


def _reexec_under_venv() -> None:
    # os.execv() replaces the process image immediately with no cleanup — anything
    # buffered on stdout (block-buffering kicks in whenever output isn't a live TTY,
    # e.g. redirected to a log file) would otherwise be silently dropped rather than
    # ever reaching whatever's capturing this script's output.
    sys.stdout.flush()
    sys.stderr.flush()
    venv_python = str(_venv_python())
    os.execv(venv_python, [venv_python, str(Path(__file__).resolve()), *sys.argv[1:]])


def _configure_run_env() -> None:
    """Points the app's database, check-image storage, and ML artifacts at .pospay-run/
    instead of their normal project-root-relative defaults (used by a manual `alembic
    upgrade head && uvicorn ...` dev setup) — this is what keeps the quickstart from
    ever writing into the checked-out source tree. setdefault() so an advanced user's
    own POSPAY_* env vars still win. Must run before the first `pospay.config.get_settings()`
    call anywhere (it's @lru_cache'd), so this is called before any `from pospay...` import."""
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("POSPAY_DATABASE_URL", f"sqlite:///{RUN_DIR / 'pospay.db'}")
    os.environ.setdefault("POSPAY_CHECK_IMAGE_STORAGE_DIR", str(RUN_DIR / "check_images"))
    os.environ.setdefault("POSPAY_ML_ARTIFACT_DIR", str(RUN_DIR / "ml_artifacts"))


def _check_tesseract() -> None:
    if shutil.which("tesseract") is None:
        print(
            "NOTE: Tesseract (used for check-image OCR) was not found on your PATH.\n"
            "      PosPay will still run — uploading a check image just won't extract\n"
            "      an amount/payee until you install it:\n"
            "        macOS:  brew install tesseract\n"
            "        Linux:  apt install tesseract-ocr\n"
        )


def _run_migrations() -> None:
    from alembic import command
    from alembic.config import Config

    print("Applying database migrations...")
    cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(PROJECT_ROOT / "migrations"))
    command.upgrade(cfg, "head")


def _prompt_first_run_setup() -> None:
    import getpass

    from sqlalchemy import select

    from pospay.db.session import get_session_factory
    from pospay.domain.tenant import Tenant
    from pospay.services.provisioning_service import create_tenant_with_admin

    session = get_session_factory()()
    try:
        if session.execute(select(Tenant.id).limit(1)).first() is not None:
            return  # already provisioned on a prior run — nothing to do

        print("No organization set up yet — let's create one.\n")
        tenant_name = input("Organization name (e.g. 'Acme Corp'): ").strip()
        default_slug = (tenant_name or "acme").lower().replace(" ", "-")
        tenant_slug = input(f"URL slug [{default_slug}]: ").strip() or default_slug
        admin_email = input("Admin email: ").strip()

        admin_password = getpass.getpass("Admin password (min 8 characters): ")
        while len(admin_password) < 8:
            print("Please choose a password of at least 8 characters.")
            admin_password = getpass.getpass("Admin password (min 8 characters): ")

        confirm_password = getpass.getpass("Confirm password: ")
        while confirm_password != admin_password:
            print("Passwords didn't match — try again.")
            admin_password = getpass.getpass("Admin password (min 8 characters): ")
            confirm_password = getpass.getpass("Confirm password: ")

        create_tenant_with_admin(
            session,
            tenant_name=tenant_name,
            tenant_slug=tenant_slug,
            admin_email=admin_email,
            admin_password=admin_password,
        )
        session.commit()
        print(f"\nCreated organization '{tenant_name}' (slug: {tenant_slug}) with admin {admin_email}.\n")
    finally:
        session.close()


def _open_browser_when_ready(url: str) -> None:
    import socket
    import threading
    import time
    import webbrowser

    def _wait_and_open() -> None:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                with socket.create_connection((HOST, PORT), timeout=0.5):
                    break
            except OSError:
                time.sleep(0.2)
        webbrowser.open(url)

    threading.Thread(target=_wait_and_open, daemon=True).start()


def main() -> None:
    os.chdir(PROJECT_ROOT)  # pin cwd regardless of how this was invoked (double-click,
    # `python3 scripts/launcher.py` from elsewhere, etc.) — everything else uses absolute paths anyway

    if not _is_running_under_venv():
        _create_venv_and_install()
        _reexec_under_venv()
        return  # unreachable: execv replaces this process

    _configure_run_env()
    _check_tesseract()
    _run_migrations()
    _prompt_first_run_setup()

    url = f"http://{HOST}:{PORT}/ui/login"
    print(f"Starting PosPay at {url}")
    print(f"Everything this run creates lives under {RUN_DIR} — delete that folder to fully reset.")
    print("Press Ctrl+C to stop.\n")
    _open_browser_when_ready(url)

    import uvicorn

    from pospay.main import app

    try:
        uvicorn.run(app, host=HOST, port=PORT)
    except OSError as exc:
        print(f"\nCouldn't start the server: {exc}")
        print(f"Something may already be using port {PORT} — close it and try again.")
        sys.exit(1)


if __name__ == "__main__":
    main()
