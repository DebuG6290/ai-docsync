"""Add immutable conflict scan evidence and human resolutions; retain all history."""
from alembic import op
from docsync.web.models import KnowledgeScan, KnowledgeConflict, ConflictResolution

revision = '004_conflicts'
down_revision = '003_lifecycle'
branch_labels = None
depends_on = None


def upgrade():
    for model in (KnowledgeScan, KnowledgeConflict, ConflictResolution):
        model.__table__.create(op.get_bind(), checkfirst=True)


def downgrade():
    raise RuntimeError('Conflict review history is retained')
