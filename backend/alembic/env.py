"""Explicit connection only. Does not load config, dotenv or DATABASE_URL."""
from alembic import context
from foundation.privileges import audit_function_privileges

connection = context.config.attributes.get('connection')
if connection is None:
    raise RuntimeError('Pass an explicit SQLAlchemy connection; environment DSNs are refused')
context.configure(connection=connection, target_metadata=None,
                  version_table='cos_v6_alembic_version', version_table_schema='public',
                  on_version_apply=lambda **kw: audit_function_privileges(connection))
with context.begin_transaction():
    context.run_migrations()
    # No revision callback fires at head; still reject unsafe privilege drift.
    audit_function_privileges(connection)
