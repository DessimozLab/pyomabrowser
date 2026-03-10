# Vite Hot-Reload Development Setup

## Quick Start

### Development Mode (Hot-Reload)

For frontend development with instant updates:

```bash
cd for_docker/
docker compose up
```

- Hot-reload enabled via `docker-compose.override.yml` (loaded automatically)
- Vite dev server on port 5173
- Changes to Vue files reflected instantly in browser

### Production Mode

To test production build:

```bash
cd frontend/ && npm run build
cd ../for_docker/
docker compose -f docker-compose.yml up -d
docker compose exec web python manage.py collectstatic --noinput
```

- Excludes override file with `-f docker-compose.yml`
- Assets built and served from `STATIC_ROOT/vite/`

## How It Works

### Development Mode

`docker-compose.override.yml` configures:
- **Vite container**: Runs dev server on port 5173, watches `frontend/src/`
- **Volume mounts**: Local code mounted for live editing
- **Environment variables**:
  - `DJANGO_VITE_DEV_MODE=true`
  - `DJANGO_VITE_DEV_SERVER_HOST=localhost` (browser-accessible)
  - `DJANGO_VITE_DEV_SERVER_PORT=5173`

Django-Vite generates URLs pointing to `http://localhost:5173/static/src/...` for hot-reload.

### Production Mode

- Frontend built with `npm run build` → outputs to `oma/static/vite/`
- `collectstatic` copies assets to `STATIC_ROOT/vite/`
- Django serves from `/static/vite/js/` and `/static/vite/assets/`
- Uses manifest.json at `STATIC_ROOT/vite/manifest.json`

**Important**: Vite config uses `base: '/static/'` in both modes for consistency.

## Troubleshooting

### Changes Not Appearing

```bash
# Check vite container is running
docker compose ps

# Check vite logs
docker compose logs -f vite

# Verify env vars
docker compose exec web env | grep VITE
```

### Assets Not Found (404 Errors)

**Development Mode**:
```bash
# Test Vite is serving correctly
curl http://localhost:5173/static/src/entries/search-token.js

# Should return 200 OK with JavaScript content
# If not, check DJANGO_VITE_DEV_SERVER_HOST=localhost in override file
```

**Production Mode**:
```bash
# Run collectstatic
docker compose exec web python manage.py collectstatic --noinput

# Verify files exist
docker compose exec web ls -la /data/static/vite/

# Restart web container
docker compose restart web
```


## Best Practices

- **Use hot-reload** when actively developing Vue components
- **Use production mode** (`-f docker-compose.yml`) when testing production builds or not working on frontend
- `docker-compose.override.yml` is tracked in git for development convenience

## Configuration Reference

### Django Settings (`pybrowser_dev/settings/base.py`)

```python
DJANGO_VITE = {
    "default": {
        "manifest_path": os.path.join(STATIC_ROOT, "vite/manifest.json"),
        "dev_mode": os.environ.get('DJANGO_VITE_DEV_MODE', 'false').lower() == 'true',
        "dev_server_host": os.environ.get('DJANGO_VITE_DEV_SERVER_HOST', 'localhost'),
        "dev_server_port": int(os.environ.get('DJANGO_VITE_DEV_SERVER_PORT', '5173')),
    }
}
```

### Vite Config (`frontend/vite.config.js`)

```javascript
export default defineConfig({
  base: '/static/',  // Always /static/ for both dev and prod
  build: {
    outDir: '../oma/static',
    manifest: 'vite/manifest.json',
    rollupOptions: {
      output: {
        entryFileNames: 'vite/js/[name].js',
        assetFileNames: 'vite/assets/[name].[ext]'
      }
    }
  }
})
```

### Output Structure

**After `npm run build`**:
```
oma/static/vite/
├── manifest.json
├── js/searchToken.js
└── assets/searchToken.css
```

**After `collectstatic` in container**:
```
/data/static/vite/  # STATIC_ROOT
├── manifest.json
├── js/searchToken.js
└── assets/searchToken.css
```

**URLs**:
- Dev: `http://localhost:5173/static/src/entries/search-token.js`
- Prod: `/static/vite/js/searchToken.js`

## Additional Resources

- [Vite Documentation](https://vitejs.dev/)
- [Vue 3 Documentation](https://vuejs.org/)
- [frontend/README.md](../frontend/README.md) - Frontend-specific details

