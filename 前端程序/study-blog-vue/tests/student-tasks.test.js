// @vitest-environment jsdom
import { mount } from "@vue/test-utils";
import { afterEach, describe, expect, it, vi } from "vitest";
import PracticeCenter from "../src/views/PracticeCenter.vue";
import HomeworkCenter from "../src/views/HomeworkCenter.vue";
import ExamCenter from "../src/views/ExamCenter.vue";
import TasksHome from "../src/views/TasksHome.vue";
import {
  fetchExamTasks,
  fetchHomeworkTasks,
  fetchPracticeQueue,
  fetchPracticeTasks,
  fetchTaskOverview,
} from "../src/services/studentTasks";

vi.mock("../src/services/studentTasks", () => ({
  fetchPracticeQueue: vi.fn(),
  fetchPracticeTasks: vi.fn(),
  fetchHomeworkTasks: vi.fn(),
  fetchExamTasks: vi.fn(),
  fetchTaskOverview: vi.fn(),
}));
vi.mock("vue-router", async (importOriginal) => ({
  ...(await importOriginal()), useRoute: () => ({ params: { areaKey: "kids" } }),
}));

const route = { params: { areaKey: "kids" } };
const global = { stubs: { RouterLink: { template: "<a :href=\"to\"><slot /></a>", props: ["to"] }, AppIcon: true }, mocks: { $route: route } };
const item = {
  source_type: "lesson_practice",
  source_id: 7,
  scope: { key: "lesson_practice:7", title: "变量练习" },
  phase_label: "来自接口",
  segment: "due_48h",
  attempts_left: null,
  origin: { course_title: "Python", section_title: "基础", lesson_title: "变量" },
  entry: { kind: "lesson_practice", lesson_id: 12, block_id: 7 },
  tries: 1,
};

const scratchHomework = { ...item, source_type: "lesson_scratch", source_id: 7, entry: { kind: "lesson_scratch", lesson_id: 12, block_id: 7 } };

describe("学生任务页面", () => {
  afterEach(() => vi.clearAllMocks());

  it("练习页先显示加载态，再渲染入口", async () => {
    fetchPracticeQueue.mockResolvedValue({
      current: { ...item, reason_label: "接口推荐" },
      upcoming: [],
      counts: { done: 0 },
    });
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

  // Scratch 作业没有答卷页：它的落点是课时里那一块。曾经作业页无条件拼
  // /learn/x/homework/y（那条路由渲染的是答卷页 ExamView），总览却落到课时播放器——
  // 同一条任务两个落点。两个用例一起盯着，缺一个都测不出「不一致」这件事本身。
  it("作业页把 Scratch 作业送回课时里那一块", async () => {
    fetchHomeworkTasks.mockResolvedValue({ items: [scratchHomework], counts: { due_48h: 1 } });
    const wrapper = mount(HomeworkCenter, { global });
    await vi.waitFor(() => expect(wrapper.text()).toContain("变量练习"));
    expect(wrapper.find("a").attributes("href")).toBe("/learn/12?block=7");
  });

  it("同一条 Scratch 作业在总览和作业页落点一致", async () => {
    fetchHomeworkTasks.mockResolvedValue({ items: [scratchHomework], counts: { due_48h: 1 } });
    fetchTaskOverview.mockResolvedValue({
      in_progress: { items: [scratchHomework] }, due_soon: { items: [] },
      to_review: { items: [] }, unfinished: { items: [] }, next_up: { items: [] },
    });
    const board = mount(HomeworkCenter, { global });
    const home = mount(TasksHome, { global });
    await vi.waitFor(() => expect(board.text()).toContain("变量练习"));
    await vi.waitFor(() => expect(home.text()).toContain("变量练习"));
    expect(home.find("a").attributes("href")).toBe(board.find("a").attributes("href"));
  });

  it("试卷作业仍然走答卷页", async () => {
    fetchHomeworkTasks.mockResolvedValue({
      items: [{ ...item, source_type: "lesson_homework", entry: { kind: "lesson_homework", lesson_id: 12, block_id: 7 } }],
      counts: { due_48h: 1 },
    });
    const wrapper = mount(HomeworkCenter, { global });
    await vi.waitFor(() => expect(wrapper.text()).toContain("变量练习"));
    expect(wrapper.find("a").attributes("href")).toBe("/learn/12/homework/7");
  });

  it("总览只渲染有内容的分组并跳转到任务入口", async () => {
    fetchTaskOverview.mockResolvedValue({ in_progress: { items: [{ ...item, entry: { kind: "lesson_homework", lesson_id: 12, block_id: 7 } }] }, due_soon: { items: [] }, to_review: { items: [] }, unfinished: { items: [] }, next_up: { items: [] } });
    const wrapper = mount(TasksHome, { global });
    await vi.waitFor(() => expect(wrapper.text()).toContain("正在进行"));
    expect(wrapper.text()).not.toContain("即将截止");
    expect(wrapper.find("a").attributes("href")).toBe("/learn/12/homework/7");
  });

  it("换一题只调整当前会话队列，不发出新请求", async () => {
    fetchPracticeQueue.mockResolvedValue({
      current: { ...item, scope: { title: "第一题" }, reason_label: "接口原因一" },
      upcoming: [{ ...item, source_id: 8, scope: { title: "第二题" }, reason_label: "接口原因二" }],
      counts: { done: 0 },
    });
    const wrapper = mount(PracticeCenter, { global });
    await vi.waitFor(() => expect(wrapper.text()).toContain("第一题"));
    await wrapper.get(".task-queue-current button").trigger("click");
    expect(wrapper.text()).toContain("第二题");
    expect(fetchPracticeQueue).toHaveBeenCalledTimes(1);
    expect(fetchPracticeTasks).not.toHaveBeenCalled();
  });

  it("练过的题默认不请求，展开时才请求一次", async () => {
    fetchPracticeQueue.mockResolvedValue({
      current: { ...item, reason_label: "接口原因" }, upcoming: [], counts: { done: 3 },
    });
    fetchPracticeTasks.mockResolvedValue({ items: [] });
    const wrapper = mount(PracticeCenter, { global });
    await vi.waitFor(() => expect(wrapper.text()).toContain("练过的题（3）"));
    expect(fetchPracticeTasks).not.toHaveBeenCalled();
    await wrapper.get(".task-completed-toggle").trigger("click");
    expect(fetchPracticeTasks).toHaveBeenCalledTimes(1);
  });

  it("作业段头使用 counts，逾期项不进入主线", async () => {
    fetchHomeworkTasks.mockResolvedValue({
      items: [
        { ...item, source_id: 1, scope: { title: "主线作业" }, segment: "due_48h" },
        { ...item, source_id: 2, scope: { title: "逾期作业" }, segment: "overdue" },
      ],
      counts: { due_48h: 9, overdue: 1 },
    });
    const wrapper = mount(HomeworkCenter, { global });
    await vi.waitFor(() => expect(wrapper.text()).toContain("48 小时内（9）"));
    expect(wrapper.get(".task-timeline-main").text()).toContain("主线作业");
    expect(wrapper.get(".task-timeline-main").text()).not.toContain("逾期作业");
    expect(wrapper.text()).toContain("有 1 份作业过了截止时间");
  });
});
