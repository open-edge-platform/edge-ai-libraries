.PHONY: help install test lint format run docker-build docker-up docker-down clean

help:
	@echo "Semantic Comparison Service - Makefile Commands"
	@echo "================================================"
	@echo "install       - Install dependencies"
	@echo "test          - Run tests with coverage"
	@echo "test-fast     - Run tests without coverage"
	@echo "lint          - Run linters"
	@echo "format        - Format code"
	@echo "run           - Run service locally"
	@echo "docker-build  - Build Docker image"
	@echo "docker-up     - Start Docker containers"
	@echo "docker-down   - Stop Docker containers"
	@echo "clean         - Clean temporary files"

install:
	@echo "📦 Installing dependencies..."
	pip install --upgrade pip
	pip install -r requirements.txt

test:
	@echo "🧪 Running tests with coverage..."
	pytest -v --cov=app --cov-report=term-missing --cov-report=html

test-fast:
	@echo "⚡ Running tests (fast)..."
	pytest -v --tb=short

lint:
	@echo "🔍 Running linters..."
	ruff check app tests
	mypy app

format:
	@echo "✨ Formatting code..."
	black app tests
	ruff check --fix app tests

run:
	@echo "🚀 Starting service..."
	uvicorn app.main:app --reload --port 8080

docker-build:
	@echo "🐳 Building Docker image..."
	cd docker && docker compose build

docker-up:
	@echo "🐳 Starting Docker containers..."
	cd docker && docker compose up -d
	@echo "✅ Service running at http://localhost:8080"
	@echo "📊 Metrics at http://localhost:9090/metrics"
	@echo "📚 API docs at http://localhost:8080/docs"

docker-down:
	@echo "🐳 Stopping Docker containers..."
	cd docker && docker compose down

docker-logs:
	@echo "📋 Viewing logs..."
	cd docker && docker compose logs -f semantic-service

clean:
	@echo "🧹 Cleaning temporary files..."
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	rm -rf htmlcov .coverage
	@echo "✅ Cleaned!"
