"""Add shared usage allowances without replacing review or knowledge history."""
from alembic import op
from docsync.web.models import UsageBucket

revision = '005_usage'
down_revision = '004_conflicts'
branch_labels = None
depends_on = None


def upgrade():
    UsageBucket.__table__.create(op.get_bind(), checkfirst=True)


def downgrade():
    raise RuntimeError('Downgrade is unsupported; restore a tested backup instead')
