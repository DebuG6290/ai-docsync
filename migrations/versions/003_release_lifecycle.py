"""Expose verified publication and knowledge refresh lifecycle."""
from alembic import op
import sqlalchemy as sa

revision = '003_lifecycle'
down_revision = '002_human'
branch_labels = None
depends_on = None


def upgrade():
    columns = {c['name'] for c in sa.inspect(op.get_bind()).get_columns('documentation_releases')}
    for name in ('merged_at', 'index_started_at', 'activated_at', 'status_checked_at'):
        if name not in columns:
            op.add_column('documentation_releases', sa.Column(name, sa.DateTime(timezone=True), nullable=True))


def downgrade():
    raise RuntimeError('Release lifecycle history is retained')
