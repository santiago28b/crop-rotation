let locationRequest
let pending = false

export function requestLocation({ refresh = false } = {}) {
  // Share the welcome-page lookup with the map, including an in-flight request.
  if (locationRequest && (!refresh || pending)) return locationRequest

  pending = true
  locationRequest = new Promise((resolve, reject) => {
    if (typeof navigator === 'undefined' || !navigator.geolocation) {
      reject(new Error('Location is not available in this browser.'))
      return
    }

    navigator.geolocation.getCurrentPosition(resolve, reject, {
      enableHighAccuracy: true,
      timeout: 10000,
      maximumAge: refresh ? 0 : 60000,
    })
  }).finally(() => {
    pending = false
  })

  return locationRequest
}
