/**
 * Entry point for SearchToken Vue component
 * This file is loaded by Django templates to initialize the search component
 */
import { createApp } from 'vue'
import SearchToken from '@/components/SearchToken.vue'

// Enable Vue DevTools in development
if (import.meta.env.DEV) {
  // Vue 3 DevTools is automatically enabled in dev mode
  // but we can add extra debugging here
  console.log('[Vue] Development mode - DevTools enabled')
}

/**
 * Initialize SearchToken component on a DOM element
 * @param {string} elementId - The ID of the element to mount the component
 * @param {Object} config - Configuration object from Django
 */
export function initSearchToken(elementId, config = {}) {
  const el = document.getElementById(elementId)
  if (!el) {
    console.error(`SearchToken: Element #${elementId} not found`)
    return null
  }

  const app = createApp(SearchToken, {
    uniqueId: elementId,
    multiline: config.multiline === 'true' || config.multiline === true,
    xrefOrder: config.xrefOrder || [],
    searchUrl: config.searchUrl || '/oma/search/token/',
    apiUrl: config.apiUrl || '/api/xref/',
    csrfToken: config.csrfToken || '',
    logoUrl: config.logoUrl || '/static/image/logo-oma-o.svg',
  })

  // Enable DevTools in development
  if (import.meta.env.DEV) {
    app.config.devtools = true
    app.config.performance = true
  }

  const instance = app.mount(el)

  // Expose instance globally for Django template interactions
  window[`search_token_vue_${elementId}`] = instance

  return instance
}

// Auto-initialize if data attributes are present
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('[data-search-token]').forEach(el => {
    const config = {
      multiline: el.dataset.multiline,
      xrefOrder: el.dataset.xrefOrder ? JSON.parse(el.dataset.xrefOrder) : [],
      searchUrl: el.dataset.searchUrl,
      apiUrl: el.dataset.apiUrl,
      csrfToken: el.dataset.csrfToken,
      logoUrl: el.dataset.logoUrl,
    }
    initSearchToken(el.id, config)
  })
})

// Expose for manual initialization from Django templates
window.initSearchToken = initSearchToken
