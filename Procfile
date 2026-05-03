web: gunicorn --chdir server wsgi:app --bind 0.0.0.0:$PORT --workers 2
release: flask --app server.wsgi db upgrade
