<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { autoUpdate, flip, offset, shift, useFloating } from "@floating-ui/vue";
import {
  AlertCircle,
  GraduationCap,
  ImagePlus,
  MessageCircleQuestion,
  RefreshCw,
  Send,
  X,
} from "lucide-vue-next";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import {
  createHelpRequest,
  getHelpChatLine,
  idempotencyKey,
  itemsOf,
  listHelpChatLines,
  messagesOf,
  recallHelpMessage,
  subscribeToHelpChatEvents,
  uploadHelpAttachment,
} from "@/services/help";
import HelpEmojiPicker from "./HelpEmojiPicker.vue";
import HelpMessageScroller from "./HelpMessageScroller.vue";

const props = defineProps({
  context: { type: Object, default: () => ({ context_type: "general" }) },
  initialLineId: { type: [String, Number], default: null },
});

const route = useRoute();
const router = useRouter();

const open = ref(false);
const loading = ref(false);
const sending = ref(false);
const loadError = ref("");
const sendError = ref("");
const lines = ref([]);
const availableClasses = ref([]);
const selectedClassId = ref(null);
const selectedLineId = ref(null);
const detail = ref(null);
const message = ref("");
const attachment = ref(null);
const attachmentError = ref("");
const previewAttachment = ref(null);
const loadingEarlier = ref(false);
const teacherTyping = ref(false);
const textarea = ref(null);
const trigger = ref(null);
const chatWindow = ref(null);
let failedAttempt = null;
let unsubscribeEvents = null;
let realtimeRefreshTimer = null;
let pendingRealtimeLineId = null;
let typingStopTimer = null;
let teacherTypingTimer = null;

const { floatingStyles } = useFloating(trigger, chatWindow, {
  open,
  placement: "top-end",
  strategy: "fixed",
  middleware: [
    offset(12),
    flip({ padding: 10 }),
    shift({ mainAxis: true, crossAxis: true, padding: 10 }),
  ],
  whileElementsMounted: autoUpdate,
});

const selectedLine = computed(
  () => lines.value.find((item) => String(item.id) === String(selectedLineId.value)) || null,
);
const activeClass = computed(
  () =>
    availableClasses.value.find(
      (item) => String(item.class_id) === String(selectedClassId.value),
    ) || null,
);
const classChoices = computed(() => {
  const choices = new Map();
  for (const line of lines.value) {
    choices.set(String(line.class_id), {
      class_id: line.class_id,
      class_name: line.class_name || `班级 ${line.class_id}`,
      line_id: line.id,
      active: false,
    });
  }
  for (const item of availableClasses.value) {
    const previous = choices.get(String(item.class_id));
    choices.set(String(item.class_id), {
      ...previous,
      ...item,
      line_id: previous?.line_id ?? null,
      active: true,
    });
  }
  return [...choices.values()];
});
const messages = computed(() => messagesOf(detail.value));
const hasMore = computed(() => !!detail.value?.has_more);
const canSend = computed(() => !!activeClass.value && !!message.value.trim() && !sending.value);
const canCompose = computed(() => !!activeClass.value);
const unreadCount = computed(() =>
  lines.value.reduce((total, line) => total + Number(line.unread_count || 0), 0),
);

function classLabel(item) {
  return item.course_title ? `${item.class_name} · ${item.course_title}` : item.class_name;
}

async function focusComposer() {
  await nextTick();
  textarea.value?.$el?.focus?.();
  textarea.value?.focus?.();
}

async function loadDetail(lineId, options) {
  detail.value = options ? await getHelpChatLine(lineId, options) : await getHelpChatLine(lineId);
}

function mergeEarlier(page) {
  const existing = messagesOf(detail.value);
  const incoming = messagesOf(page);
  const known = new Set(existing.map((item) => String(item.id)));
  detail.value = {
    ...detail.value,
    ...page,
    messages: [...incoming.filter((item) => !known.has(String(item.id))), ...existing],
    items: [...incoming.filter((item) => !known.has(String(item.id))), ...existing],
  };
}

async function loadEarlier() {
  if (!selectedLineId.value || !detail.value?.has_more || loadingEarlier.value) return;
  loadingEarlier.value = true;
  try {
    const page = await getHelpChatLine(selectedLineId.value, {
      beforeId: detail.value.next_cursor,
    });
    mergeEarlier(page);
  } finally {
    loadingEarlier.value = false;
  }
}

async function load() {
  loading.value = true;
  loadError.value = "";
  try {
    const payload = await listHelpChatLines();
    lines.value = itemsOf(payload);
    availableClasses.value = Array.isArray(payload?.available_classes)
      ? payload.available_classes
      : [];
    const activeIds = new Set(availableClasses.value.map((item) => String(item.class_id)));
    const firstActiveLine = lines.value.find((item) => activeIds.has(String(item.class_id)));
    if (availableClasses.value.length === 1) {
      selectedClassId.value = availableClasses.value[0].class_id;
    } else if (availableClasses.value.length > 1) {
      const selectedIsActive = activeIds.has(String(selectedClassId.value));
      selectedClassId.value = selectedIsActive
        ? selectedClassId.value
        : (firstActiveLine?.class_id ?? null);
    } else if (
      !classChoices.value.some((item) => String(item.class_id) === String(selectedClassId.value))
    ) {
      selectedClassId.value = lines.value[0]?.class_id ?? null;
    }
    selectedLineId.value =
      props.initialLineId != null &&
      lines.value.some((item) => String(item.id) === String(props.initialLineId))
        ? props.initialLineId
        : (lines.value.find((item) => String(item.class_id) === String(selectedClassId.value))
            ?.id ?? null);
    detail.value = selectedLineId.value ? await getHelpChatLine(selectedLineId.value) : null;
    if (props.initialLineId != null && selectedLineId.value) open.value = true;
  } catch (error) {
    loadError.value = error?.message || "暂时无法加载答疑记录，请稍后再试。";
  } finally {
    loading.value = false;
  }
}

async function refreshFromRealtimeEvent(event) {
  if (loading.value) {
    realtimeRefreshTimer = window.setTimeout(() => {
      realtimeRefreshTimer = null;
      refreshFromRealtimeEvent(event);
    }, 150);
    return;
  }
  try {
    const payload = await listHelpChatLines();
    lines.value = itemsOf(payload);
    availableClasses.value = Array.isArray(payload?.available_classes)
      ? payload.available_classes
      : [];
    if (open.value && String(selectedLineId.value) === String(event.chat_line_id)) {
      await loadDetail(event.chat_line_id);
    }
  } catch {
    // 实时通道只是刷新提示；网络短暂异常不应打断学员正在输入的消息。
  }
}

function scheduleRealtimeRefresh(event) {
  if (
    event.event === "admin_typing" &&
    String(event.chat_line_id) === String(selectedLineId.value)
  ) {
    teacherTyping.value = true;
    window.clearTimeout(teacherTypingTimer);
    teacherTypingTimer = window.setTimeout(() => (teacherTyping.value = false), 2500);
    return;
  }
  if (
    event.event === "admin_stopped_typing" &&
    String(event.chat_line_id) === String(selectedLineId.value)
  ) {
    teacherTyping.value = false;
    return;
  }
  if (event.event?.includes("typing")) return;
  pendingRealtimeLineId = event.chat_line_id;
  if (realtimeRefreshTimer != null) return;
  realtimeRefreshTimer = window.setTimeout(async () => {
    realtimeRefreshTimer = null;
    const lineId = pendingRealtimeLineId;
    pendingRealtimeLineId = null;
    if (lineId != null) await refreshFromRealtimeEvent({ chat_line_id: lineId });
  }, 80);
}

function publishTyping(isTyping) {
  if (selectedLineId.value == null) return;
  unsubscribeEvents?.send?.({
    type: "typing",
    chat_line_id: Number(selectedLineId.value),
    is_typing: isTyping,
  });
}

function onMessageInput() {
  publishTyping(true);
  window.clearTimeout(typingStopTimer);
  typingStopTimer = window.setTimeout(() => publishTyping(false), 900);
}

function insertEmoji(emoji) {
  message.value += emoji;
  focusComposer();
}

function chooseAttachment(event) {
  const file = event.target.files?.[0];
  event.target.value = "";
  attachmentError.value = "";
  if (!file) return;
  if (!file.type.startsWith("image/")) {
    attachmentError.value = "只能选择图片文件。";
    return;
  }
  if (file.size > 10 * 1024 * 1024) {
    attachmentError.value = "图片不能超过 10 MB。";
    return;
  }
  attachment.value?.previewUrl && URL.revokeObjectURL(attachment.value.previewUrl);
  attachment.value = {
    file,
    key: idempotencyKey(),
    progress: 0,
    previewUrl: URL.createObjectURL(file),
    status: "ready",
  };
}

function addOptimisticMessage(text, requestKey) {
  const local = {
    id: `local-${requestKey}`,
    body: text,
    sender_type: "student",
    created_at: new Date().toISOString(),
    status: "sending",
    requestKey,
    attachments: attachment.value
      ? [
          {
            id: `local-file-${requestKey}`,
            original_name: attachment.value.file.name,
            url: attachment.value.previewUrl,
          },
        ]
      : [],
  };
  const current = messagesOf(detail.value);
  detail.value = {
    ...(detail.value || {}),
    messages: [...current, local],
    items: [...current, local],
  };
  return local;
}

function replaceOptimisticMessage(local, created) {
  const confirmed =
    created?.messages?.find((item) => item.body === local.body && item.sender_type === "student") ||
    created?.messages?.at(-1);
  if (!confirmed) return;
  const current = messagesOf(detail.value);
  const next = current.map((item) =>
    item.id === local.id ? { ...confirmed, attachments: local.attachments } : item,
  );
  detail.value = { ...detail.value, messages: next, items: next };
}

async function retryMessage(local) {
  if (!local?.requestKey || local.status !== "failed") return;
  message.value = local.body;
  await send(local);
}

async function recall(messageToRecall) {
  try {
    const recalled = await recallHelpMessage(messageToRecall.id);
    const current = messagesOf(detail.value);
    const next = current.map((item) =>
      item.id === messageToRecall.id ? { ...item, ...recalled, recalled: true } : item,
    );
    detail.value = { ...detail.value, messages: next, items: next };
  } catch (error) {
    sendError.value = error?.message || "这条消息暂时无法撤回。";
  }
}

async function send(retrying = null) {
  const text = message.value.trim();
  if (!text || !activeClass.value || sending.value) return;

  const sameFailedBody = failedAttempt?.body === text;
  const requestKey =
    retrying?.requestKey || (sameFailedBody ? failedAttempt.key : idempotencyKey());
  const local = retrying || addOptimisticMessage(text, requestKey);
  sending.value = true;
  sendError.value = "";
  try {
    const created = await createHelpRequest(
      {
        class_id: activeClass.value.class_id,
        body: text,
        ...props.context,
      },
      { requestKey },
    );
    replaceOptimisticMessage(local, created);
    failedAttempt = null;
    message.value = "";
    publishTyping(false);
    const lineId = created.chat_line_id || selectedLineId.value;
    if (!lines.value.some((item) => String(item.id) === String(lineId))) {
      lines.value = [
        {
          id: lineId,
          class_id: activeClass.value.class_id,
          class_name: activeClass.value.class_name,
        },
        ...lines.value,
      ];
    }
    selectedLineId.value = lineId;
    if (attachment.value && created.id != null) {
      attachment.value.status = "uploading";
      const uploaded = await uploadHelpAttachment(created.id, attachment.value.file, {
        requestKey: attachment.value.key,
        onProgress: (progress) => (attachment.value.progress = progress),
      });
      const current = messagesOf(detail.value);
      const next = current.map((item) =>
        item.id === local.id || item.id === created?.messages?.at(-1)?.id
          ? {
              ...item,
              attachments: [{ ...uploaded, url: uploaded.url || attachment.value.previewUrl }],
            }
          : item,
      );
      detail.value = { ...detail.value, messages: next, items: next };
      attachment.value.status = "uploaded";
    }
    attachment.value = null;
    await loadDetail(lineId);
    await focusComposer();
  } catch (error) {
    const current = messagesOf(detail.value);
    const next = current.map((item) =>
      item.id === local.id ? { ...item, status: "failed" } : item,
    );
    detail.value = { ...detail.value, messages: next, items: next };
    failedAttempt = { body: text, key: requestKey };
    sendError.value = error?.message || "消息没有发出去，请重试。";
  } finally {
    sending.value = false;
  }
}

function onComposerKeydown(event) {
  if (event.key !== "Enter" || event.shiftKey || event.isComposing) return;
  event.preventDefault();
  send();
}

function close() {
  open.value = false;
  if (route.name === "notifications" && props.initialLineId != null) {
    router.back();
    return;
  }
  nextTick(() => (trigger.value?.$el || trigger.value)?.focus?.());
}

function onDocumentPointerDown(event) {
  if (!open.value) return;
  const target = event.target;
  const triggerElement = trigger.value?.$el || trigger.value;
  if (chatWindow.value?.contains(target) || triggerElement?.contains(target)) return;
  close();
}

function onDocumentKeydown(event) {
  if (event.key === "Escape") close();
}

onMounted(() => {
  document.addEventListener("pointerdown", onDocumentPointerDown);
  document.addEventListener("keydown", onDocumentKeydown);
  unsubscribeEvents = subscribeToHelpChatEvents(scheduleRealtimeRefresh);
  // 入口红点必须在用户点击前就可见；这里只读取会话摘要，不打开聊天窗口。
  load();
});

onBeforeUnmount(() => {
  document.removeEventListener("pointerdown", onDocumentPointerDown);
  document.removeEventListener("keydown", onDocumentKeydown);
  window.clearTimeout(realtimeRefreshTimer);
  window.clearTimeout(typingStopTimer);
  window.clearTimeout(teacherTypingTimer);
  unsubscribeEvents?.();
});

watch(open, (isOpen) => {
  if (isOpen) load().then(focusComposer);
});

watch(
  () => props.initialLineId,
  (lineId) => {
    if (lineId != null) open.value = true;
  },
);

watch(selectedClassId, async (classId, previous) => {
  if (classId === previous || loading.value) return;
  const lineId = lines.value.find((item) => String(item.class_id) === String(classId))?.id ?? null;
  selectedLineId.value = lineId;
  detail.value = null;
  sendError.value = "";
  if (!lineId) {
    focusComposer();
    return;
  }
  loading.value = true;
  loadError.value = "";
  try {
    await loadDetail(lineId);
  } catch (error) {
    loadError.value = error?.message || "暂时无法加载这段聊天。";
  } finally {
    loading.value = false;
  }
});
</script>

<template>
  <Button ref="trigger" class="help-widget-trigger" type="button" size="lg" @click="open = true">
    <MessageCircleQuestion data-icon="inline-start" />
    问老师
    <span v-if="unreadCount" class="help-unread-dot" :aria-label="`有 ${unreadCount} 条未读回复`">{{
      unreadCount > 9 ? "9+" : unreadCount
    }}</span>
  </Button>

  <Teleport to="body">
    <aside
      v-if="open"
      ref="chatWindow"
      class="help-window"
      :style="floatingStyles"
      role="dialog"
      aria-modal="false"
      aria-labelledby="help-chat-title"
      aria-describedby="help-chat-description"
    >
      <header class="help-window-header">
        <div class="help-agent">
          <div class="help-agent-avatar" aria-hidden="true">
            <GraduationCap />
          </div>
          <div>
            <h2 id="help-chat-title">联系老师</h2>
            <p id="help-chat-description">直接说哪里卡住了，老师看到后会在这里回复。</p>
          </div>
        </div>
        <Button
          class="help-close-button"
          type="button"
          variant="ghost"
          size="icon-sm"
          aria-label="关闭聊天窗口"
          title="关闭聊天窗口"
          @click="close"
        >
          <X />
        </Button>
      </header>

      <div class="help-presence" role="status">
        <span class="help-presence-dot" aria-hidden="true"></span>
        <span>把学习问题留在这里，老师看到后会回复。</span>
      </div>
      <div v-if="teacherTyping" class="help-typing" role="status">老师正在输入…</div>

      <Field v-if="classChoices.length > 1 && !loading" class="help-class-picker">
        <FieldLabel for="help-class">联系班级</FieldLabel>
        <Select v-model="selectedClassId">
          <SelectTrigger id="help-class" class="w-full">
            <SelectValue placeholder="选择要联系的班级" />
          </SelectTrigger>
          <SelectContent>
            <SelectGroup>
              <SelectItem v-for="item in classChoices" :key="item.class_id" :value="item.class_id">
                {{ classLabel(item) }}{{ item.active ? "" : "（仅历史）" }}
              </SelectItem>
            </SelectGroup>
          </SelectContent>
        </Select>
      </Field>

      <div v-if="loading" class="help-loading" aria-label="正在加载聊天">
        <Skeleton class="h-16 w-3/4" />
        <Skeleton class="ml-auto h-20 w-4/5" />
        <Skeleton class="h-12 w-2/3" />
      </div>

      <Alert v-else-if="loadError" variant="destructive" class="help-alert">
        <AlertCircle />
        <AlertTitle>聊天没有加载成功</AlertTitle>
        <AlertDescription>{{ loadError }}</AlertDescription>
        <Button type="button" size="sm" variant="outline" @click="load">
          <RefreshCw data-icon="inline-start" />
          重新加载
        </Button>
      </Alert>

      <div v-else-if="!selectedClassId && availableClasses.length > 1" class="help-empty">
        <MessageCircleQuestion aria-hidden="true" />
        <h3>先选择班级</h3>
        <p>老师会在所选班级的聊天中收到消息。</p>
      </div>

      <div v-else-if="!selectedLine && !canCompose" class="help-empty">
        <MessageCircleQuestion aria-hidden="true" />
        <h3>还没有可用的班级答疑</h3>
        <p>加入班级后，就能在这里直接给带课老师留言。</p>
        <Button type="button" size="sm" variant="outline" @click="load">
          <RefreshCw data-icon="inline-start" />
          再检查一次
        </Button>
      </div>

      <template v-else-if="selectedLine || canCompose">
        <div v-if="messages.length === 0" class="help-empty help-empty-compact">
          <MessageCircleQuestion aria-hidden="true" />
          <h3>可以直接开口</h3>
          <p>把刚才卡住的地方告诉老师吧。</p>
        </div>
        <HelpMessageScroller
          v-else
          :messages="messages"
          :has-more="hasMore"
          :loading-earlier="loadingEarlier"
          :load-earlier="loadEarlier"
          @recall="recall"
          @retry="retryMessage"
          @preview="previewAttachment = $event"
        />

        <form v-if="canCompose" class="help-composer" @submit.prevent="send">
          <FieldGroup>
            <Field :data-invalid="!!sendError">
              <FieldLabel for="help-message" class="sr-only">发给老师的消息</FieldLabel>
              <Textarea
                id="help-message"
                ref="textarea"
                v-model="message"
                class="help-composer-input"
                rows="2"
                maxlength="10000"
                placeholder="告诉老师你卡在哪里……"
                :aria-invalid="!!sendError"
                :disabled="sending"
                @input="onMessageInput"
                @keydown="onComposerKeydown"
              />
            </Field>
          </FieldGroup>
          <div v-if="attachment" class="help-attachment-queue">
            <img :src="attachment.previewUrl" alt="待发送的图片预览" />
            <div>
              <strong>{{ attachment.file.name }}</strong
              ><span v-if="attachment.status === 'uploading'"
                >上传中 {{ attachment.progress }}%</span
              ><span v-else>准备发送</span>
            </div>
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              aria-label="移除图片"
              title="移除图片"
              @click="
                URL.revokeObjectURL(attachment.previewUrl);
                attachment = null;
              "
              ><X
            /></Button>
          </div>
          <div class="help-composer-actions">
            <p v-if="sendError || attachmentError" role="alert">
              {{ sendError || attachmentError }}
            </p>
            <span v-else>Enter 发送，Shift + Enter 换行</span>
            <div class="help-composer-tools">
              <HelpEmojiPicker @select="insertEmoji" />
              <label class="help-file-button" aria-label="添加图片" title="添加图片"
                ><ImagePlus /><input type="file" accept="image/*" @change="chooseAttachment"
              /></label>
            </div>
            <Button
              class="help-send-button"
              type="submit"
              size="icon"
              :disabled="!canSend"
              :aria-label="sending ? '正在发送消息' : sendError ? '重试发送消息' : '发送消息'"
              :title="sending ? '正在发送消息' : sendError ? '重试发送消息' : '发送消息'"
            >
              <RefreshCw v-if="sending" class="animate-spin" />
              <Send v-else />
              <span class="sr-only">{{ sending ? "发送中" : sendError ? "重试" : "发送" }}</span>
            </Button>
          </div>
        </form>
        <div v-else class="help-history-note">这个班级已结束，聊天记录仍可查看。</div>
      </template>
    </aside>
  </Teleport>
  <Teleport to="body">
    <div
      v-if="previewAttachment"
      class="help-image-preview"
      role="dialog"
      aria-modal="true"
      aria-label="图片预览"
      @click.self="previewAttachment = null"
    >
      <button
        type="button"
        aria-label="关闭图片预览"
        title="关闭图片预览"
        @click="previewAttachment = null"
      >
        <X />
      </button>
      <img
        :src="previewAttachment.url || previewAttachment.thumbnail_url"
        :alt="previewAttachment.original_name || '图片附件'"
      />
    </div>
  </Teleport>
</template>

<style scoped>
.help-widget-trigger {
  position: fixed;
  right: max(20px, env(safe-area-inset-right));
  bottom: max(20px, env(safe-area-inset-bottom));
  border-radius: 999px;
  box-shadow: var(--card-shadow);
}
.help-window {
  z-index: 60;
  width: min(420px, calc(100vw - 40px));
  height: min(700px, calc(100dvh - 40px));
  display: flex;
  flex-direction: column;
  gap: 0;
  padding: 0;
  overflow: hidden;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--background);
  box-shadow: var(--card-shadow);
}
.help-unread-dot {
  min-width: 18px;
  height: 18px;
  padding: 0 4px;
  border-radius: 9px;
  background: var(--destructive);
  color: var(--primary-foreground);
  font-size: 11px;
  line-height: 18px;
}
.help-typing {
  padding: 7px 20px;
  color: var(--muted-foreground);
  font-size: 12px;
}
.help-window-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding: 18px 16px 16px 20px;
  border-bottom: 1px solid var(--border);
  background: color-mix(in srgb, var(--mint) 45%, var(--background));
}
.help-agent {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}
.help-agent-avatar {
  display: grid;
  width: 40px;
  height: 40px;
  flex: 0 0 40px;
  place-items: center;
  border-radius: 50%;
  background: var(--primary);
  color: var(--primary-foreground);
}
.help-agent-avatar svg {
  width: 21px;
  height: 21px;
}
.help-agent h2 {
  margin: 0;
  font-family: var(--font-body);
  font-size: 16px;
  font-weight: 800;
  line-height: 1.35;
}
.help-agent p {
  margin: 2px 0 0;
  color: var(--muted-foreground);
  font-size: 12px;
  line-height: 1.55;
}
.help-close-button {
  flex: 0 0 auto;
  border-radius: 50%;
}
.help-presence {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 12px 16px 0;
  padding: 9px 12px;
  border: 1px solid color-mix(in srgb, var(--primary) 25%, var(--border));
  border-radius: 8px;
  background: color-mix(in srgb, var(--primary) 6%, var(--background));
  color: var(--muted-foreground);
  font-size: 12px;
  line-height: 1.45;
}
.help-presence-dot {
  width: 8px;
  height: 8px;
  flex: 0 0 8px;
  border-radius: 50%;
  background: var(--primary);
}
.help-class-picker {
  padding: 12px 16px 0;
  border-bottom: 1px solid var(--border);
}
.help-class-picker :deep([data-slot="field-label"]) {
  font-size: 12px;
}
.help-loading {
  padding: 18px 20px;
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 14px;
}
.help-alert {
  margin: 18px;
}
.help-alert button {
  margin-top: 10px;
}
.help-empty {
  min-height: 0;
  padding: 28px 22px;
  display: flex;
  flex: 1;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: var(--muted-foreground);
  text-align: center;
}
.help-empty > svg {
  width: 32px;
  height: 32px;
  color: var(--primary);
}
.help-empty h3,
.help-empty p {
  margin: 0;
}
.help-empty h3 {
  color: var(--foreground);
  font-size: 16px;
}
.help-empty p {
  line-height: 1.65;
}
.help-empty-compact {
  padding-block: 20px;
}
.help-composer {
  padding: 12px 16px 14px;
  border-top: 1px solid var(--border);
  background: var(--background);
}
.help-composer-input {
  min-height: 76px;
  resize: none;
  border-radius: 12px 6px 12px 6px;
  padding: 12px 52px 12px 13px;
  background: color-mix(in srgb, var(--paper) 86%, var(--mint));
  line-height: 1.55;
}
.help-composer-actions {
  position: relative;
  min-height: 20px;
  margin-top: 6px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.help-composer-actions p,
.help-composer-actions span {
  margin: 0;
  color: var(--muted-foreground);
  font-size: 12px;
}
.help-send-button {
  position: absolute;
  right: 8px;
  bottom: 32px;
  border-radius: 50%;
}
.help-composer-actions p {
  color: var(--destructive);
}
.help-composer-tools {
  display: flex;
  align-items: center;
  gap: 2px;
  margin-left: auto;
  margin-right: 42px;
}
.help-file-button {
  display: grid;
  width: 34px;
  height: 34px;
  place-items: center;
  border-radius: 50%;
  color: var(--muted-foreground);
  cursor: pointer;
}
.help-file-button:hover {
  background: var(--muted-surface);
  color: var(--primary);
}
.help-file-button svg {
  width: 19px;
  height: 19px;
}
.help-file-button input {
  position: absolute;
  width: 1px;
  height: 1px;
  opacity: 0;
  pointer-events: none;
}
.help-attachment-queue {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
  padding: 7px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--muted-surface);
  font-size: 12px;
}
.help-attachment-queue img {
  width: 42px;
  height: 42px;
  object-fit: cover;
  border-radius: var(--radius-sm);
}
.help-attachment-queue div {
  display: grid;
  min-width: 0;
  flex: 1;
  gap: 2px;
}
.help-attachment-queue strong {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 600;
}
.help-attachment-queue span {
  color: var(--muted-foreground);
}
.help-image-preview {
  position: fixed;
  z-index: 80;
  inset: 0;
  display: grid;
  place-items: center;
  padding: 24px;
  background: color-mix(in srgb, var(--foreground) 72%, transparent);
}
.help-image-preview img {
  max-width: min(900px, 100%);
  max-height: calc(100dvh - 48px);
  object-fit: contain;
}
.help-image-preview button {
  position: absolute;
  top: 14px;
  right: 14px;
  display: grid;
  width: 38px;
  height: 38px;
  place-items: center;
  border: 1px solid var(--border);
  border-radius: 50%;
  background: var(--background);
  color: var(--foreground);
  cursor: pointer;
}
.help-history-note {
  padding: 14px 16px max(16px, env(safe-area-inset-bottom));
  border-top: 1px solid var(--border);
  color: var(--muted-foreground);
  font-size: 13px;
  text-align: center;
}
@media (max-width: 800px) {
  .help-widget-trigger {
    bottom: calc(88px + env(safe-area-inset-bottom));
  }
  .help-window {
    width: calc(100vw - 20px);
    height: min(680px, calc(100dvh - 20px));
    border-radius: 12px;
  }
}
@media (prefers-reduced-motion: reduce) {
  .help-widget-trigger,
  .help-window * {
    scroll-behavior: auto;
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
  }
}
</style>
