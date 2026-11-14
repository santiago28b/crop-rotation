<script setup>
defineEmits(['pick-field'])
</script>

<template>
  <main class="page-shell">
    <header class="brand" aria-label="Field Shift">
      <span class="brand-mark" aria-hidden="true">
        <svg viewBox="0 0 40 40" fill="none">
          <path d="M7 31c6.5-1.2 12.7-4 18.2-8.1C29.3 20.1 33 15 34 9" />
          <path d="M7 24.5c5.1-1 9.7-3.2 13.8-6.2C24.6 15.6 27.3 12 29 7" />
          <path d="M7 17.5c3.5-.8 6.7-2.2 9.5-4.2 2-1.4 3.7-3 5.1-4.8" />
        </svg>
      </span>
      <span>Field Shift</span>
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
          <path d="M60 96V52" />
          <path d="M60 69C43 69 34 60 34 43c17 0 26 9 26 26Z" />
          <path d="M60 60c0-15 8-23 23-23 0 15-8 23-23 23Z" />
          <path d="M30 96h60" />
          <path d="M22 105h76" />
        </svg>
      </div>
    </section>

    <footer class="page-footer">
      <span>Field Shift</span>
      <span>Practical crop planning, one field at a time.</span>
    </footer>
  </main>
</template>
