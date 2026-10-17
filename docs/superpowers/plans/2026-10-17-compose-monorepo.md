# Compose Monorepo Implementation Plan

**Goal:** Run all existing applications from one Git repository with `docker compose up -d --build`.

**Architecture:** Nginx serves the built React app and forwards `/api` and `/up` to Laravel PHP-FPM. Laravel calls the internal AI service; MySQL and Redis persist data in named volumes. Per the user's port requirement, frontend, backend FPM, AI, MySQL, and Redis use ports 47281, 47282, 47283, 47284, and 47285 respectively. Only the frontend HTTP port is published. This range passed Windows bind checks and avoids the reserved and dynamic ranges on this host.

**Constraints:** Preserve existing application code and local credentials. Exclude secrets and development dependencies from image contexts. Keep one AI worker so shared provider limits remain process-wide. Preserve the three existing Git metadata directories in an ignored backup before initializing the root repo. Do not push or delete existing history.

## Tasks

- [x] Add frontend and backend Dockerfiles, build context exclusions, Nginx routing, and a backend entrypoint that runs migrations and persists an automatically generated application key.
- [x] Add root Compose, environment examples, ignore rules, and run instructions; update the AI image for container dependencies and one worker.
- [x] Validate Compose, build and start the stack, check frontend, Laravel and AI health, and run a search through the gateway.
- [x] Check restart persistence, verify secrets are excluded, preserve child repositories and initialize the root Git repository with normal files rather than gitlinks.

## Verification

Use actual Docker builds and HTTP checks as integration verification. Confirm all five services are healthy, API requests reach Laravel, AI can reach Redis, database migrations complete, and storage/key/database data survive container recreation. Report external search provider failures separately from container startup failures.

Verified on Docker Desktop's Linux engine: all five services healthy; frontend and `/up` return HTTP 200; invalid discovery payload returns HTTP 422 JSON; Linux Chromium renders; MySQL, Redis, storage and key survive recreation; old standard listeners are closed. A real `macbook` request through the public gateway returned HTTP 200 and one Digimap recommendation in 140.14 seconds. The initial port choice was changed after Windows reported it as reserved; final ports 47281-47285 passed actual bind and container connectivity checks.
