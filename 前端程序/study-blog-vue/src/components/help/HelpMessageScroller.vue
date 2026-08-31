<script setup>
import { nextTick, ref, watch } from "vue";
import { ScrollArea } from "@/components/ui/scroll-area";
import HelpMessageBubble from "./HelpMessageBubble.vue";

const props = defineProps({
  messages: { type: Array, default: () => [] },
});

const end = ref(null);

watch(
  () => props.messages.length,
  async () => {
    await nextTick();
    if (typeof end.value?.scrollIntoView === "function") {
      end.value.scrollIntoView({ block: "end" });
    }
  },
  { immediate: true },
);
</script>

<template>
  <ScrollArea class="help-message-scroller" aria-label="与老师的聊天记录">
    <div class="help-message-list" aria-live="polite">
      <HelpMessageBubble v-for="message in messages" :key="message.id" :message="message" />
      <span ref="end" aria-hidden="true"></span>
    </div>
  </ScrollArea>
</template>

<style scoped>
.help-message-scroller {
  min-height: 0;
  flex: 1;
}
.help-message-list {
  min-height: 100%;
  padding: 18px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
</style>
