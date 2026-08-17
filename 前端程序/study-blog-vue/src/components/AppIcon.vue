<script setup>
defineProps({ name: { type: String, required: true }, size: { type: Number, default: 22 } });
</script>

<template>
  <svg
    class="app-icon"
    :width="size"
    :height="size"
    viewBox="0 0 24 24"
    fill="none"
    aria-hidden="true"
  >
    <template v-if="name === 'home'">
      <path d="M3.5 10.5 12 3l8.5 7.5" />
      <path d="M5.5 9.5V21h13V9.5M9.5 21v-7h5v7" />
    </template>
    <template v-else-if="name === 'book'">
      <path
        d="M4 4.5c3.2-.7 5.8.2 8 2.3v14c-2.2-2.1-4.8-3-8-2.3v-14ZM20 4.5c-3.2-.7-5.8.2-8 2.3v14c2.2-2.1 4.8-3 8-2.3v-14Z"
      />
    </template>
    <template v-else-if="name === 'exam'">
      <rect x="4" y="2" width="16" height="20" rx="2" />
      <path d="M8 7h8M8 11h8M8 15h5" />
    </template>
    <template v-else-if="name === 'check'">
      <rect x="3" y="3" width="18" height="18" rx="4" />
      <path d="m7.5 12 3 3 6-7" />
    </template>
    <template v-else-if="name === 'spark'">
      <path d="m12 2 1.8 5.2L19 9l-5.2 1.8L12 16l-1.8-5.2L5 9l5.2-1.8L12 2Z" />
      <path d="m18.5 15 .8 2.2 2.2.8-2.2.8-.8 2.2-.8-2.2-2.2-.8 2.2-.8.8-2.2Z" />
    </template>
    <template v-else-if="name === 'settings'">
      <circle cx="12" cy="12" r="3" />
      <path
        d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2.8 2.8-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.6v.2h-4V21a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1L4.2 17l.1-.1a1.7 1.7 0 0 0 .3-1.9A1.7 1.7 0 0 0 3 14H2.8v-4H3a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9L4.2 7 7 4.2l.1.1a1.7 1.7 0 0 0 1.9.3A1.7 1.7 0 0 0 10 3V2.8h4V3a1.7 1.7 0 0 0 1 1.6 1.7 1.7 0 0 0 1.9-.3l.1-.1L19.8 7l-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.6 1h.2v4H21a1.7 1.7 0 0 0-1.6 1Z"
      />
    </template>
    <template v-else-if="name === 'arrow-left'">
      <path d="m15 18-6-6 6-6" />
      <path d="M9 12h11" />
    </template>
    <template v-else-if="name === 'arrow-right'">
      <path d="m9 18 6-6-6-6" />
      <path d="M4 12h11" />
    </template>
    <template v-else-if="name === 'menu'"><path d="M4 7h16M4 12h16M4 17h16" /></template>
    <template v-else-if="name === 'close'"><path d="m6 6 12 12M18 6 6 18" /></template>
    <template v-else-if="name === 'sun'">
      <circle cx="12" cy="12" r="4" />
      <path
        d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"
      />
    </template>
    <template v-else-if="name === 'moon'">
      <path d="M20 15.5A8.5 8.5 0 0 1 8.5 4 8.5 8.5 0 1 0 20 15.5Z" />
    </template>
    <template v-else-if="name === 'camera'">
      <path
        d="M4 8h3l1.5-2h7L17 8h3a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V9a1 1 0 0 1 1-1Z"
      />
      <circle cx="12" cy="13" r="3.2" />
    </template>
    <template v-else-if="name === 'pencil'">
      <path d="M4 20h4L19.5 8.5a2.1 2.1 0 0 0-3-3L5 17v3Z" />
      <path d="m13.5 6.5 3 3" />
    </template>
    <template v-else-if="name === 'shield'">
      <path d="M12 3 5 5.5v5c0 4.6 3 8 7 9.5 4-1.5 7-4.9 7-9.5v-5L12 3Z" />
      <path d="m9 11.5 2 2 4-4.5" />
    </template>
    <template v-else-if="name === 'calculator'">
      <rect x="4" y="2.5" width="16" height="19" rx="2" />
      <path d="M7.5 6.5h9v3h-9zM8 13h.01M12 13h.01M16 13h.01M8 17h.01M12 17h.01M16 17h.01" />
    </template>
    <template v-else-if="name === 'keyboard'">
      <rect x="2.5" y="6" width="19" height="12" rx="2" />
      <path d="M6 10h.01M9 10h.01M12 10h.01M15 10h.01M18 10h.01M6 14h.01M9 14h6M18 14h.01" />
    </template>
    <template v-else-if="name === 'timer'">
      <circle cx="12" cy="13" r="8" />
      <path d="M9 2h6M12 5V2M17.7 7.3l1.5-1.5M12 13l3-2" />
    </template>
    <template v-else-if="name === 'play'">
      <path d="m8 5 11 7-11 7V5Z" />
    </template>
    <template v-else-if="name === 'trophy'">
      <path
        d="M8 4h8v5a4 4 0 0 1-8 0V4ZM10 17h4M12 13v4M8 7H4v1a4 4 0 0 0 4 4M16 7h4v1a4 4 0 0 1-4 4M7 21h10"
      />
    </template>
    <template v-else-if="name === 'refresh'">
      <path d="M20 7v5h-5M4 17v-5h5" />
      <path d="M18.2 9A7 7 0 0 0 6.5 6.5L4 9M5.8 15A7 7 0 0 0 17.5 17.5L20 15" />
    </template>
    <template v-else-if="name === 'undo'">
      <path d="m9 7-5 5 5 5M4 12h9a6 6 0 0 1 6 6" />
    </template>
    <template v-else-if="name === 'delete'">
      <path d="M4 7h16M9 7V4h6v3M7 7l1 14h8l1-14M10 11v6M14 11v6" />
    </template>
    <template v-else-if="name === 'lightbulb'">
      <path
        d="M9 18h6M10 22h4M8.5 15.5A7 7 0 1 1 15.5 15.5C14.5 16.3 14 17 14 18h-4c0-1-.5-1.7-1.5-2.5Z"
      />
    </template>
    <template v-else-if="name === 'info'">
      <circle cx="12" cy="12" r="9" />
      <path d="M12 10v6M12 7h.01" />
    </template>
    <template v-else>
      <circle cx="12" cy="12" r="9" />
      <path d="M8 12h8" />
    </template>
  </svg>
</template>

<style scoped>
.app-icon {
  display: block;
  flex: 0 0 auto;
  stroke: currentColor;
  stroke-width: 1.8;
  stroke-linecap: round;
  stroke-linejoin: round;
}
</style>
