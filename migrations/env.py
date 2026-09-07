from alembic import context

from pcb_inspector.config import Settings
from pcb_inspector.database import Base, make_engine


def run_migrations() -> None:
    settings = Settings()
    if context.is_offline_mode():
        context.configure(
            url=settings.database_url,
            target_metadata=Base.metadata,
            literal_binds=True,
        )
        with context.begin_transaction():
            context.run_migrations()
    else:
        engine = make_engine(settings.database_url)
        with engine.connect() as connection:
            context.configure(connection=connection, target_metadata=Base.metadata)
            with context.begin_transaction():
                context.run_migrations()
        engine.dispose()


run_migrations()
