# MESOSFER

Built by **Team MESOSFER**.

MESOSFER is an AI-assisted product discovery and recommendation application. Users enter a shopping query and an optional price range. The application searches marketplaces and retailers, collects product information, evaluates available seller and review evidence, and returns ranked recommendations with prices, store links, reasons, advantages, and trade-offs.

Search sources include Shopee, Tokopedia, Alibaba, Amazon, Erafone, Digimap, and Blibli. Recommendations depend on the information available from those sources; prices and availability should be confirmed on the seller's product page.

## How it works

1. The React frontend sends the shopping query to Laravel through the same-origin `/api` route.
2. Laravel validates the request and forwards it to the internal FastAPI service.
3. The AI service uses SerpAPI and browser extraction to discover products, removes duplicates, and resolves links to their original stores.
4. The configured language model evaluates available product and seller evidence, then ranks candidates against the shopping request.
5. The frontend displays recommendations and applies the selected price range.

One repository contains all three applications. Docker Compose builds them and runs MySQL and Redis alongside them:

| Directory or service | Responsibility | Stack |
| --- | --- | --- |
| `fe-ai-lablab/` | Search interface and recommendation cards | React, TypeScript, Vite, Nginx |
| `be-ai-lablab/` | Request validation and AI API gateway | Laravel, PHP-FPM |
| `ai/` | Discovery, deduplication, trust assessment, and ranking | Python, FastAPI, Playwright |
| MySQL | Persistent application database | MySQL 8.4 |
| Redis | Discovery cache and deduplication state | Redis 7 |

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

### 2. Configure the AI providers

Prepare the AI environment file once. Keep an existing `ai/.env` if it already contains your configuration:

```sh
cp ai/.env.example ai/.env
```

In PowerShell, use `Copy-Item ai/.env.example ai/.env`. Edit `ai/.env` and set the following for AMD Token Factory and SerpAPI:

```dotenv
LLM_PROVIDER=amd
SEARCH_PROVIDER=serpapi
AMD_API_KEY=<your AMD Token Factory key>
SERPAPI_API_KEY=<your SerpAPI key>
```

Replace the placeholders with your own keys. The AMD key must begin with `rc-`. Keep the model IDs and other settings from `ai/.env.example`, or choose models supported by your provider. Custom OpenAI-compatible and Ollama providers are also supported through that file's settings.

Containers can start without an AI environment file using the application's defaults; discovery requests require valid credentials for the selected external providers. Selecting AMD requires a valid AMD key even during startup. Compose supplies the internal Redis address automatically.

### 3. Configure the deployment environment

The root `.env` is optional for local use. For a server, copy `.env.example` to `.env`, set `APP_URL` to the server's public URL, and choose database passwords before the first startup. In PowerShell, use `Copy-Item .env.example .env`.

Root `.env` controls Compose, while `ai/.env` holds AI provider configuration. Both files are ignored by Git and excluded from application images. Leave `APP_KEY` empty to generate and persist it automatically.

### 4. Build and start all services

Build and start everything:

```sh
docker compose up -d --build
```

Open [http://localhost:47281](http://localhost:47281). The frontend serves the application and forwards `/api` requests to Laravel. Only the frontend publishes a host port; AI, MySQL, Redis, and PHP-FPM communicate over the Compose network. Laravel migrations run automatically before PHP-FPM starts.

The first build downloads the base images, application dependencies, and Chromium. Check startup progress with `docker compose logs -f` and wait for all services to report healthy in `docker compose ps`.

All Docker services listen on high ports:

| Service | Container port | Host port |
| --- | --- | --- |
| Frontend | 47281 | 47281 (configurable with `APP_PORT`) |
| Backend PHP-FPM | 47282 | Internal only |
| AI | 47283 | Internal only |
| MySQL | 47284 | Internal only |
| Redis | 47285 | Internal only |

Set both `APP_PORT` and `APP_URL` in the root `.env` when changing the public port. The default database passwords are for local development.

### 5. Test the application

Open the frontend, enter a query such as `macbook`, and select a suitable price range. Searches can take a few minutes because they collect live product information and request model analysis. A low price ceiling or unavailable sources can produce an empty recommendation list.

Check Laravel independently through the gateway:

```sh
curl -f http://localhost:47281/up
```

## Common commands

```sh
docker compose ps
docker compose logs -f frontend backend ai
docker compose up -d --build
docker compose down
```

After changing `ai/.env`, apply the new container environment with `docker compose up -d`. After changing application code or Dockerfiles, use `docker compose up -d --build`.

## Data persistence

Rebuild after application source changes. MySQL data, Redis data, and Laravel storage persist in named volumes across rebuilds and `docker compose down`. When `APP_KEY` is empty, the backend generates a key once and saves it in its storage volume. Preserve that volume or configure the same key explicitly when restoring application data.

`docker compose down -v` deletes all application volumes and their data. Changing database passwords in `.env` does not update credentials already stored in an initialized MySQL volume.

The AI container runs one Uvicorn worker so its provider request limiter is shared by requests in that process. Chromium is included for browser discovery and receives 512 MB of shared memory.

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| Docker cannot connect to its daemon | Start Docker Desktop or the Docker Engine service. |
| Frontend port cannot be bound | Set an available `APP_PORT` and matching `APP_URL` in the root `.env`, then run Compose again. |
| AI exits during startup | Inspect `docker compose logs ai`; AMD requires a valid `rc-` key when selected. |
| Search is unavailable or returns no products | Check AI logs, provider credentials and quotas, source availability, and the selected budget. |
| Database startup fails after changing passwords | Existing MySQL volumes retain their original credentials; updating `.env` alone does not change them. |

## Team

**Team MESOSFER** builds and maintains this project, bringing together the shopping interface, backend integration, and AI discovery pipeline in one repository.


