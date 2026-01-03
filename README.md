# FastAPI Docker Boilerplate

Minimal, production-ready FastAPI boilerplate with Docker and docker-compose.
Designed to be reused as a base for APIs and ML services.

## Features
- FastAPI with health check
- Dockerized development environment
- Hot reload for local development
- Basic test setup with pytest

## Requirements
- Docker
- Docker Compose

## Getting Started

Create environment file:
```bash
cp .env.example .env
```

Build and start the service:
docker-compose up --build
docker-compose down

API endpoints:

API root: http://localhost:8000

Swagger docs: http://localhost:8000/docs

Health check: http://localhost:8000/health/

## Common Commands

Run tests:
```
docker-compose run api pytest
```


Stop services:
```
docker-compose down
```


Rebuild image only:
```
docker-compose build
```

## Project Structure
```
app/
├── main.py        # App entry point
├── api/           # Route definitions
│   └── health.py
├── core/          # Config and settings
│   └── config.py
tests/             # Pytest tests
Dockerfile
docker-compose.yml
requirements.txt
.env.example
```

## Extending the Project

- Add new routes under app/api

- Add shared config in app/core/config.py

- Add dependencies to requirements.txt

- Add tests in tests/