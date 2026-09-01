<script setup>
import { computed } from "vue";
import { cn } from "@/lib/utils";

const props = defineProps({
  message: { type: Object, required: true },
});
const emit = defineEmits(["recall", "preview", "retry"]);

const fromStudent = computed(
  () => props.message.sender_type === "student" || props.message.sender_user_id != null,
);

const timeLabel = computed(() => {
  if (!props.message.created_at) return "";
  const value = new Date(props.message.created_at);
  if (Number.isNaN(value.getTime())) return "";
  return new Intl.DateTimeFormat("zh-CN", { hour: "2-digit", minute: "2-digit" }).format(value);
});
const recalled = computed(() => !!props.message.recalled);
const canRecall = computed(() => {
  if (!fromStudent.value || recalled.value || props.message.status === "sending") return false;
  if (props.message.can_recall === false) return false;
  const created = new Date(props.message.created_at).getTime();
  return Number.isFinite(created) && Date.now() - created < 2 * 60 * 1000;
});
</script>

<template>
  <article
    :class="cn('help-message', fromStudent ? 'help-message-student' : 'help-message-teacher')"
    :aria-label="fromStudent ? '我发送的消息' : '老师发送的消息'"
  >
    <p v-if="recalled" class="help-recalled">
      {{ fromStudent ? "你撤回了一条消息" : "对方撤回了一条消息" }}
    </p>
    <template v-else>
      <p>{{ message.body }}</p>
      <div v-if="message.attachments?.length" class="help-attachments">
        <button
          v-for="attachment in message.attachments"
          :key="attachment.id || attachment.url"
          type="button"
          :aria-label="`查看图片 ${attachment.original_name || ''}`"
          @click="emit('preview', attachment)"
        >
          <img
            :src="attachment.thumbnail_url || attachment.url"
            :alt="attachment.original_name || '图片附件'"
          />
        </button>
      </div>
    </template>
    <time v-if="timeLabel" :datetime="message.created_at">{{ timeLabel }}</time>
    <small v-if="message.status === 'sending'">发送中</small>
    <small v-else-if="message.status === 'failed'"
      >发送失败 <button type="button" @click="emit('retry', message)">重发</button></small
    >
    <button v-if="canRecall" class="help-recall" type="button" @click="emit('recall', message)">
      撤回
    </button>
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
.help-message small {
  display: block;
  margin-top: 3px;
  color: var(--muted-foreground);
  font-size: 11px;
  text-align: right;
}
.help-message-student {
  align-self: flex-end;
  border-color: color-mix(in srgb, var(--primary) 22%, var(--border));
  background: color-mix(in srgb, var(--primary) 14%, var(--background));
}
.help-message-teacher {
  align-self: flex-start;
  background: color-mix(in srgb, var(--card) 86%, var(--background));
}
.help-recalled {
  color: var(--muted-foreground);
  font-style: italic;
}
.help-attachments {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}
.help-attachments button {
  width: 96px;
  height: 72px;
  padding: 0;
  overflow: hidden;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--muted-surface);
  cursor: zoom-in;
}
.help-attachments img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.help-recall {
  display: block;
  margin-top: 4px;
  margin-left: auto;
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--muted-foreground);
  cursor: pointer;
  font: inherit;
  font-size: 11px;
}
.help-message small button {
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--primary);
  cursor: pointer;
  font: inherit;
}
</style>
