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

1. Clone the repository
```
git clone https://github.com/seemab-yamin/fastapi-boilerplate
cd fastapi-docker-boilerplate
```

2. Create environment file
```
cp .env.example .env
```

Edit .env if needed.


API endpoints:

API root: http://localhost:8000

Swagger docs: http://localhost:8000/docs

Health check: http://localhost:8000/health/

## Common Commands

Run tests:
```
docker-compose run api pytest
```

Build and start the service:

```docker-compose up --build```

Stop the service

```docker-compose down```


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