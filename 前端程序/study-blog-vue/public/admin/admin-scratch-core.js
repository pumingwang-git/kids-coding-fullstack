// Scratch 管理端纯逻辑：内容块判定、挑战表单校验、预览 URL。
// 与 DOM/网络无关，nodes.js / questions.html 的 Scratch 扩展共用，vitest 直接测这里。

// 第一阶段允许扩展白名单（与后端 ScratchChallenge.allowed_extensions 契约一致，
// 见开发文档 21 §5.1：只允许声明式、无硬件/云变量的官方扩展）。
export const EXTENSION_OPTIONS = [
  { key: "pen", label: "画笔" },
  { key: "music", label: "音乐" },
  { key: "videoSensing", label: "视频侦测" },
  { key: "text2speech", label: "文字朗读" },
  { key: "translate", label: "翻译" },
];

// 声明式规则类型。key 与后端 `scratch_rules._EVALUATORS` 的 type 一一对应（15 种）；
// 后端 rules_json 是**扁平**结构（参数与 type 同级），不要用 params 嵌套。
// label = 中文名称；desc = 给老师看的通俗说明（悬停显示）；example = 「添加规则」
// 时自动填入的示例参数。积木 opcode、变量名等专业名词保留英文/原名，不翻译。
export const RULE_TYPES = [
  {
    key: "require_opcode", label: "必须使用指定积木",
    desc: "作品里必须用到某个积木，可要求至少出现几次。常用于保证学生用了本课教的重点积木。",
    example: { opcode: "motion_movesteps", min_count: 1 },
    fields: [
      { key: "opcode", label: "积木 opcode", hint: "积木的英文标识，如 motion_movesteps（移动步数）、control_repeat（重复执行）", placeholder: "如 motion_movesteps" },
      { key: "min_count", label: "至少出现几次", type: "number", hint: "填数字；不填默认为 1", placeholder: "默认 1" },
      { key: "target", label: "限定角色名（可选）", hint: "只检查某个角色时填角色名；不填则检查整个作品", placeholder: "如 小猫；一般留空" },
    ],
  },
  {
    key: "forbid_opcode", label: "禁止使用指定积木",
    desc: "作品里不允许出现某个积木。常用于防止学生用「滑行到 x y」这类一步到位的积木跳过练习目标。",
    example: { opcode: "motion_glidesecstoxy" },
    fields: [
      { key: "opcode", label: "积木 opcode", hint: "要禁用的积木英文标识", placeholder: "如 motion_glidesecstoxy" },
      { key: "target", label: "限定角色名（可选）", hint: "只检查某个角色时填角色名；不填则检查整个作品", placeholder: "一般留空" },
    ],
  },
  {
    key: "require_after_hat", label: "某事件发生后必须使用积木",
    desc: "要求积木接在指定事件帽子下面（含放在循环/条件里面）。最常用：绿旗被点击后要做什么。",
    example: { hat: "event_whenflagclicked", opcode: "motion_movesteps" },
    fields: [
      { key: "hat", label: "事件帽子", hint: "如 event_whenflagclicked（当绿旗被点击）、event_whenbroadcastreceived（当接收到广播）", placeholder: "默认 event_whenflagclicked" },
      { key: "opcode", label: "积木 opcode", hint: "必须接在该事件下的积木英文标识", placeholder: "如 motion_movesteps" },
      { key: "target", label: "限定角色名（可选）", hint: "只检查某个角色时填角色名；不填则检查整个作品", placeholder: "一般留空" },
    ],
  },
  {
    key: "require_input_value", label: "积木参数必须等于指定值",
    desc: "检查某个积木上填的参数是不是要求的值，比如「移动 10 步」里的步数必须是 10。",
    example: { opcode: "motion_movesteps", input: "STEPS", equals: "10" },
    fields: [
      { key: "opcode", label: "积木 opcode", hint: "积木的英文标识", placeholder: "如 motion_movesteps" },
      { key: "input", label: "参数槽名", hint: "参数在积木里的英文槽位名，如 STEPS（步数）、SECS（秒数）", placeholder: "如 STEPS" },
      { key: "equals", label: "要求的值", hint: "参数必须等于的值；数字按数值比较（10 和 10.0 算同一个）", placeholder: "如 10" },
      { key: "target", label: "限定角色名（可选）", hint: "只检查某个角色时填角色名", placeholder: "一般留空" },
    ],
  },
  {
    key: "require_say_text", label: "角色必须说出指定文字",
    desc: "检查「说 / 思考」类积木里出现的文字。默认要一字不差，也可以改成「包含」即可。",
    example: { text: "你好", match: "equals" },
    fields: [
      { key: "text", label: "要说的文字", hint: "学生作品里角色必须说出的那句话", placeholder: "如 你好" },
      { key: "match", label: "匹配方式（可选）", hint: "equals = 一字不差；contains = 包含这句话即可。不填默认 equals", placeholder: "equals 或 contains" },
      { key: "target", label: "限定角色名（可选）", hint: "只检查某个角色时填角色名", placeholder: "一般留空" },
    ],
  },
  {
    key: "min_sprites", label: "至少要有几个角色",
    desc: "作品里的角色数量下限（不算舞台）。适合做「两个角色对话」这类题。",
    example: { count: 2 },
    fields: [
      { key: "count", label: "角色数量", type: "number", hint: "填数字，如 2", placeholder: "如 2" },
    ],
  },
  {
    key: "min_variables", label: "至少要有几个变量",
    desc: "作品里创建的变量数量下限（全局变量和角色私有变量都算）。",
    example: { count: 1 },
    fields: [
      { key: "count", label: "变量数量", type: "number", hint: "填数字，如 1", placeholder: "如 1" },
    ],
  },
  {
    key: "require_variable", label: "必须创建指定变量",
    desc: "作品里必须有某个名字的变量；可选地再检查它的初始值。",
    example: { name: "分数" },
    fields: [
      { key: "name", label: "变量名", hint: "学生在「变量」里创建的名字，如 分数", placeholder: "如 分数" },
      { key: "value", label: "初始值（可选）", hint: "填了就连初始值一起检查；不填只要求变量存在", placeholder: "如 0；一般留空" },
    ],
  },
  {
    key: "require_broadcast", label: "必须创建指定广播消息",
    desc: "作品里必须存在某个名字的广播消息（只查消息存在，不查谁发谁收；要查配对请用「广播要成对」）。",
    example: { name: "开始" },
    fields: [
      { key: "name", label: "广播消息名", hint: "广播消息的名字，如 开始", placeholder: "如 开始" },
    ],
  },
  {
    key: "sprite_start_position", label: "角色初始位置",
    desc: "检查角色保存时摆在舞台上的坐标（不是运行结束后的位置——运行后的结果判不了，会转人工点评）。",
    example: { sprite: "小猫", x: 0, y: 0 },
    fields: [
      { key: "sprite", label: "角色名", hint: "要检查的角色；不填则任意一个角色满足即算通过", placeholder: "如 小猫" },
      { key: "x", label: "x 坐标", type: "number", hint: "舞台横坐标，-240 到 240", placeholder: "如 0" },
      { key: "y", label: "y 坐标", type: "number", hint: "舞台纵坐标，-180 到 180", placeholder: "如 0" },
      { key: "tolerance", label: "允许误差（可选）", type: "number", hint: "坐标差多少以内算对；不填默认为 0（必须精确）", placeholder: "如 10" },
    ],
  },
  {
    key: "require_extension", label: "必须添加指定扩展",
    desc: "作品必须启用某个扩展（如画笔、音乐）。注意先把扩展加进上方「允许的扩展」白名单。",
    example: { name: "pen" },
    fields: [
      { key: "name", label: "扩展名", hint: "pen（画笔）/ music（音乐）/ videoSensing（视频侦测）/ text2speech（文字朗读）/ translate（翻译）", placeholder: "如 pen" },
    ],
  },
  {
    key: "no_dead_code", label: "不留没接上的积木",
    desc: "检查拖出来却没接到任何事件下面的积木（死代码）。帮助学生养成收拾画布的习惯。",
    example: { max_allowed: 0 },
    fields: [
      { key: "max_allowed", label: "最多允许几处", type: "number", hint: "填数字；不填默认为 0（一处都不许有）", placeholder: "默认 0" },
    ],
  },
  {
    key: "broadcast_pairing", label: "广播要成对",
    desc: "发出去的每条广播都要有角色接收，每个「当接收到广播」帽子也要有人发这条广播。专治「发了没人收」和「干等一条不会来的消息」。",
    example: { direction: "both" },
    fields: [
      { key: "direction", label: "检查方向（可选）", hint: "both = 两个方向都查；send = 只查发了没人收；receive = 只查等了没人发。不填默认 both", placeholder: "both / send / receive" },
    ],
  },
  {
    key: "require_initialization", label: "用之前先初始化",
    desc: "作品里用了「移动步数 / 右转 / 将变量增加」这类相对修改积木时，要求在绿旗下面先「移到固定位置 / 面向固定方向 / 将变量设为」一次，避免多点一次绿旗结果就变样。",
    example: { attributes: "position, variable:分数" },
    fields: [
      { key: "attributes", label: "要检查的属性", type: "list", hint: "用逗号分隔多项：position（位置）、direction（方向）、size（大小）、costume（造型）、visible（显示）、variable:变量名", placeholder: "如 position, variable:分数" },
      { key: "hat", label: "事件帽子（可选）", hint: "初始化要求接在哪个事件下；不填默认 event_whenflagclicked（绿旗）", placeholder: "默认绿旗" },
    ],
  },
  {
    key: "require_structure", label: "必须搭出指定嵌套结构",
    desc: "要求作品里出现某种积木套积木的骨架，比如「重复执行里面套一个如果……那么」。进阶规则，结构用 JSON 描述。",
    example: { pattern: '{"opcode":"control_repeat","contains":[{"opcode":"control_if","contains":[{"opcode":"operator_gt"}]}]}' },
    fields: [
      { key: "pattern", label: "结构描述（JSON）", type: "json", hint: '嵌套的积木树：{"opcode":"外层积木","contains":[内层要求…]}，contains 里多项不分先后、都要满足', placeholder: '如 {"opcode":"control_repeat","contains":[{"opcode":"control_if"}]}' },
      { key: "hat", label: "限定事件帽子（可选）", hint: "填了则结构必须接在该事件下面，摆在画布上的死积木不算数", placeholder: "如 event_whenflagclicked；一般留空" },
      { key: "target", label: "限定角色名（可选）", hint: "只检查某个角色时填角色名", placeholder: "一般留空" },
    ],
  },
];

// 后端冻结的规则原文（扁平）→ 表单状态（{type, params}）。type/label 之外
// 的键都是参数；label 是学生可见文案，不进参数表（表单里不编辑 label）。
export function ruleToForm(rule) {
  const params = { ...(rule || {}) };
  delete params.type;
  delete params.label;
  return { type: rule?.type || "", params };
}

export function ruleTypeLabel(key) {
  return RULE_TYPES.find((t) => t.key === key)?.label || key || "未知规则";
}

// 悬停/帮助区用的一句话说明。
export function ruleTypeHelp(key) {
  const type = RULE_TYPES.find((t) => t.key === key);
  if (!type) return null;
  const hints = type.fields.map((f) => `· ${f.label}：${f.hint}`).join("\n");
  return `${type.desc}\n\n参数怎么填：\n${hints}\n\n示例：${JSON.stringify(type.example, null, 0)}`;
}

// ---- 内容块 ----

// 「待配置」口径：没绑挑战，或绑定的挑战不是已发布状态（草稿/已撤回都不算配置完成）。
export function scratchBlockConfigured(scratch) {
  return Boolean(scratch?.challenge_id) && scratch?.challenge_status === "published";
}

export function scratchBlockMeta(scratch) {
  if (!scratch?.challenge_id) return "尚未绑定挑战";
  const title = scratch.challenge_title ? `「${scratch.challenge_title}」` : `#${scratch.challenge_id}`;
  if (scratch.challenge_status === "published") return `已绑定挑战 ${title}`;
  const statusText = { draft: "草稿", archived: "已归档" }[scratch.challenge_status] || scratch.challenge_status || "未知状态";
  return `挑战 ${title} ${statusText}，未发布`;
}

// 保存载荷：块配置只保存 challenge_id（任务书 §固定功能范围 2）。
// title/status 是后端回填的展示快照，前端不回传。
export function scratchDetailPayload(scratch) {
  return { scratch: { challenge_id: Number(scratch?.challenge_id) || null } };
}

// ---- 管理员预览 ----

// Studio 管理员预览模式：只读加载挑战（初始项目 + 规则 + 提示），永不写学生项目。
// 部署时 WorkBuddy 子应用挂在同源 `/scratch-studio/`；本地联调则由独立的 webpack
// dev server 提供（8602）。把端口选择收口在这里，管理页不用猜「当前 Vite 是 5173
// 还是 5174」，也不会误把 Studio 链接交给学习站点的 history fallback。
export function studioPreviewBase(locationLike = globalThis.location) {
  const { protocol, hostname, port } = locationLike || {};
  if ((hostname === "localhost" || hostname === "127.0.0.1") && port && port !== "8602") {
    return `${protocol}//${hostname}:8602/`;
  }
  return "/scratch-studio/";
}

// 除部署用同源相对路径外，只接纳上面的固定本地开发地址，避免内容数据把管理员导向任意外站。
export function studioPreviewUrl(challengeId, { studioBase = "/scratch-studio/", extra = {} } = {}) {
  const localStudio = /^https?:\/\/(?:localhost|127\.0\.0\.1):8602(?:\/|$)/.test(studioBase);
  const base = typeof studioBase === "string" && (studioBase.startsWith("/") || localStudio)
    ? studioBase
    : "/scratch-studio/";
  const query = new URLSearchParams({ mode: "admin_preview", challenge_id: String(challengeId), ...extra });
  return `${base}${base.includes("?") ? "&" : "?"}${query.toString()}`;
}

// 录制初始项目 / 示范项目。两个入口在页面上长得几乎一样，**必须各带明确的
// authoring_target**，不能靠按钮文字区分——Studio 读的是这个参数，不是按钮上的字。
// 缺省时 Studio 按 starter 处理，但这里仍显式写出来：将来加第三种目标时，
// 漏掉参数的入口会静默地录到初始项目上去。
export function studioStarterUrl(challengeId, locationLike = globalThis.location) {
  return studioPreviewUrl(challengeId, {
    studioBase: studioPreviewBase(locationLike),
    extra: { authoring_target: "starter" },
  });
}

export function studioDemoUrl(challengeId, locationLike = globalThis.location) {
  return studioPreviewUrl(challengeId, {
    studioBase: studioPreviewBase(locationLike),
    extra: { authoring_target: "demo" },
  });
}

// 教师批改台：按提交 id 打开**提交时冻结的那一版**（只读）。
// 与 admin_preview 不同——那条按 challenge_id 装载「挑战当前初始项目」，这里要的是
// 学生交上来的那一份快照，两者证据对不上时是批改事故。
export function studioReviewUrl(submissionId, locationLike = globalThis.location) {
  const base = studioPreviewBase(locationLike);
  const query = new URLSearchParams({ mode: "admin_review", submission_id: String(submissionId) });
  return `${base}${base.includes("?") ? "&" : "?"}${query.toString()}`;
}

// ---- 挑战表单 ----

// 把表单状态归一化为 API 载荷；返回 { payload, errors }。
// errors 非空时不允许保存（发布另有更严的 publishChecks）。
export function buildChallengePayload(form) {
  const errors = [];
  const title = String(form.title || "").trim();
  if (!title) errors.push("请填写挑战标题。");
  const allowed = (form.allowed_extensions || []).filter((key) => EXTENSION_OPTIONS.some((o) => o.key === key));
  const rules = [];
  for (const rule of form.rules || []) {
    if (!rule || !rule.type) continue;
    const type = RULE_TYPES.find((t) => t.key === rule.type);
    const flat = { type: rule.type };
    for (const field of type?.fields || []) {
      const raw = rule.params?.[field.key];
      if (field.type === "number") {
        if (raw !== "" && raw != null) flat[field.key] = Number(raw);
      } else if (field.type === "list") {
        // 逗号/顿号/换行分隔的多值参数（如 require_initialization 的 attributes）
        const items = String(raw ?? "").split(/[,，、\n]/).map((s) => s.trim()).filter(Boolean);
        if (items.length) flat[field.key] = items;
      } else if (field.type === "json") {
        // 结构描述类参数（require_structure 的 pattern）：填了就必须是合法 JSON，
        // 坏 JSON 存进库会让全班提交判不出来，所以在保存前就拦下。
        const text = String(raw ?? "").trim();
        if (text) {
          try {
            flat[field.key] = JSON.parse(text);
          } catch {
            errors.push(`规则「${type?.label || rule.type}」的「${field.label}」不是合法 JSON，请检查格式。`);
          }
        }
      } else if (raw != null && String(raw).trim() !== "") {
        flat[field.key] = String(raw).trim();
      }
    }
    // 后端 rules_json 是扁平结构（参数与 type 同级），不要包 params。
    rules.push(flat);
  }
  const hints = String(form.hints_text || "")
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
  return {
    errors,
    payload: {
      title,
      instructions_md: String(form.instructions_md || "").trim() || null,
      analysis_video_id: Number(form.analysis_video_id) || null,
      allowed_extensions: allowed,
      hints,
      rules,
      rubric: rubricPayload(form.rubric),
    },
  };
}

// 发布前校验（镜像后端 _publish_checks 的中文清单风格；后端仍会再校验一次）。
export function publishChecks(challenge) {
  const missing = [];
  if (!String(challenge.title || "").trim()) missing.push("挑战标题");
  if (!String(challenge.instructions_md || "").trim()) missing.push("任务说明");
  if (!challenge.has_starter) missing.push("初始项目（.sb3）");
  if (!(challenge.rules || []).length) missing.push("至少一条声明式规则");
  return missing;
}

export const CHALLENGE_STATUS_LABEL = { draft: "草稿", published: "已发布", archived: "已归档" };

// ---- 教师量规（rubric）----

// 推荐模板：Dr. Scratch 的 CT 维度收敛成三项（七个维度全上对 8-14 岁课堂太重）。
// 只用「程序逻辑 / 代码结构 / 创意表达」三项，老师配得动、批得动。
export const DEFAULT_RUBRIC = {
  criteria: [
    { id: "c_logic", label: "程序逻辑", desc: "绿旗后能按要求完成规定动作", levels: [
      { value: 3, label: "完全达成", points: 40, desc: "移动并说出指定文字" },
      { value: 2, label: "基本达成", points: 25, desc: "只完成其中一项" },
      { value: 1, label: "部分达成", points: 10, desc: "有尝试但结果不对" },
      { value: 0, label: "未达成", points: 0, desc: "没有相关积木" },
    ] },
    { id: "c_structure", label: "代码结构", desc: "没有死代码，角色属性有初始化", levels: [
      { value: 2, label: "清晰", points: 30, desc: "" },
      { value: 1, label: "一般", points: 15, desc: "" },
      { value: 0, label: "混乱", points: 0, desc: "" },
    ] },
    { id: "c_creative", label: "创意表达", desc: "在完成要求之外有自己的想法", levels: [
      { value: 2, label: "有亮点", points: 30, desc: "" },
      { value: 1, label: "按部就班", points: 15, desc: "" },
      { value: 0, label: "未体现", points: 0, desc: "" },
    ] },
  ],
};

// 归一化为后端 ChallengePayload.rubric 的形状；空/无准则 → {}（= 不用量规）。
// `max_score` 由前端算出（各准则最高档之和），不交给老师手填——手填错到学生看到
// 分数才发现的概率极高（文档 23 §附录 A）。
export function rubricPayload(rubric) {
  if (!rubric || !Array.isArray(rubric.criteria) || !rubric.criteria.length) return {};
  const criteria = rubric.criteria.map((c) => ({
    id: c.id,
    label: String(c.label || "").trim(),
    desc: String(c.desc || ""),
    levels: (c.levels || []).map((lvl) => ({
      value: lvl.value,
      label: String(lvl.label || "").trim(),
      points: Number(lvl.points) || 0,
      desc: String(lvl.desc || ""),
    })),
  }));
  const max_score = criteria.reduce(
    (sum, c) => sum + Math.max(...c.levels.map((l) => l.points || 0), 0),
    0,
  );
  return { max_score, criteria };
}

export const SUBMISSION_STATUS_LABEL = {
  passed: "已通过",
  failed: "未通过",
  evaluating: "判定中",
  needs_review: "待点评",
  returned: "已退回重做",
};

export function formatDateTime(value) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : date.toLocaleString("zh-CN", { hour12: false });
}
