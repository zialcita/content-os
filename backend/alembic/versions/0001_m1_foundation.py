"""Add simulation-only foundation alongside untouched legacy tables."""
from pathlib import Path
from alembic import op

revision = '0001_m1_foundation'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    sql = Path(__file__).resolve().parents[2] / 'foundation' / 'schema.sql'
    op.get_bind().exec_driver_sql(sql.read_text(), execution_options={'no_parameters': True})


def downgrade():
    raise RuntimeError('Retention-safe downgrade refused: keep cos_v6 history and forward-fix')
