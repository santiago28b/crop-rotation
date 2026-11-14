<script setup>
// Loading widget: a potato waddles across the screen to meet its friends,
// who are playing catch. Drop into any loading state:
//   <PotatoLoader v-if="loading" />
defineProps({
  message: { type: String, default: 'Working on your recommendations…' },
})
</script>

<template>
  <div class="potato-loader" role="status" aria-live="polite">
    <div class="potato-scene" aria-hidden="true">
      <div class="walk-track">
        <svg class="potato waddle" viewBox="0 0 40 40" fill="none">
          <path class="body" d="M8 23c0-8 6-13.5 14.5-13 7 .5 12 5 12 11.5 0 7.5-6.5 12.5-15 12.5C13 34 8 29.5 8 23Z" />
          <path d="M15 21.5q2-2 4 0" />
          <path d="M24 18.5q2-2 4 0" />
          <path d="M21.5 27q2-2 4 0" />
        </svg>
      </div>
      <div class="friends">
        <svg class="potato friend friend-a" viewBox="0 0 40 40" fill="none">
          <path class="body" d="M8 23c0-8 6-13.5 14.5-13 7 .5 12 5 12 11.5 0 7.5-6.5 12.5-15 12.5C13 34 8 29.5 8 23Z" />
          <path d="M15 21.5q2-2 4 0" />
          <path d="M24 18.5q2-2 4 0" />
          <path d="M21.5 27q2-2 4 0" />
        </svg>
        <span class="ball"></span>
        <svg class="potato friend friend-b" viewBox="0 0 40 40" fill="none">
          <path class="body" d="M8 23c0-8 6-13.5 14.5-13 7 .5 12 5 12 11.5 0 7.5-6.5 12.5-15 12.5C13 34 8 29.5 8 23Z" />
          <path d="M15 21.5q2-2 4 0" />
          <path d="M24 18.5q2-2 4 0" />
          <path d="M21.5 27q2-2 4 0" />
        </svg>
      </div>
      <div class="ground"></div>
    </div>
    <p class="potato-message">{{ message }}</p>
  </div>
</template>

<style scoped>
.potato-loader {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.5rem;
  padding: 1.5rem 0 0.5rem;
}
.potato-scene {
  position: relative;
  width: min(420px, 90%);
  height: 90px;
  overflow: hidden;
}
.potato {
  width: 44px;
  height: 44px;
}
.potato path {
  stroke: #8a5a2b;
  stroke-width: 2;
  stroke-linecap: round;
}
.potato .body {
  fill: #f4e4c8;
}
.ground {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 6px;
  border-bottom: 2px dashed rgba(138, 90, 43, 0.35);
}
/* the traveler: waddles across to join the game, then comes around again */
.walk-track {
  position: absolute;
  bottom: 8px;
  left: 0;
  animation: cross 5.5s linear infinite;
}
.waddle {
  animation: waddle 0.45s ease-in-out infinite alternate;
  transform-origin: 50% 90%;
}
@keyframes cross {
  from { transform: translateX(-52px); }
  to { transform: translateX(440px); }
}
@keyframes waddle {
  from { transform: rotate(-8deg) translateY(0); }
  to { transform: rotate(8deg) translateY(-3px); }
}
/* the friends, playing catch on the right */
.friends {
  position: absolute;
  right: 8px;
  bottom: 8px;
  display: flex;
  align-items: flex-end;
  gap: 34px;
}
.friend {
  width: 38px;
  height: 38px;
  transform-origin: 50% 90%;
}
.friend-a { animation: hop 1.4s ease-in-out infinite; }
.friend-b { animation: hop 1.4s ease-in-out 0.7s infinite; }
@keyframes hop {
  0%, 60%, 100% { transform: translateY(0) rotate(0deg); }
  15% { transform: translateY(-10px) rotate(-6deg); }
  30% { transform: translateY(0) rotate(4deg); }
}
/* the ball they toss back and forth */
.ball {
  position: absolute;
  left: 30px;
  bottom: 30px;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #c0392b;
  animation: toss 1.4s ease-in-out infinite;
}
@keyframes toss {
  0%, 100% { transform: translate(0, 0); }
  25% { transform: translate(22px, -26px); }
  50% { transform: translate(44px, 0); }
  75% { transform: translate(22px, -26px); }
}
.potato-message {
  margin: 0;
  font-weight: 600;
  color: #6b4423;
}
@media (prefers-reduced-motion: reduce) {
  .walk-track, .waddle, .friend-a, .friend-b, .ball { animation: none; }
}
</style>
