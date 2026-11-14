<script setup>
defineEmits(['pick-field'])
</script>

<template>
  <main class="page-shell">
    <header class="brand" aria-label="Patato">
      <span class="brand-mark" aria-hidden="true">
        <svg viewBox="0 0 40 40" fill="none">
          <path d="M8 23c0-8 6-13.5 14.5-13 7 .5 12 5 12 11.5 0 7.5-6.5 12.5-15 12.5C13 34 8 29.5 8 23Z" />
          <path d="M15 21.5q2-2 4 0" />
          <path d="M24 18.5q2-2 4 0" />
          <path d="M21.5 27q2-2 4 0" />
        </svg>
      </span>
      <span>Patato</span>
    </header>

    <section class="welcome-screen" aria-labelledby="welcome-title">
      <div class="welcome-copy">
        <p class="eyebrow">Crop planning for your farm</p>
        <h1 id="welcome-title">A better plan starts with your field.</h1>
        <p class="welcome-description">
          Explore crop options and make a growing plan that fits your land.
        </p>
        <button class="primary-button" type="button" @click="$emit('pick-field')">
          Pick a field <span aria-hidden="true">→</span>
        </button>
      </div>

      <div class="welcome-art" aria-hidden="true">
        <svg viewBox="0 0 120 120" fill="none">
          <path d="M26 72c0-19 15-32 36-31 19 1 33 12 33 28 0 18-17 30-39 30-18 0-30-10-30-27Z" />
          <path d="M44 68q4-4 8 0" />
          <path d="M68 60q4-4 8 0" />
          <path d="M60 82q4-4 8 0" />
          <path d="M62 41V25" />
          <path d="M62 32c-9 0-14-4-14-12 9 0 14 4 14 12Z" />
          <path d="M62 27c0-7 4-11 12-11 0 7-4 11-12 11Z" />
          <path d="M22 108h76" />
        </svg>
      </div>
    </section>

    <footer class="page-footer">
      <span>Patato</span>
      <span>Practical crop planning, one field at a time.</span>
    </footer>
  </main>
</template>
