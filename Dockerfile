# Image de base légère avec Python
FROM python:3.11-slim

# Bonnes pratiques : pas de bytecode, logs non bufferisés (visibles direct dans Cloud Logging)
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# On copie d'abord requirements.txt seul pour profiter du cache Docker
# (si le code change mais pas les dépendances, on ne réinstalle pas tout)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

# Cloud Run Job exécute directement cette commande, du début à la fin.
ENTRYPOINT ["python", "main.py"]
