import { onBeforeUnmount, ref } from "vue";

export function useEmailCodeCooldown() {
  const secondsLeft = ref(0);
  let timer = null;

  function start() {
    if (timer) window.clearInterval(timer);
    secondsLeft.value = 60;
    timer = window.setInterval(() => {
      secondsLeft.value -= 1;
      if (secondsLeft.value <= 0) {
        window.clearInterval(timer);
        timer = null;
      }
    }, 1000);
  }

  onBeforeUnmount(() => {
    if (timer) window.clearInterval(timer);
  });

  return { secondsLeft, startCooldown: start };
}
