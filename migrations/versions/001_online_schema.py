"""Bootstrap the existing online schema, including existing installations."""
from alembic import op
from docsync.web.models import Base

revision = '001_online'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    Base.metadata.create_all(op.get_bind())


def downgrade():
    raise RuntimeError('Online audit history cannot be dropped by migration downgrade')
