FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml alembic.ini ./
COPY backend ./backend
COPY etl ./etl
COPY analysis ./analysis
COPY configs ./configs
COPY migrations ./migrations
RUN python -m pip install --no-cache-dir .

CMD ["sh", "-c", "python -m alembic upgrade head && python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000"]

