# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Chaffed

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from pospay.config import get_settings
from pospay.workers.tasks import dropbox_import_job, notification_dispatch_job, retrain_job

_scheduler: BackgroundScheduler | None = None


def start_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is not None:
        return _scheduler

    settings = get_settings()
    _scheduler = BackgroundScheduler()
    if settings.enable_ml_scheduler:
        _scheduler.add_job(
            retrain_job,
            CronTrigger(hour=settings.ml_retrain_cron_hour, minute=0),
            id="ml_retrain_job",
            replace_existing=True,
        )
    if settings.auto_import_enabled:
        _scheduler.add_job(
            dropbox_import_job,
            IntervalTrigger(seconds=settings.auto_import_interval_seconds),
            id="dropbox_import_job",
            replace_existing=True,
        )
    if settings.notifications_enabled:
        _scheduler.add_job(
            notification_dispatch_job,
            IntervalTrigger(seconds=settings.notification_dispatch_interval_seconds),
            id="notification_dispatch_job",
            replace_existing=True,
        )
    _scheduler.start()
    return _scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
