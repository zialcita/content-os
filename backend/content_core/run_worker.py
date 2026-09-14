"""Explicitly configured development worker process; never uses DATABASE_URL.

CONTENT_WORKER_DATABASE_URL must authenticate only as the restricted worker role.
Do not supply a migration/admin URL. No provider calls or paid operations exist.
"""
import argparse
import os
import time
from sqlalchemy import create_engine
from .storage import LocalStore
from .worker import IngestionWorker


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--workspace',required=True)
    p.add_argument('--brand',required=True)
    p.add_argument('--private-root',required=True)
    p.add_argument('--development',action='store_true')
    p.add_argument('--once',action='store_true')
    args=p.parse_args()
    if not args.development: p.error('Production worker is not enabled')
    dsn=os.environ.get('CONTENT_WORKER_DATABASE_URL')
    if not dsn: p.error('Restricted worker connection must be configured outside chat')
    engine=create_engine(dsn,hide_parameters=True)
    store=LocalStore(args.private_root,development=True)
    try:
        worker=IngestionWorker(engine,store)
        while True:
            outcome=worker.process_one(args.workspace,args.brand)
            if args.once: break
            if outcome is None: time.sleep(1)
    finally:
        store.close();engine.dispose()

if __name__=='__main__':main()
