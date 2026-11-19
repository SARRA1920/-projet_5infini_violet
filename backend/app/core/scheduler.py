"""Planificateur de tâches de fond (APScheduler).

Tourne dans le même processus que l'API FastAPI (pas de service séparé) :
suffisant ici puisque les cours ne changent que par import ponctuel, pas en
flux continu. Démarré une seule fois au lancement de l'application
(voir app.main), jamais appelé directement par une route.
"""
import logging

from apscheduler.schedulers.background import BackgroundScheduler

from app.services.order_book import run_order_book_check

logger = logging.getLogger("scheduler")

ORDER_BOOK_CHECK_SECONDS = 120  # les cours bougent rarement plus vite qu'une fois par jour

_scheduler: BackgroundScheduler | None = None


def start_scheduler() -> BackgroundScheduler:
    """Démarre le planificateur (idempotent : ne recrée pas de job si déjà lancé)."""
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(
        run_order_book_check,
        trigger="interval",
        seconds=ORDER_BOOK_CHECK_SECONDS,
        id="order_book_check",
        max_instances=1,       # jamais deux passages en parallèle
        coalesce=True,         # si plusieurs déclenchements manqués, un seul rattrapage
        misfire_grace_time=60,
    )
    scheduler.start()
    _scheduler = scheduler
    logger.info("Planificateur démarré : carnet d'ordre vérifié toutes les %ss", ORDER_BOOK_CHECK_SECONDS)
    return scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
