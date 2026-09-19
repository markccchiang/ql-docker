<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/markccchiang/ql-docker/main/assets/logo/logo-dark.svg">
    <img src="https://raw.githubusercontent.com/markccchiang/ql-docker/main/assets/logo/logo.svg" alt="Interactive QuantLib Service" width="560">
  </picture>
</p>

# Interactive QuantLib Service

A browser workbench for pricing options and interest-rate swaps, backed by
[QuantLib](https://www.quantlib.org/) running as a live, stateful service.

The service keeps each session's QuantLib object graph standing between
requests: the curves, the volatility, the index and the instrument. Moving a
quote therefore reprices off the graph that already exists instead of
rebuilding it, so dragging the spot slider updates the price immediately.

This image contains the whole application, built from source:
[ql-backend](https://github.com/markccchiang/ql-backend) (the C++ WebSocket
pricing service, on QuantLib 1.43),
[ql-frontend](https://github.com/markccchiang/ql-frontend) (the React app) and
its user's guide in English and Traditional Chinese.

## Quick start

```bash
docker run --rm -p 127.0.0.1:8080:8080 markccchiang/ql-app
```

Open <http://localhost:8080>. The **Guide** button in the status bar opens the
user's guide.

Keep the `127.0.0.1:` prefix. The pricing service has no authentication, and
publishing the port on all interfaces would let anyone on your network use it.

## Tags

| Tag | Contents |
|---|---|
| `latest` | the most recent release |
| `X.Y.Z` (e.g. `0.1.0`) | a release; it never moves, so use it to stay on a known version |

Each tag is published for **linux/amd64** and **linux/arm64**, so it runs
natively on Intel/AMD machines and on Apple Silicon.

## Configuration

### Another port or host name

The service accepts a WebSocket only from browser origins it has been told
about. The defaults are `http://localhost:8080` and `http://127.0.0.1:8080`. If
you publish another port or reach the container under another name, set
`QL_ALLOWED_ORIGINS` (space-separated):

```bash
docker run --rm -p 127.0.0.1:9000:8080 \
    -e QL_ALLOWED_ORIGINS="http://localhost:9000 http://127.0.0.1:9000" \
    markccchiang/ql-app
```

Without it, the page loads but the status bar reports the service as *running,
but refusing this page*.

### Service options

Arguments after the image name are passed to ql-backend:

```bash
docker run --rm -p 127.0.0.1:8080:8080 markccchiang/ql-app --max-sessions 8
```

| Option | Meaning |
|---|---|
| `--max-sessions N` | the most live pricing sessions at once |
| `--max-connections N` | the most WebSocket connections at once |
| `--session-grace SECONDS` | how long a session outlives a dropped connection so the page can resume it (default 60, `0` turns it off) |

### Running it in the background

```bash
docker run -d --name ql-app --restart unless-stopped \
    -p 127.0.0.1:8080:8080 markccchiang/ql-app
```

The image has a health check. `docker ps` shows the container as `healthy` once
the service is answering, and `curl http://localhost:8080/ws/healthz` shows its
status. `docker stop` shuts it down cleanly.

## What is inside

| | |
|---|---|
| Port | `8080`: nginx serves the app and the guide, and passes `/ws/` to the service |
| Pricing service | ql-backend, listening on loopback inside the container only |
| Libraries | QuantLib 1.43 (sessions enabled) and Protobuf 34.0, linked statically |
| Base | `debian:trixie-slim`, running as the unprivileged user `ql` under tini |

## Source, building and issues

The Dockerfile, build instructions and building from your own checkouts are in
[markccchiang/ql-docker](https://github.com/markccchiang/ql-docker).
Report problems with the application to
[ql-frontend](https://github.com/markccchiang/ql-frontend/issues) or
[ql-backend](https://github.com/markccchiang/ql-backend/issues).

## Licence

ql-backend and ql-frontend are MIT-licensed. QuantLib is distributed under its
[modified BSD licence](https://github.com/lballabio/QuantLib/blob/master/LICENSE.TXT),
and Protobuf under the BSD 3-Clause licence.
