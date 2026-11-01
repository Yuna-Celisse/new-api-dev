# New API development deployment

Builds the unmodified `QuantumNous/new-api` main branch daily at 03:17 Asia/Shanghai, and on manual dispatch. The upstream repository is not modified or forked. GitHub schedules may be delayed.

Images: `ghcr.io/yuna-celisse/new-api:dev` and `:dev-<full upstream SHA>` (linux/amd64). Each new commit also gets an immutable prerelease containing a Docker image archive, SHA-256 checksums, and the upstream revision. The archive lets the server update without storing a GitHub or registry access token, even when GHCR packages are private. Only an image that passes a clean SQLite startup check is published.

Runtime uses SQLite, persistent data and logs, a 768 MiB container limit and a 384 MiB Go soft heap target. Redis and PostgreSQL are optional and are omitted for this single-instance deployment.

The server update timer checks for successful development releases daily after the build window. An update backs up the stopped database, starts the new image, checks health and restores the previous database and image on failure. Development versions can contain regressions; backups are retained on the server.

Server files live under `/opt/new-api`. The systemd timer runs daily between 05:30 and 05:40 Asia/Shanghai. Run `systemctl start new-api-update.service` to check immediately; read its journal to diagnose a failure. Seven database snapshots and at least three recent versioned image tags are retained. Initialization uses `NEW_API_ORIGIN=https://your-domain python3 initialize.py` while the service is bound to loopback. It creates an administrator with a random password in `/root/new-api-admin.json`, enables self-use mode and disables registration. Preserve `.env`: it contains session and channel encryption keys.

To revert to AxonHub, first stop `new-api-update.timer` and the New API container, restore the saved Caddy configuration, start the existing AxonHub PostgreSQL and application containers, and restore their previous restart policies. Original volumes are retained. Do not restore an AxonHub database into New API; their schemas differ.

No server credentials, API keys, database files or private configuration belong in this repository. Upstream source, license and notices remain available at https://github.com/QuantumNous/new-api.
