// 可复用的学员选择数据源。班级批量导入等页面只消费后端已范围过滤的结果。
import { adminRequest } from "./admin-api.js";
import { escapeHtml } from "./admin-ui.js";

export const STUDENT_PAGE_SIZE = 20;

export async function fetchStudents({ keyword = "", page = 1, pageSize = STUDENT_PAGE_SIZE, sort = "id" } = {}) {
  const params = new URLSearchParams({ page: String(page), page_size: String(pageSize), sort });
  if (keyword.trim()) params.set("keyword", keyword.trim());
  return adminRequest(`/students?${params}`);
}

export function studentOptionLabel(student) {
  return `#${student.id} · ${student.username}`;
}

/**
 * 将可搜索的单选或多选学员列表挂载到容器。调用方只得到已选择的学员对象，
 * 不复制数据范围、分页或接口细节。
 */
export function mountStudentPicker(container, { multiple = true, onChange = () => {} } = {}) {
  let state = { keyword: "", page: 1, selected: new Map(), result: null };
  container.innerHTML = `
    <div class="student-picker-search">
      <label>搜索学员 <input type="search" data-student-picker-search placeholder="学员 ID、用户名或邮箱" /></label>
      <button class="btn" type="button" data-student-picker-submit>搜索</button>
    </div>
    <div class="student-picker-results" data-student-picker-results></div>
    <div class="pager" data-student-picker-pager hidden>
      <button class="btn" type="button" data-student-picker-previous>上一页</button>
      <span data-student-picker-meta></span><span class="spacer"></span>
      <button class="btn" type="button" data-student-picker-next>下一页</button>
    </div>`;
  const search = container.querySelector("[data-student-picker-search]");
  const results = container.querySelector("[data-student-picker-results]");
  const pager = container.querySelector("[data-student-picker-pager]");

  function emitChange() {
    onChange([...state.selected.values()]);
  }

  function render() {
    const payload = state.result;
    const items = payload?.items || [];
    results.innerHTML = items.length
      ? `<div class="student-picker-options">${items.map((student) => `
          <label class="student-picker-option">
            <input type="${multiple ? "checkbox" : "radio"}" name="student-picker" value="${student.id}"${state.selected.has(student.id) ? " checked" : ""} />
            <span>${escapeHtml(studentOptionLabel(student))}</span>
            <small>${escapeHtml(student.email)}</small>
          </label>`).join("")}</div>`
      : '<p class="muted">没有匹配的学员</p>';
    const total = payload?.total || 0;
    pager.hidden = total <= STUDENT_PAGE_SIZE;
    container.querySelector("[data-student-picker-meta]").textContent = `第 ${state.page} 页，共 ${total} 人`;
    container.querySelector("[data-student-picker-previous]").disabled = state.page <= 1;
    container.querySelector("[data-student-picker-next]").disabled = state.page * STUDENT_PAGE_SIZE >= total;
  }

  async function load() {
    results.textContent = "加载中";
    try {
      state.result = await fetchStudents({ keyword: state.keyword, page: state.page });
      render();
    } catch (error) {
      results.textContent = error.message;
      pager.hidden = true;
    }
  }

  container.querySelector("[data-student-picker-submit]").addEventListener("click", () => {
    state.keyword = search.value;
    state.page = 1;
    load();
  });
  search.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      container.querySelector("[data-student-picker-submit]").click();
    }
  });
  results.addEventListener("change", (event) => {
    const input = event.target.closest("input[name='student-picker']");
    if (!input) return;
    const student = state.result?.items.find((item) => item.id === Number(input.value));
    if (!student) return;
    if (!multiple) state.selected.clear();
    if (input.checked) state.selected.set(student.id, student);
    else state.selected.delete(student.id);
    emitChange();
  });
  container.querySelector("[data-student-picker-previous]").addEventListener("click", () => {
    state.page -= 1;
    load();
  });
  container.querySelector("[data-student-picker-next]").addEventListener("click", () => {
    state.page += 1;
    load();
  });
  load();
  return {
    clear() {
      state.selected.clear();
      render();
      emitChange();
    },
    selected() {
      return [...state.selected.values()];
    },
  };
}
