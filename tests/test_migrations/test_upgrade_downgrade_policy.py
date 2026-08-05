# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

"""Codifies the upgrade/downgrade support policy (see README.md's "Upgrade and downgrade
support" section and migrations/version_history.py): upgrading is always supported, from
any prior version; downgrading is only supported up to 2 minor versions back, never
across a major version boundary.

Also carries regression coverage for a specific class of bug found while establishing
this policy: a migration that backfills a new enum-typed column's *existing* rows with a
lowercase string literal (matching the Python enum's `.value`) instead of the uppercase
member *name* this app's enum columns actually expect on read (confirmed: no
`values_callable` configured anywhere, so SQLAlchemy's default enum serialization applies
everywhere). Each bug of this shape inserts fine and then raises `LookupError` the moment
anything reads the row back through the ORM -- exactly the kind of thing "upgrading is
fully supported" must guarantee against.
"""

import sqlite3
import tomllib
import uuid
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

from migrations.version_history import VERSION_HISTORY, minor_versions_back
from pospay.config import get_settings
from pospay.db.session import reset_engine_cache

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _current_app_version() -> str:
    with open(PROJECT_ROOT / "pyproject.toml", "rb") as f:
        return tomllib.load(f)["project"]["version"]


def _alembic_config() -> Config:
    cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(PROJECT_ROOT / "migrations"))
    return cfg


@pytest.fixture
def scratch_db(tmp_path, monkeypatch):
    """A throwaway, file-backed sqlite db -- migrations/env.py reads the URL from
    pospay's own (lru_cache'd) settings, so the env var must be set and the cache
    cleared before Alembic's Config is ever touched, same "before any `from pospay...`
    import" ordering scripts/launcher.py's own doc comments call out."""
    db_path = tmp_path / "migration_policy.db"
    monkeypatch.setenv("POSPAY_DATABASE_URL", f"sqlite:///{db_path}")
    get_settings.cache_clear()
    reset_engine_cache()
    yield db_path
    get_settings.cache_clear()
    reset_engine_cache()


def test_full_upgrade_from_base_succeeds(scratch_db):
    command.upgrade(_alembic_config(), "head")


def test_upgrade_does_not_disable_other_loggers(scratch_db):
    """Regression test: migrations/env.py's fileConfig(alembic.ini) call defaults to
    disable_existing_loggers=True, which silently sets .disabled = True on every Python
    logger that already exists at that point and isn't explicitly named in alembic.ini's
    [loggers] section -- e.g. any pospay.* module logger created by an import that ran
    before this migration did. That's a standard fileConfig() gotcha (confirmed directly
    by reproducing it before the fix), not something alembic.ini's [loggers] section is
    meant to enumerate every application logger to avoid. Once disabled, a logger stays
    disabled for the rest of the process -- caught here because a real caller
    (ocr/factory.py's stub-provider warning) depends on its own logger actually firing."""
    import logging

    logger = logging.getLogger("pospay.some_arbitrary_module_not_in_alembic_ini")
    assert logger.disabled is False

    command.upgrade(_alembic_config(), "head")

    assert logger.disabled is False


class TestMinorVersionsBack:
    HISTORY = {
        "1.0.0": "revA",
        "1.1.0": "revB",
        "1.2.0": "revC",
        "1.3.0": "revD",
        "2.0.0": "revE",
    }

    def test_two_back_within_same_major(self):
        assert minor_versions_back(self.HISTORY, "1.3.0", 2) == "revB"

    def test_not_enough_history_returns_none(self):
        assert minor_versions_back(self.HISTORY, "1.1.0", 2) is None

    def test_never_crosses_a_major_version_boundary(self):
        assert minor_versions_back(self.HISTORY, "2.0.0", 2) is None

    def test_patch_release_does_not_count_as_its_own_step_back(self):
        history = {**self.HISTORY, "1.2.5": "revC2"}
        # 1 back from 1.3.0 is minor 1.2 -- and the *latest* patch recorded for that
        # minor (1.2.5's revC2), not the original 1.2.0 entry.
        assert minor_versions_back(history, "1.3.0", 1) == "revC2"


def test_downgrade_two_minor_versions_supported(scratch_db):
    current_version = _current_app_version()
    target_revision = minor_versions_back(VERSION_HISTORY, current_version, 2)
    if target_revision is None:
        pytest.skip(
            f"Not enough recorded release history yet to test downgrading 2 minor versions back from "
            f"{current_version} (see migrations/version_history.py) -- expected right after this policy lands."
        )

    command.upgrade(_alembic_config(), "head")
    command.downgrade(_alembic_config(), target_revision)


# --- Regression coverage for the four enum-casing bugs found while auditing the chain ---


def _connect(db_path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys=OFF")
    return conn


def test_payment_network_settlement_timing_survives_migration_and_orm_read(scratch_db):
    command.upgrade(_alembic_config(), "9327972d0952")  # inserts the check/ach rows itself

    from pospay.db.session import get_session_factory
    from pospay.domain.payment_network import PaymentNetwork

    session = get_session_factory()()
    try:
        rows = session.query(PaymentNetwork).all()
        assert {r.code for r in rows} == {"check", "ach"}
    finally:
        session.close()


def test_bulk_upload_file_source_survives_migration_and_orm_read(scratch_db):
    command.upgrade(_alembic_config(), "a3b4c5d6e7f8")
    conn = _connect(scratch_db)
    row_id, tenant_id, user_id = uuid.uuid4().hex, uuid.uuid4().hex, uuid.uuid4().hex
    conn.execute(
        "INSERT INTO bulk_upload_file (id, tenant_id, kind, original_filename, storage_path, size_bytes, "
        "sha256_hex, signature_hex, uploaded_by_user_id) VALUES (?, ?, 'ISSUED_ITEMS', 'x.csv', '/tmp/x', 10, 'a', 'b', ?)",
        (row_id, tenant_id, user_id),
    )
    conn.commit()
    conn.close()

    command.upgrade(_alembic_config(), "b1c2d3e4f5a6")

    from pospay.db.session import get_session_factory
    from pospay.domain.bulk_upload_file import BulkUploadFile, BulkUploadSource

    session = get_session_factory()()
    try:
        row = session.query(BulkUploadFile).one()
        assert row.source == BulkUploadSource.MANUAL
    finally:
        session.close()


def test_exception_item_source_survives_migration_and_orm_read(scratch_db):
    command.upgrade(_alembic_config(), "d4e5f6a7b8c9")
    conn = _connect(scratch_db)
    row_id, tenant_id, source_item_id = uuid.uuid4().hex, uuid.uuid4().hex, uuid.uuid4().hex
    conn.execute(
        "INSERT INTO exception_item (id, tenant_id, network_code, source_item_id, exception_types, status) "
        "VALUES (?, ?, 'check', ?, 'x', 'OPEN')",
        (row_id, tenant_id, source_item_id),
    )
    conn.commit()
    conn.close()

    command.upgrade(_alembic_config(), "e5f6a7b8c9d0")

    from pospay.db.session import get_session_factory
    from pospay.domain.exception_item import ExceptionItem, ExceptionItemSource

    session = get_session_factory()()
    try:
        row = session.query(ExceptionItem).one()
        assert row.source == ExceptionItemSource.LIVE
    finally:
        session.close()


def test_decision_source_survives_migration_and_orm_read(scratch_db):
    command.upgrade(_alembic_config(), "e5f6a7b8c9d0")
    conn = _connect(scratch_db)
    row_id, tenant_id, exception_item_id, user_id = (uuid.uuid4().hex for _ in range(4))
    conn.execute(
        "INSERT INTO decision (id, tenant_id, exception_item_id, outcome, reason_code, decided_by_user_id) "
        "VALUES (?, ?, ?, 'PAY', 'x', ?)",
        (row_id, tenant_id, exception_item_id, user_id),
    )
    conn.commit()
    conn.close()

    command.upgrade(_alembic_config(), "f7a8b9c0d1e2")

    from pospay.db.session import get_session_factory
    from pospay.domain.decision import Decision, DecisionSource

    session = get_session_factory()()
    try:
        row = session.query(Decision).one()
        assert row.source == DecisionSource.HUMAN
    finally:
        session.close()
