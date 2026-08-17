// HaveIBeenPwned Pwned Passwords k-anonymity client-side check.
// Only the first five characters of the SHA-1 digest leave the browser; the
// suffix is matched locally against the returned range.  The check is purely
// advisory (the server enforces the policy) and fails silently when the API
// is unreachable, so it can never block the form.

const HIBP_RANGE_URL = "https://api.pwnedpasswords.com/range/";
const HIBP_TIMEOUT_MS = 5000;

async function sha1Hex(text) {
  if (!globalThis.crypto?.subtle) return null;
  const digest = await globalThis.crypto.subtle.digest("SHA-1", new TextEncoder().encode(text));
  return [...new Uint8Array(digest)]
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("")
    .toUpperCase();
}

export async function pwnedBreachCount(password) {
  try {
    const digest = await sha1Hex(password);
    if (!digest) return null;
    const prefix = digest.slice(0, 5);
    const suffix = digest.slice(5);
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), HIBP_TIMEOUT_MS);
    let response;
    try {
      response = await fetch(`${HIBP_RANGE_URL}${prefix}`, {
        signal: controller.signal,
        headers: { "Add-Padding": "true" },
      });
    } finally {
      clearTimeout(timer);
    }
    if (!response.ok) return null;
    const body = await response.text();
    for (const line of body.split("\n")) {
      const [candidate, count] = line.trim().split(":");
      if (candidate.toUpperCase() === suffix) return Number(count) || 1;
    }
    return 0;
  } catch {
    return null;
  }
}
