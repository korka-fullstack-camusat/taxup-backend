from celery import Celery
from app.core.config import settings

celery_app = Celery(
    "taxup",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_routes={
        "app.workers.tasks.process_transaction_async": {"queue": "transactions"},
        "app.workers.tasks.send_fraud_notification": {"queue": "notifications"},
        "app.workers.tasks.generate_daily_report": {"queue": "reports"},
    },
    beat_schedule={
        "generate-daily-report": {
            "task": "app.workers.tasks.generate_daily_report",
            "schedule": 86400.0,  # every 24 hours
        },
        "cleanup-old-tokens": {
            "task": "app.workers.tasks.cleanup_expired_sessions",
            "schedule": 3600.0,  # every hour
        },
    },
)
