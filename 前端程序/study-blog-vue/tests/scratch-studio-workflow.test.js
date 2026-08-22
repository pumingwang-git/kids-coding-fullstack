import {describe, expect, it} from "vitest";
import {capabilitiesFor} from "../../scratch-studio/src/gui/studioCapabilities.js";
import {
  canViewTeacherDemo,
  submitActionFor,
} from "../../scratch-studio/src/components/challengeActions.js";
import {subscribeProjectTitle} from "../../scratch-studio/src/gui/projectTitle.js";

describe("Scratch 作业能力边界", () => {
  it("作业关闭文件、改名与 Debug；自由创作保留它们", () => {
    expect(capabilitiesFor("challenge")).toMatchObject({
      canManageFiles: false,
      canEditTitle: false,
      showDebug: false,
    });
    expect(capabilitiesFor("free")).toMatchObject({
      canManageFiles: true,
      canEditTitle: true,
      showDebug: true,
    });
  });

  it("未保存不能提交；未通过和退回保持主提交；通过后降级为再提交", () => {
    expect(submitActionFor(null, false, false)).toMatchObject({
      label: "提交作品",
      primary: true,
      disabled: true,
      title: "请先保存作品",
    });
    expect(submitActionFor({submission_status: "failed"}, true, false)).toMatchObject({
      label: "提交作品",
      primary: true,
      disabled: false,
    });
    expect(submitActionFor({submission_status: "returned"}, true, false)).toMatchObject({
      label: "提交作品",
      primary: true,
      disabled: false,
    });
    expect(submitActionFor({submission_status: "passed"}, true, false)).toMatchObject({
      label: "再提交",
      primary: false,
      disabled: false,
    });
  });

  it("示范项目只有服务端开放且具有本页地址时才能显示入口", () => {
    expect(canViewTeacherDemo({available: false}, "?mode=student_demo")).toBe(false);
    expect(canViewTeacherDemo({available: true}, null)).toBe(false);
    expect(canViewTeacherDemo({available: true}, "?mode=student_demo")).toBe(true);
  });

  it("标题订阅建立前已有的服务端标题会立即同步", () => {
    let title = "原作品标题";
    let listener = null;
    const store = {
      getState: () => ({scratchGui: {projectTitle: title}}),
      subscribe: (next) => {
        listener = next;
        return () => { listener = null; };
      },
    };
    const observed = [];
    const unsubscribe = subscribeProjectTitle(store, (next) => observed.push(next));

    expect(observed).toEqual(["原作品标题"]);
    title = "用户修改后的标题";
    listener();
    expect(observed).toEqual(["原作品标题", "用户修改后的标题"]);
    unsubscribe();
    expect(listener).toBeNull();
  });
});
