<script setup>
import { computed, ref } from "vue";
import {
  changePassword,
  confirmMfa,
  requestPasswordChangeVerification,
  setupMfa,
} from "../services/auth";
import { session } from "../stores/session";

const pw = ref({ current: "", next: "", confirm: "" });
const pwLoading = ref(false);
const pwMessage = ref("");
const pwError = ref("");
const changeVerificationRequested = ref(false);
const changeCode = ref("");

const passwordRules = computed(() => {
  const value = pw.value.next;
  return [
    { label: "至少 12 位字符", met: value.length >= 12 },
    { label: "包含英文字母", met: /[A-Za-z]/.test(value) },
    { label: "包含数字", met: /\d/.test(value) },
    { label: "包含特殊符号", met: /[^A-Za-z0-9\s]/.test(value) },
  ];
});
const passwordValid = computed(() => passwordRules.value.every((rule) => rule.met));

async function change() {
  pwError.value = "";
  pwMessage.value = "";
  if (!changeVerificationRequested.value) {
    pwError.value = "请先发送并填写邮箱验证码。";
    return;
  }
  if (pw.value.next !== pw.value.confirm) {
    pwError.value = "两次输入的新密码不一致。";
    return;
  }
  if (!passwordValid.value) {
    pwError.value = "新密码至少 12 位，且必须包含英文字母、数字和特殊符号。";
    return;
  }
  pwLoading.value = true;
  try {
    await changePassword({
      current_password: pw.value.current,
      new_password: pw.value.next,
      code: changeCode.value,
    });
    pwMessage.value = "密码已修改，旧会话已全部失效。";
    pw.value = { current: "", next: "", confirm: "" };
    changeCode.value = "";
    changeVerificationRequested.value = false;
  } catch (reason) {
    pwError.value = reason.message;
  } finally {
    pwLoading.value = false;
  }
}

async function requestChangeCode() {
  pwError.value = "";
  pwMessage.value = "";
  if (!pw.value.current) {
    pwError.value = "请先填写当前密码。";
    return;
  }
  pwLoading.value = true;
  try {
    await requestPasswordChangeVerification({ current_password: pw.value.current });
    changeVerificationRequested.value = true;
    pwMessage.value = "验证码已发送到已绑定邮箱，15 分钟内有效。";
  } catch (reason) {
    pwError.value = reason.message;
  } finally {
    pwLoading.value = false;
  }
}

const setup = ref(null);
const code = ref("");
const mfaLoading = ref(false);
const mfaMessage = ref("");
const mfaError = ref("");

async function start() {
  mfaLoading.value = true;
  mfaError.value = "";
  mfaMessage.value = "";
  try {
    setup.value = await setupMfa();
  } catch (reason) {
    mfaError.value = reason.message;
  } finally {
    mfaLoading.value = false;
  }
}

async function confirm() {
  mfaLoading.value = true;
  mfaError.value = "";
  mfaMessage.value = "";
  try {
    await confirmMfa({ code: code.value });
    mfaMessage.value = "MFA 已启用。下次登录请填写验证器中的 6 位动态码。";
    setup.value = null;
    code.value = "";
  } catch (reason) {
    mfaError.value = reason.message;
  } finally {
    mfaLoading.value = false;
  }
}
</script>

<template>
  <main class="verify-wrap shell">
    <section class="verify-card">
      <p class="eyebrow">ACCOUNT SECURITY</p>
      <h1>账号安全</h1>
      <section>
        <h2 class="security-section-title">登录密码</h2>
        <p class="muted">
          新密码不能与当前密码或最近 5 次使用过的密码相同，且不得是公开泄露库中出现过的密码。
        </p>
        <form @submit.prevent="changeVerificationRequested ? change() : requestChangeCode()">
          <label
            >当前密码<input
              v-model="pw.current"
              type="password"
              maxlength="128"
              required
              autocomplete="current-password"
          /></label>
          <label
            >新密码<input
              v-model="pw.next"
              type="password"
              minlength="12"
              maxlength="128"
              required
              autocomplete="new-password"
          /></label>
          <ul class="password-checklist">
            <li v-for="rule in passwordRules" :key="rule.label" :class="{ met: rule.met }">
              <i>{{ rule.met ? "✓" : "×" }}</i
              >{{ rule.label }}
            </li>
          </ul>
          <label
            >确认新密码<input
              v-model="pw.confirm"
              type="password"
              minlength="12"
              maxlength="128"
              required
              autocomplete="new-password"
            /><small v-if="pw.confirm && pw.next !== pw.confirm" class="inline-error"
              >两次输入的新密码不一致。</small
            ></label
          >
          <label v-if="changeVerificationRequested"
            >邮箱验证码<input
              v-model.trim="changeCode"
              inputmode="numeric"
              pattern="[0-9]{6}"
              maxlength="6"
              required
              autocomplete="one-time-code"
              placeholder="6 位验证码"
          /></label>
          <p v-if="pwError" class="form-error">{{ pwError }}</p>
          <p v-if="pwMessage" class="form-success">{{ pwMessage }}</p>
          <button class="button button-primary full" :disabled="pwLoading">
            {{
              pwLoading
                ? "正在处理…"
                : changeVerificationRequested
                  ? "确认修改密码"
                  : "发送邮箱验证码"
            }}
          </button>
        </form>
      </section>
      <section v-if="session.user?.mfa_enabled" class="security-section-divider">
        <h2 class="security-section-title">动态验证（MFA）</h2>
        <template v-if="!setup && !mfaMessage">
          <button class="button button-primary full" :disabled="mfaLoading" @click="start">
            {{ mfaLoading ? "正在生成…" : "开始设置 MFA" }}
          </button>
        </template>
        <form v-else-if="setup" @submit.prevent="confirm">
          <p class="muted">
            在 Microsoft Authenticator、Google Authenticator 或 1Password
            中选择“手动输入密钥”，复制下方密钥后输入当前显示的 6 位码。
          </p>
          <label>密钥<input :value="setup.secret" readonly autocomplete="off" /></label>
          <label
            >动态验证码<input
              v-model.trim="code"
              inputmode="numeric"
              pattern="[0-9]{6}"
              maxlength="6"
              required
              autocomplete="one-time-code"
              placeholder="6 位动态验证码"
          /></label>
          <p v-if="mfaError" class="form-error">{{ mfaError }}</p>
          <button class="button button-primary full" :disabled="mfaLoading">
            {{ mfaLoading ? "正在确认…" : "确认并启用" }}
          </button>
        </form>
        <p v-else class="form-success">{{ mfaMessage }}</p>
      </section>
    </section>
  </main>
</template>

<style scoped>
.security-section-title {
  margin: 0 0 4px;
  font-size: 20px;
  letter-spacing: -1px;
}
.security-section-divider {
  margin-top: 40px;
  padding-top: 32px;
  border-top: 1px solid var(--line);
}
</style>
