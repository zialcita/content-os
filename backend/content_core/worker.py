"""Separate non-paid ingestion worker. Real file validation, not provider simulation.

This milestone supports a bounded UTF-8 text policy, not general antivirus. Other
formats remain BLOCKED until an approved scanner/probe adapter is installed.
"""
import codecs
import hashlib
import time
from uuid import UUID
from sqlalchemy import text
from .security import guard_worker
from .storage import StorageError


def call(c,name,**params):
    return c.execute(text('SELECT cos_v6.'+name+'('+','.join(':'+k for k in params)+')'),params).scalar_one()


class IngestionWorker:
    def __init__(self,engine,store,*,text_policy=True):
        guard_worker(engine)
        self.engine,self.store,self.text_policy=engine,store,text_policy

    def process_one(self,workspace,brand):
        w,b=UUID(str(workspace)),UUID(str(brand))
        with self.engine.begin() as c:
            work=call(c,'cc_claim',w=w,b=b)
        if work is None or work['status']!='RUNNING': return work
        params=dict(w=w,b=b,jid=UUID(work['job_id']),cap=work['claim'],fence=work['fence'])
        outcome='CLEAR';digest=None;size=0;mime=work.get('mime_type');scanner=None;probe=None
        try:
            if work['job_kind']=='PURGE_CANCELLED_UPLOAD':
                with self.engine.begin() as c: call(c,'cc_heartbeat',**params)
                self.store.purge(work['key']);outcome='PURGED'
            elif self.store is None:
                outcome='STORAGE_UNCONFIGURED'
            elif not self.text_policy or mime!='text/plain':
                outcome='SCANNER_UNCONFIGURED'
            else:
                hasher=hashlib.sha256();decoder=codecs.getincrementaldecoder('utf8')();started=time.monotonic()
                for data in self.store.chunks(work['key'],work['parts']):
                    if time.monotonic()-started>30: outcome='PROCESSING_LIMIT';break
                    hasher.update(data);size+=len(data)
                    text_value=decoder.decode(data)
                    if any(ord(ch)<32 and ch not in '\n\r\t' for ch in text_value): outcome='SCAN_REJECTED';break
                    if size==len(data) and data.startswith((b'%PDF-',b'PK\x03\x04',b'MZ',b'\x7fELF')): outcome='MIME_MISMATCH';break
                    with self.engine.begin() as c: call(c,'cc_heartbeat',**params)
                decoder.decode(b'',final=True)
                digest=hasher.digest()
                if outcome=='CLEAR':
                    if size!=work['expected_size']: outcome='SIZE_MISMATCH'
                    elif digest.hex()!=work['expected_sha256']: outcome='HASH_MISMATCH'
                    else: scanner,probe='TEXT_POLICY_V1','UTF8_BOUNDS_V1'
        except UnicodeDecodeError: outcome='PROBE_REJECTED'
        except StorageError: outcome='STORAGE_INVALID'
        # A lost DB/lease/authorization outcome propagates; never fake success or blindly finish.
        with self.engine.begin() as c:
            return call(c,'cc_finish',**params,outcome=outcome,h=digest,sz=size,mime=mime,scanner=scanner,probe=probe)
