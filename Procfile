web: sh start.sh
worker: celery -A app.workers.celery_app.celery worker --loglevel=info
beat: celery -A app.workers.celery_app.celery beat --loglevel=info
