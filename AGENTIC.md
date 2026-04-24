# BarnSight API - Agent Guidance

This document provides context and instructions for AI agents working on the BarnSight API codebase.

## Project Overview

BarnSight API is an asynchronous FastAPI backend for agricultural hygiene monitoring. It ingests computer-vision events from edge devices installed in barns, tracks physical device and per-camera health, stores remote edge configuration, and powers farmer/inspector analytics.

## Stack

- Framework: FastAPI, Python 3.11+
- Database: MongoDB via PyMongo async APIs
- Cache/status/rate limiting: Redis
- Auth: `X-API-Key` for edge devices, RS256 JWT for web users
- Images: Cloudinary for detection snapshots
- Tooling: `uv`, `pytest`, `ruff`

## Development Workflow

Install and run checks with:

```bash
uv sync --all-extras
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

Keep endpoint behavior account scoped. Edge API-key requests resolve `owner_id`; JWT requests use the token subject unless an existing admin-only path explicitly supports global querying.

## Production Edge Contracts

- Events live in `src/app/api/v1/routers/events.py`, `src/app/core/schemas/events.py`, and `src/app/crud/event_crud.py`.
- Physical device and camera registry plus device config live in `src/app/api/v1/routers/devices.py` and `src/app/core/schemas/devices.py`.
- Camera-scoped status, zones, and detections live in `src/app/api/v1/routers/cameras.py`.
- Analytics are served from `src/app/api/v1/routers/analytics.py` using event aggregation.

Identity model:
- `device_id` is the physical edge host/gateway, shared by all camera workers on that box.
- `camera_id` is one unique RTSP/USB stream and one edge worker/container.
- Zones must be scoped by `account_id + camera_id + zone_id`, not only by zone ID.
- Do not store RTSP credentials unless an encrypted secret system is added; store redacted stream labels only.

Important safety rules:
- Never log API keys or raw image payloads.
- Validate all edge payloads with Pydantic schemas.
- Reject oversized snapshots before Cloudinary upload.
- Replace raw base64 snapshots with Cloudinary URLs before MongoDB persistence.
- Preserve `event_id` idempotency using account-scoped uniqueness.
- Treat a camera as offline when its Redis heartbeat TTL expires.
- Treat a device as offline when all attached cameras are offline.

## Data and Indexes

The `barnsight.events` collection requires:
- unique partial index on `account_id + event_id`
- `account_id + timestamp`
- `account_id + barn_id + timestamp`
- `account_id + device_id + timestamp`
- `account_id + camera_id + timestamp`
- `account_id + barn_id + zone_id + timestamp`

Device collections:
- `devices`: physical edge hosts, unique per `account_id + device_id`
- `cameras`: streams/workers, unique per `account_id + camera_id`, indexed by `account_id + device_id`
- `device_configs`: remote config per `account_id + device_id`
- `detection_zones`: floor masks per `account_id + camera_id + zone_id`

## Code Style

- Use 2-space indentation and Ruff line length 100.
- Prefer existing dependencies and CRUD patterns.
- Keep tests under `src/tests`.
- Use `rg` for search.
- Avoid unrelated refactors and never remove account scoping.
