// @vitest-environment jsdom
import { mount } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import PracticeCenter from "../src/views/PracticeCenter.vue";
import HomeworkCenter from "../src/views/HomeworkCenter.vue";
import ExamCenter from "../src/views/ExamCenter.vue";
import TasksHome from "../src/views/TasksHome.vue";
import { fetchExamTasks, fetchHomeworkTasks, fetchPracticeTasks, fetchTaskOverview } from "../src/services/studentTasks";

vi.mock("../src/services/studentTasks", () => ({
  fetchPracticeTasks: vi.fn(), fetchHomeworkTasks: vi.fn(), fetchExamTasks: vi.fn(), fetchTaskOverview: vi.fn(),
}));
vi.mock("vue-router", async (importOriginal) => ({
  ...(await importOriginal()), useRoute: () => ({ params: { areaKey: "kids" } }),
}));

const route = { params: { areaKey: "kids" } };
const global = { stubs: { RouterLink: { template: "<a :href=\"to\"><slot /></a>", props: ["to"] }, AppIcon: true }, mocks: { $route: route } };
const item = { source_type: "lesson_practice", source_id: 7, scope: { key: "lesson_practice:7", title: "变量练习" }, phase_label: "来自接口", origin: { course_title: "Python", lesson_title: "变量" }, entry: { kind: "lesson_practice", lesson_id: 12, block_id: 7 }, tries: 1 };

describe("学生任务页面", () => {
  afterEach(() => vi.clearAllMocks());

  it("练习页先显示加载态，再渲染入口", async () => {
    fetchPracticeTasks.mockResolvedValue({ items: [item] });
    const wrapper = mount(PracticeCenter, { global });
    expect(wrapper.text()).toContain("正在加载练习");
    await vi.waitFor(() => expect(wrapper.text()).toContain("变量练习"));
    expect(wrapper.find("a").attributes("href")).toBe("/learn/12");
  });

  it("作业页在空集时给出真实空状态", async () => {
    fetchHomeworkTasks.mockResolvedValue({ items: [] });
    const wrapper = mount(HomeworkCenter, { global });
    await vi.waitFor(() => expect(wrapper.text()).toContain("暂时没有作业"));
  });

  it("考试页使用 token 入口", async () => {
    fetchExamTasks.mockResolvedValue({ items: [{ ...item, source_type: "exam_link", source_id: 9, entry: { kind: "exam_link", token: "safe-token" } }] });
    const wrapper = mount(ExamCenter, { global });
    await vi.waitFor(() => expect(wrapper.text()).toContain("变量练习"));
    expect(wrapper.find("a").attributes("href")).toBe("/exam/safe-token");
  });

  it("总览只渲染有内容的分组并跳转到任务入口", async () => {
    fetchTaskOverview.mockResolvedValue({ in_progress: { items: [{ ...item, entry: { kind: "lesson_homework", lesson_id: 12, block_id: 7 } }] }, due_soon: { items: [] }, to_review: { items: [] }, unfinished: { items: [] }, next_up: { items: [] } });
    const wrapper = mount(TasksHome, { global });
    await vi.waitFor(() => expect(wrapper.text()).toContain("正在进行"));
    expect(wrapper.text()).not.toContain("即将截止");
    expect(wrapper.find("a").attributes("href")).toBe("/learn/12/homework/7");
  });
});
