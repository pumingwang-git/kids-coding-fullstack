<script setup>
import { nextTick, onMounted, ref, watch } from "vue";
import HelpMessageBubble from "./HelpMessageBubble.vue";

const props = defineProps({
  messages: { type: Array, default: () => [] },
  hasMore: { type: Boolean, default: false },
  loadingEarlier: { type: Boolean, default: false },
  loadEarlier: { type: Function, default: null },
});

const viewport = ref(null);
let wasAtEnd = true;
let initialPositioned = false;

async function loadOlder() {
  if (!props.hasMore || props.loadingEarlier || !props.loadEarlier || !viewport.value) return;
  const previousHeight = viewport.value.scrollHeight;
  const previousTop = viewport.value.scrollTop;
  await props.loadEarlier();
  await nextTick();
  viewport.value.scrollTop = previousTop + viewport.value.scrollHeight - previousHeight;
}

function onScroll() {
  if (!viewport.value) return;
  wasAtEnd =
    viewport.value.scrollHeight - viewport.value.scrollTop - viewport.value.clientHeight < 24;
  if (viewport.value.scrollTop < 40) loadOlder();
}

watch(
  () => props.messages.length,
  async () => {
    await nextTick();
    if (viewport.value && (!initialPositioned || wasAtEnd)) {
      viewport.value.scrollTop = viewport.value.scrollHeight;
      initialPositioned = true;
    }
  },
  { immediate: true },
);

onMounted(async () => {
  await nextTick();
  if (viewport.value) viewport.value.scrollTop = viewport.value.scrollHeight;
  initialPositioned = true;
});
</script>

<template>
  <div
    ref="viewport"
    class="help-message-scroller"
    aria-label="与老师的聊天记录"
    @scroll="onScroll"
  >
    <div class="help-message-list" aria-live="polite">
      <button
        v-if="hasMore"
        class="help-load-earlier"
        type="button"
        :disabled="loadingEarlier"
        @click="loadOlder"
      >
        {{ loadingEarlier ? "正在加载…" : "加载更早消息" }}
      </button>
      <p v-else class="help-no-more">没有更多了</p>
      <HelpMessageBubble
        v-for="message in messages"
        :key="message.id"
        :message="message"
        @recall="$emit('recall', $event)"
        @retry="$emit('retry', $event)"
        @preview="$emit('preview', $event)"
      />
    </div>
  </div>
</template>

<style scoped>
.help-message-scroller {
  min-height: 0;
  flex: 1;
  overflow-y: auto;
  overscroll-behavior: contain;
}
.help-message-list {
  min-height: 100%;
  padding: 18px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.help-load-earlier {
  align-self: center;
  border: 0;
  background: transparent;
  color: var(--primary);
  cursor: pointer;
  font: inherit;
  font-size: 12px;
}
.help-load-earlier:disabled {
  cursor: wait;
  opacity: 0.65;
}
.help-no-more {
  align-self: center;
  margin: 0;
  color: var(--muted-foreground);
  font-size: 12px;
}
</style>
