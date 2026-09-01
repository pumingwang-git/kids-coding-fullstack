<script setup>
import { ref } from "vue";
import { Smile } from "lucide-vue-next";

defineEmits(["select"]);
const open = ref(false);
const emojis = [
  "😀",
  "😊",
  "😂",
  "😍",
  "🤔",
  "😮",
  "😢",
  "😡",
  "👍",
  "👎",
  "👏",
  "🙏",
  "💪",
  "🎉",
  "❤️",
  "⭐",
  "🔥",
  "💡",
  "✅",
  "❓",
  "🐍",
  "💻",
  "🚀",
  "📚",
];
</script>

<template>
  <div class="help-emoji-picker">
    <button
      type="button"
      class="help-emoji-trigger"
      aria-label="选择表情"
      title="选择表情"
      @click="open = !open"
    >
      <Smile />
    </button>
    <div v-if="open" class="help-emoji-grid" role="dialog" aria-label="选择表情">
      <button
        v-for="emoji in emojis"
        :key="emoji"
        type="button"
        :aria-label="`插入表情 ${emoji}`"
        @click="
          $emit('select', emoji);
          open = false;
        "
      >
        {{ emoji }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.help-emoji-picker {
  position: relative;
}
.help-emoji-trigger {
  display: grid;
  width: 34px;
  height: 34px;
  place-items: center;
  border: 0;
  border-radius: 50%;
  background: transparent;
  color: var(--muted-foreground);
  cursor: pointer;
}
.help-emoji-trigger:hover {
  background: var(--muted-surface);
  color: var(--primary);
}
.help-emoji-trigger svg {
  width: 19px;
  height: 19px;
}
.help-emoji-grid {
  position: absolute;
  z-index: 2;
  right: 0;
  bottom: calc(100% + 8px);
  display: grid;
  grid-template-columns: repeat(6, 34px);
  gap: 2px;
  width: max-content;
  max-width: min(228px, calc(100vw - 40px));
  padding: 8px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--popover);
  box-shadow: var(--card-shadow);
}
.help-emoji-grid button {
  width: 34px;
  height: 34px;
  padding: 0;
  border: 0;
  border-radius: var(--radius-sm);
  background: transparent;
  cursor: pointer;
  font-size: 19px;
}
.help-emoji-grid button:hover {
  background: var(--muted-surface);
}
@media (max-width: 420px) {
  .help-emoji-grid {
    grid-template-columns: repeat(5, 34px);
  }
}
</style>
