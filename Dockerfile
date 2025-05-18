# Basis-Image mit Python 3.11
FROM python:3.11-slim

# System-Tools und Node.js installieren
RUN apt-get update && apt-get install -y curl gnupg && \
    curl -fsSL https://deb.nodesource.com/setup_18.x | bash - && \
    apt-get install -y nodejs && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Arbeitsverzeichnis setzen
WORKDIR /app

# Projektdateien kopieren
COPY . .

# Python-Abhängigkeiten installieren
RUN pip install --no-cache-dir -r requirements.txt

# Startskript schreiben: client_secrets.json erzeugen + App starten
RUN echo '#!/bin/sh\n' \
         'echo "$CLIENT_SECRETS_CONTENT" > /app/client_secrets.json\n' \
         'exec python gsc_server.py' \
         > /app/start.sh && chmod +x /app/start.sh

# Startkommando setzen
CMD ["sh", "/app/start.sh"]
