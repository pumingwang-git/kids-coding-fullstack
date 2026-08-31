<script setup>
import { computed } from "vue";
import { cn } from "@/lib/utils";

const props = defineProps({
  message: { type: Object, required: true },
});

const fromStudent = computed(
  () => props.message.sender_type === "student" || props.message.sender_user_id != null,
);

const timeLabel = computed(() => {
  if (!props.message.created_at) return "";
  const value = new Date(props.message.created_at);
  if (Number.isNaN(value.getTime())) return "";
  return new Intl.DateTimeFormat("zh-CN", { hour: "2-digit", minute: "2-digit" }).format(value);
});
</script>

<template>
  <article
    :class="cn('help-message', fromStudent ? 'help-message-student' : 'help-message-teacher')"
    :aria-label="fromStudent ? '我发送的消息' : '老师发送的消息'"
  >
    <p>{{ message.body }}</p>
    <time v-if="timeLabel" :datetime="message.created_at">{{ timeLabel }}</time>
    <small v-if="fromStudent && message.read_by_assigned_teacher">老师已读</small>
    <small v-else-if="!fromStudent && message.read_by_student">已读</small>
  </article>
</template>

<style scoped>
.help-message {
  width: fit-content;
  max-width: min(84%, 30rem);
  padding: 10px 13px;
  border: 1px solid var(--border);
  border-radius: 14px 6px 14px 6px;
  overflow-wrap: anywhere;
}
.help-message p {
  margin: 0;
  white-space: pre-wrap;
  line-height: 1.65;
}
.help-message time {
  display: block;
  margin-top: 4px;
  color: var(--muted-foreground);
  font-size: 11px;
}
.help-message small { display: block; margin-top: 3px; color: var(--muted-foreground); font-size: 11px; text-align: right; }
.help-message-student {
  align-self: flex-end;
  border-color: color-mix(in srgb, var(--primary) 22%, var(--border));
  background: color-mix(in srgb, var(--primary) 14%, var(--background));
}
.help-message-teacher {
  align-self: flex-start;
  background: color-mix(in srgb, var(--card) 86%, white);
}
</style>
