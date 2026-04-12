# Prompt for Building a Tauri Mobile Client for BarnSight

*Copy the text below and paste it into a new LLM conversation to generate the architecture and code for the Tauri mobile app.*

---

**System Role:** You are an expert mobile app developer and systems architect specializing in Tauri v2, Rust, React (TypeScript), and real-time distributed systems.

**Context:** We have a production-ready FastAPI backend for "BarnSight," an agricultural AI monitoring platform. The backend handles event ingestion from edge cameras and provides real-time updates via WebSockets backed by Redis Pub/Sub. It uses JWT authentication, cursor-based pagination for event history, and tracks device health (heartbeats).

**Objective:** Design and implement the architecture and core boilerplate for a **Tauri v2 Mobile Application** (targeting Android and iOS) for farmers to monitor their barns in real-time.

**Core Technology Stack:**
*   **App Framework:** Tauri v2 (Mobile Support).
*   **Backend (Tauri Core):** Rust (for native system integrations, local SQLite caching, and handling heavy WebSocket logic if needed).
*   **Frontend:** React 18+ with TypeScript, Vite, and Tailwind CSS.
*   **State Management:** Zustand or React Query (for caching API responses).
*   **Local Storage:** `tauri-plugin-sql` (SQLite) for offline caching of events, as farms often have poor connectivity.
*   **API Communication:** Axios or `tauri-plugin-http` for REST calls; native WebSockets for the live feed.

**Key Requirements & Features:**

1.  **Authentication & Secure Storage:**
    *   Implement a login screen that hits `[API_URL]/api/v1/auth/login` to receive a JWT.
    *   Securely store the JWT on the device using `tauri-plugin-store` or the system keychain.

2.  **Real-Time WebSocket Feed (The "Live" View):**
    *   Connect to `wss://[API_URL]/api/v1/ws/events?token=[JWT]`.
    *   When a new event arrives (JSON payload with confidence, timestamp, bounding box, and image URL), instantly prepend it to a virtualized list in the UI.
    *   *Architectural Decision needed:* Should the WebSocket connection live in the Rust backend (Tauri Core) and emit events to the frontend, or live purely in the React frontend? (Provide your recommendation and implement it).

3.  **Offline-First Event History (Cursor Pagination):**
    *   Fetch historical events from `GET /api/v1/events?cursor=[CURSOR]&limit=50`.
    *   Cache these events locally in an SQLite database using `tauri-plugin-sql`.
    *   If the app goes offline (e.g., farmer walks into a metal barn), the app should still display the locally cached history gracefully.

4.  **Device Health Dashboard:**
    *   Fetch the list of barns and cameras from `GET /api/v1/barns`.
    *   The API returns a `status` field (`"online"` or `"offline"`) based on Redis heartbeats.
    *   Display a clean UI showing the status of all edge devices with visual indicators.

5.  **Push Notifications (Future-Proofing):**
    *   Outline the strategy for integrating push notifications (e.g., Firebase Cloud Messaging via a Tauri plugin) so farmers receive alerts when the API detects a "Detection Spike".

**Deliverables Required in Your Response:**
1.  **High-Level Architecture Diagram/Explanation:** Explain data flow between the React frontend, the Rust Tauri core, the local SQLite database, and the external FastAPI server.
2.  **Tauri Setup & Config:** Provide the necessary configuration for `tauri.conf.json` specifically enabling mobile targets and required plugins (`http`, `sql`, `store`).
3.  **Rust Core Implementation (`src-tauri/src/lib.rs`):** Provide the Rust setup, including initializing the SQLite database schema for caching events.
4.  **React Frontend Core:**
    *   A custom React Hook (`useBarnSightWebSocket.ts`) to manage the WebSocket connection, auto-reconnection, and state updates.
    *   A sample component (`LiveFeed.tsx`) that consumes the WebSocket hook and displays new detections with their image snapshots.

**Tone & Style:** Professional, focused on mobile performance, offline resilience, and clean TypeScript/Rust code. No boilerplate omitted if it is critical to the architecture.

---