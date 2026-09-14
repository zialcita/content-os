"""Combined revision and wall-clock boundary evidence; fixture identities only."""
import asyncio
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import create_engine, text

from conftest import onboard, brand
from foundation.service import call as foundation_call
from secure_api.errors import APIError
from secure_api.oidc import OIDCVerifier


def test_foundation_accounting_still_works_after_identity_upgrade(api):
    owner = api.login()
    w = UUID(onboard(api, owner)['workspace_id'])
    b = UUID(brand(owner, str(w))['brand_id'])
    user = UUID(owner.response.json()['user']['user_id'])
    role = 'fixture_combined_' + uuid4().hex
    with api.db.engine.begin() as c:
        c.exec_driver_sql(f'CREATE ROLE {role} LOGIN INHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS')
        c.exec_driver_sql(f'GRANT cos_foundation_runtime TO {role}')
        c.execute(text('INSERT INTO cos_v6.database_principals VALUES(:r,:u)'), {'r':role, 'u':user})
    engine = create_engine(api.db.runtime.url.set(username=role), hide_parameters=True)
    try:
        with engine.begin() as c:
            job = foundation_call(c, 'enqueue', w,b,uuid4(),b'z'*32).scalar_one()
            foundation_call(c,'set_budget',w,None,'USD',100,'combined fixture')
            foundation_call(c,'set_budget',w,job,'USD',100,'combined fixture')
        worker=uuid4()
        with engine.begin() as c:
            step=foundation_call(c,'claim',w,b,worker,30).mappings().one()
            args=(w,step['id'],worker,step['fencing_token'])
            foundation_call(c,'reserve',*args,'USD',10)
            foundation_call(c,'record_intent',*args)
        with engine.begin() as c:
            foundation_call(c,'complete',*args,7)
        with engine.connect() as c:
            ledger=c.execute(text('SELECT execution_mode,amount_units FROM cos_v6.usage_ledger WHERE workspace_id=:w'), {'w':w}).one()
            assert tuple(ledger) == ('SIMULATED',7)
            assert c.execute(text('SELECT count(*) FROM cos_v6.event_outbox WHERE workspace_id=:w'), {'w':w}).scalar_one() == 1
    finally:
        engine.dispose()
        with api.db.engine.begin() as c:
            c.execute(text('DELETE FROM cos_v6.database_principals WHERE database_role=:r'), {'r':role})
            c.exec_driver_sql(f'REVOKE cos_foundation_runtime FROM {role}')
            c.exec_driver_sql(f'DROP ROLE {role}')


def test_oidc_exchange_has_a_total_wall_clock_deadline(api, monkeypatch):
    class SlowStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            for _ in range(20):
                await asyncio.sleep(.05)
                yield b'x'
    def handler(request):
        return httpx.Response(200,stream=SlowStream(),headers={'Content-Type':'application/json'})
    verifier=OIDCVerifier(api.settings.oidc,httpx.MockTransport(handler))
    monkeypatch.setattr(verifier,'total_timeout_seconds',.01)
    with pytest.raises(APIError,match='INVALID_LOGIN'):
        asyncio.run(verifier.complete('fixture-code','fixture-verifier','fixture-nonce'))


def test_session_cannot_reference_another_users_identity(api):
    from sqlalchemy.exc import DBAPIError
    first, second = api.login(), api.login()
    a = UUID(first.response.json()['user']['user_id'])
    b = UUID(second.response.json()['user']['user_id'])
    with pytest.raises(DBAPIError) as error:
        with api.db.engine.begin() as c:
            c.execute(text('UPDATE cos_v6.sessions SET identity_id=(SELECT id FROM cos_v6.user_identities WHERE user_id=:b) WHERE user_id=:a'), {'a':a, 'b':b})
    assert error.value.orig.sqlstate == '23503'
