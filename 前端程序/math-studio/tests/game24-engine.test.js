import { describe, expect, it } from "vitest";
import { Fraction, classifyPuzzle, generatePuzzle, puzzleKey, solvePuzzle, validateExpression } from "../src/engine/game24";

function number(value, source) {
  return { type: "number", value, source };
}

function operator(value) {
  return { type: "operator", value };
}

describe("24 点精确分数运算", () => {
  it("约分并避免浮点误差", () => {
    expect(new Fraction(6, 8)).toEqual(new Fraction(3, 4));
    expect(new Fraction(1, 3).add(new Fraction(2, 3))).toEqual(new Fraction(1));
    expect(new Fraction(8).divide(new Fraction(3)).toDisplay()).toBe("8/3");
  });
});

describe("24 点题目生成与分类", () => {
  it("区分整数解与需要分数的解", () => {
    expect(classifyPuzzle([1, 2, 3, 4])).toBe("easy");
    expect(classifyPuzzle([4, 5, 8, 10])).toBe("medium");
    expect(classifyPuzzle([3, 3, 8, 8])).toBe("hard");
    expect(solvePuzzle([1, 1, 1, 1])).toBeNull();
  });

  it("过滤无解题和已使用题", () => {
    const excluded = new Set([puzzleKey([1, 2, 3, 4])]);
    const puzzle = generatePuzzle("easy", excluded);
    expect(classifyPuzzle(puzzle)).toBe("easy");
    expect(excluded.has(puzzleKey(puzzle))).toBe(false);
  });
});

describe("24 点算式校验", () => {
  it("接受四个数字各用一次的正确算式", () => {
    const tokens = [number(1, 0), operator("*"), number(2, 1), operator("*"), number(3, 2), operator("*"), number(4, 3)];
    expect(validateExpression(tokens, [1, 2, 3, 4]).ok).toBe(true);
  });

  it("拒绝错误结果、漏用数字和非法表达式", () => {
    const wrong = [number(1, 0), operator("+"), number(2, 1), operator("+"), number(3, 2), operator("+"), number(4, 3)];
    expect(validateExpression(wrong, [1, 2, 3, 4]).kind).toBe("wrong");
    expect(validateExpression(wrong.slice(0, 5), [1, 2, 3, 4]).kind).toBe("error");
    const invalid = [number(1, 0), operator("+"), operator("*"), number(2, 1), number(3, 2), number(4, 3)];
    expect(validateExpression(invalid, [1, 2, 3, 4]).kind).toBe("error");
  });
});
