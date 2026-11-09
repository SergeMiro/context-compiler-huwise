"""One scan per portal across all workers: MariaDB GET_LOCK on a dedicated connection.
Dedicated, because Django may close/reopen the ORM connection mid-task and would silently drop the lock;
if the worker dies, MariaDB releases the lock with the connection."""
import contextlib
import hashlib

import MySQLdb
from django.conf import settings


@contextlib.contextmanager
def portal_lock(name, domain):
    db = settings.DATABASES["default"]
    conn = MySQLdb.connect(host=db["HOST"], port=int(db["PORT"]), user=db["USER"], password=db["PASSWORD"],
                           database=db["NAME"] if not db.get("TEST_NAME_IN_USE") else db["NAME"])
    key = f"ctxc:{name}:{hashlib.sha1(domain.encode()).hexdigest()[:16]}"  # GET_LOCK names are <= 64 chars
    try:
        cur = conn.cursor()
        cur.execute("SELECT GET_LOCK(%s, 0)", [key])
        got = cur.fetchone()[0] == 1
        try:
            yield got
        finally:
            if got:
                cur.execute("SELECT RELEASE_LOCK(%s)", [key])
    finally:
        conn.close()
