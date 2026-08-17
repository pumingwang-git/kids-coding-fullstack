// @vitest-environment jsdom
import { describe, expect, it } from "vitest";
import { mount } from "@vue/test-utils";
import { nextTick } from "vue";
import QuestionCoding from "../src/components/exam/QuestionCoding.vue";

if (!Range.prototype.getClientRects) {
  Range.prototype.getClientRects = () => ({ length: 0, item: () => null });
  Range.prototype.getBoundingClientRect = () => ({ left: 0, right: 0, top: 0, bottom: 0 });
}

function question(last_code = "int main() {\nreturn 0;\n}") {
  return {
    problem_id_no: "P1",
    type: "programming",
    sub_type: "cpp",
    score: 50,
    stem: "test",
    programming: { samples: [] },
    last_code,
  };
}

function editor(wrapper) {
  return wrapper.get(".cm-content").element;
}

function press(element, init) {
  const event = new KeyboardEvent("keydown", { bubbles: true, cancelable: true, ...init });
  element.dispatchEvent(event);
  return event;
}

function mountEditor(props = {}) {
  return mount(QuestionCoding, {
    props: { question: question(), ...props },
    global: {
      stubs: {
        ExamModal: { template: "<div><slot /></div>" },
        MarkdownBody: { template: "<div />" },
        SubmissionDetail: { template: "<div />" },
      },
    },
  });
}

describe("编程器快捷键", () => {
  it("Shift+Alt+F 整理整份代码的缩进", async () => {
    const wrapper = mountEditor();
    const event = press(editor(wrapper), {
      key: "f",
      code: "KeyF",
      shiftKey: true,
      altKey: true,
    });
    await nextTick();

    expect(event.defaultPrevented).toBe(true);
    expect(wrapper.emitted("draft-change").at(-1)[0].code).toBe("int main() {\n  return 0;\n}");
  });

  it("Ctrl+Enter 仅提交判题，不插入空行", async () => {
    const wrapper = mountEditor();
    press(editor(wrapper), { key: "Enter", ctrlKey: true });
    await nextTick();

    expect(wrapper.emitted("run")).toHaveLength(1);
    expect(wrapper.emitted("run")[0][0].kind).toBe("submit");
    expect(wrapper.emitted("draft-change")).toBeUndefined();
    wrapper.emitted("run")[0][0].reject(new Error("stop"));
  });

  it("Tab 与 Shift+Tab 分别缩进、反缩进当前行", async () => {
    const wrapper = mountEditor({ question: question("int value = 1;") });
    press(editor(wrapper), { key: "Tab" });
    await nextTick();
    expect(wrapper.emitted("draft-change").at(-1)[0].code).toBe("  int value = 1;");

    press(editor(wrapper), { key: "Tab", shiftKey: true });
    await nextTick();
    expect(wrapper.emitted("draft-change").at(-1)[0].code).toBe("int value = 1;");
  });

  it("默认的行注释与块注释键位各只执行一次", async () => {
    const lineWrapper = mountEditor({ question: question("int value = 1;") });
    press(editor(lineWrapper), { key: "/", ctrlKey: true });
    await nextTick();
    expect(lineWrapper.emitted("draft-change")).toHaveLength(1);
    expect(lineWrapper.emitted("draft-change")[0][0].code).toBe("// int value = 1;");

    const blockWrapper = mountEditor({ question: question("int value = 1;") });
    press(editor(blockWrapper), { key: "A", shiftKey: true, altKey: true });
    await nextTick();
    expect(blockWrapper.emitted("draft-change")).toHaveLength(1);
    expect(blockWrapper.emitted("draft-change")[0][0].code).toBe("/*  */int value = 1;");
  });
});
