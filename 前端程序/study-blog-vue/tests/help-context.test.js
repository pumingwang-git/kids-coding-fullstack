import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import {
  lessonBlockHelpContext,
  paperAttemptHelpContext,
  resetHelpState,
  setHelpEnabled,
  helpEnabled,
} from "../src/stores/helpContext";

describe("lesson help context", () => {
  it("attaches the server block id only while a visible practice question is active", () => {
    expect(lessonBlockHelpContext({ id: 42, block_type: "practice", lock_reason: null })).toEqual({
      context_type: "block",
      context_id: 42,
    });
    expect(lessonBlockHelpContext({ id: 43, block_type: "video", lock_reason: null })).toBeNull();
    expect(
      lessonBlockHelpContext({ id: 44, block_type: "practice", lock_reason: "sequential" }),
    ).toBeNull();
  });

  it("never builds a client problem number", () => {
    expect(
      lessonBlockHelpContext({
        id: 45,
        block_type: "practice",
        problem_id_no: "PY-7",
      }),
    ).toEqual({ context_type: "block", context_id: 45 });
  });
});

it("构造作业当前题目的 paper_attempt 上下文", () => {
  expect(paperAttemptHelpContext(12, "HW-7")).toEqual({
    context_type: "attempt",
    context_source: "paper_attempt",
    context_id: 12,
    problem_id_no: "HW-7",
  });
});

it("离开考试后恢复联系老师入口", () => {
  setHelpEnabled(false);
  expect(helpEnabled.value).toBe(false);
  resetHelpState();
  expect(helpEnabled.value).toBe(true);
});

it("ExamView 接线上保留考试状态复位与作答上下文", () => {
  const source = readFileSync(resolve(process.cwd(), "src", "views", "ExamView.vue"), "utf8");
  expect(source).toMatch(/onBeforeUnmount\s*\(\(\)\s*=>\s*\{[\s\S]*?resetHelpState\(\)\s*;?[\s\S]*?\}\)/);
  const currentQuestion = source.slice(source.indexOf("function onCurrentQuestion"), source.indexOf("async function onBack"));
  expect(currentQuestion).toContain("paperAttemptHelpContext(");
  expect(currentQuestion).toContain("setActiveHelpContext(");
});
