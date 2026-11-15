<script setup>
// Loading widget for the field-info step: a small satellite circles the
// farmer's field and scans it, while the text says which data is being read.
//   <SatelliteLoader v-if="loading" />
import { onBeforeUnmount, onMounted, ref } from 'vue'

const steps = [
  'Reading 25 years of NASA weather for your area…',
  'Checking satellite measurements of your field’s water use…',
  'Looking up your soil in USDA soil maps…',
  'Finding past crops from USDA satellite crop maps…',
]
const step = ref(0)
const reduceMotion = typeof window !== 'undefined'
  && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
let timer = null

onMounted(() => {
  timer = setInterval(() => { step.value = (step.value + 1) % steps.length }, 3200)
})
onBeforeUnmount(() => clearInterval(timer))
</script>

<template>
  <div class="satellite-loader" role="status" aria-live="polite">
    <svg class="sat-scene" viewBox="0 0 240 160" aria-hidden="true">
      <!-- the field: a few crop rows -->
      <g class="field">
        <path d="M70 118 L170 118 L190 140 L50 140 Z" class="field-base" />
        <path d="M86 118 L74 140 M106 118 L100 140 M126 118 L126 140 M146 118 L152 140 M162 118 L176 140" class="field-rows" />
      </g>

      <!-- scan beam from the satellite to the field -->
      <path class="beam" d="M120 52 L82 118 L158 118 Z" />

      <!-- orbit path -->
      <ellipse cx="120" cy="52" rx="92" ry="26" class="orbit" />

      <!-- satellite riding the orbit -->
      <g class="sat-orbit" :transform="reduceMotion ? 'translate(190 40)' : undefined">
        <animateMotion
          v-if="!reduceMotion"
          dur="6s"
          repeatCount="indefinite"
          path="M28 52 a92 26 0 1 0 184 0 a92 26 0 1 0 -184 0"
        />
        <g class="satellite">
          <rect x="-7" y="-6" width="14" height="12" rx="2" class="sat-body" />
          <rect x="-27" y="-4" width="17" height="8" rx="1" class="sat-panel" />
          <rect x="10" y="-4" width="17" height="8" rx="1" class="sat-panel" />
          <path d="M-10 0 H-7 M7 0 H10" class="sat-arm" />
          <path d="M0 6 V11" class="sat-arm" />
          <circle cx="0" cy="12" r="2" class="sat-dish" />
        </g>
      </g>

      <!-- little signal waves coming down -->
      <g class="signals">
        <path d="M112 92 q8 -6 16 0" />
        <path d="M108 100 q12 -8 24 0" />
      </g>
    </svg>

    <p class="sat-title">Getting your field’s data from NASA satellites and USDA</p>
    <p class="sat-step">{{ steps[step] }}</p>
    <p class="sat-hint">This usually takes 10–20 seconds.</p>
  </div>
</template>

<style scoped>
.satellite-loader { display: grid; justify-items: center; gap: 6px; padding: 8px 0 4px; text-align: center; }
.sat-scene { width: min(100%, 300px); height: auto; overflow: visible; }

.field-base { fill: #e7d3a8; stroke: #c9a46a; stroke-width: 1.5; }
.field-rows { stroke: #7f9b5f; stroke-width: 3; stroke-linecap: round; }

.orbit { fill: none; stroke: #c9a46a; stroke-width: 1.2; stroke-dasharray: 3 5; opacity: .7; }

.satellite { animation: bob 1.6s ease-in-out infinite; }
.sat-body { fill: #f3e6cc; stroke: #6d441d; stroke-width: 1.5; }
.sat-panel { fill: #5f7f9e; stroke: #34506b; stroke-width: 1.2; }
.sat-arm { stroke: #6d441d; stroke-width: 1.5; stroke-linecap: round; }
.sat-dish { fill: #6d441d; }

.beam { fill: #f1cd73; opacity: 0; animation: scan 6s ease-in-out infinite; }
.signals path { fill: none; stroke: #8b5a2b; stroke-width: 2; stroke-linecap: round; opacity: 0; animation: ping 1.8s ease-out infinite; }
.signals path:nth-child(2) { animation-delay: .5s; }

.sat-title { margin: 6px 0 0; color: var(--ink); font-size: 17px; font-weight: 750; }
.sat-step { min-height: 1.5em; margin: 0; color: var(--green-dark); font-size: 15px; font-weight: 650; }
.sat-hint { margin: 0; color: var(--muted); font-size: 13px; }

@keyframes bob { 0%, 100% { transform: translateY(0); } 50% { transform: translateY(-2px); } }
@keyframes scan { 0%, 30% { opacity: 0; } 40%, 60% { opacity: .35; } 70%, 100% { opacity: 0; } }
@keyframes ping { 0% { opacity: .9; transform: translateY(-6px); } 100% { opacity: 0; transform: translateY(10px); } }

@media (prefers-reduced-motion: reduce) {
  .satellite, .signals path { animation: none; }
  .beam { animation: none; opacity: .3; }
}
</style>
