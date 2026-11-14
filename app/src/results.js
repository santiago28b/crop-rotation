// Shared helpers for showing recommendation results.
//
// Result shape (one per field), produced by ResourcesPage and emitted via
// 'recommendations-ready' -> { fields, results }:
//   {
//     insights:      /fields/insights response or null,
//     insightsError: '' or a message to show,
//     report:        /report response or null (summary, options[5], year_odds,
//                    snowpack, field_water_use, region_warning, data_sources...),
//     reportError:   '' or a message to show,
//   }

// The economics engine models silage corn; CDL/insights call grain corn "maize".
// This mapping lives only at the /report boundary.
export function reportCropId(id) {
  return id === 'maize' ? 'corn_silage' : id
}

export function formatMoney(value) {
  if (value == null) return 'Not available'
  return new Intl.NumberFormat(undefined, { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(value)
}

export function formatPercent(value) {
  return value == null ? '—' : `${Math.round(value * 100)}%`
}

export function doyToDate(doy) {
  if (doy == null) return ''
  return new Date(Date.UTC(2026, 0, doy)).toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'UTC' })
}

export const TAG_LABELS = {
  current: 'Your current crop',
  best_overall: 'Best overall',
  safest_dry_year: 'Safest in a dry year',
  best_for_soil: 'Best for the soil',
  alternative: 'Also worth a look',
}

// One row per money option (already ranked, options[0] = current crop),
// joined with its agronomy candidate by crop id. candidate may be null.
export function mergedOptions(result) {
  const candidates = new Map((result.insights?.candidates || [])
    .map((candidate) => [reportCropId(candidate.crop_id), candidate]))
  return (result.report?.options || []).map((option) => ({
    option,
    candidate: candidates.get(option.crop) || null,
  }))
}

// Agronomy-only candidates the economics table has no numbers for.
export function extraCandidates(result) {
  const inReport = new Set((result.report?.options || []).map((option) => option.crop))
  return (result.insights?.candidates || [])
    .filter((candidate) => !inReport.has(reportCropId(candidate.crop_id)))
    .slice(0, 5)
}

// option.data_notes is {yield: '...', price: '...'} -> one readable line.
export function dataNotesText(option) {
  const notes = option.data_notes
  if (!notes || typeof notes !== 'object') return ''
  return Object.entries(notes).map(([key, value]) => `${key.replaceAll('_', ' ')}: ${value}`).join(' · ')
}
