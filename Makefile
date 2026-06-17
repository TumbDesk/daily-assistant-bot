.PHONY: install run test docker-up docker-down clean

# Install virtual environment and dependencies for local development
install:
	python3 -m venv .venv
	.venv/bin/pip install --upgrade pip
	.venv/bin/pip install -r requirements.txt -r requirements-dev.txt
	mkdir -p data

# Run the Telegram bot locally using the virtual environment
run:
	.venv/bin/python3 main.py

# Run the pytest suite
test:
	.venv/bin/pytest

# Initialize .env (if missing) and start the Docker containers
docker-up:
	cp -n .env.example .env || true
	docker compose up -d --build

# Stop and remove Docker containers
docker-down:
	docker compose down

# Clean up temporary Python cache files and logs
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type d -name ".pytest_cache" -exec rm -rf {} +