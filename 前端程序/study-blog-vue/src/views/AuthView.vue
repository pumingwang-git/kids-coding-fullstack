<script setup>
import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  getCaptcha,
  getCurrentUser,
  login,
  register,
  resendVerification,
  verifyEmail,
} from "../services/auth";
import { pwnedBreachCount } from "../services/pwned";
import { session } from "../stores/session";
import EmailCodeInput from "../components/EmailCodeInput.vue";
import { useEmailCodeCooldown } from "../composables/useEmailCodeCooldown";

const router = useRouter();
const route = useRoute();
const mode = ref("login");
const loading = ref(false);
const error = ref("");
const message = ref("");
const verificationSent = ref(false);
const { secondsLeft, startCooldown } = useEmailCodeCooldown();
const captcha = ref(null);
const captchaAnswer = ref("");
const form = ref({
  username: "",
  email: "",
  identifier: "",
  password: "",
  confirmPassword: "",
  code: "",
});
const isRegister = computed(() => mode.value === "register");
const breachWarning = ref("");
async function checkPasswordBreach() {
  breachWarning.value = "";
  if (!isRegister.value || form.value.password.length < 12) return;
  const count = await pwnedBreachCount(form.value.password);
  if (count > 0) breachWarning.value = `该密码已在公开泄露数据库中出现过 ${count} 次，建议更换。`;
}
const passwordFocused = ref(false);
const showPassword = ref(false);
const passwordRules = computed(() => {
  const password = form.value.password;
  const hasLetter = /[A-Za-z]/.test(password);
  const hasNumber = /\d/.test(password);
  const hasSymbol = /[^A-Za-z0-9\s]/.test(password);
  return [
    { label: "至少 12 位字符", met: password.length >= 12 },
    { label: "包含英文字母", met: hasLetter },
    { label: "包含数字", met: hasNumber },
    { label: "包含特殊符号", met: hasSymbol },
  ];
});
const passwordValid = computed(() => passwordRules.value.every((rule) => rule.met));
const showPasswordChecklist = computed(
  () => isRegister.value && (passwordFocused.value || form.value.password.length > 0),
);
const showPasswordTooltip = computed(
  () => isRegister.value && passwordFocused.value && !passwordValid.value,
);
function resetRegisterState() {
  error.value = "";
  message.value = "";
  verificationSent.value = false;
  secondsLeft.value = 0;
  form.value.code = "";
}
async function refreshCaptcha() {
  captchaAnswer.value = "";
  try {
    captcha.value = await getCaptcha();
  } catch (reason) {
    error.value = reason.message;
  }
}
function startCountdown() {
  startCooldown();
}
function validateRegistration() {
  if (form.value.password !== form.value.confirmPassword) return "两次输入的密码不一致。";
  if (!passwordValid.value) return "密码至少 12 位，且必须包含英文字母、数字和特殊符号。";
  return "";
}
async function sendCode() {
  const validation = validateRegistration();
  if (validation) {
    error.value = validation;
    return;
  }
  loading.value = true;
  error.value = "";
  message.value = "";
  try {
    if (!verificationSent.value) {
      await register({
        username: form.value.username,
        email: form.value.email,
        password: form.value.password,
      });
      verificationSent.value = true;
    } else {
      await resendVerification({ email: form.value.email });
    }
    message.value = "验证码已发送到你的 QQ 邮箱，请输入 6 位数字完成注册。";
    startCountdown();
  } catch (reason) {
    error.value = reason.message;
  } finally {
    loading.value = false;
  }
}
async function submit() {
  loading.value = true;
  error.value = "";
  message.value = "";
  try {
    if (isRegister.value) {
      if (!verificationSent.value) {
        await sendCode();
        return;
      }
      await verifyEmail({ email: form.value.email, code: form.value.code });
      message.value = "邮箱验证完成，请使用刚创建的账号登录。";
      mode.value = "login";
      form.value.identifier = form.value.username;
      form.value.password = "";
    } else {
      await login({
        identifier: form.value.identifier,
        password: form.value.password,
        captcha_id: captcha.value?.captcha_id,
        captcha_answer: captchaAnswer.value,
      });
      session.user = await getCurrentUser();
      session.loaded = true;
      await router.push(route.query.next || "/study");
    }
  } catch (reason) {
    error.value = reason.message;
  } finally {
    loading.value = false;
    await refreshCaptcha();
  }
}
onMounted(refreshCaptcha);
</script>

<template>
  <main class="auth-layout shell">
    <section class="auth-intro">
      <p class="eyebrow">{{ isRegister ? "CREATE ACCOUNT" : "WELCOME BACK" }}</p>
      <h1>
        {{ isRegister ? "从第一节课，开始。" : "准备好，继续往前走。" }}
      </h1>
      <p>
        {{
          isRegister
            ? "注册时请使用可接收验证码的 QQ 邮箱。验证完成后，课程与练习记录才会绑定到你的账号。"
            : "请使用已绑定的 QQ 邮箱登录。若邮箱尚未验证，登录后部分课程记录可能无法同步。"
        }}
      </p>
      <img src="/assets/otter-reading.png" alt="阅读笔记的水獭" />
    </section>
    <section class="auth-card">
      <div class="tabs">
        <button
          :class="{ active: !isRegister }"
          @click="
            mode = 'login';
            error = '';
            message = '';
          "
        >
          登录</button
        ><button
          :class="{ active: isRegister }"
          @click="
            mode = 'register';
            resetRegisterState();
          "
        >
          注册
        </button>
      </div>
      <p class="eyebrow">ACCOUNT</p>
      <h2>{{ isRegister ? "创建你的账号" : "欢迎回来" }}</h2>
      <p class="muted">
        {{ isRegister ? "使用真实的邮箱注册学习系统" : "使用用户名或邮箱登录学习系统。" }}
      </p>
      <form @submit.prevent="submit">
        <template v-if="isRegister">
          <label
            >用户名<input
              v-model.trim="form.username"
              :disabled="verificationSent"
              minlength="3"
              maxlength="50"
              required
              autocomplete="username"
          /></label>
          <label
            >QQ 邮箱<input
              v-model.trim="form.email"
              :disabled="verificationSent"
              type="email"
              placeholder="example@qq.com"
              required
              autocomplete="email"
          /></label>
        </template>
        <label v-else
          >用户名或邮箱<input v-model.trim="form.identifier" required autocomplete="username"
        /></label>
        <label class="password-label"
          >密码
          <div class="password-input-wrap">
            <input
              v-model="form.password"
              :disabled="isRegister && verificationSent"
              :type="showPassword ? 'text' : 'password'"
              :minlength="isRegister ? 12 : 1"
              maxlength="128"
              required
              :autocomplete="isRegister ? 'new-password' : 'current-password'"
              @focus="passwordFocused = true"
              @blur="
                passwordFocused = false;
                checkPasswordBreach();
              "
            />
            <!-- <button
              class="password-toggle"
              type="button"
              :disabled="isRegister && verificationSent"
              :aria-label="showPassword ? '隐藏密码' : '显示密码'"
              @mousedown.prevent
              @click="showPassword = !showPassword"
            >
              {{ showPassword ? "🙈" : "👀" }}
            </button> -->
          </div>
          <aside v-if="showPasswordTooltip" class="password-tooltip">
            <b>设置一个更安全的密码</b><span>满足以下全部规则后，提示会自动收起。 </span>
          </aside>
          <ul v-if="showPasswordChecklist" class="password-checklist">
            <li v-for="rule in passwordRules" :key="rule.label" :class="{ met: rule.met }">
              <i>{{ rule.met ? "✓" : "×" }}</i
              >{{ rule.label }}
            </li>
          </ul>
          <p v-if="breachWarning" class="form-error">{{ breachWarning }}</p></label
        >
        <label v-if="!isRegister"
          >图片验证码
          <div class="code-row">
            <input
              v-model.trim="captchaAnswer"
              maxlength="5"
              required
              autocomplete="off"
              placeholder="输入图片中的 5 位字符"
            /><button
              class="captcha-refresh"
              type="button"
              title="换一张验证码"
              @click="refreshCaptcha"
            >
              <img
                v-if="captcha"
                class="captcha-image"
                :src="captcha.image"
                alt="点击更换图片验证码"
              />
            </button>
          </div>
          <small>看不清可点击图片更换；验证码仅能使用一次。</small></label
        >
        <template v-if="isRegister">
          <label
            >确认密码<input
              v-model="form.confirmPassword"
              :disabled="verificationSent"
              type="password"
              minlength="12"
              maxlength="128"
              required
              autocomplete="new-password"
            /><small
              v-if="form.confirmPassword && form.password !== form.confirmPassword"
              class="inline-error"
              >两次密码不一致。</small
            ></label
          >
          <EmailCodeInput
            v-model="form.code"
            :loading="loading"
            :seconds-left="secondsLeft"
            @resend="sendCode"
          />
        </template>
        <p v-if="error" class="form-error">{{ error }}</p>
        <p v-if="message" class="form-success">{{ message }}</p>
        <button class="button button-primary full" :disabled="loading">
          {{
            loading
              ? "正在处理…"
              : isRegister
                ? verificationSent
                  ? "完成注册"
                  : "发送验证码"
                : "登录并继续"
          }}
          <span>→</span>
        </button>
        <RouterLink v-if="!isRegister" class="text-button" to="/forgot-password"
          >忘记密码？</RouterLink
        >
      </form>
    </section>
  </main>
</template>
