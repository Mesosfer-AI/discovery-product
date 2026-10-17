# MESOSFER

Built by **Team MESOSFER**.

MESOSFER is an AI-assisted product discovery and recommendation application. Users enter a shopping query and an optional price range. The application searches marketplaces and retailers, collects product information, evaluates available seller and review evidence, and returns ranked recommendations with prices, store links, reasons, advantages, and trade-offs.

Search sources include Shopee, Tokopedia, Alibaba, Amazon, Erafone, Digimap, and Blibli. Recommendations depend on the information available from those sources; prices and availability should be confirmed on the seller's product page.

## How it works

1. The React frontend sends the shopping query to Laravel through the same-origin `/api` route.
2. Laravel validates the request, queues it in the existing database, and immediately returns a search ID with HTTP 202. The background worker calls the internal FastAPI service.
3. The AI service uses SerpAPI and browser extraction to discover products, removes duplicates, and resolves links to their original stores.
4. The configured language model evaluates available product and seller evidence, then ranks candidates against the shopping request.
5. The frontend polls the search status every two seconds, then displays recommendations and applies the selected price range. Long searches do not hold a browser request open beyond Cloudflare's proxy timeout.

One repository contains all three applications. Docker Compose runs the frontend, backend, AI service, and a Laravel background worker using the backend image. MySQL, Redis, and optional S3/MinIO storage are existing external services:

| Directory or service | Responsibility | Stack |
| --- | --- | --- |
| `fe-ai-lablab/` | Search interface and recommendation cards | React, TypeScript, Vite, Nginx |
| `be-ai-lablab/` | Request validation and AI API gateway | Laravel, PHP-FPM |
| `worker` | Processes queued searches and stores their results | Laravel database queue |
| `ai/` | Discovery, deduplication, trust assessment, and ranking | Python, FastAPI, Playwright |
| External MySQL | Persistent application database | Existing server |
| External Redis | Discovery cache and deduplication state | Existing server |

Run Git commands from this root. The previous repositories' Git metadata is preserved locally in the ignored `.repo-backups/` directory; the application folders are ordinary directories in the new repository, not submodules.

## Setup

### 1. Install the prerequisites

Install Docker Engine with the Compose plugin on Linux, or Docker Desktop using Linux containers on Windows/macOS. Docker Compose 2.24 or newer is required. Node.js, PHP, Composer, Python, and Chromium are installed inside the images, so separate host installations are unnecessary.

Verify Docker is running:

```sh
docker version
docker compose version
```

Clone or download this repository and open a terminal at its root, where `compose.yaml` is located.

### 2. Configure the project environment

Prepare the single shared environment file in the repository root. Keep an existing root `.env` if it already contains your configuration:

```sh
cp .env.example .env
```

In PowerShell, use `Copy-Item .env.example .env`. This one file configures the frontend, Laravel backend, AI service, and Docker Compose. Do not create environment files inside the application directories. The file is ignored by Git and excluded from application images; only public `VITE_*` values belong in the frontend bundle.

For AMD Token Factory and SerpAPI, edit the root `.env`:

```dotenv
LLM_PROVIDER=amd
SEARCH_PROVIDER=serpapi
AMD_API_KEY=<your AMD Token Factory key>
SERPAPI_API_KEY=<your SerpAPI key>
```

Replace the placeholders with your own keys. The AMD key must begin with `rc-`. Keep the model IDs and other settings from the root `.env.example`, or choose models supported by your provider. Custom OpenAI-compatible and Ollama providers are also supported through this file.

The AI service can start without provider credentials using the default custom provider; discovery requests require valid credentials for the selected external providers. Selecting AMD requires a valid AMD key even during startup. Laravel requires the configured external database before it can finish startup.

### 3. Review deployment settings

Set `APP_URL` to the server's public URL. Configure `DB_HOST`, `DB_PORT`, `DB_DATABASE`, `DB_USERNAME`, and `DB_PASSWORD` for an existing MySQL database and user with migration privileges. Configure `REDIS_HOST`, `REDIS_PORT`, and `REDIS_PASSWORD` for Laravel, and `REDIS_URL` for the AI service. For authenticated Redis, include credentials in the AI URL, for example `redis://username:password@hostname:6379/0` (URL-encode special characters). Set `AI_SERVICE_TIMEOUT=600` to allow up to ten minutes per AI search, including when upgrading an existing root `.env` that still has the previous 180-second value.

The template uses `host.docker.internal` to reach services on the Docker host, including Linux through the host gateway mapping. Existing services must listen on an address reachable from the containers and allow these connections. For remote services, use their reachable hostnames and ports. For another Docker network, arrange shared network connectivity and use that network's service addresses.

Optional `AWS_*` settings pass existing S3/MinIO configuration to Laravel. The application keeps `FILESYSTEM_DISK=local`; selecting the `s3` disk requires an S3 filesystem adapter, which is not currently installed. No storage service is created by Compose. Leave `APP_KEY` empty to generate and persist it automatically, and leave `VITE_BACKEND_URL` empty for same-origin `/api` requests. `AI_SERVICE_URL` points to the AI container inside the Compose network.

### 4. Build and start all services

Build and start everything:

```sh
docker compose up -d --build
```

Open [http://localhost:47281](http://localhost:47281). The frontend serves the application and forwards `/api` requests to Laravel. Only the frontend publishes a host port; AI and PHP-FPM communicate over the Compose network. Laravel migrations run automatically against the configured external database before PHP-FPM starts.

The first build downloads the base images, application dependencies, and Chromium. Check startup progress with `docker compose logs -f`. In `docker compose ps`, frontend, backend, and AI should report healthy, and worker should be running.

All Docker services listen on high ports:

| Service | Container port | Host port |
| --- | --- | --- |
| Frontend | 47281 | 47281 (configurable with `APP_PORT`) |
| Backend PHP-FPM | 47282 | Internal only |
| AI | 47283 | Internal only |
| Background worker | None | None |

Set both `APP_PORT` and `APP_URL` in the root `.env` when changing the public port. External database, Redis, and storage ports are configured separately in the same file.

### 5. Test the application

Open the frontend, enter a query such as `macbook`, and select a suitable price range. Searches can take a few minutes because they collect live product information and request model analysis. A low price ceiling or unavailable sources can produce an empty recommendation list.

The frontend uses `POST /api/v1/discover/jobs` to submit a search and `GET /api/v1/discover/jobs/{id}` to poll for `queued`, `processing`, `completed`, or `failed`. Results are stored in the application's existing database cache table for one hour and are returned with `Cache-Control: no-store, private`. The dedicated `discovery` database queue is used even when the general `QUEUE_CONNECTION` is `sync`; the existing `jobs` and `cache` migrations provide its tables. Browser polling stops after 15 minutes or when the search is cancelled. Cancelling the browser request does not cancel a queued job.

The original synchronous `POST /api/v1/discover` remains available for internal clients; it can still hit a proxy timeout for long searches. Public clients should use the job endpoints. For native development outside Compose, run `php artisan queue:work discovery --queue=discovery --sleep=1 --tries=1` from `be-ai-lablab/` alongside the backend.

Check Laravel independently through the gateway:

```sh
curl -f http://localhost:47281/up
```

## Common commands

```sh
docker compose ps
docker compose logs -f frontend backend worker ai
docker compose up -d --build
docker compose down
```

After changing the root `.env`, apply the new environment with `docker compose up -d --build`. Rebuilding also applies public frontend build values. Use the same command after changing application code or Dockerfiles.

## Data persistence

Rebuild after application source changes. Compose owns only the `backend_storage` named volume for Laravel storage, which persists across rebuilds and `docker compose down`. When `APP_KEY` is empty, the backend generates a key once and saves it in this volume. Preserve that volume or configure the same key explicitly when restoring application data.

External MySQL, Redis, and S3/MinIO data are managed by their existing services. Compose does not create or delete those services or their data; Laravel startup applies its application migrations to the configured database.

The AI container runs one Uvicorn worker so its provider request limiter is shared by requests in that process. Chromium is included for browser discovery and receives 512 MB of shared memory.

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| Docker cannot connect to its daemon | Start Docker Desktop or the Docker Engine service. |
| Frontend port cannot be bound | Set an available `APP_PORT` and matching `APP_URL` in the root `.env`, then run Compose again. |
| AI exits during startup | Inspect `docker compose logs ai`; AMD requires a valid `rc-` key when selected. |
| Search is unavailable or returns no products | Check AI logs, provider credentials and quotas, source availability, and the selected budget. |
| Search remains queued | Check `docker compose ps worker` and `docker compose logs worker`; the worker must reach the same database as the backend. |
| Old production frontend still returns Cloudflare 524 | Rebuild the frontend and backend, start the worker, then refresh the page to use the job endpoints. Check the browser Network panel for `POST /api/v1/discover/jobs` returning HTTP 202. |
| Backend cannot finish startup | Check external MySQL credentials, database existence, migration privileges, and network access from the backend container. |

## Team

**Team MESOSFER** builds and maintains this project, bringing together the shopping interface, backend integration, and AI discovery pipeline in one repository.
