<div align="center">

# BarnSight API

**The robust event ingestion and analytics backbone for BarnSight Edge devices.**

[![Python](https://img.shields.io/badge/python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi)](https://fastapi.tiangolo.com)
[![Docker](https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://www.docker.com/)
[![License](https://img.shields.io/badge/license-MIT-00D100?style=for-the-badge)](LICENSE)

[**Features**](#-features) • [**Quick Start**](#-quick-start) • [**API Reference**](#-api-reference) • [**Configuration**](#-configuration) • [**Architecture**](#-architecture) • [**Contributing**](CONTRIBUTING.md)

</div>

---

## Philosophy

BarnSight API is built for the harsh, low-connectivity environment of modern farming. It provides a high-performance, asynchronous bridge between **Edge AI devices** (detecting animal excrement in real-time) and **Farmer Dashboards** (providing data-driven hygiene insights).

> "Turning routine hygiene checks into fast, reliable, data-driven workflows."

---

## Features

### Edge-First Ingestion

- **Dual-Auth Architecture**: Supports **API Keys** for Edge-to-Server ingestion and **JWT** for Web-to-Server interactions.
- **High Throughput**: Optimized async MongoDB persistence for rapid bursts of detection events from multiple cameras.
- **Data Integrity**: Strict Pydantic v2 validation for timestamps, confidence scores, and bounding box coordinates.
- **Image Handling**: Automatic base64-to-Cloudinary upload for detection snapshots.

### Security & Account Isolation

- **Account Scoping**: Every event and API key is strictly isolated by `account_id`, ensuring privacy between different farms.
- **Secure API Keys**: Farmer-generated keys are SHA-256 hashed in the database — the raw key is never stored.
- **Asymmetric JWT (RS256)**: Tokens signed with RSA private keys, verified with public keys.
- **RBAC**: Fine-grained permissions for **Admins** (Farmers), **Users** (Staff), and **Edge** (Hardware).
- **Rate Limiting**: Tiered protection (Edge: 1000/min, User: 300/min, Anonymous: 100/min) backed by Redis.

### Analytics & Management

- **Real-time Aggregation**: Detection counts per camera, per device, and total volume.
- **Admin Dashboard**: Overview of connected edge devices, active users, and ingestion stats.
- **Prometheus Metrics**: `/metrics` endpoint for monitoring and alerting.

---

## Quick Start

### Prerequisites

- Docker and Docker Compose
- MongoDB Atlas account (or local MongoDB)
- Redis Cloud account (or local Redis)

### 1. Clone and configure

```bash
git clone https://github.com/BarnSight/barnsight-api.git && cd barnsight-api
cp .env.example .env
```

### 2. Generate RSA keys for JWT

```bash
openssl genrsa -out private_key.pem 2048
openssl rsa -in private_key.pem -pubout -out public_key.pem
```

Add the formatted keys to your `.env` as `PRIVATE_KEY_PEM` and `PUBLIC_KEY_PEM`.

### 3. Launch

```bash
docker compose up --build -d
```

The API will be available at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

---

## API Reference

All endpoints are prefixed with `/api/v1`.

### Edge Device Endpoints (API Key auth)

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/events` | Submit a detection event |
| `GET` | `/events` | Query events (filter by camera, device, time range) |

**Example — Submit event:**

```bash
curl -X POST http://localhost:8000/api/v1/events \
  -H "X-API-Key: bs_your_key_here" \
  -H "Content-Type: application/json" \
  -d '{
    "timestamp": "2026-03-18T12:34:56Z",
    "camera_id": "barn_01_cam_A",
    "device_id": "edge_01",
    "confidence": 0.92,
    "bounding_box": {"x": 150, "y": 300, "width": 100, "height": 80},
    "image_snapshot": "base64_encoded_image_data..."
  }'
```

### Web User Endpoints (JWT auth)

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/auth/login` | Login with username/password |
| `POST` | `/auth/token` | Refresh or revoke JWT |
| `POST` | `/auth/logout` | Logout (blacklists JWT in Redis) |
| `GET` | `/auth/google` | OAuth2 login via Google |
| `GET` | `/user/me` | Get current user profile |
| `PATCH` | `/user/me` | Update profile |
| `PATCH` | `/user/me/password` | Change password |
| `PATCH` | `/user/password` | Recover password |
| `PATCH` | `/user/email` | Update email |
| `POST` | `/api-keys` | Create API key for edge devices |
| `GET` | `/api-keys` | List API keys |
| `DELETE` | `/api-keys/{key_id}` | Revoke API key |

### Admin Endpoints (JWT + admin scope)

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/admin/setup` | Create initial admin account |
| `POST` | `/admin/register/farmer` | Register a new farmer account |
| `POST` | `/admin/register/staff` | Register a new staff account |
| `GET` | `/admin/dashboard` | System-wide statistics |
| `PATCH` | `/admin/users/{username}/role` | Change user role |

### Public Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Health check |
| `GET` | `/analytics` | Aggregated detection insights |
| `GET` | `/metrics` | Prometheus metrics |

---

## Configuration

All settings are loaded from `.env`. See `.env.example` for the full template.

| Variable | Default | Description |
|---|---|---|
| `MONGO_HOSTNAME` | `localhost` | MongoDB host (use Atlas hostname for cloud) |
| `MONGO_PORT` | `27017` | MongoDB port |
| `MONGO_USERNAME` | `root` | MongoDB username |
| `MONGO_PASSWORD` | `root` | MongoDB password |
| `REDIS_HOST` | `localhost` | Redis host |
| `REDIS_PORT` | `6379` | Redis port |
| `REDIS_PASSWORD` | | Redis password |
| `SECRET_KEY` | *(auto-generated)* | Session middleware secret |
| `PRIVATE_KEY_PEM` | *(required)* | RSA private key for JWT signing |
| `PUBLIC_KEY_PEM` | *(required)* | RSA public key for JWT verification |
| `GOOGLE_CLIENT_ID` | | Google OAuth client ID |
| `GOOGLE_CLIENT_SECRET` | | Google OAuth client secret |
| `CLOUDINARY_CLOUD_NAME` | | Cloudinary cloud name |
| `CLOUDINARY_API_KEY` | | Cloudinary API key |
| `CLOUDINARY_API_SECRET` | | Cloudinary API secret |
| `RATE_LIMIT_ANONYMOUS` | `100/minute` | Rate limit for unauthenticated requests |
| `RATE_LIMIT_EDGE` | `1000/minute` | Rate limit for edge device API keys |
| `RATE_LIMIT_USER` | `300/minute` | Rate limit for authenticated web users |
| `CACHE_EXPIRE_MINUTES` | `60` | Redis cache TTL for user profiles |

---

## Architecture

```
Edge Devices (barnsight-edge)
        │
        │  POST /api/v1/events  (X-API-Key)
        ▼
    ┌─────────┐
    │  Nginx  │  Reverse proxy, TLS termination
    └────┬────┘
         │
    ┌────┴────┐
    │ FastAPI │  Async route handlers
    └────┬────┘
         │
    ┌────┴────────────────────┐
    │                         │
┌───┴────┐            ┌──────┴──────┐
│MongoDB │            │    Redis    │
│ users  │            │  Cache +    │
│barnsight│           │  Rate Limit │
└────────┘            └─────────────┘
```

### Database Structure

| Database | Collections | Purpose |
|---|---|---|
| `users` | `admins`, `farmers`, `staff`, `edge`, `api_keys`, `user_barns` | User accounts, API keys, barn assignments |
| `barnsight` | `barns`, `zones`, `devices`, `events` | Farm infrastructure and detection events |

### Database Structure

| Database | Collections | Purpose |
|---|---|---|
| `users` | `admins`, `farmers`, `staff`, `edge`, `api_keys`, `user_barns` | User accounts, API keys, barn assignments |
| `barnsight` | `barns`, `zones`, `devices`, `events` | Farm infrastructure and detection events |

### Project Structure

```
src/app/
├── main.py                    # FastAPI app factory, middleware, lifespan
├── api/
│   ├── dependencies.py        # DB clients, auth, rate limiting
│   ├── auth_dependencies.py   # API key validation for edge devices
│   └── v1/routers/
│       ├── events.py          # Event ingestion and querying
│       ├── analytics.py       # Aggregated detection insights
│       ├── barns.py           # Barn/zone/device management
│       ├── detections.py      # Detection-specific routes
│       ├── reports.py         # Report generation
│       ├── auth.py            # Login, token refresh, logout
│       ├── google_auth.py     # Google OAuth2 flow
│       ├── user.py            # Profile management
│       ├── users.py           # Admin user management
│       ├── admin.py           # Admin setup, dashboard, role changes, user registration
│       ├── api_keys.py        # API key CRUD
│       └── health.py          # Health check
├── core/
│   ├── config.py              # Pydantic settings from .env
│   ├── logger.py              # Structured logging
│   ├── database/
│   │   ├── mongo.py           # Async MongoDB client
│   │   └── redis.py           # Async Redis client
│   ├── schemas/               # Pydantic request/response models
│   ├── security/
│   │   ├── jwt.py             # RSA JWT encode/decode/blacklist
│   │   └── utils.py           # Password hashing (Argon2)
│   ├── services/
│   │   ├── cloudinary_service.py  # Image upload to Cloudinary
│   │   └── oauth/google.py        # Google OAuth2 client
│   └── middleware/
│       └── limiter.py         # Rate limit context preparation
└── crud/
    ├── base_crud.py           # Generic CRUD base class
    ├── user_crud.py           # User operations across role collections
    ├── event_crud.py          # Event operations and analytics
    ├── api_key_crud.py        # API key validation and management
    └── barn_crud.py           # Barn/zone/device operations
```

---

## Farmer Workflow

1. **Admin Creates Account**: An admin registers the farmer account via `/admin/register/farmer`.
2. **Login**: Farmer logs in via username/password or Google OAuth.
3. **Generate API Key**: Navigate to `/api-keys` to create a key for your barn's hardware.
4. **Deploy Edge**: Insert the generated `bs_...` key into your **BarnSight Edge** configuration.
5. **Monitor**: View real-time manure detections and analytics reports.

---

## Development

### Local setup (without Docker)

```bash
uv sync --all-extras
uv run python -m app.main
```

### Running tests

```bash
uv run pytest src/tests/ -v
```

---

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

<div align="center">

**Built for the future of farming.**

</div>
