"""Explicit authoritative human version provenance."""
from alembic import op
import sqlalchemy as sa

revision = '002_human'
down_revision = '001_online'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    columns = {c['name'] for c in sa.inspect(bind).get_columns('proposal_versions')}
    if 'human_modified' not in columns:
        op.add_column('proposal_versions', sa.Column('human_modified', sa.Boolean(), nullable=False, server_default=sa.false()))
    bind.execute(sa.text("UPDATE proposal_versions SET human_modified = true WHERE author = 'human'"))


def downgrade():
    raise RuntimeError('Human provenance is retained')
