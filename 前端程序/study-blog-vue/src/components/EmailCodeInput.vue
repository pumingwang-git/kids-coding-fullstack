<script setup>
defineProps({
  modelValue: { type: String, default: "" },
  loading: { type: Boolean, default: false },
  secondsLeft: { type: Number, default: 0 },
});
defineEmits(["update:modelValue", "resend"]);
</script>

<template>
  <label
    >邮箱验证码
    <div class="code-row">
      <input
        :value="modelValue"
        inputmode="numeric"
        pattern="[0-9]{6}"
        maxlength="6"
        required
        autocomplete="one-time-code"
        placeholder="6 位验证码"
        @input="$emit('update:modelValue', $event.target.value.trim())"
      />
      <button
        class="send-code"
        type="button"
        :disabled="loading || secondsLeft > 0"
        @click="$emit('resend')"
      >
        {{ secondsLeft > 0 ? `${secondsLeft}s 后重发` : "重新发送" }}
      </button>
    </div>
    <small>验证码为 6 位数字，15 分钟内有效；请勿提供给他人。</small>
  </label>
</template>
