# Frontend Development with Vite

This directory contains the Vue.js frontend built with Vite for the OMA Browser.

## Prerequisites

- Node.js 18+ 
- npm or pnpm

## Setup

```bash
cd frontend
npm install
```

## Development

### Start Vite dev server

```bash
npm run dev
```

This starts the Vite development server at `http://localhost:5173` with:
- Hot Module Replacement (HMR)
- Fast refresh for Vue components

### Run Django simultaneously

In another terminal, start Django as usual:

```bash
cd ..
python manage.py runserver
```

The templates will automatically load Vue components from the Vite dev server when `DEBUG=True`.

## Production Build

```bash
npm run build
```

This generates optimized assets in `../oma/static/dist/`:
- Minified JavaScript bundles
- CSS extracted and optimized
- `manifest.json` for django-vite integration

## Project Structure

```
frontend/
├── src/
│   ├── components/          # Vue Single File Components
│   │   └── SearchToken.vue  # Search token input component
│   └── entries/             # Entry points for different pages
│       └── search-token.js  # Entry for search functionality
├── package.json
├── vite.config.js
└── README.md
```

## Django Integration

### Settings

Add to `settings/base.py`:

```python
INSTALLED_APPS = [
    ...
    'django_vite',
]

DJANGO_VITE = {
    "default": {
        "manifest_path": os.path.join(BASE_DIR, "../oma/static/dist/manifest.json"),
        "dev_mode": DEBUG,
        "dev_server_host": "localhost",
        "dev_server_port": 5173,
    }
}
```

### Templates

Use the new template include:

```django
{% include "includes/search-token-vue-vite.html" with unique_id='search_nav' multiline='true' %}
```

### Interacting from Django Templates

The Vue component exposes methods globally:

```javascript
// Preload tokens (e.g., from search results page)
window.search_token_vue_search_nav.preloadToken([
  {query: 'P53_RAT', single_term: true, prefix: 'proteinid', type: 'Protein'}
]);
```

## Adding New Components

1. Create a new `.vue` file in `src/components/`
2. Create an entry point in `src/entries/`
3. Add the entry to `vite.config.js` rollupOptions.input
4. Create a Django template include

## Migrating from Old Vue Code

The old inline Vue code in `search-token-vue.html` has been migrated to:
- `src/components/SearchToken.vue` - Component logic and template
- `src/entries/search-token.js` - Initialization and global exposure

Key changes:
- Options API → Composition API with `<script setup>`
- Inline styles → Scoped CSS
- Django template variables → Props via data attributes
- Custom delimiters `$[` `]$` → Standard Vue `{{ }}`
