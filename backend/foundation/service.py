"""Small SQLAlchemy interface to the privilege-enforced simulation routines.

Connections must authenticate as a provisioned individual database login. There
is deliberately no actor_id setter, service bypass, env/config import or LIVE mode.
Transactions are caller-owned and must use READ COMMITTED isolation. SQL actor/
authorize entrypoints reject other isolation levels (including REPEATABLE READ and
SERIALIZABLE), even for direct SQL callers; configure isolation before beginning a
transaction. Workspace locking alone cannot refresh a transaction-wide snapshot.
Commit intent before any hypothetical external work.
"""
from sqlalchemy import text

PUBLIC_ROUTINES = frozenset({
    'set_membership', 'set_brand_grant', 'set_budget', 'enqueue', 'claim',
    'heartbeat', 'reserve', 'release_reservation', 'record_intent', 'complete',
    'consume', 'recover', 'claim_event', 'ack_event',
})


def call(connection, routine, *args):
    if routine not in PUBLIC_ROUTINES:
        raise ValueError('No public foundation routine by that name')
    # psycopg cannot infer uuid from a Python string in overloaded function calls.
    # Callers use uuid.UUID, bytes, int, bool and lists, not ambiguous string IDs.
    placeholders = ','.join(f':p{i}' for i in range(len(args)))
    return connection.execute(text(f'SELECT * FROM cos_v6.{routine}({placeholders})'),
                              {f'p{i}': value for i, value in enumerate(args)})
