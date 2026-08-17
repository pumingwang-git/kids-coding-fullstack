"""Scratch 声明式判定：第一版**只做静态规则**（任务书 21b 强制约束第 6 条）。

判定输入是 `scratch_sb3.inspect_sb3()` 解析出来的 `project.json` 结构，输出是逐条
规则结论。**本模块不运行任何学生代码**——不起 VM、不点绿旗、不算舞台状态。

## 三态结论，以及为什么必须有第三态

    passed        全部规则通过
    failed        有规则没通过
    needs_review  规则里出现了本版判不了的类型（或挑战压根没配规则）→ 挂起等人工

第三态是这套设计的安全底座。挑战规则是教研在管理端填的 JSON，早晚会出现
"绿旗后角色最终坐标是 (100,0)"这类**必须真的跑一遍**才知道的规则。判不了的时候
只有两个选择：当作通过，或者挂起。当作通过 = 教研写了一条更严的要求，系统却把
全班放行；所以一律挂起（fail closed）。等受限任务执行器落地，再把这些 type 从
`UNSUPPORTED` 挪进 `_EVALUATORS` 即可，判定口径与三态形状都不用改。

## 规则表达

`rules_json` 是一个 JSON 数组，每项形如：

    {"type": "require_after_hat", "hat": "event_whenflagclicked",
     "opcode": "motion_movesteps", "label": "绿旗被点击后让角色移动"}

`label` 可选，是给学生看的任务清单文案；缺省时由 `describe()` 按类型生成一句中文。
**规则参数不下发给学生**，只下发 label——参数里带着期望值（比如要说的那句话），
下发等于把答案印在题面上。

## 已支持的类型

| type | 参数 | 判定 |
| --- | --- | --- |
| `require_opcode` | opcode, min_count?, target? | 存在 N 个该积木 |
| `forbid_opcode` | opcode, target? | 不允许出现该积木 |
| `require_after_hat` | hat, opcode, target? | 从该事件帽子沿 next/子栈可达该积木 |
| `require_input_value` | opcode, input, equals | 该积木的某个输入等于字面值 |
| `require_say_text` | text, match?(equals/contains) | 说/思考类积木输出指定文本 |
| `min_sprites` | count | 角色数量下限（不含舞台） |
| `min_variables` | count | 变量数量下限（舞台+角色） |
| `require_variable` | name, value? | 存在指定变量（可校验初始值） |
| `require_broadcast` | name | 存在指定广播消息 |
| `sprite_start_position` | sprite?, x, y, tolerance? | 角色**保存时**的坐标（不是运行后的） |
| `require_extension` | name | 项目启用了指定扩展 |
| `no_dead_code` | max_allowed? | 没有游离的死代码积木（未接事件的顶层块 / 断链孤儿块） |
| `broadcast_pairing` | direction?(send/receive/both) | 每条广播都有接收方，每个接收帽都有发送方 |
| `require_initialization` | attributes | 用了相对修改积木，就要在绿旗帽下做对应初始化 |
| `require_structure` | pattern, hat? | 存在满足嵌套关系的积木结构（沿子栈递归匹配） |
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field

from .scratch_sb3 import Sb3Summary

PASSED = "passed"
FAILED = "failed"
NEEDS_REVIEW = "needs_review"

# 判定已出结果的三个状态（`evaluating` 与未提交都不在内）。
#
# 放在这里而不是某个 router 里：解析视频、示范项目、课时入口卡片三处都要拿它当闸门，
# 而 courses.py 与 scratch.py 互相 import 会成环（scratch 依赖 courses 的完成流程）。
# 判定词表本来就属于规则层，两边都从这里取，就不会长出第二份。
TERMINAL_STATUSES = frozenset({PASSED, FAILED, NEEDS_REVIEW})

# 声明得出、但第一版判不了的规则类型。命中即挂起人工，绝不自动通过。
# 落地受限执行器后从这里搬进 _EVALUATORS，三态形状不用动。
UNSUPPORTED = {
    "sprite_end_position",   # 运行后坐标
    "variable_end_value",    # 运行后变量值
    "stage_output",          # 运行后舞台可观察输出
    "run_script",            # 自定义运行脚本
}


@dataclass
class RuleResult:
    index: int
    type: str
    label: str
    passed: bool
    message: str
    evidence: dict = field(default_factory=dict)


@dataclass
class Evaluation:
    status: str
    passed: bool
    score: int | None
    results: list[RuleResult]
    unsupported: list[str]
    note: str = ""

    def to_json(self) -> dict:
        return {
            "status": self.status,
            "passed": self.passed,
            "score": self.score,
            "note": self.note,
            "unsupported": self.unsupported,
            "rules": [asdict(r) for r in self.results],
        }


# ---------- project.json 遍历辅助 ----------


def _targets(summary: Sb3Summary, target: str | None) -> list[dict]:
    """按规则的 target 参数挑角色：None=全部 / "stage"=舞台 / 其余按角色名匹配。"""
    if not target:
        return summary.targets
    if target == "stage":
        stage = summary.stage
        return [stage] if stage else []
    return [t for t in summary.targets if t.get("name") == target]


def _blocks(target: dict) -> dict[str, dict]:
    """一个角色里的积木字典。

    顶层的裸变量/列表读取块在 `project.json` 里是**数组**（compressed primitive，
    形如 `[12, "分数", "varId", x, y]`）而不是对象，遍历时必须跳过，否则
    `block.get("opcode")` 会当场 AttributeError。
    """
    raw = target.get("blocks")
    if not isinstance(raw, dict):
        return {}
    return {bid: b for bid, b in raw.items() if isinstance(b, dict)}


def _count_opcode(summary: Sb3Summary, opcode: str, target: str | None) -> int:
    """统计某 opcode 的出现次数。**跳过 shadow 块**——下拉菜单（如
    `motion_goto_menu`）也是块，把它们算进去会让"至少 1 个"这种规则凭空满足。
    """
    total = 0
    for t in _targets(summary, target):
        for block in _blocks(t).values():
            if block.get("opcode") == opcode and not block.get("shadow"):
                total += 1
    return total


def _input_block_refs(block: dict) -> list[str]:
    """一个积木的输入里引用到的其它积木 id（子栈、被拖进槽位的运算块都在这儿）。

    输入格式有三种：`[1, [4,"10"]]` 字面值 / `[2, "blockId"]` 直接引用 /
    `[3, "blockId", [4,"10"]]` 引用遮住了字面值。只有后两种带 id。
    """
    refs: list[str] = []
    for value in (block.get("inputs") or {}).values():
        if not isinstance(value, list):
            continue
        for item in value[1:]:
            if isinstance(item, str):
                refs.append(item)
    return refs


def _reachable_opcodes(blocks: dict[str, dict], start_id: str) -> set[str]:
    """从某个积木出发，沿 `next` 链与输入引用（含子栈）可达的全部 opcode。

    为什么要连输入一起走：`重复 10 次 { 移动 10 步 }` 里的"移动"挂在 SUBSTACK 输入上，
    不在 next 链上。只走 next 的话，凡是把积木放进循环/条件里的学生一律判不通过——
    而那恰恰是课程希望他们做的事。
    """
    seen: set[str] = set()
    opcodes: set[str] = set()
    stack = [start_id]
    while stack:
        bid = stack.pop()
        if bid in seen:
            continue
        seen.add(bid)
        block = blocks.get(bid)
        if not isinstance(block, dict):
            continue
        if not block.get("shadow"):
            opcode = block.get("opcode")
            if isinstance(opcode, str):
                opcodes.add(opcode)
        nxt = block.get("next")
        if isinstance(nxt, str):
            stack.append(nxt)
        stack.extend(_input_block_refs(block))
    return opcodes


def _literal_input(block: dict, name: str) -> str | None:
    """取输入槽里的字面值。被别的积木遮住（`[3, id, [4,"10"]]`）时取被遮的字面值。

    返回字符串：`project.json` 里数字有时是 `"10"` 有时是 `10`，统一成字符串比较，
    调用方再做数值/文本判定，省得每处各写一次类型分支。
    """
    value = (block.get("inputs") or {}).get(name)
    if not isinstance(value, list) or len(value) < 2:
        return None
    for item in value[1:]:
        if isinstance(item, list) and len(item) >= 2:
            return str(item[1])
    return None


def _variables(summary: Sb3Summary) -> dict[str, str]:
    """全部变量：名 → 初始值（字符串化）。舞台的全局变量与角色私有变量都算。"""
    out: dict[str, str] = {}
    for target in summary.targets:
        raw = target.get("variables")
        if not isinstance(raw, dict):
            continue
        for entry in raw.values():
            if isinstance(entry, list) and len(entry) >= 2:
                out[str(entry[0])] = str(entry[1])
    return out


def _broadcasts(summary: Sb3Summary) -> set[str]:
    out: set[str] = set()
    for target in summary.targets:
        raw = target.get("broadcasts")
        if isinstance(raw, dict):
            out.update(str(v) for v in raw.values())
    return out


def _numeric(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# ---------- 逐类型判定 ----------


SAY_OPCODES = ("looks_say", "looks_sayforsecs", "looks_think", "looks_thinkforsecs")


def _eval_require_opcode(rule: dict, summary: Sb3Summary) -> tuple[bool, str, dict]:
    opcode = str(rule.get("opcode") or "")
    need = max(1, int(rule.get("min_count") or 1))
    got = _count_opcode(summary, opcode, rule.get("target"))
    ok = got >= need
    return ok, ("" if ok else f"还缺少积木 {opcode}（需要 {need} 个，当前 {got} 个）。"), \
        {"opcode": opcode, "need": need, "got": got}


def _eval_forbid_opcode(rule: dict, summary: Sb3Summary) -> tuple[bool, str, dict]:
    opcode = str(rule.get("opcode") or "")
    got = _count_opcode(summary, opcode, rule.get("target"))
    return got == 0, ("" if got == 0 else f"本关不允许使用积木 {opcode}。"), \
        {"opcode": opcode, "got": got}


def _eval_require_after_hat(rule: dict, summary: Sb3Summary) -> tuple[bool, str, dict]:
    hat = str(rule.get("hat") or "event_whenflagclicked")
    opcode = str(rule.get("opcode") or "")
    for target in _targets(summary, rule.get("target")):
        blocks = _blocks(target)
        for bid, block in blocks.items():
            if block.get("opcode") != hat:
                continue
            if opcode in _reachable_opcodes(blocks, bid):
                return True, "", {"hat": hat, "opcode": opcode, "target": target.get("name")}
    return False, f"没有找到「{hat}」之后连着的积木 {opcode}。", {"hat": hat, "opcode": opcode}


def _eval_require_input_value(rule: dict, summary: Sb3Summary) -> tuple[bool, str, dict]:
    opcode = str(rule.get("opcode") or "")
    name = str(rule.get("input") or "")
    expected = str(rule.get("equals"))
    found: list[str] = []
    for target in _targets(summary, rule.get("target")):
        for block in _blocks(target).values():
            if block.get("opcode") != opcode or block.get("shadow"):
                continue
            actual = _literal_input(block, name)
            if actual is None:
                continue
            found.append(actual)
            # 数值先按数值比：10 与 "10.0" 是同一个意思，字符串比会判错。
            left, right = _numeric(actual), _numeric(expected)
            if (left is not None and right is not None and left == right) or actual == expected:
                return True, "", {"opcode": opcode, "input": name, "value": actual}
    return False, f"积木 {opcode} 的「{name}」还不是要求的值。", \
        {"opcode": opcode, "input": name, "found": found[:5]}


def _eval_require_say_text(rule: dict, summary: Sb3Summary) -> tuple[bool, str, dict]:
    expected = str(rule.get("text") or "")
    mode = str(rule.get("match") or "equals")
    found: list[str] = []
    for target in _targets(summary, rule.get("target")):
        for block in _blocks(target).values():
            if block.get("opcode") not in SAY_OPCODES or block.get("shadow"):
                continue
            actual = _literal_input(block, "MESSAGE")
            if actual is None:
                continue
            found.append(actual)
            if (actual == expected) if mode == "equals" else (expected in actual):
                return True, "", {"text": actual}
    return False, "角色还没有说出题目要求的那句话。", {"found": found[:5]}


def _eval_min_sprites(rule: dict, summary: Sb3Summary) -> tuple[bool, str, dict]:
    need = int(rule.get("count") or 1)
    got = summary.sprite_count
    return got >= need, ("" if got >= need else f"至少需要 {need} 个角色，当前 {got} 个。"), \
        {"need": need, "got": got}


def _eval_min_variables(rule: dict, summary: Sb3Summary) -> tuple[bool, str, dict]:
    need = int(rule.get("count") or 1)
    got = summary.variable_count
    return got >= need, ("" if got >= need else f"至少需要 {need} 个变量，当前 {got} 个。"), \
        {"need": need, "got": got}


def _eval_require_variable(rule: dict, summary: Sb3Summary) -> tuple[bool, str, dict]:
    name = str(rule.get("name") or "")
    variables = _variables(summary)
    if name not in variables:
        return False, f"还没有创建变量「{name}」。", {"name": name}
    if "value" in rule and rule.get("value") is not None:
        expected, actual = str(rule.get("value")), variables[name]
        left, right = _numeric(actual), _numeric(expected)
        ok = (left is not None and right is not None and left == right) or actual == expected
        return ok, ("" if ok else f"变量「{name}」的初始值还不对。"), \
            {"name": name, "value": actual}
    return True, "", {"name": name, "value": variables[name]}


def _eval_require_broadcast(rule: dict, summary: Sb3Summary) -> tuple[bool, str, dict]:
    name = str(rule.get("name") or "")
    ok = name in _broadcasts(summary)
    return ok, ("" if ok else f"还没有创建广播消息「{name}」。"), {"name": name}


def _eval_sprite_start_position(rule: dict, summary: Sb3Summary) -> tuple[bool, str, dict]:
    """角色**保存时**的坐标。注意这不是"运行后的坐标"——那要真跑一遍，属于
    `sprite_end_position`（UNSUPPORTED）。两者容易混，题面文案要写清楚。
    """
    name = rule.get("sprite")
    candidates = _targets(summary, name) if name else summary.sprites
    candidates = [t for t in candidates if not t.get("isStage")]
    if not candidates:
        return False, f"没有找到角色「{name}」。", {"sprite": name}
    tolerance = float(rule.get("tolerance") or 0)
    want_x, want_y = _numeric(rule.get("x")), _numeric(rule.get("y"))
    for target in candidates:
        got_x, got_y = _numeric(target.get("x")), _numeric(target.get("y"))
        if got_x is None or got_y is None or want_x is None or want_y is None:
            continue
        if abs(got_x - want_x) <= tolerance and abs(got_y - want_y) <= tolerance:
            return True, "", {"sprite": target.get("name"), "x": got_x, "y": got_y}
    first = candidates[0]
    return False, "角色的位置还不在题目要求的坐标上。", \
        {"sprite": first.get("name"), "x": first.get("x"), "y": first.get("y")}


def _eval_require_extension(rule: dict, summary: Sb3Summary) -> tuple[bool, str, dict]:
    name = str(rule.get("name") or "")
    ok = name in summary.extensions
    return ok, ("" if ok else f"还没有添加「{name}」扩展。"), {"name": name}


# ---------- 死代码 / 广播配对 / 初始化 / 结构模式 ----------

# 能当脚本起点的"帽子"：事件类 + 克隆体启动 + 自定义积木定义。
# 顶层块不是这三类之一，就是永远不会被执行的死代码。
_HAT_OPCODES = ("control_start_as_clone", "procedures_definition")


def _is_hat(block: dict) -> bool:
    opcode = block.get("opcode")
    return isinstance(opcode, str) and (
        opcode.startswith("event_") or opcode in _HAT_OPCODES
    )


def _eval_no_dead_code(rule: dict, summary: Sb3Summary) -> tuple[bool, str, dict]:
    """死代码积木：永远不会被执行的块。

    两种形态：
    - `topLevel=true` 但不是帽子——拖出来没接到任何事件上的脚本；
    - 孤儿块——`parent` 指向一个不存在的块（删母块时把子块留在了画布上）。

    `max_allowed` 允许留几个（比如示范项目故意摆的"备用积木"），默认 0。
    """
    max_allowed = int(rule.get("max_allowed") or 0)
    if max_allowed < 0:
        return False, "规则参数错误：max_allowed 不能是负数。", {"max_allowed": max_allowed}
    dead: list[dict] = []
    for target in _targets(summary, rule.get("target")):
        blocks = _blocks(target)
        for bid, block in blocks.items():
            if block.get("shadow"):
                continue
            if block.get("topLevel"):
                if _is_hat(block):
                    continue
            else:
                # 沿 parent 链向上走：走不到顶层（断链或成环）才是孤儿。
                seen: set[str] = set()
                pid = block.get("parent")
                orphan = False
                while isinstance(pid, str):
                    if pid in seen:  # parent 成环：不可能被任何脚本执行到
                        orphan = True
                        break
                    seen.add(pid)
                    parent = blocks.get(pid)
                    if not isinstance(parent, dict):
                        orphan = True
                        break
                    if parent.get("topLevel"):
                        break
                    pid = parent.get("parent")
                # parent 链断在"顶层死块"上不重复计：那块顶层块自己已经被记过了，
                # 把它的整个子树都再记一遍只会淹没有效信息。
                if not orphan:
                    continue
            dead.append({"sprite": target.get("name"), "opcode": block.get("opcode")})
    ok = len(dead) <= max_allowed
    if ok:
        return True, "", {"dead": len(dead), "max_allowed": max_allowed}
    shown = "、".join(f"{d['opcode']}（{d['sprite']}）" for d in dead[:5])
    more = f" 等 {len(dead)} 处" if len(dead) > 5 else ""
    return False, f"发现 {len(dead)} 处没有接到任何事件上的死代码积木：{shown}{more}，请删掉或接到事件下面。", \
        {"dead": len(dead), "max_allowed": max_allowed, "blocks": dead[:10]}


# 发送广播的两个积木；接收帽是 event_whenbroadcastreceived。
_BROADCAST_SEND_OPCODES = ("event_broadcast", "event_broadcastandwait")


def _sent_broadcast_name(block: dict, blocks: dict[str, dict]) -> str | None | bool:
    """取发送积木的消息名。

    真实格式（scratch-vm sb3.js 与官方导出的 project.json 实证）：发送侧输入名是
    **`BROADCAST_INPUT`**（不是 BROADCAST_OPTION——那是接收帽 fields 里的名字），
    形态三种：`[1, [11, 名字, id]]` 内联广播 primitive（类型码 11 才是广播，
    12/13 是变量/列表）/ `[1, "menuBlockId"]` 引用 `event_broadcast_menu` shadow
    / `[3, "menuId", [11, …]]` 被遮住带兜底。

    三种结果：名字字符串 / None（没配消息，按 Scratch 的默认行为视为不可判定）
    / False（消息名来自变量等动态积木——**静态判不了**，调用方记 warning 跳过，
    绝不猜一个名字去比对，那会把无辜的作品判挂）。
    """
    inputs = block.get("inputs") or {}
    value = inputs.get("BROADCAST_INPUT") or inputs.get("BROADCAST_OPTION")
    if not isinstance(value, list) or len(value) < 2:
        return None
    for item in value[1:]:
        if isinstance(item, list) and len(item) >= 2:
            if item[0] == 11:  # 广播 primitive
                return str(item[1])
            return False  # 内联的变量(12)/列表(13) primitive：消息名运行时才定
        if isinstance(item, str):
            ref = blocks.get(item)
            if not isinstance(ref, dict):
                return None
            if ref.get("opcode") == "event_broadcast_menu":
                field_value = (ref.get("fields") or {}).get("BROADCAST_OPTION")
                if isinstance(field_value, list) and field_value:
                    return str(field_value[0])
                return None
            return False  # 变量/运算结果决定消息名
    return None


def _received_broadcast_name(block: dict) -> str | None:
    """接收帽的消息名在 fields 里：`BROADCAST_OPTION: [名字, id]`。"""
    value = (block.get("fields") or {}).get("BROADCAST_OPTION")
    if isinstance(value, list) and value:
        return str(value[0])
    return None


def _eval_broadcast_pairing(rule: dict, summary: Sb3Summary) -> tuple[bool, str, dict]:
    """广播配对：发出的每条消息要有人接，每个接收帽要有人发。

    单向告警的用处：`direction="send"` 只查"发出去没人收"（学生常忘做接收方），
    `"receive"` 只查"干等一条永远不会来的消息"。默认 both 两个方向都查。
    """
    direction = str(rule.get("direction") or "both")
    if direction not in ("send", "receive", "both"):
        return False, f"规则参数错误：direction 只能是 send / receive / both，当前是「{direction}」。", \
            {"direction": direction}
    sent: set[str] = set()
    received: set[str] = set()
    warnings: list[str] = []
    for target in _targets(summary, rule.get("target")):
        blocks = _blocks(target)
        for block in blocks.values():
            if block.get("shadow"):
                continue
            opcode = block.get("opcode")
            if opcode in _BROADCAST_SEND_OPCODES:
                name = _sent_broadcast_name(block, blocks)
                if name is False:
                    warnings.append(f"{target.get('name')} 里有用变量决定消息名的广播，已跳过配对检查。")
                elif isinstance(name, str):
                    sent.add(name)
            elif opcode == "event_whenbroadcastreceived":
                name = _received_broadcast_name(block)
                if isinstance(name, str):
                    received.add(name)
    problems: list[str] = []
    if direction in ("send", "both"):
        lonely = sorted(sent - received)
        if lonely:
            problems.append(f"广播 {'、'.join(f'「{n}」' for n in lonely[:5])} 发出去了，但没有任何角色接收它")
    if direction in ("receive", "both"):
        deaf = sorted(received - sent)
        if deaf:
            problems.append(f"接收 {'、'.join(f'「{n}」' for n in deaf[:5])} 的帽子存在，但没有任何积木发出这条广播")
    evidence = {"sent": sorted(sent), "received": sorted(received), "warnings": warnings}
    if problems:
        return False, "；".join(problems) + "。", evidence
    return True, "", evidence


# 相对修改 → 对应的绝对初始化积木。判不了初始化的属性不在这张表里，
# 规则写了就直接转人工（见 _eval_require_initialization 的 ValueError 出口）。
_INIT_PAIRS = {
    "position": {
        "relative": {"motion_movesteps", "motion_changexby", "motion_changeyby"},
        "absolute": {"motion_gotoxy", "motion_setx", "motion_sety"},
        "hint": "把角色放到固定起点（如「移到 x: y:」）",
    },
    "direction": {
        "relative": {"motion_turnright", "motion_turnleft"},
        "absolute": {"motion_pointindirection"},
        "hint": "用「面向 90 方向」固定朝向",
    },
    "size": {
        "relative": {"looks_changesizeby"},
        "absolute": {"looks_setsizeto"},
        "hint": "用「将大小设为」固定大小",
    },
    "costume": {
        "relative": {"looks_nextcostume"},
        "absolute": {"looks_switchcostumeto"},
        "hint": "用「换成 … 造型」固定初始造型",
    },
    "visible": {
        "relative": {"looks_hide"},
        "absolute": {"looks_show"},
        "hint": "用「显示」固定初始可见状态",
    },
}
_VARIABLE_RELATIVE = "data_changevariableby"
_VARIABLE_ABSOLUTE = "data_setvariableto"


def _stack_after_hat(blocks: dict[str, dict], hat_id: str) -> list[dict]:
    """帽子积木正下方沿 next 依次连接的积木（不钻进子栈）。

    "初始化区"刻意只认主链：写进 `重复执行` 里的赋值每次循环都重设，
    不是"先初始化一次"，不能拿来抵初始化的数。
    """
    out: list[dict] = []
    seen: set[str] = {hat_id}
    bid = blocks.get(hat_id, {}).get("next")
    while isinstance(bid, str) and bid not in seen:
        seen.add(bid)
        block = blocks.get(bid)
        if not isinstance(block, dict):
            break
        out.append(block)
        bid = block.get("next")
    return out


def _variable_field(block: dict) -> str | None:
    """变量积木的变量名。序列化进 project.json 的字段名是 `VARIABLE`
    （scratch-vm sb3.js 反序列化时才改名 VAR）；个别工具链会写 `VAR`，两个都认。"""
    fields = block.get("fields") or {}
    for key in ("VARIABLE", "VAR"):
        value = fields.get(key)
        if isinstance(value, list) and value:
            return str(value[0])
    return None


def _eval_require_initialization(rule: dict, summary: Sb3Summary) -> tuple[bool, str, dict]:
    """初始化检查（Hairball 的 Initialization 思路）：用了"相对修改"积木，
    就要在绿旗帽子下先做一次"绝对赋值"，否则再点一次绿旗结果会跟着上次跑完
    的状态漂移（角色越跑越偏、变量越加越大）。

    `attributes` 逐项是 `"position"` / `"direction"` / `"size"` / `"costume"` /
    `"visible"` / `"variable:<名字>"`。某属性全作品都没有相对修改时，该项视为
    满足（没用到就不需要初始化）。判不了的属性名（拼错、或本表没覆盖的）
    抛 ValueError → 由 evaluate() 统一转 needs_review，绝不误判 failed。
    """
    raw = rule.get("attributes")
    if not isinstance(raw, list) or not raw or not all(isinstance(a, str) and a for a in raw):
        return False, "规则参数错误：attributes 必须是非空的属性名数组（如 [\"position\", \"variable:分数\"]）。", \
            {"attributes": raw}
    hat = str(rule.get("hat") or "event_whenflagclicked")

    problems: list[str] = []
    evidence: dict = {"checked": [], "missing": []}
    for attribute in raw:
        if attribute.startswith("variable:"):
            var_name = attribute.split(":", 1)[1]
            if not var_name:
                return False, "规则参数错误：variable: 后面必须跟变量名。", {"attributes": raw}
            used = False
            initialized = False
            for target in summary.targets:
                blocks = _blocks(target)
                for bid, block in blocks.items():
                    if block.get("shadow"):
                        continue
                    if block.get("opcode") == _VARIABLE_RELATIVE and _variable_field(block) == var_name:
                        used = True
                for bid, block in blocks.items():
                    if block.get("opcode") != hat:
                        continue
                    for stacked in _stack_after_hat(blocks, bid):
                        if stacked.get("opcode") == _VARIABLE_ABSOLUTE \
                                and _variable_field(stacked) == var_name:
                            initialized = True
            evidence["checked"].append({"attribute": attribute, "used": used,
                                        "initialized": initialized})
            if used and not initialized:
                evidence["missing"].append(attribute)
                problems.append(
                    f"变量「{var_name}」用了「将变量增加」却从没在绿旗下「将变量设为」初始值")
            continue
        spec = _INIT_PAIRS.get(attribute)
        if spec is None:
            # 拼错或本版覆盖不到的属性：判不了 → 转人工，与 UNSUPPORTED 同一条出口。
            raise ValueError(f"unknown attribute: {attribute}")
        # 位置/朝向这类属性是**每个角色各自**的：哪个角色用了相对修改，
        # 就要求哪个角色自己的绿旗下有初始化，不能拿别的角色的赋值充数。
        for target in summary.targets:
            blocks = _blocks(target)
            used = any(
                block.get("opcode") in spec["relative"] and not block.get("shadow")
                for block in blocks.values()
            )
            if not used:
                continue
            initialized = False
            for bid, block in blocks.items():
                if block.get("opcode") != hat:
                    continue
                if any(stacked.get("opcode") in spec["absolute"]
                       for stacked in _stack_after_hat(blocks, bid)):
                    initialized = True
                    break
            evidence["checked"].append({"attribute": attribute,
                                        "sprite": target.get("name"),
                                        "initialized": initialized})
            if not initialized:
                evidence["missing"].append(f"{attribute}@{target.get('name')}")
                problems.append(
                    f"角色「{target.get('name')}」动了{attribute}却没在绿旗下初始化：{spec['hint']}")
    if problems:
        return False, "；".join(problems) + "。", evidence
    return True, "", evidence


def _reachable_block_ids(blocks: dict[str, dict], start_id: str) -> set[str]:
    """与 `_reachable_opcodes` 同一条遍历口径（next 链 + 全部输入引用），返回 id 集合。"""
    seen: set[str] = set()
    stack = [start_id]
    while stack:
        bid = stack.pop()
        if bid in seen:
            continue
        seen.add(bid)
        block = blocks.get(bid)
        if not isinstance(block, dict):
            continue
        nxt = block.get("next")
        if isinstance(nxt, str):
            stack.append(nxt)
        stack.extend(_input_block_refs(block))
    return seen


def _match_structure(blocks: dict[str, dict], candidates: set[str], pattern: dict) -> bool:
    """在 candidates 里找一个 opcode 匹配的块，且它的每个 contains 子要求都能在
    它自己的可达范围里被满足（无序多要求，各自独立匹配）。"""
    for bid in candidates:
        block = blocks.get(bid)
        if not isinstance(block, dict) or block.get("shadow"):
            continue
        if block.get("opcode") != pattern["opcode"]:
            continue
        inner = _reachable_block_ids(blocks, bid)
        if all(_match_structure(blocks, inner, sub) for sub in pattern.get("contains") or []):
            return True
    return False


def _validate_structure_pattern(pattern, depth: int = 0):
    """pattern 必须形如 {"opcode": "...", "contains": [子 pattern, ...]}。"""
    if not isinstance(pattern, dict) or not isinstance(pattern.get("opcode"), str) \
            or not pattern["opcode"]:
        return None
    contains = pattern.get("contains") or []
    if not isinstance(contains, list) or depth >= 8:
        return None
    if any(_validate_structure_pattern(sub, depth + 1) is None for sub in contains):
        return None
    return {"opcode": pattern["opcode"], "contains": contains}


def _eval_require_structure(rule: dict, summary: Sb3Summary) -> tuple[bool, str, dict]:
    """嵌套结构模式：`重复执行 { 如果 … 那么 { … } }` 这类"骨架要求"。

    匹配沿块的全部输入引用（子栈、条件槽）与 next 链递归——与 `_reachable_opcodes`
    同一条口径，学生把条件块写在条件槽里还是嵌在子栈里都认。传了 `hat` 就先限定
    搜索范围为该事件帽子可达的积木（比如必须挂在绿旗下，摆个死代码不算数）。
    """
    pattern = _validate_structure_pattern(rule.get("pattern"))
    if pattern is None:
        return False, "规则参数错误：pattern 必须是嵌套的 opcode 树（如 {\"opcode\": \"control_repeat\", \"contains\": [...]}）。", \
            {"pattern": rule.get("pattern")}
    hat = rule.get("hat")
    hat = str(hat) if hat else None
    for target in _targets(summary, rule.get("target")):
        blocks = _blocks(target)
        if hat:
            candidates: set[str] = set()
            for bid, block in blocks.items():
                if block.get("opcode") == hat:
                    candidates |= _reachable_block_ids(blocks, bid)
        else:
            candidates = set(blocks)
        if _match_structure(blocks, candidates, pattern):
            return True, "", {"pattern": pattern, "target": target.get("name"),
                              "hat": hat}
    wanted = pattern["opcode"]
    if pattern.get("contains"):
        wanted += "（内含 " + "、".join(sub["opcode"] for sub in pattern["contains"]) + "）"
    where = f"「{hat}」下面" if hat else "作品里"
    return False, f"没有在{where}找到要求的积木结构：{wanted}。", \
        {"pattern": pattern, "hat": hat}


_EVALUATORS = {
    "require_opcode": _eval_require_opcode,
    "forbid_opcode": _eval_forbid_opcode,
    "require_after_hat": _eval_require_after_hat,
    "require_input_value": _eval_require_input_value,
    "require_say_text": _eval_require_say_text,
    "min_sprites": _eval_min_sprites,
    "min_variables": _eval_min_variables,
    "require_variable": _eval_require_variable,
    "require_broadcast": _eval_require_broadcast,
    "sprite_start_position": _eval_sprite_start_position,
    "require_extension": _eval_require_extension,
    "no_dead_code": _eval_no_dead_code,
    "broadcast_pairing": _eval_broadcast_pairing,
    "require_initialization": _eval_require_initialization,
    "require_structure": _eval_require_structure,
}

SUPPORTED_TYPES = frozenset(_EVALUATORS)
KNOWN_TYPES = SUPPORTED_TYPES | UNSUPPORTED


def describe(rule: dict) -> str:
    """规则的学生可见文案。教研填了 `label` 就用它，否则按类型生成一句中文。"""
    label = rule.get("label")
    if isinstance(label, str) and label.strip():
        return label.strip()
    kind = rule.get("type")
    if kind == "require_opcode":
        return f"使用积木 {rule.get('opcode')}"
    if kind == "forbid_opcode":
        return f"不要使用积木 {rule.get('opcode')}"
    if kind == "require_after_hat":
        return f"在「{rule.get('hat')}」之后使用积木 {rule.get('opcode')}"
    if kind == "require_input_value":
        return f"把 {rule.get('opcode')} 的「{rule.get('input')}」设成指定值"
    if kind == "require_say_text":
        return "让角色说出题目要求的文字"
    if kind == "min_sprites":
        return f"至少有 {rule.get('count')} 个角色"
    if kind == "min_variables":
        return f"至少有 {rule.get('count')} 个变量"
    if kind == "require_variable":
        return f"创建变量「{rule.get('name')}」"
    if kind == "require_broadcast":
        return f"创建广播消息「{rule.get('name')}」"
    if kind == "sprite_start_position":
        return "把角色摆到题目要求的位置"
    if kind == "require_extension":
        return f"添加「{rule.get('name')}」扩展"
    if kind == "no_dead_code":
        return "不要留下没接到事件上的积木"
    if kind == "broadcast_pairing":
        return "每条广播都要有对应的接收与发送"
    if kind == "require_initialization":
        return "在绿旗下先初始化再使用相对修改积木"
    if kind == "require_structure":
        return "搭出题目要求的积木嵌套结构"
    return "本条要求由老师人工点评"


def parse_rules(rules_json: str) -> list[dict]:
    """把 `rules_json` 解析成规则列表。脏数据一律当空规则（→ 挂起人工），不抛异常。

    判定路径上抛异常 = 学生交作品时看到 500。规则是教研填的，坏了该由发布检查和
    人工点评兜底，不该由学生承担。
    """
    try:
        parsed = json.loads(rules_json or "[]")
    except (TypeError, json.JSONDecodeError):
        return []
    if not isinstance(parsed, list):
        return []
    return [r for r in parsed if isinstance(r, dict) and isinstance(r.get("type"), str)]


def checklist(rules_json: str) -> list[str]:
    """学生可见的任务清单：只出 label 文案，**不出规则参数**（参数里带着期望值）。"""
    return [describe(rule) for rule in parse_rules(rules_json)]


def evaluate(rules_json: str, summary: Sb3Summary) -> Evaluation:
    """按冻结的规则原文判定一份作品。纯函数，不碰数据库、不碰请求。"""
    rules = parse_rules(rules_json)
    if not rules:
        return Evaluation(
            status=NEEDS_REVIEW, passed=False, score=None, results=[], unsupported=[],
            note="本关未配置自动判定规则，已提交给老师人工点评。",
        )

    results: list[RuleResult] = []
    unsupported: list[str] = []
    for index, rule in enumerate(rules):
        kind = rule["type"]
        evaluator = _EVALUATORS.get(kind)
        if evaluator is None:
            unsupported.append(kind)
            results.append(RuleResult(
                index=index, type=kind, label=describe(rule), passed=False,
                message="这条要求需要真实运行项目，已转人工点评。", evidence={},
            ))
            continue
        try:
            ok, message, evidence = evaluator(rule, summary)
        except (TypeError, ValueError, KeyError, AttributeError):
            # 规则参数写错（比如 count 填了 "三"）不该把学生的提交打成 500：
            # 当成"这条判不了"转人工，和运行型规则同一个出口。
            unsupported.append(kind)
            results.append(RuleResult(
                index=index, type=kind, label=describe(rule), passed=False,
                message="这条要求暂时无法自动判定，已转人工点评。", evidence={},
            ))
            continue
        results.append(RuleResult(
            index=index, type=kind, label=describe(rule), passed=ok,
            message=message, evidence=evidence,
        ))

    if unsupported:
        # 挂起态不给 score：判不全的分数会被前端当成"还差一点"，误导学生继续改。
        return Evaluation(
            status=NEEDS_REVIEW, passed=False, score=None, results=results,
            unsupported=sorted(set(unsupported)),
            note="其中有需要老师确认的要求，本次提交已转人工点评。",
        )
    done = sum(1 for r in results if r.passed)
    all_passed = done == len(results)
    return Evaluation(
        status=PASSED if all_passed else FAILED,
        passed=all_passed,
        score=round(done / len(results) * 100),
        results=results,
        unsupported=[],
        note="全部要求都达成了。" if all_passed else "还有要求没达成，按提示改一改再交一次。",
    )
