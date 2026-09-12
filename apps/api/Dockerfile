FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# libcairo2 : cairosvg rasterise les elements de skin, livres en SVG.
# fonts-dejavu-core : sans aucune police installee, le texte que portent ces
# SVG disparaitrait du rendu -- l'image de base n'en embarque pas.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libjpeg62-turbo libfreetype6 libcairo2 fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
