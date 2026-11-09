"""Cold path in Celery (broker RabbitMQ): scan -> compile -> project, one portal at a time."""
import logging
import zlib

import httpx
from celery import shared_task
from django.db import transaction

from catalog.models import Portal
from ctx.compile import compile_portal as _compile
from ctx.locks import portal_lock
from sources.explore import scan

log = logging.getLogger(__name__)
NET = dict(autoretry_for=(httpx.TransportError,), retry_backoff=True, max_retries=3, acks_late=True)


@shared_task(**NET)
def scan_portal(domain, full=False):
    with portal_lock("scan", domain) as got:
        if not got:
            log.info("scan %s skipped: another scan holds the lock", domain)
            return {"skipped": "locked"}
        portal = Portal.objects.get(domain=domain)
        stats = scan(portal, full=full)
    transaction.on_commit(lambda: compile_portal.delay(domain))  # never enqueue work for uncommitted rows
    log.info("scan %s: %s", domain, stats)
    return stats


@shared_task(acks_late=True)
def compile_portal(domain):
    stats = _compile(Portal.objects.get(domain=domain), with_ids=True)
    if stats["changed"]:
        transaction.on_commit(lambda: project_portal.delay(domain, stats["changed"]))
    log.info("compile %s: %s compiled, %s unchanged", domain, stats["compiled"], stats["unchanged"])
    return {k: v for k, v in stats.items() if k != "changed"}


@shared_task(**NET)
def project_portal(domain, changed=None):
    from catalog.models import Dataset
    from projections import es, graph
    portal = Portal.objects.get(domain=domain)
    if changed:
        for ds in Dataset.objects.filter(portal=portal, dataset_id__in=changed).select_related("portal"):
            es.upsert_es(ds)
    else:
        es.project_es(portal)
    g = graph.project_graph(portal)
    log.info("project %s: es %s cards, neo4j %s", domain, len(changed) if changed else "all", g)
    return {"es": len(changed) if changed else "all", "neo4j": g}


@shared_task
def scan_all():
    """Hourly (beat). Spread portals over the hour so 5 000 portals do not hit the API in the same minute."""
    for domain in Portal.objects.values_list("domain", flat=True):
        scan_portal.apply_async((domain,), countdown=(zlib.crc32(domain.encode()) % 60) * 60)
