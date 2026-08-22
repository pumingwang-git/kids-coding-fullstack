// 学员列表只显示后端按 visible_student_ids() 收窄后的数据。
import { initLayout } from "./admin-layout.js";
import { escapeHtml, fmtTime } from "./admin-ui.js";
import { fetchStudents, STUDENT_PAGE_SIZE } from "./student-picker.js";

initLayout();

const $ = (id) => document.getElementById(id);
let state = { keyword: "", page: 1, result: null };

function render() {
  const result = state.result || { items: [], total: 0, page: state.page, page_size: STUDENT_PAGE_SIZE };
  const items = result.items || [];
  $("studentRows").innerHTML = items
    .map(
      (student) => `
        <tr>
          <td class="student-id">#${escapeHtml(student.id)}</td>
          <td class="student-name">${escapeHtml(student.username)}</td>
          <td class="cell-clip" title="${escapeHtml(student.email)}">${escapeHtml(student.email)}</td>
          <td><span class="tag">${escapeHtml(student.status_label)}</span></td>
          <td>${escapeHtml(fmtTime(student.created_at) || "未记录")}</td>
        </tr>`,
    )
    .join("");
  $("studentEmpty").hidden = items.length > 0;
  $("studentListMeta").textContent = `共 ${result.total} 名学员`;
  $("studentPager").hidden = result.total <= result.page_size;
  $("studentPageMeta").textContent = `第 ${result.page} 页，共 ${Math.max(1, Math.ceil(result.total / result.page_size))} 页`;
  $("previousStudentPage").disabled = result.page <= 1;
  $("nextStudentPage").disabled = result.page * result.page_size >= result.total;
}

async function loadStudents() {
  $("studentError").hidden = true;
  $("studentEmpty").hidden = true;
  $("studentRows").innerHTML = '<tr><td class="student-loading" colspan="5">加载中</td></tr>';
  try {
    state.result = await fetchStudents({ keyword: state.keyword, page: state.page });
    if (state.result.items.length === 0 && state.page > 1) {
      state.page -= 1;
      state.result = await fetchStudents({ keyword: state.keyword, page: state.page });
    }
    render();
  } catch (error) {
    $("studentRows").innerHTML = "";
    $("studentErrorText").textContent = error.message;
    $("studentError").hidden = false;
    $("studentPager").hidden = true;
    $("studentListMeta").textContent = "加载失败";
  }
}

$("studentSearchForm").addEventListener("submit", (event) => {
  event.preventDefault();
  state.keyword = $("studentSearch").value.trim();
  state.page = 1;
  loadStudents();
});
$("refreshStudents").addEventListener("click", loadStudents);
$("retryStudents").addEventListener("click", loadStudents);
$("previousStudentPage").addEventListener("click", () => {
  state.page -= 1;
  loadStudents();
});
$("nextStudentPage").addEventListener("click", () => {
  state.page += 1;
  loadStudents();
});

loadStudents();
