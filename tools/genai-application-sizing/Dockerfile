FROM python:3.11-slim

RUN groupadd -g 1000 appuser && \
    useradd -m -g appuser appuser

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

USER appuser

ENTRYPOINT ["python3", "profile-runner.py"]
