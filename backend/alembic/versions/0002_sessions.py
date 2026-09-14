"""Opaque sessions and isolated identity API; no foundation actor replacement."""
from pathlib import Path
from alembic import op
from secure_api.audit import audit_identity_privileges

revision = '0002_sessions'
down_revision = '0001_m1_foundation'
branch_labels = ('identity',)
depends_on = None


def upgrade():
    path = Path(__file__).resolve().parents[2] / 'secure_api' / 'session_schema.sql'
    op.get_bind().exec_driver_sql(path.read_text(), execution_options={'no_parameters': True})
    audit_identity_privileges(op.get_bind())


def downgrade():
    raise RuntimeError('Retention-safe identity downgrade refused: preserve identity/audit history; forward-fix')
