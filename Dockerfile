FROM python:3.11-slim

# libcairo2 + fontconfig: PNG rendering of strips (cairosvg) for the Android widgets.
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    build-essential \
    git \
    libcairo2 \
    fontconfig \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY . .

# cairosvg ignores the @font-face embedded in our SVGs and resolves fonts by
# family name through fontconfig — install Brusseline system-wide so the PNG
# renders match the SVG ones.
RUN mkdir -p /usr/local/share/fonts \
    && cp app/assets/fonts/brusseline-bold.ttf /usr/local/share/fonts/ \
    && fc-cache -f

ENV PYTHONPATH=/app

EXPOSE 8000
