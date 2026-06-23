/**
 * Ackee analytics tracker — SPA-aware.
 * Creates an instance once and stops the previous record on each navigation.
 * Lazy import: if ackee-tracker fails to load, analytics is silently skipped.
 */
let create = null
let attributes = null
let loaded = false

async function ensureLoaded() {
  if (loaded) return true
  try {
    const mod = await import('ackee-tracker')
    create = mod.create
    attributes = mod.attributes
    loaded = true
    return true
  } catch (e) {
    console.warn('Analytics unavailable:', e)
    return false
  }
}

const SERVER = 'https://analytics.porgy-ruler.ts.net'
const DOMAIN_ID = '2431b998-ee1d-4cd5-b7ab-8c3f9c31cf7c'

let instance = null
let stopCurrent = null

export async function initAnalytics() {
  if (instance) return
  const ok = await ensureLoaded()
  if (!ok) return
  instance = create(SERVER)
  recordPageView()
}

export function recordPageView() {
  if (!instance) return

  if (stopCurrent) {
    stopCurrent()
    stopCurrent = null
  }

  const attrs = attributes({
    siteLocation: window.location.href,
    siteName: document.title,
  })

  const { stop } = instance.record(DOMAIN_ID, attrs)
  stopCurrent = stop
}
