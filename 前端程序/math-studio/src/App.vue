<script setup>
import { RouterView } from "vue-router";
import { CloudOff } from "@lucide/vue";
import { isOffline } from "./platform/session";
</script>

<template>
  <div class="app-root">
    <div v-if="isOffline" class="offline-banner" role="status">
      <CloudOff :size="17" aria-hidden="true" />
      当前离线，本次记录会在网络恢复后同步
    </div>
    <RouterView />
  </div>
</template>
