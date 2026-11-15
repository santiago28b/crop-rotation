const API_BASE = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '')

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  })
  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    const detail = typeof data.detail === 'string' ? data.detail : `Request failed (${response.status})`
    throw new Error(detail)
  }
  return data
}

export function toGeoJSON(field) {
  const ring = (field.boundary || []).map(({ lat, lng }) => [lng, lat])
  if (ring.length && (ring[0][0] !== ring.at(-1)[0] || ring[0][1] !== ring.at(-1)[1])) {
    ring.push([...ring[0]])
  }
  return { type: 'Polygon', coordinates: [ring] }
}

export async function getCatalog() {
  return request('/catalog/crops')
}

export async function getReportCrops() {
  return request('/crops')
}

function fieldBody(field) {
  return JSON.stringify({ geometry: toGeoJSON(field), name: field.name })
}

export function isHistoryPending(history) {
  return ['partial', 'loading'].includes(history?.status)
}

// One call. Returns as soon as the backend has soil/climate and whatever crop history
// finished inside its time budget; follow up with pollFieldHistory while it is pending.
export function getFieldProfile(field, { signal } = {}) {
  return request('/fields/profile', { method: 'POST', body: fieldBody(field), signal })
}

function wait(ms, signal) {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) return reject(signal.reason)
    const timer = setTimeout(resolve, ms)
    signal?.addEventListener('abort', () => {
      clearTimeout(timer)
      reject(signal.reason)
    }, { once: true })
  })
}

// Re-polls crop history until it is no longer partial/loading, the time budget runs out,
// or the signal aborts. Calls onUpdate with every response; resolves with the last one
// (still pending if the budget ran out).
export async function pollFieldHistory(field, { signal, onUpdate, budgetMs = 180000, delayMs = 4000 } = {}) {
  const deadline = Date.now() + budgetMs
  let history = null
  do {
    await wait(delayMs, signal)
    history = await request('/fields/history', { method: 'POST', body: fieldBody(field), signal })
    onUpdate?.(history)
  } while (isHistoryPending(history) && Date.now() < deadline)
  return history
}

export function getInsights(field, history, resources, priorities) {
  return request('/fields/insights', {
    method: 'POST',
    body: JSON.stringify({
      geometry: toGeoJSON(field),
      name: field.name,
      history,
      resources,
      priorities,
    }),
  })
}

export function getProfitReport(field, currentCrop, waterSupply, areaCrops, irrigationMethod, waterSource, cropWaterNeedIn, priorities) {
  return request('/report', {
    method: 'POST',
    body: JSON.stringify({
      field: toGeoJSON(field),
      current_crop: currentCrop,
      water_supply: waterSupply,
      area_crops: areaCrops?.length ? areaCrops : undefined,
      irrigation_method: irrigationMethod || undefined,
      water_source: waterSource || undefined,
      crop_water_need_in: cropWaterNeedIn && Object.keys(cropWaterNeedIn).length ? cropWaterNeedIn : undefined,
      priorities: priorities || undefined,
    }),
  })
}
