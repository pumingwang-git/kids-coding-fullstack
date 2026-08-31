import { readonly, shallowRef } from "vue";

const current = shallowRef(null);
const enabled = shallowRef(true);

export const activeHelpContext = readonly(current);
export const helpEnabled = readonly(enabled);

export function lessonBlockHelpContext(block) {
  if (!block || block.block_type !== "practice" || block.lock_reason) return null;
  const blockId = Number(block.id);
  return Number.isSafeInteger(blockId) && blockId > 0
    ? { context_type: "block", context_id: blockId }
    : null;
}

export function setActiveHelpContext(context) {
  current.value = context;
}

export function clearActiveHelpContext() {
  current.value = null;
}

export function setHelpEnabled(value) {
  enabled.value = value !== false;
}

export function resetHelpState() {
  enabled.value = true;
  current.value = null;
}

export function paperAttemptHelpContext(attemptId, problemIdNo) {
  if (!Number.isSafeInteger(Number(attemptId)) || Number(attemptId) < 1 || !problemIdNo) return null;
  return {
    context_type: "attempt",
    context_source: "paper_attempt",
    context_id: Number(attemptId),
    problem_id_no: problemIdNo,
  };
}
