from app.worker.celery_app import celery_app


def test_celery_app_uses_quorum_queue_defaults() -> None:
    queue = celery_app.conf.task_queues[0]

    assert queue.name == "npm-sentinel"
    assert queue.durable is True
    assert queue.queue_arguments == {"x-queue-type": "quorum"}
    assert celery_app.conf.task_ignore_result is True
    assert celery_app.conf.task_acks_late is True
    assert celery_app.conf.task_reject_on_worker_lost is True
    assert celery_app.conf.worker_prefetch_multiplier == 1
    assert celery_app.conf.worker_detect_quorum_queues is True
    assert celery_app.conf.worker_enable_remote_control is False
