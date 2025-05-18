FROM python:3.10-slim

WORKDIR /app

COPY . .

RUN pip install --no-cache-dir -r requirements.txt

# Startskript schreiben, das das Secret als Datei speichert und den Server startet
RUN echo '#!/bin/sh\n' \
         'echo "$CLIENT_SECRETS_CONTENT" > /app/client_secrets.json\n' \
         'exec python gsc_server.py' \
         > /app/start.sh && chmod +x /app/start.sh

CMD ["sh", "/app/start.sh"]
