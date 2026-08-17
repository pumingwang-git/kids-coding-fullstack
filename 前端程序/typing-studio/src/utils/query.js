// URL 参数读取：/typing-studio/?age=7-12&mode=spell
export function getQuery(name) {
  return new URLSearchParams(window.location.search).get(name);
}

export function setQuery(name, value) {
  const url = new URL(window.location.href);
  url.searchParams.set(name, value);
  window.history.replaceState(null, '', url.toString());
}
