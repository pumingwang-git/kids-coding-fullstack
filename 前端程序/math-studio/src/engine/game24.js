const OPERATORS = ["+", "-", "*", "/"];

const OPERATOR_LABELS = { "+": "+", "-": "−", "*": "×", "/": "÷" };

export const DIFFICULTY_RANGES = {
  easy: [1, 9],
  medium: [1, 10],
  hard: [1, 13],
};

const FALLBACK_PUZZLES = {
  easy: [[1, 2, 3, 4], [2, 3, 4, 5], [2, 4, 6, 8]],
  medium: [[4, 5, 8, 10], [2, 4, 8, 10], [3, 5, 7, 10]],
  hard: [[3, 3, 8, 8], [1, 5, 5, 5], [1, 3, 4, 6]],
};

function gcd(a, b) {
  let left = Math.abs(a);
  let right = Math.abs(b);
  while (right) [left, right] = [right, left % right];
  return left || 1;
}

export class Fraction {
  constructor(numerator, denominator = 1) {
    if (denominator === 0) throw new Error("不能除以 0");
    const sign = denominator < 0 ? -1 : 1;
    const divisor = gcd(numerator, denominator);
    this.numerator = (sign * numerator) / divisor;
    this.denominator = Math.abs(denominator) / divisor;
  }

  add(other) {
    return new Fraction(
      this.numerator * other.denominator + other.numerator * this.denominator,
      this.denominator * other.denominator,
    );
  }
  subtract(other) {
    return new Fraction(
      this.numerator * other.denominator - other.numerator * this.denominator,
      this.denominator * other.denominator,
    );
  }
  multiply(other) {
    return new Fraction(this.numerator * other.numerator, this.denominator * other.denominator);
  }
  divide(other) {
    if (other.numerator === 0) throw new Error("不能除以 0");
    return new Fraction(this.numerator * other.denominator, this.denominator * other.numerator);
  }
  equals(other) {
    return this.numerator === other.numerator && this.denominator === other.denominator;
  }
  isInteger() {
    return this.denominator === 1;
  }
  toDisplay() {
    return this.denominator === 1 ? String(this.numerator) : `${this.numerator}/${this.denominator}`;
  }
}

function calculate(left, right, operator) {
  if (operator === "+") return left.add(right);
  if (operator === "-") return left.subtract(right);
  if (operator === "*") return left.multiply(right);
  return left.divide(right);
}

function solveItems(items, integerOnly) {
  if (items.length === 1) {
    return items[0].value.equals(new Fraction(24)) ? items[0].expression : null;
  }
  for (let leftIndex = 0; leftIndex < items.length; leftIndex += 1) {
    for (let rightIndex = 0; rightIndex < items.length; rightIndex += 1) {
      if (leftIndex === rightIndex) continue;
      const remaining = items.filter((_, index) => index !== leftIndex && index !== rightIndex);
      const left = items[leftIndex];
      const right = items[rightIndex];
      for (const operator of OPERATORS) {
        if ((operator === "+" || operator === "*") && leftIndex > rightIndex) continue;
        try {
          const value = calculate(left.value, right.value, operator);
          if (integerOnly && !value.isInteger()) continue;
          const result = solveItems(
            [...remaining, { value, expression: `(${left.expression}${OPERATOR_LABELS[operator]}${right.expression})` }],
            integerOnly,
          );
          if (result) return result;
        } catch {
          // Division by zero is not a valid branch.
        }
      }
    }
  }
  return null;
}

export function solvePuzzle(numbers) {
  if (!Array.isArray(numbers) || numbers.length !== 4) return null;
  const items = numbers.map((number) => ({ value: new Fraction(number), expression: String(number) }));
  const integerExpression = solveItems(items, true);
  if (integerExpression) return { expression: integerExpression, integerOnly: true };
  const expression = solveItems(items, false);
  return expression ? { expression, integerOnly: false } : null;
}

export function classifyPuzzle(numbers) {
  const solution = solvePuzzle(numbers);
  if (!solution) return null;
  if (!solution.integerOnly) return "hard";
  const max = Math.max(...numbers);
  if (max <= 9) return "easy";
  if (max <= 10) return "medium";
  return null;
}

export function puzzleKey(numbers) {
  return [...numbers].sort((a, b) => a - b).join(",");
}

export function generatePuzzle(difficulty, excluded = new Set()) {
  const [minimum, maximum] = DIFFICULTY_RANGES[difficulty] || DIFFICULTY_RANGES.easy;
  for (let attempt = 0; attempt < 320; attempt += 1) {
    const numbers = Array.from(
      { length: 4 },
      () => minimum + Math.floor(Math.random() * (maximum - minimum + 1)),
    );
    if (excluded.has(puzzleKey(numbers))) continue;
    if (classifyPuzzle(numbers) === difficulty) return numbers;
  }
  const available = FALLBACK_PUZZLES[difficulty].find((numbers) => !excluded.has(puzzleKey(numbers)));
  return [...(available || FALLBACK_PUZZLES[difficulty][0])];
}

export function tokensToDisplay(tokens) {
  return tokens
    .map((token) => token.type === "number" ? String(token.value) : token.type === "operator" ? OPERATOR_LABELS[token.value] : token.value)
    .join(" ");
}

function parseTokens(tokens) {
  let position = 0;
  const current = () => tokens[position];
  function parseFactor() {
    const token = tokens[position++];
    if (!token) throw new Error("算式还没有写完整");
    if (token.type === "number") return new Fraction(token.value);
    if (token.type === "parenthesis" && token.value === "(") {
      const value = parseExpression();
      const closing = tokens[position];
      if (!closing || closing.type !== "parenthesis" || closing.value !== ")") {
        throw new Error("左右括号没有配对");
      }
      position += 1;
      return value;
    }
    throw new Error("请检查数字和运算符的顺序");
  }
  function parseTerm() {
    let value = parseFactor();
    while (current()?.type === "operator" && ["*", "/"].includes(current().value)) {
      const operator = current().value;
      position += 1;
      value = calculate(value, parseFactor(), operator);
    }
    return value;
  }
  function parseExpression() {
    let value = parseTerm();
    while (current()?.type === "operator" && ["+", "-"].includes(current().value)) {
      const operator = current().value;
      position += 1;
      value = calculate(value, parseTerm(), operator);
    }
    return value;
  }
  if (!tokens.length) throw new Error("先用下面的数字写出算式");
  const value = parseExpression();
  if (position !== tokens.length) throw new Error("请检查数字和运算符的顺序");
  return value;
}

export function validateExpression(tokens, numbers) {
  const usedSources = tokens.filter((token) => token.type === "number").map((token) => token.source).sort((a, b) => a - b);
  if (usedSources.length !== numbers.length || usedSources.some((source, index) => source !== index)) {
    return { ok: false, kind: "error", message: "4 个数字都要用，而且每个只能用一次" };
  }
  try {
    const value = parseTokens(tokens);
    if (!value.equals(new Fraction(24))) {
      return { ok: false, kind: "wrong", message: `这次算得 ${value.toDisplay()}，再调整一下就能到 24` };
    }
    return { ok: true, value, message: "正好等于 24！" };
  } catch (error) {
    return { ok: false, kind: "error", message: error.message || "算式暂时无法计算" };
  }
}
