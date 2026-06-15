FROM python:3.12-slim

WORKDIR /app

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV DATABASE_URL=sqlite:////app/data/bot.db
ENV TZ=Europe/Berlin

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY database/ database/
COPY services/ services/
COPY views/ views/
COPY handlers/ handlers/
COPY main.py .
COPY version.py .

RUN mkdir -p /app/data

CMD ["python", "main.py"]
