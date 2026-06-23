# System Behaviour Simulator — Observability Lab

A production-style local observability sandbox built for DevOps portfolio demonstrations. Trigger simulated system behaviours (success, errors, latency, CPU load) and observe the full telemetry pipeline in real time.

## Architecture

```
┌─────────────┐       ┌──────────────┐
│   Frontend  │──────▶│   Backend    │
│  (nginx)    │ /api  │  (FastAPI)   │
└─────────────┘       └──────┬───────┘
                             │ /metrics
                             ▼
┌──────────────────────────────────────────────┐
│              Observability Stack              │
├──────────────┬───────────┬───────────────────┤
│  Prometheus  │   Loki    │   Alertmanager    │
│  (metrics)   │  (logs)   │    (alerts)       │
└──────┬───────┴─────▲─────┴───────────────────┘
       │             │
       ▼             │
┌──────────────┐  ┌──────────┐
│   Grafana    │  │ Promtail │◀── Docker logs
│ (dashboards) │  └──────────┘
└──────────────┘
       ▲
       │
┌──────┴───────┬────────────────┐
│  cAdvisor    │  Node Exporter │
│ (containers) │    (host)      │
└──────────────┴────────────────┘
```

## Quick Start

```bash
docker compose up --build
```

That's it. All 9 services start with proper dependency ordering and health checks.

## Access Points

| Service       | URL                          | Credentials     |
|---------------|------------------------------|-----------------|
| Frontend UI   | http://localhost:3000         | —               |
| Backend API   | http://localhost:8000         | —               |
| Grafana       | http://localhost:3001         | admin / admin   |
| Prometheus    | http://localhost:9090         | —               |
| Alertmanager  | http://localhost:9093         | —               |
| cAdvisor      | http://localhost:8080         | —               |
| Node Exporter | http://localhost:9100/metrics | —               |

## Simulation Endpoints

| Endpoint              | Behaviour                                    |
|-----------------------|----------------------------------------------|
| `/simulate/success`   | Returns 200 immediately                      |
| `/simulate/error`     | Returns 500 (simulated failure)              |
| `/simulate/slow?delay=3` | Waits N seconds before responding          |
| `/simulate/cpu`       | Burns CPU for ~1-2 seconds                   |
| `/simulate/random`    | 40% chance of failure, random latency        |
| `/health`             | Health check endpoint                        |
| `/metrics`            | Prometheus metrics (counters, histograms)    |

## Observability Flow

### Metrics Pipeline
1. Backend exposes `/metrics` (Prometheus client) with request count, latency histogram, error counter
2. Prometheus scrapes backend, cAdvisor, and Node Exporter every 15s
3. Alert rules evaluate error rate, latency P95, and container CPU
4. Alertmanager receives firing alerts and groups them

### Logging Pipeline
1. Backend emits structured JSON logs via `structlog`
2. Promtail discovers Docker containers and ships logs to Loki
3. Logs are labeled by `service`, `container`, and parsed JSON fields (level, event, request_id)
4. Grafana queries Loki for log panels with full-text search

### Dashboards
Grafana is auto-provisioned with:
- Request rate by endpoint
- Error rate percentage with threshold colouring
- P95 latency by endpoint
- CPU and memory usage per container
- Application logs panel (Loki)

## Project Structure

```
observability-simulator/
├── backend/
│   ├── app/
│   │   ├── main.py           # FastAPI app + endpoints
│   │   ├── middleware.py     # Request ID + timing middleware
│   │   ├── metrics.py        # Prometheus instrumentation
│   │   └── logging_config.py # structlog JSON setup
│   ├── pyproject.toml        # Dependencies (managed by uv)
│   └── Dockerfile            # Multi-stage build with uv
├── frontend/
│   ├── index.html            # Simulator UI
│   ├── nginx.conf            # Static serve + reverse proxy
│   └── Dockerfile
├── prometheus/
│   ├── prometheus.yml        # Scrape configuration
│   └── alert_rules.yml       # Alerting rules
├── grafana/
│   └── provisioning/
│       ├── datasources/      # Prometheus + Loki
│       └── dashboards/       # Auto-loaded dashboard JSON
├── loki/
│   └── loki-config.yml
├── promtail/
│   └── promtail-config.yml
├── alertmanager/
│   └── alertmanager.yml
├── docker-compose.yml
├── .env
└── README.md
```

## What This Demonstrates

- **Container orchestration** — Multi-service Docker Compose with health checks, dependency ordering, and restart policies
- **Metrics engineering** — Custom Prometheus counters and histograms with meaningful labels
- **Logging pipelines** — Structured JSON logs collected via Promtail → Loki with service-level labeling
- **Dashboarding** — Auto-provisioned Grafana with rate, latency, resource, and log panels
- **Alerting** — Prometheus alert rules with Alertmanager routing and inhibition
- **Infrastructure as Code** — Fully declarative configuration, reproducible with a single command

## Tear Down

```bash
docker compose down -v
```

The `-v` flag removes persistent volumes (Prometheus data, Grafana state, Loki chunks).

## Tech Stack

| Component      | Technology              |
|----------------|-------------------------|
| Backend        | Python 3.12, FastAPI, uv |
| Frontend       | HTML/JS, nginx          |
| Metrics        | Prometheus, cAdvisor, Node Exporter |
| Logs           | Loki, Promtail, structlog |
| Dashboards     | Grafana                 |
| Alerts         | Alertmanager            |
| Orchestration  | Docker Compose          |
