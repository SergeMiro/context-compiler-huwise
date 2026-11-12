"""Smart cache for query results. The key holds everything that can change the answer or who may see it:
portal (tenant) + permission scope + dataset + schema hash + data version + normalised params + recipe version.
A new schema, a new data version or another API key gives a new key, so a stale or foreign result is never served.
The scope is an HMAC of the client key: the key itself never enters the cache, a log or a trace."""
import hashlib
import hmac
import json
import threading
import time

from django.conf import settings

TTL_S = 3600
MAX_ITEMS = 2048


def scope_of(api_key):
    if not api_key:
        return "public"
    return "key:" + hmac.new(settings.SECRET_KEY.encode(), api_key.encode(), hashlib.sha256).hexdigest()[:16]


def data_version(ds):
    m = ds.raw_metas or {}
    return str(m.get("data_processed") or m.get("modified") or ds.modified or "")


def schema_version(ds):
    rows = sorted(ds.fields.values_list("name", "type"))
    return hashlib.sha256(repr(rows).encode()).hexdigest()[:16]


def key(portal, scope, ds, params, recipe=""):
    raw = json.dumps([portal, scope, ds.dataset_id, schema_version(ds), data_version(ds),
                      sorted((k, str(v).strip()) for k, v in params.items()), recipe], ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()


class Cache:
    # shortcut: per-process dict; move to a shared store (MariaDB table or memcached) with more than one server
    def __init__(self, ttl=TTL_S, max_items=MAX_ITEMS, clock=time.monotonic):
        self.ttl, self.max, self.clock = ttl, max_items, clock
        self.items, self.hits, self.misses = {}, 0, 0
        self.lock = threading.Lock()

    def get(self, k):
        with self.lock:
            hit = self.items.get(k)
            if hit and self.clock() - hit[0] < self.ttl:
                self.hits += 1
                return hit[1]
            self.items.pop(k, None)
            self.misses += 1
            return None

    def put(self, k, value):
        with self.lock:
            if len(self.items) >= self.max:
                self.items.pop(next(iter(self.items)))
            self.items[k] = (self.clock(), value)

    def stats(self):
        total = self.hits + self.misses
        return {"hits": self.hits, "misses": self.misses, "hit_ratio": round(self.hits / total, 3) if total else None}


CACHE = Cache()
