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

export async function getFieldProfile(field) {
  const body = { geometry: toGeoJSON(field), name: field.name }
  let profile = await request('/fields/profile', { method: 'POST', body: JSON.stringify(body) })
  let attempts = 0
  while (['partial', 'loading'].includes(profile.crop_history?.status) && attempts < 20) {
    await new Promise((resolve) => setTimeout(resolve, 3000))
    const history = await request('/fields/history', { method: 'POST', body: JSON.stringify(body) })
    profile = { ...profile, crop_history: history }
    attempts += 1
  }
  return profile
}

export function getInsights(field, history, resources) {
  return request('/fields/insights', {
    method: 'POST',
    body: JSON.stringify({
      geometry: toGeoJSON(field),
      name: field.name,
      history,
      resources,
    }),
  })
}

export function getProfitReport(field, currentCrop, waterSupply, areaCrops) {
  return request('/report', {
    method: 'POST',
    body: JSON.stringify({
      field: toGeoJSON(field),
      current_crop: currentCrop,
      water_supply: waterSupply,
      area_crops: areaCrops?.length ? areaCrops : undefined,
    }),
  })
}
