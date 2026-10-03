from alembic import context
from sqlalchemy import text
from docsync.web.config import get_settings
from docsync.web.database import make_engine
from docsync.web.models import Base

engine = make_engine(get_settings().database_url)
with engine.connect() as connection:
    context.configure(connection=connection, target_metadata=Base.metadata)
    with context.begin_transaction():
        if engine.dialect.name == 'postgresql':
            connection.execute(text('SELECT pg_advisory_xact_lock(741029610)'))
            connection.execute(text('CREATE EXTENSION IF NOT EXISTS vector'))
        context.run_migrations()
