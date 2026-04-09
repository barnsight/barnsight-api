# BarnSight API - Instructional Context

This document provides essential context and instructions for AI agents working on the BarnSight API codebase.

## Project Overview

BarnSight API is a robust, asynchronous event ingestion and analytics backend designed for farm hygiene monitoring. It bridges Edge AI devices (monitoring animal excrement) with farmer dashboards.

### Core Technology Stack
- **Framework:** [FastAPI](https://fastapi.tiangolo.com) (Python 3.11+)
- **Database:** [MongoDB](https://www.mongodb.com/) (using `motor` for async access)
- **Caching & Rate Limiting:** [Redis](https://redis.io/)
- **Authentication:** 
  - **Edge Devices:** SHA-256 hashed API Keys (custom headers).
  - **Web Users:** RS256 JWT (Asymmetric signing) and Google OAuth2.
- **Image Hosting:** [Cloudinary](https://cloudinary.com/) for detection snapshots.
- **Monitoring:** [Prometheus](https://prometheus.io/) via `prometheus-fastapi-instrumentator`.
- **Dependency Management:** [uv](https://github.com/astral-sh/uv).

### Architecture
The project follows a modular FastAPI structure:
- `src/app/main.py`: Application factory, middleware, and lifespan management.
- `src/app/api/`: Route handlers and dependencies.
- `src/app/core/`: Centralized configuration, database clients, security utilities, and Pydantic schemas.
- `src/app/crud/`: Database abstraction layer (CRUD pattern).
- `src/app/services/`: External service integrations (Cloudinary, Google OAuth).

## Development Workflows

### Environment Setup
1.  **Dependencies:** Use `uv` for lightning-fast installs.
    ```bash
    uv sync --all-extras
    ```
2.  **Configuration:** Copy `.env.example` to `.env` and fill in the required variables (MongoDB, Redis, Cloudinary, etc.).
3.  **JWT Keys:** Generate RSA keys for JWT signing if they aren't provided in the environment (the app will auto-generate them for dev if missing, but `openssl` is preferred for persistence).

### Building and Running
- **With Docker (Recommended):**
  ```bash
  docker compose up --build
  ```
- **Local Development:**
  ```bash
  uv run python -m app.main
  ```

### Testing and Validation
- **Run Tests:**
  ```bash
  uv run pytest src/tests/ -v
  ```
- **Linting & Formatting:** The project uses `ruff`.
  ```bash
  uv run ruff check .
  uv run ruff format .
  ```

## Coding Conventions

- **Indentation:** 2 spaces.
- **Line Length:** 100 characters (enforced by Ruff).
- **Asynchronous First:** Always use `async`/`await` for I/O operations (DB, Redis, HTTP requests).
- **Validation:** Use Pydantic v2 models for all request bodies and response schemas in `src/app/core/schemas/`.
- **Database Access:** Avoid direct database calls in routers. Encapsulate logic within the `src/app/crud/` layer.
- **Error Handling:** Use custom exception handlers and FastAPI's `HTTPException`.
- **Security:** 
  - Never store raw API keys; use SHA-256 hashes.
  - Use `Argon2` for password hashing.
  - Follow the dual-auth architecture: `API Key` for ingestion, `JWT` for management.

## Key Directories
- `src/app/api/v1/routers/`: contains all endpoint logic.
- `src/app/core/schemas/`: contains Pydantic models for data validation.
- `src/app/crud/`: contains logic for MongoDB interactions.
- `scripts/`: utility scripts for building and cleaning the environment.
