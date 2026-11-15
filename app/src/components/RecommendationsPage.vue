<script setup>
import { computed, onMounted, ref } from 'vue'
import { mergedOptions, extraCandidates, formatMoney as money, formatPercent as percent, TAG_LABELS as tags } from '../results.js'
import PotatoLoader from './PotatoLoader.vue'

const props = defineProps({
  fields: { type: Array, default: () => [] },
  results: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  error: { type: String, default: '' },
})
const emit = defineEmits(['go-back'])
const pageTitle = ref(null)
const selectedIndex = ref(0)
const field = computed(() => props.fields[selectedIndex.value])
const result = computed(() => props.results[selectedIndex.value])
const fieldName = computed(() => field.value?.name || `Field ${selectedIndex.value + 1}`)

const options = computed(() => mergedOptions(result.value || {}))
const otherCandidates = computed(() => extraCandidates(result.value || {}))

const sources = computed(() => [...new Set([
  ...(result.value?.report?.data_sources || []),
  ...(result.value?.insights?.sources || []),
])])

function growingFit(candidate) {
  return percent(candidate?.suitability?.overall ?? candidate?.score)
}

function date(doy) {
  if (doy == null) return 'Not available'
  const year = result.value?.insights?.planting_year || new Date().getFullYear() + 1
  return new Date(Date.UTC(year, 0, doy)).toLocaleDateString(undefined, {
    month: 'short', day: 'numeric', timeZone: 'UTC',
  })
}

function plantingWindow(candidate) {
  const window = candidate?.plant_window
  if (!window) return 'Not available'
  return `${date(window.start_doy)} – ${date(window.end_doy)}${window.start_doy > window.end_doy ? ' (across New Year)' : ''}`
}

const riskWords = { low: 'Low', medium: 'Medium', high: 'High' }
const soilWords = { builds: 'Helps your soil', neutral: 'Neutral', hard: 'Hard on soil' }

function notes(option) {
  if (!option.data_notes || typeof option.data_notes !== 'object') return []
  return Object.entries(option.data_notes).map(([key, value]) => ({
    label: key.replaceAll('_', ' '), value,
  }))
}

onMounted(() => {
  pageTitle.value?.focus({ preventScroll: true })
  window.scrollTo({ top: 0 })
})
</script>

<template>
  <main class="page-shell">
    <header class="brand" aria-label="Patato">
      <span class="brand-mark" aria-hidden="true">
        <svg viewBox="0 0 40 40" fill="none">
          <path d="M8 23c0-8 6-13.5 14.5-13 7 .5 12 5 12 11.5 0 7.5-6.5 12.5-15 12.5C13 34 8 29.5 8 23Z" />
          <path d="M15 21.5q2-2 4 0M24 18.5q2-2 4 0M21.5 27q2-2 4 0" />
        </svg>
      </span>
      <span>Patato</span>
    </header>

    <section class="recommendations-page" aria-labelledby="recommendations-title" :aria-busy="loading">
      <button class="back-button" type="button" @click="emit('go-back')">
        <span aria-hidden="true">←</span> Edit answers
      </button>

      <div class="recommendations-heading">
        <div>
          <p class="eyebrow">A plan that fits your field</p>
          <h1 id="recommendations-title" ref="pageTitle" tabindex="-1">Your crop options</h1>
          <p class="recommendations-intro">Compare <strong>growing fit</strong>, <strong>water risk</strong>, <strong>income</strong>, and <strong>soil health</strong> before choosing your next crop.</p>
        </div>
        <span class="field-count">{{ fields.length }} {{ fields.length === 1 ? 'field' : 'fields' }}</span>
      </div>

      <nav v-if="fields.length > 1" class="recommendation-fields" aria-label="Choose a field to compare">
        <button
          v-for="(item, index) in fields"
          :key="index"
          type="button"
          :aria-pressed="selectedIndex === index"
          @click="selectedIndex = index"
        >
          {{ item.name || `Field ${index + 1}` }}
        </button>
      </nav>

      <div v-if="loading && !result" class="recommendation-state">
        <h2>Finding what fits {{ fieldName }}</h2>
        <PotatoLoader class="recommendations-loader" />
        <p>Checking growing conditions, water needs, and estimated returns. This can take a little while.</p>
      </div>

      <div v-else-if="error || !result" class="recommendation-state recommendation-state--error" role="alert">
        <h2>We couldn’t finish the comparison</h2>
        <p>{{ error || 'No recommendations are available for this field yet.' }}</p>
        <button class="primary-button" type="button" @click="emit('go-back')">Back to your answers</button>
      </div>

      <template v-else>
        <section class="field-outlook" aria-labelledby="field-outlook-title">
          <div class="outlook-label">
            <span class="outlook-dot" aria-hidden="true"></span>
            Field outlook
          </div>
          <h2 id="field-outlook-title">{{ fieldName }}</h2>
          <p v-if="result.report?.summary" class="outlook-summary">{{ result.report.summary }}</p>
          <p v-else class="outlook-summary">Here’s what may grow well on your field, based on the information available.</p>
          <div v-if="result.report?.year_odds" class="year-outlook" aria-label="Next-season outlook">
            <span>Dry year <strong>{{ percent(result.report.year_odds.dry) }}</strong></span>
            <span>Normal year <strong>{{ percent(result.report.year_odds.normal) }}</strong></span>
            <span>Wet year <strong>{{ percent(result.report.year_odds.wet) }}</strong></span>
          </div>
        </section>

        <p v-if="result.report?.region_warning" class="recommendation-notice" role="note">{{ result.report.region_warning }}</p>
        <p v-if="result.insightsError" class="recommendation-notice" role="alert"><strong>Growing-fit analysis is unavailable.</strong> {{ result.insightsError }}</p>
        <p v-if="result.reportError" class="recommendation-notice" role="alert"><strong>Profit estimates are unavailable.</strong> {{ result.reportError }}</p>
        <p v-if="!result.report && !result.reportError" class="recommendation-notice">Choose your current crop in <strong>Edit answers</strong> to include a profit comparison.</p>

        <div v-if="result.report?.field_water_use?.season_et_in != null" class="measured-water">
          <div>
            <span class="metric-label">Measured field water use</span>
            <strong>{{ result.report.field_water_use.season_et_in }} <small>in / season</small></strong>
          </div>
          <p>{{ result.report.field_water_use.note }}</p>
        </div>

        <div v-if="options.length" class="options-heading">
          <h2>Compare your options</h2>
          <p>Ranked by how well each crop fits your field and holds up with your water. Income is compared with what you grow now.</p>
        </div>

        <div class="crop-options">
          <article
            v-for="{ option, candidate } in options"
            :key="option.crop"
            class="crop-option"
            :class="{
              'crop-option--best': option.tag === 'best_overall',
              'crop-option--current': option.tag === 'current',
            }"
          >
            <div class="crop-option-heading">
              <span class="crop-tag" :class="`crop-tag--${option.tag}`">{{ tags[option.tag] || 'Another option' }}</span>
              <h3>{{ option.label || option.crop.replaceAll('_', ' ') }}</h3>
            </div>

            <dl v-if="option.card" class="crop-tiers">
              <div>
                <dt>Water risk in a dry year</dt>
                <dd><span class="tier" :class="`tier--${option.card.water_risk}`">{{ riskWords[option.card.water_risk] }}</span></dd>
                <dd class="tier-detail">{{ option.card.water_text }}</dd>
              </div>
              <div>
                <dt>Income</dt>
                <dd><span class="tier" :class="`tier--${option.card.income_vs_current}`">{{ option.card.income_text }}</span></dd>
              </div>
              <div>
                <dt>Soil</dt>
                <dd><span class="tier" :class="`tier--soil-${option.card.soil}`">{{ soilWords[option.card.soil] }}</span></dd>
                <dd class="tier-detail">{{ option.card.soil_text }}</dd>
              </div>
            </dl>

            <ul v-if="option.card?.watch_outs?.length" class="crop-watch-outs">
              <li v-for="item in option.card.watch_outs" :key="item">{{ item }}</li>
            </ul>

            <p v-if="option.why" class="crop-reason">{{ option.why }}</p>

            <dl v-if="candidate" class="growing-facts">
              <div><dt>Growing fit</dt><dd class="fit-value">{{ growingFit(candidate) }}</dd></div>
              <div><dt>Planting window</dt><dd>{{ plantingWindow(candidate) }}</dd></div>
              <div v-if="candidate.water?.crop_need_mm != null"><dt>Seasonal water need</dt><dd>{{ Math.round(candidate.water.crop_need_mm / 25.4) }} in</dd></div>
            </dl>

            <p v-if="option.risks?.length" class="crop-risk"><strong>Watch for:</strong> {{ option.risks[0] }}</p>
            <details class="crop-evidence">
              <summary>Why this option &amp; where the numbers come from</summary>
              <dl class="return-comparison">
                <div>
                  <dt>Rough net return</dt>
                  <dd :class="{ 'negative-return': option.expected_profit_per_acre < 0 }">{{ money(option.expected_profit_per_acre) }} <small>/ acre</small></dd>
                </div>
                <div>
                  <dt>In a dry year</dt>
                  <dd :class="{ 'negative-return': option.dry_year_profit_per_acre < 0 }">{{ money(option.dry_year_profit_per_acre) }} <small>/ acre</small></dd>
                </div>
              </dl>
              <p v-if="result.report?.money_note" class="evidence-gap">{{ result.report.money_note }}</p>
              <ul v-if="option.risks?.length"><li v-for="risk in option.risks" :key="risk">{{ risk }}</li></ul>
              <p v-for="flag in candidate?.rotation?.flags || []" :key="flag">{{ flag }}</p>
              <p v-for="evidence in candidate?.evidence || []" :key="evidence">{{ evidence }}</p>
              <p v-for="gap in candidate?.gaps || []" :key="gap" class="evidence-gap">{{ gap }}</p>
              <dl v-if="notes(option).length" class="source-notes">
                <div v-for="note in notes(option)" :key="note.label"><dt>{{ note.label }}</dt><dd>{{ note.value }}</dd></div>
              </dl>
            </details>
          </article>
        </div>

        <section v-if="otherCandidates.length" class="other-crops" aria-labelledby="other-crops-title">
          <p class="eyebrow">More growing possibilities</p>
          <h2 id="other-crops-title">{{ options.length ? 'Other crops that may fit' : 'Growing-fit options' }}</h2>
          <p>These options have a growing-fit analysis, but no profit estimate in this comparison.</p>
          <div class="other-crop-list">
            <article v-for="candidate in otherCandidates" :key="candidate.crop_id">
              <div><h3>{{ candidate.name }}</h3><span>{{ candidate.role === 'cover' ? 'Cover crop' : candidate.role === 'forage' ? 'Forage crop' : 'Crop option' }}</span></div>
              <strong>{{ growingFit(candidate) }} <small>growing fit</small></strong>
              <p>Plant {{ plantingWindow(candidate) }}</p>
              <p v-if="candidate.water?.crop_need_mm != null">About <strong>{{ Math.round(candidate.water.crop_need_mm / 25.4) }} in</strong> seasonal water need</p>
            </article>
          </div>
        </section>

        <p v-if="!options.length && !otherCandidates.length" class="recommendation-notice">No crop options could be compared for this field. Edit your answers to try again.</p>

        <details class="field-sources">
          <summary>Field data &amp; assumptions</summary>
          <p v-if="result.report?.disclaimer">{{ result.report.disclaimer }}</p>
          <p v-if="result.report?.snowpack?.note">{{ result.report.snowpack.note }}</p>
          <p v-if="result.report?.field_water_use?.source">{{ result.report.field_water_use.source }}</p>
          <ul><li v-for="source in sources" :key="source">{{ source }}</li></ul>
          <p v-for="note in result.insights?.notes || []" :key="note">{{ note }}</p>
        </details>
      </template>
    </section>
  </main>
</template>

<style scoped>
.recommendations-page { width: min(100%, 1120px); margin: 28px auto 48px; }
.recommendations-heading { display: flex; justify-content: space-between; align-items: flex-start; gap: 24px; margin: 36px 0 28px; }
.recommendations-heading .eyebrow { margin-bottom: 12px; }
.recommendations-heading h1 { max-width: none; font-size: clamp(38px, 5.2vw, 62px); }
.recommendations-intro { max-width: 650px; margin: 18px 0 0; color: var(--muted); font-size: 18px; line-height: 1.65; }
.recommendations-intro strong { color: var(--ink); font-weight: 700; }
.field-count { flex: 0 0 auto; margin-top: 28px; padding: 10px 16px; border: 1px solid var(--line); border-radius: 999px; color: var(--green-dark); background: #fff; font-weight: 700; }
.recommendation-fields { display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 24px; }
.recommendation-fields button { min-height: 46px; padding: 10px 18px; border: 1px solid var(--line); border-radius: 999px; background: #fff; color: var(--green-dark); cursor: pointer; font-weight: 700; }
.recommendation-fields button[aria-pressed='true'] { border-color: var(--green); background: var(--green); color: #fff; }
.field-outlook { padding: clamp(24px, 4vw, 40px); border: 1px solid #dcc29d; border-left: 6px solid var(--green); border-radius: 18px; background: #f5e9d1; }
.outlook-label { display: flex; align-items: center; gap: 8px; color: var(--green-dark); font-size: 13px; font-weight: 800; letter-spacing: .08em; text-transform: uppercase; }
.outlook-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--sprout); }
.field-outlook h2 { margin: 14px 0 12px; color: var(--green-dark); font-size: 28px; }
.outlook-summary { max-width: 900px; margin: 0; color: var(--ink); font-size: clamp(19px, 2.1vw, 24px); font-weight: 650; line-height: 1.55; }
.year-outlook { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 22px; }
.year-outlook span { padding: 8px 12px; border: 1px solid #e3d0ae; border-radius: 8px; background: #fff9ef; color: var(--muted); font-size: 14px; }
.year-outlook strong { margin-left: 5px; color: var(--green-dark); }
.options-heading { margin: 36px 0 20px; }
.options-heading h2, .other-crops h2 { margin: 0 0 10px; font-size: 28px; }
.options-heading p { margin: 0; color: var(--muted); font-size: 14px; line-height: 1.6; }
.crop-options { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); align-items: start; gap: 20px; }
.crop-option { min-width: 0; padding: clamp(22px, 3vw, 30px); border: 1px solid var(--line); border-radius: 18px; background: #fff; box-shadow: 0 5px 20px #6d441d06; }
.crop-option--best { border: 2px solid var(--green); box-shadow: 0 6px 24px #6d441d12; }
.crop-option--current { background: #fffaf1; }
.crop-option-heading h3 { margin: 16px 0 22px; color: var(--ink); font-size: 28px; line-height: 1.2; letter-spacing: -.035em; }
.crop-tiers { display: grid; gap: 14px; margin: 0 0 18px; }
.crop-tiers dt { margin-bottom: 6px; color: var(--muted); font-size: 12px; font-weight: 800; letter-spacing: .06em; text-transform: uppercase; }
.crop-tiers dd { margin: 0; }
.tier { display: inline-block; padding: 5px 10px; border-radius: 7px; border: 1px solid var(--line); background: #fbf6ec; color: var(--ink); font-size: 14px; font-weight: 750; }
.tier-detail { margin-top: 5px !important; color: var(--muted); font-size: 13px; line-height: 1.5; }
.tier--low, .tier--much_higher, .tier--higher, .tier--soil-builds { border-color: #9fbf8a; background: #eef5e6; color: #35572a; }
.tier--medium, .tier--similar, .tier--soil-neutral { border-color: #e3c98f; background: #fbf1da; color: #7a5410; }
.tier--high, .tier--lower, .tier--much_lower, .tier--soil-hard { border-color: #e2a99a; background: #fbe9e4; color: #8a3423; }
.tier--current { color: var(--green-dark); }
.crop-watch-outs { margin: 0 0 16px; padding: 12px 14px 12px 30px; border-radius: 10px; background: #fbf1da; color: #6a4a12; font-size: 14px; line-height: 1.55; }
.crop-tag { display: inline-block; padding: 7px 11px; border-radius: 7px; color: var(--green-dark); background: #f2e7d2; font-size: 12px; font-weight: 800; letter-spacing: .025em; }
.crop-tag--best_overall { background: var(--green); color: #fff; }
.crop-tag--best_for_soil, .crop-tag--safest_dry_year { background: #eaf1e2; color: #355f28; }
.crop-tag--current { border: 1px solid #dfcbae; background: transparent; }
.metric-label { color: var(--muted); font-size: 13px; font-weight: 700; }
.expected-return p { margin: 5px 0 22px; color: var(--muted); }
.expected-return strong { color: var(--green-dark); font-size: clamp(34px, 4vw, 46px); font-weight: 800; letter-spacing: -.05em; line-height: 1.1; }
.negative-return { color: #a03f29 !important; }
.return-comparison { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin: 0; padding: 18px 0; border-top: 1px solid var(--line); border-bottom: 1px solid var(--line); }
.return-comparison dt, .growing-facts dt { margin-bottom: 7px; color: var(--muted); font-size: 12px; font-weight: 600; }
.return-comparison dd { margin: 0; color: var(--ink); font-size: 21px; font-weight: 750; }
.return-comparison small { font-size: 12px; font-weight: 500; }
.crop-reason { margin: 20px 0; color: #544633; font-size: 15px; line-height: 1.7; }
.growing-facts { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; margin: 0 0 20px; padding: 16px; border-radius: 10px; background: #faf6ed; }
.growing-facts dd { margin: 0; color: var(--ink); font-size: 14px; font-weight: 700; line-height: 1.5; }
.growing-facts .fit-value { color: #355f28; font-size: 21px; }
.crop-risk { margin: 16px 0; padding-left: 12px; border-left: 3px solid #c5924e; color: #78502b; font-size: 13px; line-height: 1.6; }
.crop-evidence { margin-top: 20px; padding-top: 16px; border-top: 1px solid var(--line); }
.crop-evidence summary, .field-sources summary { min-height: 36px; color: var(--green-dark); cursor: pointer; font-size: 13px; font-weight: 700; line-height: 1.6; }
.crop-evidence p, .crop-evidence li, .field-sources p, .field-sources li { color: var(--muted); font-size: 13px; line-height: 1.7; overflow-wrap: anywhere; }
.crop-evidence ul, .field-sources ul { padding-left: 20px; }
.evidence-gap { font-style: italic; }
.source-notes { margin-bottom: 0; }
.source-notes div { margin-top: 10px; }
.source-notes dt { color: var(--ink); font-size: 12px; font-weight: 700; text-transform: capitalize; }
.source-notes dd { margin: 3px 0 0; color: var(--muted); font-size: 12px; line-height: 1.7; }
.recommendation-notice { margin: 20px 0; padding: 16px 20px; border: 1px solid #e0c09a; border-radius: 12px; background: #fff7e8; color: #78502b; font-size: 14px; line-height: 1.65; }
.measured-water { display: flex; align-items: center; gap: 24px; margin-top: 24px; padding: 20px 24px; border: 1px solid var(--line); border-radius: 12px; background: #fff; }
.measured-water > div { flex: 0 0 auto; }
.measured-water .metric-label { display: block; margin-bottom: 6px; }
.measured-water strong { color: var(--green-dark); font-size: 24px; }
.measured-water small { font-size: 13px; font-weight: 500; }
.measured-water p { margin: 0; color: var(--muted); font-size: 13px; line-height: 1.65; }
.other-crops { margin-top: 30px; padding: 28px; border: 1px solid var(--line); border-radius: 18px; background: #f3efdf; }
.other-crops .eyebrow { margin-bottom: 10px; }
.other-crops > p:not(.eyebrow) { color: var(--muted); line-height: 1.6; }
.other-crop-list { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 230px), 1fr)); gap: 12px; margin-top: 20px; }
.other-crop-list article { padding: 18px; border: 1px solid #e4dcc6; border-radius: 12px; background: #fff; }
.other-crop-list h3 { margin: 0 0 5px; color: var(--ink); font-size: 18px; }
.other-crop-list span { color: var(--muted); font-size: 12px; }
.other-crop-list article > strong { display: block; margin-top: 16px; color: #355f28; font-size: 22px; }
.other-crop-list small { font-size: 12px; font-weight: 600; }
.other-crop-list p { margin-bottom: 0; color: var(--muted); font-size: 12px; line-height: 1.6; }
.field-sources { margin-top: 28px; padding: 22px 26px; border: 1px solid var(--line); border-radius: 12px; background: #fffbf4; }
.field-sources summary { font-size: 15px; }
.recommendation-state { display: flex; min-height: 320px; flex-direction: column; align-items: center; justify-content: center; padding: 40px 24px; border: 1px solid var(--line); border-radius: 18px; background: #fffaf1; text-align: center; }
.recommendations-loader { width: 100%; }
.recommendation-state h2 { margin: 24px 0 12px; font-size: 28px; }
.recommendation-state p { max-width: 480px; margin: 0; color: var(--muted); line-height: 1.7; }
.recommendation-state--error { border-color: #e0c09a; }
.recommendation-state .primary-button { margin-top: 24px; }
@media (max-width: 760px) {
  .recommendations-heading { flex-direction: column; gap: 16px; margin-top: 28px; }
  .field-count { margin: 0; }
  .crop-options { grid-template-columns: 1fr; }
  .measured-water { align-items: flex-start; flex-direction: column; gap: 14px; }
  .other-crops { padding: 22px; }
}
@media (max-width: 420px) {
  .growing-facts { grid-template-columns: 1fr 1fr; }
  .return-comparison { gap: 12px; }
  .return-comparison dd { font-size: 19px; }
}
</style>
