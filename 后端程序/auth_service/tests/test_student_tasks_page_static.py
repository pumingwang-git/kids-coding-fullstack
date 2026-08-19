"""学生任务页必须消费服务端下发的状态文案，新增页面时同步更新清单。"""
from pathlib import Path

from app.student_tasks import EXAM_PHASE_LABELS, HOMEWORK_PHASE_LABELS, PRACTICE_PHASE_LABELS


VUE_DIR = Path(__file__).resolve().parents[3] / "前端程序" / "study-blog-vue" / "src"
# 新增学生端任务页面或 service 时，必须加入此处，否则静态守卫不会检查新文件。
STUDENT_TASK_FILES = (
    "views/TasksHome.vue", "views/PracticeCenter.vue", "views/HomeworkCenter.vue",
    "views/ExamCenter.vue", "services/studentTasks.js",
)


def test_student_task_guard_covers_every_task_page():
    expected = {"views/TasksHome.vue", "services/studentTasks.js"}
    expected |= {f"views/{path.name}" for path in (VUE_DIR / "views").glob("*Center.vue")}
    assert expected <= set(STUDENT_TASK_FILES)


def test_student_task_pages_do_not_hardcode_server_status_labels():
    source = "\n".join((VUE_DIR / path).read_text(encoding="utf-8") for path in STUDENT_TASK_FILES)
    for label in set(HOMEWORK_PHASE_LABELS.values()) | set(PRACTICE_PHASE_LABELS.values()) | set(EXAM_PHASE_LABELS.values()):
        assert label not in source
