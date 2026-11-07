from alembic import context
from sqlalchemy import engine_from_config, pool

from unimatch.config import Settings
from unimatch.db_models import Base

config = context.config
target_metadata = Base.metadata

# A pre-built SQLAlchemy connection may be injected via config.attributes['connection']
# to run migrations against an isolated schema (e.g. in integration tests).
# When present, DATABASE_URL is not required and the normal engine path is skipped.
_injected_connection = config.attributes.get("connection")

if _injected_connection is None:
    settings = Settings.from_environment()
    if settings.database_url is None:
        raise RuntimeError("DATABASE_URL must be configured to run Alembic migrations")
    config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))
else:
    settings = Settings.from_environment()


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url if _injected_connection is None else None,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    if _injected_connection is not None:
        # Use the pre-built connection; search_path must already be set by the caller.
        context.configure(
            connection=_injected_connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()
        return

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()

    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
