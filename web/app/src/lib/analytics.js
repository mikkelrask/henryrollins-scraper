/**
 * Ackee analytics tracker — SPA-aware.
 * Creates an instance once and stops the previous record on each navigation.
 */
import { create, attributes } from 'ackee-tracker'

const SERVER = 'https://analytics.porgy-ruler.ts.net'
const DOMAIN_ID = '2431b998-ee1d-4cd5-b7ab-8c3f9c31cf7c'

let instance = null
let stopCurrent = null

export function initAnalytics() {
  if (instance) return
  instance = create(SERVER)

  // Track the initial page view
  recordPageView()
}

export function recordPageView() {
  if (!instance) return

  // Stop tracking the previous page duration
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
