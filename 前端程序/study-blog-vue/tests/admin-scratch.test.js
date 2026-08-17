// @vitest-environment jsdom
// Scratch 管理端护栏测试（任务书 21c）：纯逻辑（块配置判定/载荷/预览 URL/表单校验）
// + 契约 mock 的关键行为（CRUD、发布校验、保存冲突、失败开关、块与挑战状态联动）。
import { beforeEach, describe, expect, it } from "vitest";
import {
  RULE_TYPES,
  buildChallengePayload,
  publishChecks,
  ruleToForm,
  ruleTypeHelp,
  ruleTypeLabel,
  scratchBlockConfigured,
  scratchBlockMeta,
  scratchDetailPayload,
  studioDemoUrl,
  studioPreviewBase,
  studioPreviewUrl,
  studioStarterUrl,
} from "../public/admin/admin-scratch-core.js";
import { blocksRequest, scratchRequest, setScratchMock, setScratchMockFail } from "../public/admin/admin-scratch-api.js";

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
  setScratchMock(true);
  setScratchMockFail(false);
});

describe("scratch 内容块纯逻辑", () => {
  it("未绑定已发布挑战一律「待配置」", () => {
    expect(scratchBlockConfigured(null)).toBe(false);
    expect(scratchBlockConfigured({ challenge_id: null })).toBe(false);
    expect(scratchBlockConfigured({ challenge_id: 1, challenge_status: "draft" })).toBe(false);
    expect(scratchBlockConfigured({ challenge_id: 1, challenge_status: "withdrawn" })).toBe(false);
    expect(scratchBlockConfigured({ challenge_id: 1, challenge_status: "published" })).toBe(true);
  });

  it("块 meta 反映绑定与发布状态", () => {
    expect(scratchBlockMeta({})).toContain("尚未绑定");
    expect(scratchBlockMeta({ challenge_id: 2, challenge_status: "draft", challenge_title: "接苹果" })).toContain("未发布");
    expect(scratchBlockMeta({ challenge_id: 1, challenge_status: "published", challenge_title: "小猫" })).toContain("已绑定");
  });

  it("保存载荷只带 challenge_id，不回传展示快照", () => {
    expect(scratchDetailPayload({ challenge_id: 7, challenge_title: "x", challenge_status: "draft" })).toEqual({ scratch: { challenge_id: 7 } });
    expect(scratchDetailPayload({ challenge_id: null })).toEqual({ scratch: { challenge_id: null } });
  });

  it("管理员预览 URL：只读模式、只接受同源基地址", () => {
    const url = studioPreviewUrl(5, { extra: { scratch_mock: "1" } });
    expect(url).toContain("/scratch-studio/");
    expect(url).toContain("mode=admin_preview");
    expect(url).toContain("challenge_id=5");
    expect(url).toContain("scratch_mock=1");
    expect(studioPreviewUrl(5, { studioBase: "https://evil.example/x" })).not.toContain("evil.example");
  });

  it("两个录制入口各带明确的 authoring_target，不靠按钮文字区分", () => {
    // 缺省时 Studio 按 starter 处理，但入口仍必须显式写出来：将来加第三种目标，
    // 漏参数的入口会静默地录到初始项目上去。
    const starter = studioStarterUrl(5, { protocol: "https:", hostname: "course.example", port: "" });
    const demo = studioDemoUrl(5, { protocol: "https:", hostname: "course.example", port: "" });
    expect(starter).toContain("authoring_target=starter");
    expect(demo).toContain("authoring_target=demo");
    expect(starter).not.toContain("authoring_target=demo");
    expect(demo).toContain("mode=admin_preview");
    expect(demo).toContain("challenge_id=5");
  });

  it("本地管理站点应跳转独立 Studio 开发服务，不落入 Vite 首页", () => {
    const localBase = studioPreviewBase({ protocol: "http:", hostname: "localhost", port: "5174" });
    expect(localBase).toBe("http://localhost:8602/");
    expect(studioPreviewUrl(2, { studioBase: localBase })).toContain("http://localhost:8602/?mode=admin_preview");
    expect(studioPreviewBase({ protocol: "https:", hostname: "course.example", port: "" })).toBe("/scratch-studio/");
  });
});

describe("挑战表单校验", () => {
  it("标题必填；规则参数数值化；提示按行拆分去空", () => {
    const noTitle = buildChallengePayload({ title: " ", rules: [] });
    expect(noTitle.errors.length).toBeGreaterThan(0);

    const { errors, payload } = buildChallengePayload({
      title: "接苹果",
      instructions_md: "说明",
      hints_text: "第一条\n\n  第二条  \n",
      allowed_extensions: ["pen", "hack_ext"],
      rules: [{ type: "min_sprites", params: { count: "2" } }],
    });
    expect(errors).toEqual([]);
    expect(payload.hints).toEqual(["第一条", "第二条"]);
    expect(payload.allowed_extensions).toEqual(["pen"]); // 白名单外的扩展被剔除
    expect(payload.rules).toEqual([{ type: "min_sprites", count: 2 }]); // 扁平，与后端 rules_json 契约一致
  });

  it("规则字典覆盖后端全部 15 种类型，且示例可原样通过 payload 归一化", () => {
    // 与后端 app/scratch_rules.py 的 _EVALUATORS 一一对应；多一种少一种都算契约漂移。
    const expected = [
      "require_opcode", "forbid_opcode", "require_after_hat", "require_input_value",
      "require_say_text", "min_sprites", "min_variables", "require_variable",
      "require_broadcast", "sprite_start_position", "require_extension",
      "no_dead_code", "broadcast_pairing", "require_initialization", "require_structure",
    ];
    expect(RULE_TYPES.map((t) => t.key).sort()).toEqual(expected.sort());
    for (const type of RULE_TYPES) {
      expect(type.label).toBeTruthy();
      expect(type.desc).toBeTruthy();
      expect(ruleTypeHelp(type.key)).toContain(type.desc);
      // 示例参数经 buildChallengePayload 归一化后仍是合法扁平规则
      const { errors, payload } = buildChallengePayload({
        title: "t", rules: [{ type: type.key, params: { ...type.example } }],
      });
      expect(errors).toEqual([]);
      expect(payload.rules[0].type).toBe(type.key);
      expect(payload.rules[0].params).toBeUndefined(); // 不允许嵌套 params
    }
    expect(ruleTypeLabel("no_dead_code")).toBe("不留没接上的积木");
    expect(ruleTypeLabel("unknown_type")).toBe("unknown_type");
  });

  it("ruleToForm 把后端扁平规则还原成表单状态，label 不进参数", () => {
    expect(ruleToForm({ type: "require_say_text", text: "你好", label: "说你好" }))
      .toEqual({ type: "require_say_text", params: { text: "你好" } });
    expect(ruleToForm({ type: "min_sprites", count: 2 }))
      .toEqual({ type: "min_sprites", params: { count: 2 } });
  });

  it("list/json 参数归一化：逗号分隔成数组，坏 JSON 保存前拦下", () => {
    const ok = buildChallengePayload({
      title: "t",
      rules: [{ type: "require_initialization", params: { attributes: "position, variable:分数" } }],
    });
    expect(ok.errors).toEqual([]);
    expect(ok.payload.rules).toEqual([
      { type: "require_initialization", attributes: ["position", "variable:分数"] },
    ]);

    const bad = buildChallengePayload({
      title: "t",
      rules: [{ type: "require_structure", params: { pattern: "{not json" } }],
    });
    expect(bad.errors.length).toBeGreaterThan(0);
    expect(bad.errors[0]).toContain("JSON");

    const good = buildChallengePayload({
      title: "t",
      rules: [{ type: "require_structure", params: { pattern: '{"opcode":"control_repeat"}' } }],
    });
    expect(good.errors).toEqual([]);
    expect(good.payload.rules[0].pattern).toEqual({ opcode: "control_repeat" });
  });

  it("发布校验：缺初始项目或规则不能发布", () => {
    expect(publishChecks({ title: "t", instructions_md: "i", has_starter: false, rules: [{}] })).toContain("初始项目（.sb3）");
    expect(publishChecks({ title: "t", instructions_md: "i", has_starter: true, rules: [] })).toContain("至少一条声明式规则");
    expect(publishChecks({ title: "t", instructions_md: "i", has_starter: true, rules: [{}] })).toEqual([]);
  });
});

describe("契约 mock：挑战生命周期", () => {
  it("种子数据可列出；新建的是草稿", async () => {
    const list = await scratchRequest("/scratch/challenges");
    expect(list.items.length).toBeGreaterThanOrEqual(2);
    const created = await scratchRequest("/scratch/challenges", { method: "POST", body: JSON.stringify({ title: "新挑战" }) });
    expect(created.status).toBe("draft");
    expect(created.version).toBe(1);
  });

  it("内容不全时发布被拒（不弹成功）", async () => {
    const created = await scratchRequest("/scratch/challenges", { method: "POST", body: JSON.stringify({ title: "半成品" }) });
    await expect(scratchRequest(`/scratch/challenges/${created.id}/publish`, { method: "POST", body: "{}" })).rejects.toThrow("不能发布");
  });

  it("base_version 过期 = 保存冲突", async () => {
    const created = await scratchRequest("/scratch/challenges", { method: "POST", body: JSON.stringify({ title: "冲突演示" }) });
    const payload = { title: "改", instructions_md: "", allowed_extensions: [], hints: [], rules: [] };
    await scratchRequest(`/scratch/challenges/${created.id}`, { method: "PUT", body: JSON.stringify({ ...payload, base_version: 1 }) });
    await expect(
      scratchRequest(`/scratch/challenges/${created.id}`, { method: "PUT", body: JSON.stringify({ ...payload, base_version: 1 }) }),
    ).rejects.toThrow("保存冲突");
  });

  it("edit_seq 随保存递增、version 不动；拉新 edit_seq 重试即可强制覆盖", async () => {
    // 与真实后端同口径：base_version 比对的是编辑序号 edit_seq，不是发布版次 version。
    const created = await scratchRequest("/scratch/challenges", { method: "POST", body: JSON.stringify({ title: "锁演示" }) });
    expect(created.edit_seq).toBe(1);
    expect(created.version).toBe(1);
    const payload = { title: "改", instructions_md: "", allowed_extensions: [], hints: [], rules: [] };

    const saved = await scratchRequest(`/scratch/challenges/${created.id}`, { method: "PUT", body: JSON.stringify({ ...payload, base_version: 1 }) });
    expect(saved.edit_seq).toBe(2);
    expect(saved.version).toBe(1); // 草稿编辑不动发布版次

    // 连续保存：用响应里的新 edit_seq，不误报 409
    const again = await scratchRequest(`/scratch/challenges/${created.id}`, { method: "PUT", body: JSON.stringify({ ...payload, base_version: saved.edit_seq }) });
    expect(again.edit_seq).toBe(3);

    // 另一标签页已保存过：本地旧 edit_seq 409；重新拉取后重试同一个 PUT 成功（强制覆盖路径）
    await expect(
      scratchRequest(`/scratch/challenges/${created.id}`, { method: "PUT", body: JSON.stringify({ ...payload, base_version: 1 }) }),
    ).rejects.toThrow("保存冲突");
    const latest = await scratchRequest(`/scratch/challenges/${created.id}`);
    const forced = await scratchRequest(`/scratch/challenges/${created.id}`, { method: "PUT", body: JSON.stringify({ ...payload, base_version: latest.edit_seq }) });
    expect(forced.edit_seq).toBe(latest.edit_seq + 1);
  });

  it("失败开关：所有请求报 500 文案", async () => {
    setScratchMockFail(true);
    await expect(scratchRequest("/scratch/challenges")).rejects.toThrow("模拟 API 失败");
  });

  it("非 .sb3 上传被拒", async () => {
    await expect(
      scratchRequest("/scratch/challenges/1/starter-project", { method: "POST", body: JSON.stringify({ file_name: "a.exe", size: 10 }) }),
    ).rejects.toThrow(".sb3");
  });
});

describe("契约 mock：内容块与挑战状态联动", () => {
  it("scratch 块创建后随挑战状态回填快照；撤回挑战 → 块回到待配置", async () => {
    const block = await blocksRequest("/lessons/9/blocks", {
      method: "POST",
      body: JSON.stringify({ block_type: "scratch", title: "Scratch 编程挑战", required: true, unlock_rule: "free", detail: { scratch: { challenge_id: 1 } } }),
    });
    expect(block.scratch.challenge_status).toBe("published");
    expect(scratchBlockConfigured(block.scratch)).toBe(true);

    const list = await blocksRequest("/lessons/9/blocks");
    expect(list.blocks.some((b) => b.block_type === "scratch")).toBe(true);

    await scratchRequest("/scratch/challenges/1/withdraw", { method: "POST", body: "{}" });
    const after = await blocksRequest("/lessons/9/blocks");
    const rebound = after.blocks.find((b) => b.block_type === "scratch");
    expect(rebound.scratch.challenge_status).toBe("draft");
    expect(scratchBlockConfigured(rebound.scratch)).toBe(false);
  });

  it("mock 块可排序、删除", async () => {
    const mk = (title) =>
      blocksRequest("/lessons/8/blocks", {
        method: "POST",
        body: JSON.stringify({ block_type: "scratch", title, required: true, unlock_rule: "free", detail: { scratch: { challenge_id: 1 } } }),
      });
    const a = await mk("A");
    const b = await mk("B");
    await blocksRequest("/lessons/8/blocks/reorder", { method: "POST", body: JSON.stringify({ ids: [b.id, a.id] }) });
    const list = await blocksRequest("/lessons/8/blocks");
    expect(list.blocks[0].title).toBe("B");
    await blocksRequest(`/lesson-blocks/${b.id}`, { method: "DELETE" });
    const after = await blocksRequest("/lessons/8/blocks");
    expect(after.blocks.filter((x) => x.block_type === "scratch")).toHaveLength(1);
  });

  it("学生作品只读列表支持按挑战过滤", async () => {
    const all = await scratchRequest("/scratch/submissions");
    expect(all.total).toBeGreaterThanOrEqual(3);
    const filtered = await scratchRequest("/scratch/submissions?challenge_id=2");
    expect(filtered.total).toBe(0);
    const detail = await scratchRequest("/scratch/submissions/1");
    expect(detail.snapshot.revision_no).toBe(5);
  });

  it("已发布挑战复制为新的草稿，不带学生提交", async () => {
    const copied = await scratchRequest("/scratch/challenges/1/duplicate", { method: "POST", body: "{}" });
    expect(copied.status).toBe("draft");
    expect(copied.has_starter).toBe(true);
    expect(copied.rules.length).toBeGreaterThan(0);
    expect(copied.submission_count).toBe(0);
  });
});
