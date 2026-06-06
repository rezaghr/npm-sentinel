from celery import Celery
from kombu import Exchange, Queue

from app.core.config import get_settings
from app.core.logging import configure_logging

settings = get_settings()
configure_logging(settings)

celery_kwargs = {
    "broker": settings.celery_broker_url,
}
if settings.celery_result_backend:
    celery_kwargs["backend"] = settings.celery_result_backend

celery_app = Celery("npm_sentinel", **celery_kwargs)

celery_app.conf.update(
    task_default_queue="npm-sentinel",
    task_default_exchange="npm-sentinel",
    task_default_exchange_type="direct",
    task_default_routing_key="npm-sentinel",
    task_queues=(
        Queue(
            "npm-sentinel",
            exchange=Exchange("npm-sentinel", type="direct", durable=True),
            routing_key="npm-sentinel",
            durable=True,
            queue_arguments={"x-queue-type": "quorum"},
        ),
    ),
    task_create_missing_queues=False,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_ignore_result=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    timezone="UTC",
    enable_utc=True,
    worker_prefetch_multiplier=1,
    worker_detect_quorum_queues=True,
    worker_enable_remote_control=False,
    broker_transport_options={"confirm_publish": True},
    imports=("app.worker.tasks",),
)
