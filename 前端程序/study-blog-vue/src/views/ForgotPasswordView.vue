<script setup>
import { computed, ref } from "vue";
import { useRouter } from "vue-router";
import { confirmPasswordReset, requestPasswordReset } from "../services/auth";
import { pwnedBreachCount } from "../services/pwned";
import EmailCodeInput from "../components/EmailCodeInput.vue";
import { useEmailCodeCooldown } from "../composables/useEmailCodeCooldown";

const router = useRouter();
const form = ref({ email: "", password: "", confirmPassword: "", code: "" });
const requested = ref(false);
const loading = ref(false);
const error = ref("");
const message = ref("");
const breachWarning = ref("");
const { secondsLeft, startCooldown } = useEmailCodeCooldown();

const passwordRules = computed(() => [
  { label: "至少 12 位字符", met: form.value.password.length >= 12 },
  { label: "包含英文字母", met: /[A-Za-z]/.test(form.value.password) },
  { label: "包含数字", met: /\d/.test(form.value.password) },
  { label: "包含特殊符号", met: /[^A-Za-z0-9\s]/.test(form.value.password) },
]);
const passwordValid = computed(() => passwordRules.value.every((rule) => rule.met));

async function checkPasswordBreach() {
  breachWarning.value = "";
  if (form.value.password.length < 12) return;
  const count = await pwnedBreachCount(form.value.password);
  if (count > 0) breachWarning.value = `该密码已在公开泄露数据库中出现过 ${count} 次，建议更换。`;
}

async function requestCode() {
  loading.value = true;
  error.value = "";
  message.value = "";
  try {
    await requestPasswordReset({ email: form.value.email });
    requested.value = true;
    message.value = "验证码已发送到已绑定邮箱，请在 15 分钟内完成操作。";
    startCooldown();
  } catch (reason) {
    error.value = reason.message;
  } finally {
    loading.value = false;
  }
}

async function resetPassword() {
  error.value = "";
  message.value = "";
  if (!passwordValid.value) {
    error.value = "新密码至少 12 位，且必须包含英文字母、数字和特殊符号。";
    return;
  }
  if (form.value.password !== form.value.confirmPassword) {
    error.value = "两次输入的新密码不一致。";
    return;
  }
  loading.value = true;
  try {
    await confirmPasswordReset({
      email: form.value.email,
      code: form.value.code,
      new_password: form.value.password,
    });
    message.value = "密码已重置，请使用新密码重新登录。";
    form.value.password = "";
    form.value.confirmPassword = "";
    form.value.code = "";
    requested.value = false;
  } catch (reason) {
    error.value = reason.message;
  } finally {
    loading.value = false;
  }
}
</script>

<template>
  <main class="auth-layout shell">
    <section class="auth-intro">
      <p class="eyebrow">RESET PASSWORD</p>
      <h1>找回账号，重新出发。</h1>
      <p>通过已绑定邮箱的一次性验证码，安全地设置新的登录密码。</p>
      <img src="/assets/otter-reading.png" alt="阅读笔记的水獭" />
    </section>
    <section class="auth-card">
      <p class="eyebrow">ACCOUNT</p>
      <h2>找回登录密码</h2>
      <p class="muted">请输入已注册并完成验证的邮箱，验证码会发送到该邮箱。</p>
      <form v-if="!requested" @submit.prevent="requestCode">
        <label
          >已绑定邮箱<input v-model.trim="form.email" type="email" required autocomplete="email"
        /></label>
        <p v-if="error" class="form-error">{{ error }}</p>
        <p v-if="message" class="form-success">{{ message }}</p>
        <button class="button button-primary full" :disabled="loading">
          {{ loading ? "正在发送…" : "发送重置验证码" }}
        </button>
      </form>
      <form v-else @submit.prevent="resetPassword">
        <label>已绑定邮箱<input :value="form.email" readonly autocomplete="email" /></label>
        <EmailCodeInput
          v-model="form.code"
          :loading="loading"
          :seconds-left="secondsLeft"
          @resend="requestCode"
        />
        <label
          >新密码<input
            v-model="form.password"
            type="password"
            minlength="12"
            maxlength="128"
            required
            autocomplete="new-password"
            @blur="checkPasswordBreach"
        /></label>
        <ul class="password-checklist">
          <li v-for="rule in passwordRules" :key="rule.label" :class="{ met: rule.met }">
            <i>{{ rule.met ? "✓" : "×" }}</i
            >{{ rule.label }}
          </li>
        </ul>
        <p v-if="breachWarning" class="form-error">{{ breachWarning }}</p>
        <label
          >确认新密码<input
            v-model="form.confirmPassword"
            type="password"
            minlength="12"
            maxlength="128"
            required
            autocomplete="new-password"
          /><small
            v-if="form.confirmPassword && form.confirmPassword !== form.password"
            class="inline-error"
            >两次密码不一致。</small
          ></label
        >
        <p v-if="error" class="form-error">{{ error }}</p>
        <p v-if="message" class="form-success">{{ message }}</p>
        <button class="button button-primary full" :disabled="loading">
          {{ loading ? "正在重置…" : "确认重置密码" }}
        </button>
      </form>
      <button class="text-button" type="button" @click="router.push('/auth')">返回登录</button>
    </section>
  </main>
</template>

<style scoped>
.text-button {
  width: 100%;
  margin-top: 14px;
  border: 0;
  background: transparent;
  color: var(--accent);
  cursor: pointer;
  font: inherit;
}
</style>
