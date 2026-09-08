# Linkr web — static frontend

Four static files. **No build step, no npm, no node_modules.** Serve the
directory with any static web server (nginx, Caddy, S3+CloudFront) and it works.

```
index.html    markup
styles.css    styles
config.js     RUNTIME configuration  <- the only per-environment file
app.js        behaviour
```

## The one thing that matters for deployment

`config.js` sets `window.LINKR_CONFIG.apiBase`, and it is loaded at **runtime**,
not baked in at build time. That means one artifact ships to every environment
and only `config.js` changes.

| `apiBase` | When to use it |
|---|---|
| `""` (default) | API and web are served from the same origin — e.g. nginx serves `/` from here and reverse-proxies `/api/` and `/health` to the API. **Preferred:** no CORS, no per-env config at all. |
| `"https://api.staging.example"` | API is on a different host/port. The API's `LINKR_CORS_ORIGINS` must then list the web origin. |

If you go with the same-origin proxy, note the API also owns the top-level
redirect route `GET /{code}` — so the proxy must send unknown top-level paths to
the API, not answer them with the SPA. Routes the API owns:
`/api/*`, `/health`, `/ready`, `/docs`, `/openapi.json`, and `/{code}`.

## Run it locally

```bash
python -m http.server 8080 --directory project/web
```

Then set `apiBase` to `http://localhost:8000` (and run the API with
`LINKR_CORS_ORIGINS=http://localhost:8080`), or put a proxy in front of both.
