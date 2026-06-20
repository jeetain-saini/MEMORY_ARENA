"""Concrete scheduler infrastructure (Stage 11).

``InProcessScheduler`` implements the application's ``Scheduler`` port: it
registers ``ScheduledJob`` s and triggers them. A production driver (APScheduler,
Celery beat, Kubernetes CronJob) can replace it behind the same port with no
change to the jobs.
"""
