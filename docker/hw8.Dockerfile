# HW8 image for the Part 1 worker and FastAPI wrapper (same image, two commands)
FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONPATH=/app

COPY docker/requirements-hw8.txt /app/requirements-hw8.txt
RUN pip install --no-cache-dir -r /app/requirements-hw8.txt

# only the HW8 package is copied; the rest of the project is not needed here
COPY src/hw8_kafka /app/src/hw8_kafka
