<script setup>
import { computed, onMounted, ref } from "vue";
import { RouterLink, useRoute } from "vue-router";
import AppIcon from "../components/AppIcon.vue";
import { getProfile, updateProfile, uploadAvatar } from "../services/auth";
import { session } from "../stores/session";

const route = useRoute();
// 个人资料页是全局页（/profile），但「进入错题本 / 工具箱」要落在当前专区。
// App.vue 顶部头像跳转时带 ?area=xxx；直接访问 /profile 时回落 kids。
const areaKey = computed(() => String(route.query.area || route.meta.areaKey || "kids"));

const profile = ref({ user: {}, avatar_url: "", learning_signature: "", overview: {} });
const loading = ref(true);
const loadError = ref("");

// 进入个人主页时资料接口还在请求，优先复用已加载的会话头像，避免先闪过默认头像。
const avatarSrc = computed(
  () => profile.value.avatar_url || session.user?.avatar_url || "/assets/otter-avatar-128.webp",
);
const overview = computed(() => profile.value.overview || {});
const accuracy = computed(() =>
  overview.value.recent_review_accuracy == null ? "-" : `${overview.value.recent_review_accuracy}%`,
);

async function load() {
  loading.value = true;
  loadError.value = "";
  try {
    profile.value = await getProfile();
  } catch (reason) {
    loadError.value = reason.message || "个人资料暂时无法打开，请稍后重试。";
  } finally {
    loading.value = false;
  }
}

// ---------- 头像 ----------
const fileInput = ref(null);
const uploading = ref(false);
const avatarMessage = ref("");
const avatarError = ref(false);
const AVATAR_MAX_MB = 2;

function pickAvatar() {
  avatarMessage.value = "";
  avatarError.value = false;
  fileInput.value?.click();
}

async function onFile(event) {
  const file = event.target.files?.[0];
  event.target.value = "";
  if (!file) return;
  // 前端先拦一道，后端还有第二道（格式白名单 + 重编码 + 大小上限）。
  if (!file.type.startsWith("image/")) {
    avatarMessage.value = "请选择图片文件。";
    avatarError.value = true;
    return;
  }
  if (file.size > AVATAR_MAX_MB * 1024 * 1024) {
    avatarMessage.value = `头像不能超过 ${AVATAR_MAX_MB} MB。`;
    avatarError.value = true;
    return;
  }
  uploading.value = true;
  avatarMessage.value = "";
  avatarError.value = false;
  try {
    const body = await uploadAvatar(file);
    profile.value.avatar_url = body.avatar_url;
    // 顶部头像跟着更新（/me 也会带，这里直接同步，不必等下次整页刷新）
    if (session.user) session.user.avatar_url = body.avatar_url;
    avatarMessage.value = "头像已更新。";
  } catch (reason) {
    avatarMessage.value = reason.message || "头像上传失败，请稍后重试。";
    avatarError.value = true;
  } finally {
    uploading.value = false;
  }
}

// ---------- 学习签名 ----------
const editingSignature = ref(false);
const signatureDraft = ref("");
const signatureSaving = ref(false);
const signatureMessage = ref("");
const SIGNATURE_MAX = 80;

function startSignature() {
  signatureDraft.value = profile.value.learning_signature || "";
  signatureMessage.value = "";
  editingSignature.value = true;
}
function cancelSignature() {
  editingSignature.value = false;
  signatureMessage.value = "";
}

async function saveSignature() {
  const value = signatureDraft.value.trim();
  if (value.length > SIGNATURE_MAX) {
    signatureMessage.value = `学习签名不能超过 ${SIGNATURE_MAX} 字。`;
    return;
  }
  signatureSaving.value = true;
  signatureMessage.value = "";
  try {
    const body = await updateProfile({ learning_signature: value });
    profile.value.learning_signature = body.learning_signature;
    if (session.user) session.user.learning_signature = body.learning_signature;
    editingSignature.value = false;
    signatureMessage.value = "学习签名已保存。";
  } catch (reason) {
    signatureMessage.value = reason.message || "保存失败，请稍后重试。";
  } finally {
    signatureSaving.value = false;
  }
}

onMounted(load);
</script>

<template>
  <main class="kids-page profile-page">
    <header class="profile-heading">
      <div class="profile-avatar">
        <img :src="avatarSrc" alt="我的头像" width="96" height="96" />
        <button
          class="avatar-edit"
          type="button"
          :aria-label="uploading ? '正在上传头像' : '更换头像'"
          :disabled="uploading || loading || !!loadError"
          @click="pickAvatar"
        >
          <AppIcon name="camera" :size="16" />
        </button>
        <input ref="fileInput" type="file" accept="image/*" hidden @change="onFile" />
      </div>
      <div class="profile-meta">
        <h1>{{ profile.user.username || "同学" }}</h1>
        <p class="profile-id">
          <span v-if="profile.user.id">账号 ID {{ profile.user.id }}</span>
          <template v-if="profile.user.email"
            ><span aria-hidden="true">·</span>{{ profile.user.email }}</template
          >
        </p>

        <div class="profile-signature">
          <template v-if="editingSignature">
            <textarea
              v-model="signatureDraft"
              :maxlength="SIGNATURE_MAX"
              rows="2"
              aria-label="学习签名"
            ></textarea>
            <div class="signature-actions">
              <button
                class="button button-primary"
                type="button"
                :disabled="signatureSaving"
                @click="saveSignature"
              >
                保存
              </button>
              <button class="button" type="button" @click="cancelSignature">取消</button>
            </div>
          </template>
          <template v-else>
            <p class="signature-text">
              {{ profile.learning_signature || "还没有学习签名，写一句鼓励自己的话吧。" }}
            </p>
            <button
              class="signature-edit"
              type="button"
              :disabled="loading || !!loadError"
              @click="startSignature"
            >
              <AppIcon name="pencil" :size="14" /> 编辑签名
            </button>
          </template>
          <p v-if="signatureMessage" class="profile-note" role="status">{{ signatureMessage }}</p>
        </div>

        <p v-if="avatarMessage" class="profile-note" :class="{ error: avatarError }" role="status">
          {{ avatarMessage }}
        </p>
      </div>
    </header>

    <p v-if="loading" class="profile-message" aria-live="polite">正在整理你的学习资料...</p>
    <section v-else-if="loadError" class="profile-message profile-error" role="alert">
      <p>{{ loadError }}</p>
      <button class="button button-primary" type="button" @click="load">重新加载</button>
    </section>

    <template v-else>
      <section class="profile-summary" aria-label="学习概览">
        <div>
          <strong>{{ overview.total_answered }}</strong
          ><span>累计完成题数</span>
        </div>
        <div>
          <strong>{{ overview.total }}</strong
          ><span>累计错题</span>
        </div>
        <div>
          <strong>{{ overview.due }}</strong
          ><span>待复习</span>
        </div>
        <div>
          <strong>{{ accuracy }}</strong
          ><span>近 7 次正确率</span>
        </div>
      </section>

      <section class="profile-grid">
        <article class="profile-card">
          <h2>我的错题</h2>
          <p>系统会自动归纳做错的题目，重做后掌握度与复习记录自动更新。</p>
          <dl>
            <div>
              <dt>待复习</dt>
              <dd>{{ overview.due }} 题</dd>
            </div>
            <div>
              <dt>已掌握</dt>
              <dd>{{ overview.mastered }} 题</dd>
            </div>
          </dl>
          <RouterLink class="primary-action" :to="`/areas/${areaKey}/tasks/mistakes`">
            <AppIcon name="arrow-right" :size="18" /> 进入错题本
          </RouterLink>
        </article>
        <article class="profile-card">
          <h2>常用入口</h2>
          <p>工具箱里的数学思维、打字练习等学习工具。</p>
          <RouterLink class="entry-link" :to="`/areas/${areaKey}/toolbox`">
            <AppIcon name="spark" :size="18" /> 工具箱
          </RouterLink>
          <RouterLink class="entry-link" :to="{ path: '/settings', query: { area: areaKey } }">
            <AppIcon name="settings" :size="18" /> 设置
          </RouterLink>
        </article>
      </section>
    </template>
  </main>
</template>

<style scoped>
.profile-page {
  max-width: 1060px;
}
.profile-heading {
  display: flex;
  align-items: center;
  gap: 26px;
  padding: 36px clamp(28px, 5vw, 56px);
  border-radius: 24px 8px 24px 8px;
  background: var(--area-surface);
  color: #203c5b;
}
.profile-avatar {
  position: relative;
  flex: 0 0 auto;
}
.profile-avatar img {
  display: block;
  width: 96px;
  height: 96px;
  border-radius: 50%;
  border: 3px solid rgba(255, 255, 255, 0.75);
  object-fit: cover;
  background: var(--kids-panel);
}
.avatar-edit {
  position: absolute;
  right: -4px;
  bottom: -2px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border: 0;
  border-radius: 50%;
  color: #fff;
  background: var(--kids-blue);
  cursor: pointer;
}
.avatar-edit:disabled {
  opacity: 0.6;
  cursor: wait;
}
.profile-meta {
  min-width: 0;
  flex: 1;
}
.profile-meta h1 {
  margin: 0;
  font: 900 30px/1.25 var(--font-display);
  letter-spacing: 0;
}
.profile-id {
  margin: 6px 0 0;
  color: #54708d;
  font-size: 13px;
}
.profile-signature {
  margin-top: 14px;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
}
.signature-text {
  margin: 0;
  color: #33516f;
  line-height: 1.6;
}
.signature-edit {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  border: 0;
  padding: 4px 8px;
  border-radius: 999px;
  color: var(--accent);
  background: color-mix(in srgb, var(--accent) 12%, transparent);
  font-size: 12px;
  font-weight: 800;
  cursor: pointer;
}
.profile-signature textarea {
  width: 100%;
  min-height: 58px;
  padding: 10px 12px;
  border: 1px solid rgba(55, 87, 123, 0.3);
  border-radius: 8px;
  background: var(--kids-panel);
  color: var(--ink);
  font: inherit;
  line-height: 1.55;
  resize: vertical;
}
.signature-actions {
  display: flex;
  gap: 10px;
}
.profile-note {
  width: 100%;
  margin: 2px 0 0;
  color: #226551;
  font-size: 13px;
}
.profile-note.error {
  color: var(--danger);
}
.profile-summary {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  margin-top: 20px;
  border: 1px solid rgba(55, 87, 123, 0.14);
  border-radius: 8px;
  background: var(--kids-panel);
  overflow: hidden;
}
.profile-summary > div {
  min-width: 0;
  padding: 20px 22px;
  border-right: 1px solid rgba(55, 87, 123, 0.12);
}
.profile-summary > div:last-child {
  border-right: 0;
}
.profile-summary strong {
  display: block;
  font: 800 28px/1.1 var(--font-body);
  color: var(--accent);
}
.profile-summary span {
  display: block;
  margin-top: 7px;
  color: var(--muted);
  font-size: 13px;
}
.profile-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 20px;
  margin-top: 38px;
}
.profile-card {
  padding: 24px 26px;
  border: 1px solid rgba(55, 87, 123, 0.14);
  border-radius: 8px;
  background: var(--kids-panel);
}
.profile-card h2 {
  margin: 0;
  font: 800 22px/1.3 var(--font-display);
  letter-spacing: 0;
}
.profile-card > p {
  margin: 8px 0 0;
  color: var(--muted);
  font-size: 13px;
  line-height: 1.6;
}
.profile-card dl {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
  margin: 18px 0;
}
.profile-card dt,
.profile-card dd {
  margin: 0;
}
.profile-card dt {
  color: var(--muted);
  font-size: 13px;
}
.profile-card dd {
  margin-top: 4px;
  font-size: 22px;
  font-weight: 800;
  color: var(--ink);
}
.entry-link {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 10px;
  padding: 12px 14px;
  border: 1px solid rgba(55, 87, 123, 0.14);
  border-radius: 8px;
  color: var(--ink);
  font-weight: 800;
}
.entry-link:hover {
  border-color: var(--kids-blue);
  box-shadow: 0 8px 18px rgba(34, 43, 40, 0.08);
}
.profile-message {
  margin-top: 18px;
  padding: 32px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--kids-panel);
  color: var(--muted);
  text-align: center;
}
.profile-message p {
  margin: 0 0 16px;
  line-height: 1.6;
}
.profile-error {
  color: var(--danger);
}
@media (max-width: 800px) {
  .profile-heading {
    gap: 18px;
    padding: 28px 24px;
  }
  .profile-avatar img {
    width: 76px;
    height: 76px;
  }
  .profile-summary {
    grid-template-columns: repeat(2, 1fr);
  }
  .profile-summary > div:nth-child(2) {
    border-right: 0;
  }
  .profile-summary > div:nth-child(-n + 2) {
    border-bottom: 1px solid rgba(55, 87, 123, 0.12);
  }
  .profile-grid {
    grid-template-columns: 1fr;
    margin-top: 24px;
  }
}
@media (max-width: 480px) {
  .profile-heading {
    flex-direction: column;
    align-items: flex-start;
  }
  .profile-summary > div {
    padding: 16px;
  }
  .profile-summary strong {
    font-size: 24px;
  }
}
</style>
