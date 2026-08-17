<script setup>
import { ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { resendVerification, verifyEmail } from "../services/auth";
const route = useRoute();
const router = useRouter();
const email = ref(route.query.email || "");
const code = ref("");
const message = ref("");
const error = ref("");
const loading = ref(false);
async function verify() {
  loading.value = true;
  error.value = "";
  try {
    await verifyEmail({ email: email.value, code: code.value });
    message.value = "邮箱验证完成，现在可以登录。";
  } catch (reason) {
    error.value = reason.message;
  } finally {
    loading.value = false;
  }
}
async function resend() {
  error.value = "";
  try {
    await resendVerification({ email: email.value });
    message.value = "如果账号待验证，新的验证码已发送，请查收邮箱。";
  } catch (reason) {
    error.value = reason.message;
  }
}
</script>
<template>
  <main class="verify-wrap shell">
    <section class="verify-card">
      <img src="/assets/otter-encouraging.png" alt="鼓励学习的水獭" />
      <p class="eyebrow">VERIFY EMAIL</p>
      <h1>确认你的邮箱</h1>
      <p class="muted">
        输入邮件中的 6 位验证码。验证码 15 分钟内有效，新验证码会自动替换旧验证码。
      </p>
      <form @submit.prevent="verify">
        <label>邮箱<input v-model.trim="email" type="email" required /></label
        ><label
          >验证码<input
            v-model.trim="code"
            inputmode="numeric"
            pattern="[0-9]{6}"
            maxlength="6"
            required
        /></label>
        <p v-if="error" class="form-error">{{ error }}</p>
        <p v-if="message" class="form-success">{{ message }}</p>
        <button class="button button-primary full" :disabled="loading">
          {{ loading ? "正在验证…" : "完成验证" }} <span>→</span>
        </button>
      </form>
      <div class="verify-actions">
        <button class="text-button" type="button" @click="resend">重新发送验证码</button
        ><button v-if="message" class="text-button" type="button" @click="router.push('/auth')">
          前往登录
        </button>
      </div>
    </section>
  </main>
</template>
