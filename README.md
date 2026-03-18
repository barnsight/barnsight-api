<div align="center">

<img src="./images/logo.png" width="450" alt="BarnSight API logo">

# 🐄 BarnSight API
**The robust event ingestion and analytics backbone for BarnSight Edge devices.**

[![Coverage](https://img.shields.io/badge/coverage-100%25-00D100?style=for-the-badge&logo=pytest)](https://github.com/BarnSight/barnsight-api)
[![Python](https://img.shields.io/badge/python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi)](https://fastapi.tiangolo.com)
[![Docker](https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://www.docker.com/)

[**Features**](#-features) • [**Farmer Workflow**](#-farmer-workflow) • [**Edge Integration**](#-edge-integration) • [**The Stack**](#-the-stack) • [**Contributing**](CONTRIBUTING.md)

</div>

---

## 🌪️ Philosophy
BarnSight API is built for the harsh, low-connectivity environment of modern farming. It provides a high-performance, asynchronous bridge between **Edge AI devices** (detecting animal excrement in real-time) and **Farmer Dashboards** (providing data-driven hygiene insights).

> "Turning routine hygiene checks into fast, reliable, data-driven workflows."

---

## 🚀 Features

### **⚡ Edge-First Ingestion**
*   **Dual-Auth Architecture**: Supports **API Keys** for Edge-to-Server ingestion and **JWT** for Web-to-Server interactions.
*   **High Throughput**: Optimized MongoDB persistence for rapid bursts of detection events from multiple cameras.
*   **Data Integrity**: Strict Pydantic v2 validation for timestamps, confidence scores, and bounding box coordinates.

### **🛡️ Security & Account Isolation**
*   **Account Scoping**: Every event and API key is strictly isolated by `account_id`, ensuring privacy between different farms.
*   **Secure API Keys**: Farmer-generated keys are SHA-256 hashed in the database.
*   **RBAC**: Fine-grained permissions for **Admins** (Farmers), **Users** (Staff/Coworkers), and **Edge** (Hardware).

### **📊 Analytics & Management**
*   **Real-time Aggregation**: Aggregated insights on detections per camera, device statistics, and hygiene trends.
*   **Admin Dashboard**: Overview of connected edge devices, active users, and total ingestion volume.
*   **Rate Limiting**: Tiered protection (Edge: 1000/min, User: 300/min) backed by Redis.

---

## 🕹️ Speedrun

```bash
# 1. Clone the repository
git clone https://github.com/BarnSight/barnsight-api.git && cd barnsight-api

# 2. Setup environment
cp .env.example .env

# 3. Generate RSA keys for JWT Authentication
openssl genrsa -out private_key.pem 2048
openssl rsa -in private_key.pem -pubout -out public_key.pem
# Add formatted keys to .env as PRIVATE_KEY_PEM and PUBLIC_KEY_PEM

# 4. Launch Stack
docker compose up --build
```
The API will be available at `http://localhost:8000`.

---

## 👨‍🌾 Farmer Workflow

1.  **Create Account**: Register and log in via the Web Dashboard.
2.  **Generate API Key**: Navigate to `/api-keys` to create a new key for your barn's hardware.
3.  **Deploy Edge**: Insert the generated `bs_...` key into your **BarnSight Edge** configuration.
4.  **Monitor**: View real-time manure detections and analytics reports.

---

## 📷 Edge Integration

Edge devices (`barnsight-edge`) push data via HTTPS:

*   **Endpoint**: `POST /api/v1/events`
*   **Auth Header**: `X-API-Key: bs_your_key_here`
*   **Payload**:
```json
{
  "timestamp": "2026-03-18T12:34:56Z",
  "camera_id": "barn_01_cam_A",
  "confidence": 0.92,
  "bounding_box": {"x": 150, "y": 300, "width": 100, "height": 80}
}
```

---

## 🏗️ The Stack

| Layer | Technology |
| :--- | :--- |
| **API Framework** | FastAPI + Python 3.11+ |
| **Database** | MongoDB + Motor (Async) |
| **Cache / Rate Limit** | Redis + aioredis |
| **Auth** | Asymmetric JWT (RS256) + Hashed API Keys |
| **Gateway** | Nginx |

---

## 📄 License

This project is licensed under the GPL-3.0 License. See the LICENSE file for details.

<div align="center">

**Built for the future of farming.**  
⭐ **Star this repo if it helps your barn!**

</div>
