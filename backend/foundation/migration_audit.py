"""Compose installed-slice audits after every migration and on head reruns.

No environment lookup, credentials or implicit migration connection. Revision001
remains independently testable; identity auditing becomes mandatory when any of
its principal schema markers exists. Features must add explicit reviewed audits.
"""
from sqlalchemy import text
from foundation.privileges import audit_function_privileges


def audit_migrated_privileges(connection):
    audit_function_privileges(connection)
    identity_present = connection.execute(text("""
        SELECT to_regclass('cos_v6.sessions') IS NOT NULL
            OR EXISTS(SELECT 1 FROM pg_roles WHERE rolname IN
                ('cos_api_runtime','cos_identity_auth','cos_identity_owner'))
            OR EXISTS(SELECT 1 FROM public.cos_v6_alembic_version WHERE version_num='0002_sessions')
    """)).scalar_one()
    if identity_present:
        from secure_api.audit import audit_identity_privileges
        audit_identity_privileges(connection)
