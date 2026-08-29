FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Pillow renders the PDA cards inside the container. The slim Python image does
# not ship a Cyrillic-capable TrueType font, so without this Ukrainian text is
# rendered as square placeholder glyphs. DejaVu Sans covers Ukrainian/Cyrillic
# and matches the paths already used by app/pda_renderer.py.
RUN apt-get update \
    && apt-get install -y --no-install-recommends fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY app ./app
RUN pip install --no-cache-dir .

RUN mkdir -p /app/data

CMD ["python", "-m", "app.main"]
