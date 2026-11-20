from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine

from mc_hub.db import (
    migrate,
    models,  # noqa: F401
)
from mc_hub.db.base import Base


def test_migrations_match_models(tmp_path):
    db = tmp_path / "m.db"
    migrate.upgrade_sync(db)
    eng = create_engine(f"sqlite:///{db}")
    with eng.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == []
