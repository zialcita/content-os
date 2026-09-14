"""Private local uploads, fenced ingestion and immutable source versions."""
from pathlib import Path
from alembic import op
from content_core.security import audit_content_privileges
revision='0003_content_core'
down_revision='0002_sessions'
branch_labels=None
depends_on=None


def upgrade():
    path=Path(__file__).resolve().parents[2]/'content_core'/'schema.sql'
    op.get_bind().exec_driver_sql(path.read_text(),execution_options={'no_parameters':True})
    audit_content_privileges(op.get_bind())


def downgrade():
    raise RuntimeError('Retention-safe content downgrade refused: preserve source and ingestion history')
