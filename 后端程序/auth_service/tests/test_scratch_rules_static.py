"""scratch_rules 新增静态规则的单元测试（no_dead_code / broadcast_pairing /
require_initialization / require_structure）。

不走 .sb3 打包与 HTTP：直接构造 `project.json` 风格的 target 字典塞进
`Sb3Summary(targets=[...])` 喂给 `evaluate()`。判定是纯函数，这条最短路径
足以覆盖规则语义；打包与路由层的集成回归在 test_scratch.py。
"""
import json

from app.scratch_rules import (
    FAILED,
    NEEDS_REVIEW,
    PASSED,
    evaluate,
)
from app.scratch_sb3 import Sb3Summary


def make_summary(*targets) -> Sb3Summary:
    return Sb3Summary(
        sprite_count=sum(1 for t in targets if not t.get("isStage")),
        targets=list(targets),
        block_count=0,
        variable_count=0,
    )


def stage(blocks=None, variables=None) -> dict:
    return {
        "isStage": True,
        "name": "Stage",
        "blocks": blocks or {},
        "variables": variables or {},
        "broadcasts": {},
    }


def sprite(name="小猫", blocks=None, variables=None) -> dict:
    return {
        "isStage": False,
        "name": name,
        "blocks": blocks or {},
        "variables": variables or {},
    }


def hat(next_id=None, opcode="event_whenflagclicked") -> dict:
    return {"opcode": opcode, "next": next_id, "parent": None,
            "inputs": {}, "fields": {}, "topLevel": True}


def block(opcode, next_id=None, parent=None, inputs=None, fields=None,
          top_level=False) -> dict:
    return {"opcode": opcode, "next": next_id, "parent": parent,
            "inputs": inputs or {}, "fields": fields or {}, "topLevel": top_level}


def run(rules: list[dict], summary: Sb3Summary):
    return evaluate(json.dumps(rules, ensure_ascii=False), summary)


# ---------- no_dead_code ----------


class TestNoDeadCode:
    RULE = {"type": "no_dead_code"}

    def test_clean_project_passes(self):
        blocks = {
            "h": hat(next_id="m"),
            "m": block("motion_movesteps", parent="h"),
        }
        result = run([self.RULE], make_summary(stage(), sprite(blocks=blocks)))
        assert result.status == PASSED
        assert result.results[0].passed

    def test_top_level_non_hat_is_dead(self):
        blocks = {
            "h": hat(),
            "d": block("looks_say", top_level=True),  # 拖出来没接事件
        }
        result = run([self.RULE], make_summary(stage(), sprite(blocks=blocks)))
        assert result.status == FAILED
        item = result.results[0]
        assert not item.passed
        assert "looks_say" in item.message
        assert "小猫" in item.message

    def test_orphan_parent_chain_is_dead(self):
        blocks = {
            "h": hat(),
            "o": block("motion_movesteps", parent="ghost"),  # parent 不存在
        }
        result = run([self.RULE], make_summary(stage(), sprite(blocks=blocks)))
        assert result.status == FAILED
        assert not result.results[0].passed

    def test_clone_start_and_procedure_definition_are_hats(self):
        blocks = {
            "c": block("control_start_as_clone", top_level=True),
            "p": block("procedures_definition", top_level=True),
        }
        result = run([self.RULE], make_summary(stage(), sprite(blocks=blocks)))
        assert result.status == PASSED

    def test_max_allowed(self):
        blocks = {"d": block("looks_say", top_level=True)}
        assert run([{"type": "no_dead_code", "max_allowed": 1}],
                   make_summary(stage(), sprite(blocks=blocks))).status == PASSED
        assert run([self.RULE],
                   make_summary(stage(), sprite(blocks=blocks))).status == FAILED

    def test_child_of_dead_top_level_not_double_counted(self):
        # 顶层死块的子块不再重复计数
        blocks = {
            "d": block("control_repeat", next_id=None, top_level=True,
                       inputs={"SUBSTACK": [2, "inner"]}),
            "inner": block("motion_movesteps", parent="d"),
        }
        result = run([self.RULE], make_summary(stage(), sprite(blocks=blocks)))
        assert result.results[0].evidence["dead"] == 1

    def test_negative_max_allowed_is_param_error(self):
        result = run([{"type": "no_dead_code", "max_allowed": -1}],
                     make_summary(stage(), sprite()))
        assert result.status == FAILED
        assert "参数错误" in result.results[0].message


# ---------- broadcast_pairing ----------


def send_block(name, next_id=None, parent=None):
    """event_broadcast，消息名走内联 shadow 字面值。"""
    return block("event_broadcast", next_id=next_id, parent=parent,
                 inputs={"BROADCAST_INPUT": [1, [11, name, f"broadcastMsgId-{name}"]]})


def send_via_menu(name, menu_id):
    """消息名放在独立 shadow 菜单块里（Scratch 真实导出形态）。"""
    return block("event_broadcast",
                 inputs={"BROADCAST_INPUT": [1, menu_id]})


def menu_block(name, parent):
    return {"opcode": "event_broadcast_menu", "shadow": True, "parent": parent,
            "inputs": {}, "fields": {"BROADCAST_OPTION": [name, f"id-{name}"]}}


def receive_hat(name):
    return {"opcode": "event_whenbroadcastreceived", "next": None, "parent": None,
            "inputs": {}, "fields": {"BROADCAST_OPTION": [name, f"id-{name}"]},
            "topLevel": True}


class TestBroadcastPairing:
    RULE = {"type": "broadcast_pairing"}

    def test_paired_passes(self):
        blocks = {
            "h": hat(next_id="b"),
            "b": send_block("开始", parent="h"),
            "r": receive_hat("开始"),
        }
        result = run([self.RULE], make_summary(stage(), sprite(blocks=blocks)))
        assert result.status == PASSED, result.results[0].message

    def test_send_without_receiver_fails(self):
        blocks = {"h": hat(next_id="b"), "b": send_block("开始", parent="h")}
        result = run([self.RULE], make_summary(stage(), sprite(blocks=blocks)))
        assert result.status == FAILED
        assert "开始" in result.results[0].message

    def test_receiver_without_send_fails(self):
        blocks = {"r": receive_hat("胜利")}
        result = run([self.RULE], make_summary(stage(), sprite(blocks=blocks)))
        assert result.status == FAILED
        assert "胜利" in result.results[0].message

    def test_direction_send_only(self):
        blocks = {"r": receive_hat("胜利")}
        result = run([{"type": "broadcast_pairing", "direction": "send"}],
                     make_summary(stage(), sprite(blocks=blocks)))
        assert result.status == PASSED

    def test_direction_receive_only(self):
        blocks = {"h": hat(next_id="b"), "b": send_block("开始", parent="h")}
        result = run([{"type": "broadcast_pairing", "direction": "receive"}],
                     make_summary(stage(), sprite(blocks=blocks)))
        assert result.status == PASSED

    def test_shadow_menu_name_resolved(self):
        blocks = {
            "h": hat(next_id="b"),
            "b": send_via_menu("开始", "menu1"),
            "menu1": menu_block("开始", parent="b"),
            "r": receive_hat("开始"),
        }
        result = run([self.RULE], make_summary(stage(), sprite(blocks=blocks)))
        assert result.status == PASSED

    def test_variable_message_skipped_with_warning(self):
        # 消息名由变量决定：静态判不了，跳过 + 记 warning，不误判
        var_reporter = {"opcode": "data_variable", "shadow": False, "parent": "b",
                        "inputs": {}, "fields": {"VAR": ["消息", "vid"]},
                        "topLevel": False, "next": None}
        blocks = {
            "h": hat(next_id="b"),
            "b": block("event_broadcast", parent="h",
                       inputs={"BROADCAST_INPUT": [3, "v", [11, "默认", "did"]]}),
            "v": var_reporter,
            "r": receive_hat("随便"),
        }
        # [3, id, literal] 形态带被遮字面值：会取到 "默认"。真正"纯变量"形态是 [1, id]。
        blocks["b"]["inputs"]["BROADCAST_INPUT"] = [1, "v"]
        result = run([self.RULE], make_summary(stage(), sprite(blocks=blocks)))
        # "随便" 这个接收帽仍然没有发送方 → 仍失败；变量那条被跳过而不是乱配对
        assert result.status == FAILED
        assert "随便" in result.results[0].message
        assert result.results[0].evidence["warnings"]

    def test_invalid_direction_is_param_error(self):
        result = run([{"type": "broadcast_pairing", "direction": "up"}],
                     make_summary(stage(), sprite()))
        assert result.status == FAILED
        assert "参数错误" in result.results[0].message


# ---------- require_initialization ----------


class TestRequireInitialization:
    def test_position_initialized_passes(self):
        blocks = {
            "h": hat(next_id="g"),
            "g": block("motion_gotoxy", parent="h", next_id="loop"),
            "loop": block("control_repeat", parent="g",
                          inputs={"SUBSTACK": [2, "m"]}),
            "m": block("motion_movesteps", parent="loop"),
        }
        result = run([{"type": "require_initialization", "attributes": ["position"]}],
                     make_summary(stage(), sprite(blocks=blocks)))
        assert result.status == PASSED, result.results[0].message

    def test_position_relative_without_init_fails(self):
        blocks = {"h": hat(next_id="m"), "m": block("motion_movesteps", parent="h")}
        result = run([{"type": "require_initialization", "attributes": ["position"]}],
                     make_summary(stage(), sprite(blocks=blocks)))
        assert result.status == FAILED
        assert "小猫" in result.results[0].message

    def test_no_relative_use_is_vacuously_ok(self):
        blocks = {"h": hat(next_id="s"), "s": block("looks_say", parent="h")}
        result = run([{"type": "require_initialization", "attributes": ["position"]}],
                     make_summary(stage(), sprite(blocks=blocks)))
        assert result.status == PASSED

    def test_direction_init(self):
        blocks = {
            "h": hat(next_id="p"),
            "p": block("motion_pointindirection", parent="h", next_id="t"),
            "t": block("motion_turnright", parent="p"),
        }
        result = run([{"type": "require_initialization", "attributes": ["direction"]}],
                     make_summary(stage(), sprite(blocks=blocks)))
        assert result.status == PASSED

    def test_variable_init(self):
        var_blocks = {
            "h": hat(next_id="s"),
            "s": block("data_setvariableto", parent="h", next_id="loop",
                       fields={"VARIABLE": ["分数", "vid"]}),
            "loop": block("control_repeat", parent="s",
                          inputs={"SUBSTACK": [2, "c"]}),
            "c": block("data_changevariableby", parent="loop",
                       fields={"VARIABLE": ["分数", "vid"]}),
        }
        result = run(
            [{"type": "require_initialization", "attributes": ["variable:分数"]}],
            make_summary(stage(), sprite(blocks=var_blocks)))
        assert result.status == PASSED, result.results[0].message

    def test_variable_change_without_set_fails(self):
        blocks = {
            "h": hat(next_id="c"),
            "c": block("data_changevariableby", parent="h",
                       fields={"VARIABLE": ["分数", "vid"]}),
        }
        result = run(
            [{"type": "require_initialization", "attributes": ["variable:分数"]}],
            make_summary(stage(), sprite(blocks=blocks)))
        assert result.status == FAILED
        assert "分数" in result.results[0].message

    def test_init_inside_repeat_does_not_count(self):
        # 初始化必须沿主链在绿旗正下方；塞进循环里每次重设不算"初始化一次"
        blocks = {
            "h": hat(next_id="loop"),
            "loop": block("control_repeat", parent="h",
                          inputs={"SUBSTACK": [2, "g"]}),
            "g": block("motion_gotoxy", parent="loop", next_id="m"),
            "m": block("motion_movesteps", parent="g"),
        }
        result = run([{"type": "require_initialization", "attributes": ["position"]}],
                     make_summary(stage(), sprite(blocks=blocks)))
        assert result.status == FAILED

    def test_unknown_attribute_goes_needs_review(self):
        result = run([{"type": "require_initialization", "attributes": ["positoin"]}],
                     make_summary(stage(), sprite()))
        assert result.status == NEEDS_REVIEW

    def test_missing_attributes_is_param_error(self):
        result = run([{"type": "require_initialization"}],
                     make_summary(stage(), sprite()))
        assert result.status == FAILED
        assert "参数错误" in result.results[0].message

    def test_other_sprite_init_does_not_cover(self):
        # 位置是每角色各自的：甲角色初始化了，乙角色用了 movesteps 仍要失败
        cat = sprite(name="甲", blocks={
            "h": hat(next_id="g"),
            "g": block("motion_gotoxy", parent="h"),
        })
        dog = sprite(name="乙", blocks={
            "h": hat(next_id="m"),
            "m": block("motion_movesteps", parent="h"),
        })
        result = run([{"type": "require_initialization", "attributes": ["position"]}],
                     make_summary(stage(), cat, dog))
        assert result.status == FAILED
        assert "乙" in result.results[0].message


# ---------- require_structure ----------


class TestRequireStructure:
    PATTERN = {"opcode": "control_repeat",
               "contains": [{"opcode": "control_if",
                             "contains": [{"opcode": "operator_gt"}]}]}
    RULE = {"type": "require_structure", "pattern": PATTERN}

    def nested_project(self):
        return {
            "h": hat(next_id="r"),
            "r": block("control_repeat", parent="h",
                       inputs={"SUBSTACK": [2, "i"]}),
            "i": block("control_if", parent="r",
                       inputs={"CONDITION": [2, "gt"]}),
            "gt": block("operator_gt", parent="i"),
        }

    def test_nested_structure_passes(self):
        result = run([self.RULE],
                     make_summary(stage(), sprite(blocks=self.nested_project())))
        assert result.status == PASSED, result.results[0].message

    def test_missing_inner_condition_fails(self):
        blocks = {
            "h": hat(next_id="r"),
            "r": block("control_repeat", parent="h",
                       inputs={"SUBSTACK": [2, "i"]}),
            "i": block("control_if", parent="r"),  # 没有 operator_gt
        }
        result = run([self.RULE], make_summary(stage(), sprite(blocks=blocks)))
        assert result.status == FAILED

    def test_flat_repeat_without_if_fails(self):
        blocks = {
            "h": hat(next_id="r"),
            "r": block("control_repeat", parent="h",
                       inputs={"SUBSTACK": [2, "m"]}),
            "m": block("motion_movesteps", parent="r"),
        }
        result = run([self.RULE], make_summary(stage(), sprite(blocks=blocks)))
        assert result.status == FAILED

    def test_hat_constraint(self):
        # 结构存在，但不在绿旗下（挂在广播帽下面）→ 限定 hat 时不算
        blocks = self.nested_project()
        blocks["h"]["opcode"] = "event_whenbroadcastreceived"
        with_hat = dict(self.RULE, hat="event_whenflagclicked")
        result = run([with_hat], make_summary(stage(), sprite(blocks=blocks)))
        assert result.status == FAILED
        # 不限 hat 则通过
        result = run([self.RULE], make_summary(stage(), sprite(blocks=blocks)))
        assert result.status == PASSED

    def test_invalid_pattern_is_param_error(self):
        for bad in (None, {}, {"contains": []}, {"opcode": 42}, "control_repeat"):
            result = run([{"type": "require_structure", "pattern": bad}],
                         make_summary(stage(), sprite()))
            assert result.status == FAILED
            assert "参数错误" in result.results[0].message

    def test_contains_is_unordered_multi_requirement(self):
        pattern = {"opcode": "control_repeat",
                   "contains": [{"opcode": "motion_movesteps"},
                                {"opcode": "looks_say"}]}
        blocks = {
            "h": hat(next_id="r"),
            "r": block("control_repeat", parent="h", inputs={
                "SUBSTACK": [2, "m"], "SUBSTACK2": [2, "s"]}),
            "m": block("motion_movesteps", parent="r"),
            "s": block("looks_say", parent="r"),
        }
        result = run([{"type": "require_structure", "pattern": pattern}],
                     make_summary(stage(), sprite(blocks=blocks)))
        assert result.status == PASSED


# ---------- 真实 sb3 格式回归（对照 scratch-vm sb3.js 与官方 fixture 取证） ----------


class TestRealSb3Formats:
    """字段名以 scratch-editor/scratch-vm 真实导出为准：
    - 发送广播：inputs.BROADCAST_INPUT，内联 primitive 类型码 11（12/13 是变量/列表）
    - 变量积木：fields.VARIABLE（不是 VAR——VAR 是反序列化后的内存名）
    - 监视器：住在 project.json 顶层 monitors 数组，不进 blocks
    """

    def test_broadcast_input_real_name(self):
        # clear-color.sb3 的真实形态：inputs.BROADCAST_INPUT = [1, [11, name, id]]
        blocks = {
            "h": hat(next_id="b"),
            "b": block("event_broadcast", parent="h",
                       inputs={"BROADCAST_INPUT": [1, [11, "START", "broadcastMsgId-start"]]}),
            "r": receive_hat("START"),
        }
        result = run([{"type": "broadcast_pairing"}],
                     make_summary(stage(), sprite(blocks=blocks)))
        assert result.status == PASSED, result.results[0].message

    def test_broadcast_shadowed_menu_form(self):
        # [3, menuId, [11, 兜底]]：shadow 菜单遮住字面值，消息名以菜单块为准
        blocks = {
            "h": hat(next_id="b"),
            "b": block("event_broadcast", parent="h",
                       inputs={"BROADCAST_INPUT": [3, "menu1", [11, "旧名", "oid"]]}),
            "menu1": menu_block("开始", parent="b"),
            "r": receive_hat("开始"),
        }
        result = run([{"type": "broadcast_pairing"}],
                     make_summary(stage(), sprite(blocks=blocks)))
        assert result.status == PASSED, result.results[0].message

    def test_broadcast_inline_variable_primitive_skipped(self):
        # [1, [12, 变量名, id]]：内联变量 primitive，消息名运行时才定 → 跳过+warning
        blocks = {
            "h": hat(next_id="b"),
            "b": block("event_broadcast", parent="h",
                       inputs={"BROADCAST_INPUT": [1, [12, "频道", "vid"]]}),
        }
        result = run([{"type": "broadcast_pairing"}],
                     make_summary(stage(), sprite(blocks=blocks)))
        assert result.status == PASSED
        assert result.results[0].evidence["warnings"]

    def test_variable_field_real_name(self):
        # fields.VARIABLE（clear-color.sb3 实证），不是 VAR
        blocks = {
            "h": hat(next_id="s"),
            "s": block("data_setvariableto", parent="h", next_id="c",
                       fields={"VARIABLE": ["分数", "vid-分数"]}),
            "c": block("data_changevariableby", parent="s",
                       fields={"VARIABLE": ["分数", "vid-分数"]}),
        }
        result = run(
            [{"type": "require_initialization", "attributes": ["variable:分数"]}],
            make_summary(stage(), sprite(blocks=blocks)))
        assert result.status == PASSED, result.results[0].message

    def test_monitors_do_not_pollute_blocks(self):
        # 监视器在顶层 monitors 数组里（monitor-variable.sb3 实证），不进 blocks，
        # no_dead_code 不该把它们当死代码。
        st = stage()
        sp = sprite(blocks={"h": hat()})
        summary = make_summary(st, sp)
        # 模拟真实 project.json：监视器与 blocks 平级
        st["monitors"] = [{"opcode": "data_variable", "params": {"VAR": "分数"},
                           "visible": True, "topLevel": True, "x": 5, "y": 5}]
        result = run([{"type": "no_dead_code"}], summary)
        assert result.status == PASSED

    def test_procedures_definition_with_prototype_not_dead(self):
        # 自定义积木：definition 是合法帽子；prototype 挂在其 inputs.custom_block 下
        blocks = {
            "def": block("procedures_definition", top_level=True,
                         inputs={"custom_block": [1, "proto"]}),
            "proto": block("procedures_prototype", parent="def"),
        }
        result = run([{"type": "no_dead_code"}], make_summary(stage(), sprite(blocks=blocks)))
        assert result.status == PASSED

    def test_compressed_primitive_skipped(self):
        # 顶层裸变量读取是压缩数组而不是对象：遍历必须跳过，不能 AttributeError
        blocks = {
            "h": hat(),
            "prim": [12, "分数", "vid", 10, 20],
        }
        result = run([{"type": "no_dead_code"}], make_summary(stage(), sprite(blocks=blocks)))
        assert result.status == PASSED
