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
| `GET` | `/events` | Query events filtered by barn, device, camera, zone, and time range |
| `POST` | `/devices` | Register/update a physical edge host |
| `GET` | `/devices` | List physical edge hosts |
| `POST` | `/devices/{device_id}/cameras` | Register/update a camera stream on a device |
| `GET` | `/devices/{device_id}/cameras` | List cameras attached to a device |
| `POST` | `/devices/heartbeat` | Persist the latest structured heartbeat and refresh online TTL |
| `GET` | `/devices/{device_id}/config` | Fetch remote edge configuration |
| `GET` | `/cameras/{camera_id}/status` | Fetch camera online/offline status |
| `GET` | `/cameras/{camera_id}/zones` | Fetch camera-scoped floor zones |

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

### Edge Event Contract

BarnSight runs one edge worker/container per camera. Multiple camera workers on the same physical host share the same `device_id`; every stream has a unique `camera_id`. `POST /api/v1/events` accepts `X-API-Key` or JWT auth. Required fields are `timestamp`, `device_id`, `camera_id`, `confidence`, and `bounding_box`. Optional production edge metadata: `event_id`, `barn_id`, `zone_id`, `image_snapshot`, `model_version`, `model_path`, `img_size`, `threshold`, `snapshot_mode`, `edge_app_version`, and `queue_latency_seconds`.

Validation rules:
- `confidence` and `threshold` must be between `0.0` and `1.0`.
- `bounding_box.width` and `bounding_box.height` must be positive.
- `image_snapshot` must be valid base64 and decode under `EDGE_MAX_SNAPSHOT_BYTES`.
- `event_id` is an account-scoped idempotency key; retries with the same `event_id` return the existing event.
- Raw base64 snapshots are replaced with the Cloudinary URL after upload.

### Heartbeat Contract

`POST /api/v1/devices/heartbeat` requires `X-API-Key` and stores the latest state in
`barnsight.devices` and `barnsight.cameras`. Redis stores `camera:{account_id}:{camera_id}:status` and `device:{account_id}:{device_id}:status` with `DEVICE_HEARTBEAT_TTL_SECONDS`.
If a camera key expires, that camera is offline. A physical device is offline when none of its cameras have live heartbeat keys.

Supported heartbeat fields: `device_id`, `camera_id`, `status`, `edge_app_version`,
`model_version`, `model_path`, `camera_connected`, `model_loaded`, `last_frame_at`,
`last_detection_at`, `fps`, `inference_fps`, `queue_size`, `queue_max_size`,
`queue_dropped_count`, `memory_used_mb`, `disk_free_mb`, `temperature_c`,
`uptime_seconds`, and `errors`.

Device status endpoints:
- `GET /api/v1/devices`
- `GET /api/v1/devices/{device_id}`
- `GET /api/v1/devices/{device_id}/status`
- `GET /api/v1/devices/{device_id}/cameras`
- `GET /api/v1/cameras/{camera_id}`
- `GET /api/v1/cameras/{camera_id}/status`

### Device Config Contract

Remote configuration is account scoped:
- `GET /api/v1/devices/{device_id}/config`
- `PUT /api/v1/devices/{device_id}/config`

Fields: `enabled`, `inference_fps`, `img_size`, `min_confidence`, `cooldown_seconds`,
`image_cooldown_seconds`, `region_overlap_threshold`, `jpeg_quality`,
`send_image_snapshot`, `snapshot_mode`, `max_image_bytes`, `detection_zones`, and
`updated_at`. Validation is strict: unknown fields are rejected and numeric ranges are bounded.

### Detection Zones

Detection zones define barn floor masks for edge cameras. Each zone stores `zone_id`,
`barn_id`, `device_id`, `camera_id`, normalized polygon points, `enabled`, and `label`.
Zones are camera-specific because each camera has a different floor perspective.

Endpoints:
- `GET /api/v1/cameras/{camera_id}/zones`
- `POST /api/v1/cameras/{camera_id}/zones`
- `PUT /api/v1/cameras/{camera_id}/zones/{zone_id}`
- `DELETE /api/v1/cameras/{camera_id}/zones/{zone_id}`

### Barn, Device, Camera Model

- Barn: physical facility area.
- Device: physical edge host/gateway installed at a barn.
- Camera: one RTSP/USB stream attached to a device.
- Zone: optional polygon/floor area for one camera view.
- Event: contamination detection produced by one camera worker.

Do not store RTSP credentials in this API. Store only redacted stream labels such as `north-aisle-main` or `rtsp-redacted-a`.

### Security Expectations

- Use `X-API-Key` for edge devices; API keys are hashed at rest.
- Do not send API keys in query strings or logs.
- Use HTTPS/TLS in production and rotate keys when devices are replaced.
- Keep `EDGE_MAX_SNAPSHOT_BYTES` below the ingress/proxy body limit.
- Use account scoping for every query and write.
- Do not store raw base64 image payloads after Cloudinary upload.

### Recommended Production Settings

Set durable `PRIVATE_KEY_PEM`, `PUBLIC_KEY_PEM`, `SECRET_KEY`, MongoDB credentials,
Redis credentials, and Cloudinary credentials. Recommended edge-specific settings:

| Variable | Recommended starting point |
|---|---|
| `EDGE_MAX_SNAPSHOT_BYTES` | `2000000` |
| `DEVICE_HEARTBEAT_TTL_SECONDS` | `300` |
| `RATE_LIMIT_EDGE` | `1000/minute` or higher per farm size |
| Reverse proxy body limit | Slightly above `EDGE_MAX_SNAPSHOT_BYTES` plus JSON overhead |

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
| `POST` | `/farmers` | Register a new farmer account |
| `POST` | `/staff` | Register a new staff account |
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
| `EDGE_MAX_SNAPSHOT_BYTES` | `2000000` | Maximum decoded base64 snapshot accepted before upload |
| `DEVICE_HEARTBEAT_TTL_SECONDS` | `300` | Redis TTL used to determine device online/offline status |

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
| `barnsight` | `barns`, `zones`, `devices`, `cameras`, `events`, `device_configs`, `detection_zones` | Farm infrastructure, edge status/config, floor masks, and detection events |

Required production indexes include:
- `events`: `account_id + event_id` unique when `event_id` exists.
- `events`: `account_id + timestamp`, `account_id + barn_id + timestamp`, `account_id + device_id + timestamp`, `account_id + camera_id + timestamp`, `account_id + barn_id + zone_id + timestamp`.
- `devices`: `account_id + device_id` unique.
- `cameras`: `account_id + camera_id` unique and `account_id + device_id`.
- `detection_zones`: `account_id + camera_id + zone_id` unique.

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
ing.**

</div>
