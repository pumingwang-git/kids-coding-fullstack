import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

# 编辑器会在保存前收紧为无空格格式；服务端仍兼容用户手工输入时在
# placeholder、方括号或花括号之间插入的空白字符。
BLANK_KEY_RE = re.compile(
    r"\\placeholder\s*\[\s*([A-Za-z][A-Za-z0-9_-]{0,63})\s*\]\s*\{\s*[^{}]*\s*\}"
)


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    captcha_id: str | None = Field(default=None, min_length=36, max_length=36)
    captcha_answer: str | None = Field(default=None, min_length=5, max_length=5)

    @field_validator("username")
    @classmethod
    def username_not_blank(cls, value):
        if not value.strip():
            raise ValueError("用户名不能为空")
        return value

    @field_validator("password")
    @classmethod
    def password_meets_requirements(cls, value):
        if not re.search(r"[A-Za-z]", value):
            raise ValueError("密码必须包含英文字母")
        if not re.search(r"\d", value):
            raise ValueError("密码必须包含数字")
        if not re.search(r"[^A-Za-z0-9\s]", value):
            raise ValueError("密码必须包含特殊符号")
        return value


class LoginRequest(BaseModel):
    identifier: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=128)
    captcha_id: str | None = Field(default=None, min_length=36, max_length=36)
    captcha_answer: str | None = Field(default=None, min_length=5, max_length=5)
    mfa_code: str | None = Field(default=None, pattern=r"^\d{6}$")


class VerificationRequest(BaseModel):
    email: EmailStr
    code: str = Field(pattern=r"^\d{6}$")


class ResendRequest(BaseModel):
    email: EmailStr


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirmRequest(BaseModel):
    email: EmailStr
    code: str = Field(pattern=r"^\d{6}$")
    new_password: str = Field(min_length=12, max_length=128)
    mfa_code: str | None = Field(default=None, pattern=r"^\d{6}$")

    @field_validator("new_password")
    @classmethod
    def new_password_meets_requirements(cls, value):
        if (
            not re.search(r"[A-Za-z]", value)
            or not re.search(r"\d", value)
            or not re.search(r"[^A-Za-z0-9\s]", value)
        ):
            raise ValueError("密码必须包含英文字母、数字和特殊符号")
        return value


class PasswordChangeRequest(BaseModel):
    """Authenticated password change confirmed by the account email."""

    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=12, max_length=128)
    code: str = Field(pattern=r"^\d{6}$")

    @field_validator("new_password")
    @classmethod
    def new_password_meets_requirements(cls, value):
        if (
            not re.search(r"[A-Za-z]", value)
            or not re.search(r"\d", value)
            or not re.search(r"[^A-Za-z0-9\s]", value)
        ):
            raise ValueError("密码必须包含英文字母、数字和特殊符号")
        return value


class PasswordChangeVerificationRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)


class MfaCodeRequest(BaseModel):
    code: str = Field(pattern=r"^\d{6}$")


class AdminLoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=1, max_length=128)
    slider_id: str | None = Field(default=None, min_length=36, max_length=36)
    slider_x: int | None = Field(default=None, ge=0, le=400)


class SliderVerifyRequest(BaseModel):
    slider_id: str = Field(min_length=36, max_length=36)
    slider_x: int = Field(ge=0, le=400)


class UserResponse(BaseModel):
    id: int
    username: str
    email: EmailStr
    status: str
    mfa_enabled: bool = False
    # access_token 的过期时刻（aware UTC，FastAPI 序列化为 ISO）+ 生命周期（分钟）。
    # 学员端主动续期（文档17 P1）据此算时机：remaining < lifetime * 20% 时续。
    # access_expires_at 由 /me 和 /refresh（create_login_response）填充；
    # access_token_minutes 仅 /me 填充（配置值，不变）。其他用 UserResponse 的地方留 None。
    access_expires_at: datetime | None = None
    access_token_minutes: int | None = None
    # 学生个人资料（文档 28 P2）：/me 一并带回，顶部头像/资料卡直接可用。
    # 没有资料行时为 None，前端回落默认头像/空签名。
    avatar_url: str | None = None
    learning_signature: str | None = None

# ==================== 题库（problems） ====================

ProblemType = Literal["choice", "multi_choice", "judge", "fill", "programming"]
ProgrammingLanguage = Literal["cpp", "python"]
PassCondition = Literal["编译通过", "样例通过", "全测试点通过"]
DIFFICULTIES = {"入门", "普及-", "普及", "普及+", "提高-", "提高", "提高+", "省选", "NOI", "普及/提高-", "普及+/提高", "提高+/省选-", "省选/NOI-", "NOI/NOI+/CTSC"}
SOURCES = {"第三方", "原创", "自命题", "洛谷", "NOIP", "CSP-J", "CSP-S", "USACO"}
STRUCTURES = {"单项知识点", "多项知识点", "综合应用"}


class CommonTagPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    difficulty: str = Field(default="入门", max_length=32)
    source: str = Field(default="第三方", max_length=64)
    structure: str = Field(default="单项知识点", max_length=32)
    knowledge: list[str] = Field(default_factory=list, max_length=20)
    stage: list[str] = Field(default_factory=list, max_length=20)
    business: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("knowledge", "stage", "business")
    @classmethod
    def tags_are_clean_and_unique(cls, value: list[str]) -> list[str]:
        cleaned = [name.strip() for name in value]
        if any(not name or len(name) > 64 for name in cleaned) or len(set(cleaned)) != len(cleaned):
            raise ValueError("标签不能为空、不能超过 64 个字符且不能重复。")
        return cleaned

    @model_validator(mode="after")
    def enum_values_are_known(self):
        if self.difficulty not in DIFFICULTIES:
            raise ValueError("不支持的难度。")
        if self.source not in SOURCES:
            raise ValueError("不支持的来源。")
        if self.structure not in STRUCTURES:
            raise ValueError("不支持的题目结构。")
        return self


class OptionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str = Field(default="", max_length=20_000)
    is_correct: bool = False


class BlankPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    blank_index: int = 0
    blank_key: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
    # 标准答案：展示给学员的那一个写法
    answer: str = Field(default="", max_length=10_000)
    # 其它同样算对的写法。判分时与 answer 平权，展示时一概不用。
    # 上限 20 条：再多说明这个空问得太开放，该改题面而不是继续堆同义词。
    alternatives: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("alternatives")
    @classmethod
    def alternatives_are_clean(cls, value: list[str]) -> list[str]:
        """去空、去重、限长。去重按原样字符串做，规范化后的去重交给判分层——
        这里把 'List' 和 'list' 合并掉的话，录题人就再也看不到自己填过什么。"""
        cleaned: list[str] = []
        for item in value:
            item = item.strip()
            if len(item) > 10_000:
                raise ValueError("可接受写法过长。")
            if item and item not in cleaned:
                cleaned.append(item)
        return cleaned


class RejectProblemPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("reason")
    @classmethod
    def rejection_reason_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("请填写打回原因。")
        return value.strip()


class SamplePayload(BaseModel):
    """样例。**不设逐点限制**——样例是给人看的示范，学员照着样例估算耗时，
    样例的限制与真正判分的隐藏点不一致只会误导。样例恒继承题目级。"""

    model_config = ConfigDict(extra="forbid")
    input: str = Field(default="", max_length=100_000)
    output: str = Field(default="", max_length=100_000)


class ManualTestCasePayload(BaseModel):
    """Python 手工隐藏测试点；文件引用只允许由服务器生成。"""

    model_config = ConfigDict(extra="forbid")
    input: str = Field(default="", max_length=100_000)
    output: str = Field(default="", max_length=100_000)
    time_limit_ms: int | None = Field(default=None, ge=100, le=10_000)
    memory_limit_mb: int | None = Field(default=None, ge=16, le=512)


class RefCodePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cpp: str = Field(default="", max_length=200_000)
    python: str = Field(default="", max_length=200_000)


class TestcaseLimitsPayload(BaseModel):
    """「统一设定」的请求体：只改题目级，逐点值由服务端清空回到继承。"""
    model_config = ConfigDict(extra="forbid")
    time_limit_ms: int = Field(ge=100, le=10_000)
    memory_limit_mb: int = Field(ge=16, le=512)


class ImportedCaseMetaPayload(BaseModel):
    """ZIP 导入的单个测试点的可编辑元数据：分值与逐点限制。

    输入输出不在这里——那是 ZIP 的内容，改它得重新上传，否则库里的元数据
    和磁盘上的 .in/.out 就对不上了。
    """

    model_config = ConfigDict(extra="forbid")
    case_no: int = Field(ge=1, le=10_000)
    # None = 不单独计分，判分时按等权 1 处理（与 config.yaml 不写 score 一致）
    score: int | None = Field(default=None, ge=0, le=1000)
    # None = 继承题目级。范围与题目级同一套（见 ProgrammingPayload）。
    time_limit_ms: int | None = Field(default=None, ge=100, le=10_000)
    memory_limit_mb: int | None = Field(default=None, ge=16, le=512)


class ImportedCasesPayload(BaseModel):
    """已导入测试点的批量改动。整表提交而不是逐行 PATCH：
    分值是一组相对权重，逐行提交时中间状态的总分是错的。"""

    model_config = ConfigDict(extra="forbid")
    cases: list[ImportedCaseMetaPayload] = Field(default_factory=list, max_length=500)


class ProgrammingPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(default="", max_length=200)
    pass_condition: PassCondition = "编译通过"
    input_format: str = Field(default="", max_length=20_000)
    output_format: str = Field(default="", max_length=20_000)
    hints: str = Field(default="无", max_length=20_000)
    samples: list[SamplePayload] = Field(default_factory=list, max_length=20)
    ref_code: RefCodePayload = Field(default_factory=RefCodePayload)
    manual_test_cases: list[ManualTestCasePayload] = Field(default_factory=list, max_length=50)
    # 题目级限制。范围推导见交接文档 §3：
    # 时间上限 10s 卡在 judge_timeout_seconds（判题层 clockLimit = 2× cpuLimit）；
    # 内存上限 512MB 由《判题沙箱搭建手册》§二的内存账推出，提到 512 以上必须先加内存重算。
    time_limit_ms: int = Field(default=1000, ge=100, le=10_000)
    memory_limit_mb: int = Field(default=256, ge=16, le=512)


class ProblemPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: ProblemType
    sub_type: ProgrammingLanguage | None = None
    common: CommonTagPayload = Field(default_factory=CommonTagPayload)
    stem: str = Field(default="", max_length=50_000)
    analysis: str = Field(default="", max_length=50_000)
    analysis_video_id: int | None = Field(default=None, ge=1)
    options: list[OptionPayload] = Field(default_factory=list, max_length=8)
    blanks: list[BlankPayload] = Field(default_factory=list, max_length=50)
    programming: ProgrammingPayload | None = None

    @model_validator(mode="after")
    def data_matches_problem_type(self):
        if self.type == "programming":
            if self.sub_type not in {"cpp", "python"} or not self.programming:
                raise ValueError("操作题必须提供 cpp/python 子类型和操作题内容。")
            if self.options or self.blanks:
                raise ValueError("操作题不能携带选择或填空答案。")
            if self.sub_type == "cpp" and self.programming.manual_test_cases:
                raise ValueError("C++ 隐藏测试点只能通过 ZIP 上传。")
            return self
        if self.sub_type is not None or self.programming is not None:
            raise ValueError("非操作题不能设置 sub_type。")
        if self.type in {"choice", "multi_choice", "judge"}:
            if self.blanks:
                raise ValueError("选择或判断题不能携带填空答案。")
            if self.type == "judge" and self.options and [item.content for item in self.options] != ["对", "错"]:
                raise ValueError("判断题选项必须固定为“对”和“错”。")
            return self
        if self.type != "fill":
            return self
        if self.options:
            raise ValueError("填空题不能携带选择答案。")
        # 草稿允许暂存未完成的空位；提交审核时由服务端基于已落库内容做完整校验。
        keys = BLANK_KEY_RE.findall(self.stem)
        if keys and len(set(keys)) != len(keys):
            raise ValueError("同一填空题内的 placeholder 标识必须唯一。")
        answer_keys = [blank.blank_key for blank in self.blanks]
        if keys and answer_keys and answer_keys != keys:
            raise ValueError("填空答案必须与题干 placeholder 按出现顺序一一对应。")
        if self.blanks and [blank.blank_index for blank in self.blanks] != list(range(len(self.blanks))):
            raise ValueError("填空答案的 blank_index 必须从 0 按顺序连续编号。")
        return self


class TransferProblemOwnerPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    owner_id: int = Field(ge=1)


class DryRunPayload(BaseModel):
    """参考代码试跑的请求体。

    language 省略时用题目的 sub_type——绝大多数情况下要跑的就是那一门；
    显式给是为了 C++ 题里也放了 Python 参考代码时能分别验一遍。
    """

    model_config = ConfigDict(extra="forbid")
    language: ProgrammingLanguage | None = None
    # samples = 只跑公开样例（快，改完题面点一下）；all = 全部测试点（提交审核前的完整验证）；
    # custom = 一次性 stdin，手工探边界输入。
    scope: Literal["samples", "all", "custom"] = "all"
    custom_input: str | None = Field(default=None, max_length=64_000)

    @model_validator(mode="after")
    def custom_scope_needs_input(self):
        if self.scope == "custom" and self.custom_input is None:
            raise ValueError("自定义输入试跑必须提供输入内容。")
        return self


class CreateTagPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=64)
    category: Literal["knowledge", "stage", "business"]
    parent_id: int | None = Field(default=None, ge=1)  # 三级树：父标签 id（一级为 None）
    description: str | None = Field(default=None, max_length=500)  # 悬浮提示/说明


# ==================== 试卷（papers） ====================

PAPER_TYPES = {"练习卷", "测试卷", "模拟卷", "竞赛卷", "作业卷"}
PaperSubject = Literal["cpp", "python", "scratch", "general"]
PaperRuleset = Literal["IOI", "ACM", "OI", "custom"]
ScoreMode = Literal["testcase", "all_or_nothing"]
ScorePolicy = Literal["best", "last", "first"]
FeedbackMode = Literal["realtime", "compile_only", "after_close"]
ShowAnalysis = Literal["never", "after_submit", "after_close"]
ShowScore = Literal["immediate", "after_close", "never"]
LateStartPolicy = Literal["truncate", "block", "overrun"]


class PaperQuestionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    problem_id_no: str = Field(min_length=1, max_length=64)
    score: int = Field(ge=1, le=100_000)
    sort_order: int = Field(default=0, ge=0)


class PaperPayload(BaseModel):
    """试卷（内容层）全量更新载荷：属性 + 题目清单一次提交，与题库 options/blanks 同风格。

    时间/次数/呈现等考试安排属性不在这里——它们属于 ExamLinkPayload（场次层）。
    """
    model_config = ConfigDict(extra="forbid")
    # 必填，不给默认值：Pydantic 不校验默认值，留 default="" 会让"省略 title"绕过 title_not_blank。
    title: str = Field(max_length=200)
    description: str = Field(default="", max_length=20_000)
    paper_type: str = Field(default="练习卷", max_length=32)
    subject: PaperSubject = "cpp"
    ruleset: PaperRuleset = "IOI"  # 仅记录预设来源，后端不做行为分支
    score_mode: ScoreMode = "testcase"
    partial_credit_multi: bool = False
    pass_score: int | None = Field(default=None, ge=0, le=100_000)
    questions: list[PaperQuestionPayload] = Field(default_factory=list, max_length=200)

    @field_validator("title")
    @classmethod
    def title_not_blank(cls, value: str) -> str:
        # strip 后判空：纯空格标题也要拦住。删题时的引用保护报错列的是试卷名，
        # 空标题会让「题目已被引用，无法删除：」后面没有指引。
        if not value.strip():
            raise ValueError("请填写试卷名称。")
        return value.strip()

    @model_validator(mode="after")
    def fields_are_consistent(self):
        if self.paper_type not in PAPER_TYPES:
            raise ValueError("不支持的试卷类型。")
        id_nos = [item.problem_id_no.strip() for item in self.questions]
        if len(set(id_nos)) != len(id_nos):
            raise ValueError("同一道题不能重复加入试卷。")
        if self.pass_score is not None and self.pass_score > sum(item.score for item in self.questions):
            raise ValueError("及格分不能超过试卷总分。")
        return self


class ExamLinkPayload(BaseModel):
    """考试链接（场次层）：一次考试安排。一张卷可有多条，各自独立配置。"""
    model_config = ConfigDict(extra="forbid")
    name: str = Field(max_length=100)  # 必填，同 title 的理由：列表靠它区分场次
    open_at: datetime | None = None
    close_at: datetime | None = None
    duration_minutes: int | None = Field(default=None, ge=1, le=100_000)  # null = 不限时
    late_start_policy: LateStartPolicy = "truncate"
    attempt_limit: int = Field(default=1, ge=0, le=100)  # 按链接计数，0 = 不限
    score_policy: ScorePolicy = "best"
    penalty_minutes: int = Field(default=0, ge=0, le=10_000)  # 本期只存不用
    feedback_mode: FeedbackMode = "realtime"
    show_analysis: ShowAnalysis = "after_submit"
    show_score: ShowScore = "immediate"
    shuffle_questions: bool = False
    shuffle_options: bool = False
    # ---- 考前提醒与规则：本期只在后台配置与存储，学员端（M9）消费 ----
    notice: str = Field(default="", max_length=5_000)
    notice_ack_required: bool = False
    entry_open_minutes: int = Field(default=0, ge=0, le=1440)
    remind_minutes: str = Field(default="", max_length=64)
    warn_unanswered: bool = True

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("请填写链接名称。")
        return value.strip()

    @field_validator("remind_minutes")
    @classmethod
    def normalize_reminders(cls, value: str) -> str:
        """规范化后落库：去重、降序、逗号分隔。库里永远是规范形式，
        学员端读出来 split(",") 即可用，不必再排序去重——那是重复且容易漏的一步。"""
        tokens = [token for token in re.split(r"[,，、\s]+", value or "") if token]
        minutes: set[int] = set()
        for token in tokens:
            if not token.isdigit():
                raise ValueError("考中提醒只能填分钟数，用逗号分隔（如 30,10,5）。")
            minute = int(token)
            if not 1 <= minute <= 1440:
                raise ValueError("考中提醒的分钟数必须在 1–1440 之间。")
            minutes.add(minute)
        if len(minutes) > 5:
            raise ValueError("考中提醒最多设置 5 个时间点。")
        return ",".join(str(minute) for minute in sorted(minutes, reverse=True))

    @model_validator(mode="after")
    def schedule_is_consistent(self):
        if self.open_at and self.close_at and self.open_at >= self.close_at:
            raise ValueError("开放时间必须早于关闭时间。")
        if self.late_start_policy == "block" and self.open_at and self.close_at and self.duration_minutes:
            window = (self.close_at - self.open_at).total_seconds()
            if window < self.duration_minutes * 60:
                raise ValueError("开放窗口短于考试时长，禁止开始策略下没有任何人能开始作答。")
        # 下面四条都是「配了也永远不会触发」的死配置：
        if self.remind_minutes and self.duration_minutes is None and self.close_at is None:
            raise ValueError("不限时且不设关闭时间的链接算不出剩余时间，无法设置考中提醒。")
        if self.remind_minutes and self.duration_minutes:
            if int(self.remind_minutes.split(",")[0]) >= self.duration_minutes:
                raise ValueError("考中提醒的时间点必须小于考试时长，否则永远不会触发。")
        if self.entry_open_minutes and self.open_at is None:
            raise ValueError("未设开放时间的链接本来就随时可进，无需配置提前进入。")
        if self.notice_ack_required and not self.notice.strip():
            raise ValueError("要求确认已读时，考试须知不能为空。")
        return self


class TransferPaperOwnerPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    owner_id: int = Field(ge=1)


# ==================== 学员端作答 ====================
# 判别联合：answer.type 必须与题目实际题型一致，不一致 422 挡在门口。
# 让脏数据进库、等交卷判分时才炸，排查成本高一个数量级。


class ChoiceAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["choice", "judge"]
    picked: str | None = Field(default=None, max_length=8)  # 选项原始 label，不是洗牌后的下标


class MultiChoiceAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["multi_choice"]
    picked: list[str] = Field(default_factory=list, max_length=26)

    @field_validator("picked")
    @classmethod
    def labels_are_short_and_unique(cls, value: list[str]) -> list[str]:
        if any(len(item) > 8 for item in value):
            raise ValueError("选项标识不合法。")
        return sorted(set(value))


class FillAnswerPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["fill"]
    blanks: dict[str, str] = Field(default_factory=dict)

    @field_validator("blanks")
    @classmethod
    def blanks_within_limits(cls, value: dict[str, str]) -> dict[str, str]:
        if len(value) > 50:
            raise ValueError("填空数量超出限制。")
        if any(len(item) > 2_000 for item in value.values()):
            raise ValueError("填空内容过长。")
        return value


class ProgrammingAnswer(BaseModel):
    """编程题作答：已提交记录用于计分，草稿代码用于跨刷新恢复，二者不能互相覆盖。"""
    model_config = ConfigDict(extra="forbid")
    type: Literal["programming"]
    language: ProgrammingLanguage | None = None
    submission_id: int | None = Field(default=None, ge=1)
    draft_code: str | None = Field(default=None, max_length=200_000)


ExamAnswer = ChoiceAnswer | MultiChoiceAnswer | FillAnswerPayload | ProgrammingAnswer


class SaveAnswerPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    problem_id_no: str = Field(min_length=1, max_length=64)
    answer: ExamAnswer = Field(discriminator="type")


class SubmitCodePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    problem_id_no: str = Field(min_length=1, max_length=64)
    language: ProgrammingLanguage
    code: str = Field(default="", max_length=64_000)
    kind: Literal["trial", "submit"] = "trial"
    # 自测的自定义输入。只对 kind="trial" 生效，submit 携带时忽略而不是 422——
    # 前端切页签时把它一起带上是常事，为此报错只会让人莫名其妙交不上。
    # 空串是合法的「用空输入跑一次」，与 None（跑库里的样例）语义不同。
    custom_input: str | None = Field(default=None, max_length=64_000)
