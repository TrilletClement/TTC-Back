FROM python:3.11-slim

# On ajoute 'git' à la liste des paquets à installer
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Le point de départ est la racine, donc requirements.txt est visible ici
COPY requirements.txt .

# On met à jour pip et on installe tout
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONPATH=/app

EXPOSE 8000