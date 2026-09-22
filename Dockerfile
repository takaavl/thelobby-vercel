FROM python:3.13-slim

WORKDIR /app
COPY . /app

ENV PYTHONUNBUFFERED=1     HOST=0.0.0.0     PORT=8765

EXPOSE 8765
CMD ["python","server.py"]
