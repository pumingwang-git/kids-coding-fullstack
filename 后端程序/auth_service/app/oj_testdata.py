"""安全解析 Hydro 风格的 OJ 测试数据 ZIP。

只识别数字编号的 ``N.in`` / ``N.out`` 配对；配置文件与数据文件分离，
``config.yaml`` 仅承载时空限制、比较器和分值等元数据。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path, PurePosixPath
import re
import zipfile

import yaml


CASE_FILE_RE = re.compile(r"^(?P<number>[1-9]\d*)\.(?P<kind>in|out)$", re.IGNORECASE)


@dataclass(frozen=True)
class ImportedCase:
    case_no: int
    input_member: str
    output_member: str
    score: int | None
    time_limit_ms: int | None = None
    memory_limit_mb: int | None = None


@dataclass(frozen=True)
class ParsedTestData:
    config_yaml: str | None
    checker: str
    time_limit_ms: int | None
    memory_limit_mb: int | None
    cases: list[ImportedCase]


def _safe_member(name: str) -> PurePosixPath:
    path = PurePosixPath(name.replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts or not path.name:
        raise ValueError("压缩包包含不安全的文件路径。")
    return path


# 限制的取值范围，与 app/schemas.py 的 Field(ge=..., le=...) 必须是同一套数：
# 时间上限卡在 judge_timeout_seconds（判题层 clockLimit = 2× cpuLimit）；
# 内存上限由《判题沙箱搭建手册》§二的内存账推出，提到 512 以上必须先加内存重算。
TIME_LIMIT_RANGE = (100, 10_000)
MEMORY_LIMIT_RANGE = (16, 512)


def _check_range(value: int, *, milliseconds: bool, where: str) -> int:
    lo, hi = TIME_LIMIT_RANGE if milliseconds else MEMORY_LIMIT_RANGE
    unit = "ms" if milliseconds else "MB"
    if not (lo <= value <= hi):
        raise ValueError(f"config.yaml {where}超出范围 [{lo}, {hi}]{unit}。")
    return value


def _parse_limit(value: object, *, milliseconds: bool) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("config.yaml 中的限制值必须是数字。")
    if isinstance(value, (int, float)):
        parsed = float(value)
    elif isinstance(value, str):
        match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*(ms|s|mb|m)?\s*", value, re.IGNORECASE)
        if not match:
            raise ValueError("config.yaml 中的限制值格式不正确。")
        parsed = float(match.group(1))
        suffix = (match.group(2) or "").lower()
        if milliseconds and suffix == "s":
            parsed *= 1000
        # m 与 mb 都当 MB。"256m" 是内存的常见写法，按 1024 倍放大只会得到 262144MB
        # 这种荒谬值——加了范围校验之后它还会变成一条莫名其妙的 400。
    else:
        raise ValueError("config.yaml 中的限制值必须是数字。")
    result = int(parsed)
    if result <= 0:
        raise ValueError("config.yaml 中的限制值必须大于 0。")
    return result


def _case_meta(config: dict) -> dict[int, dict]:
    """解析 config.yaml 的逐点元数据：score + 可选的 time_limit_ms / memory_limit_mb。
    校验口径与 schema 一致：超范围抛 ValueError，让上传接口回 400 并指明是哪个测试点。"""
    raw_cases = config.get("cases", config.get("test_cases", {}))
    metas: dict[int, dict] = {}
    if isinstance(raw_cases, dict):
        entries = raw_cases.items()
    elif isinstance(raw_cases, list):
        entries = ((item.get("case", item.get("id")), item) for item in raw_cases if isinstance(item, dict))
    elif raw_cases in (None, ""):
        return metas
    else:
        raise ValueError("config.yaml 的 cases 必须是对象或列表。")
    for number, meta in entries:
        try:
            case_no = int(number)
        except (TypeError, ValueError) as exc:
            raise ValueError("config.yaml 的测试点编号必须是正整数。") from exc
        if case_no <= 0 or not isinstance(meta, dict):
            continue
        item: dict = {}
        if "score" in meta:
            score = meta["score"]
            if isinstance(score, bool) or not isinstance(score, (int, float)) or score < 0 or int(score) != score:
                raise ValueError("config.yaml 的测试点分值必须是非负整数。")
            item["score"] = int(score)
        for key, milliseconds in (("time_limit_ms", True), ("memory_limit_mb", False)):
            if key not in meta or meta[key] is None:
                continue
            value = _parse_limit(meta[key], milliseconds=milliseconds)
            item[key] = _check_range(value, milliseconds=milliseconds, where=f"测试点 {case_no} 的 {key} ")
        metas[case_no] = item
    return metas


def parse_testdata_zip(raw: bytes, *, max_files: int, max_unpacked_bytes: int) -> ParsedTestData:
    try:
        archive = zipfile.ZipFile(BytesIO(raw))
    except zipfile.BadZipFile as exc:
        raise ValueError("上传文件不是有效的 ZIP 压缩包。") from exc

    with archive:
        infos = [info for info in archive.infolist() if not info.is_dir()]
        if len(infos) > max_files:
            raise ValueError(f"压缩包文件数不能超过 {max_files} 个。")
        if sum(info.file_size for info in infos) > max_unpacked_bytes:
            raise ValueError("压缩包解压后的总大小超出限制。")

        files: dict[tuple[int, str], str] = {}
        config_member: str | None = None
        for info in infos:
            if info.flag_bits & 0x1:
                raise ValueError("不支持加密 ZIP 压缩包。")
            # Unix symlink mode; do not follow a link embedded in an archive.
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError("压缩包不能包含符号链接。")
            path = _safe_member(info.filename)
            if path.name.lower() == "config.yaml":
                if config_member:
                    raise ValueError("压缩包只能包含一份 config.yaml。")
                config_member = info.filename
                continue
            suffix = path.suffix.lower()
            match = CASE_FILE_RE.fullmatch(path.name)
            if suffix in (".in", ".out") and not match:
                raise ValueError("测试点文件必须以数字编号命名，例如 1.in 和 1.out。")
            if not match:
                continue
            key = (int(match.group("number")), match.group("kind").lower())
            if key in files:
                raise ValueError(f"测试点 {key[0]}.{key[1]} 重复。")
            files[key] = info.filename

        numbers = sorted({number for number, _ in files})
        if not numbers:
            raise ValueError("未识别到测试点；请使用 1.in / 1.out 这类数字编号文件。")
        incomplete = [str(number) for number in numbers if (number, "in") not in files or (number, "out") not in files]
        if incomplete:
            raise ValueError("以下测试点缺少 .in 或 .out 配对文件：" + "、".join(incomplete))

        config_yaml = archive.read(config_member).decode("utf-8-sig") if config_member else None
        try:
            config = yaml.safe_load(config_yaml) if config_yaml else {}
        except yaml.YAMLError as exc:
            raise ValueError("config.yaml 格式错误。") from exc
        if config is None:
            config = {}
        if not isinstance(config, dict):
            raise ValueError("config.yaml 根节点必须是对象。")
        checker = str(config.get("checker", config.get("comparator", "default"))).strip() or "default"
        if len(checker) > 128:
            raise ValueError("config.yaml 的 checker 过长。")
        case_meta = _case_meta(config)
        # 题目级限制和逐点限制走同一套范围校验。少了这两行，config.yaml 里写
        # memory_limit: 4096 就能把题目级顶到 4G，绕开手册第二节那笔内存账。
        time_limit_ms = _parse_limit(config.get("time_limit_ms", config.get("time_limit")), milliseconds=True)
        memory_limit_mb = _parse_limit(config.get("memory_limit_mb", config.get("memory_limit")), milliseconds=False)
        if time_limit_ms is not None:
            _check_range(time_limit_ms, milliseconds=True, where="的 time_limit ")
        if memory_limit_mb is not None:
            _check_range(memory_limit_mb, milliseconds=False, where="的 memory_limit ")
        return ParsedTestData(
            config_yaml=config_yaml,
            checker=checker,
            time_limit_ms=time_limit_ms,
            memory_limit_mb=memory_limit_mb,
            cases=[
                ImportedCase(
                    number, files[(number, "in")], files[(number, "out")],
                    case_meta.get(number, {}).get("score"),
                    case_meta.get(number, {}).get("time_limit_ms"),
                    case_meta.get(number, {}).get("memory_limit_mb"),
                )
                for number in numbers
            ],
        )


def build_config_yaml(*, time_limit_ms: int, memory_limit_mb: int, checker: str,
                      cases: Sequence[Mapping[str, int | None]]) -> str:
    """按当前库里的值生成 config.yaml。

    **生成器和解析器必须放在同一个文件里**：形状要与 `_case_meta()` 能吃进去的
    完全一致，隔开放迟早漂成两套。这条性质是导出的意义所在——下载下来改一改再传回去，
    分值和逐点限制不能在这一趟里丢。

    逐点只写设过的键：写成 `time_limit_ms: null` 会被解析器当成"没设"，虽然结果一样，
    但清单里满屏的 null 会让人以为这些点真的配置过。

    cases 的每一项形如 {"case_no": 1, "score": 50, "time_limit_ms": None, ...}。
    """
    payload: dict = {
        "time_limit_ms": time_limit_ms,
        "memory_limit_mb": memory_limit_mb,
        "checker": checker or "default",
    }
    entries: dict[int, dict] = {}
    for case in cases:
        meta = {key: case.get(key) for key in ("score", "time_limit_ms", "memory_limit_mb")}
        entries[int(case["case_no"])] = {key: value for key, value in meta.items() if value is not None}
    if entries:
        payload["cases"] = dict(sorted(entries.items()))
    return yaml.safe_dump(payload, allow_unicode=True, sort_keys=False, default_flow_style=False)


def write_testdata_files(raw: bytes, parsed: ParsedTestData, destination: Path) -> None:
    """按解析结果写入目标目录；不使用 ZipFile.extractall 避免 Zip Slip。"""
    destination.mkdir(parents=True, exist_ok=False)
    with zipfile.ZipFile(BytesIO(raw)) as archive:
        for case in parsed.cases:
            (destination / f"{case.case_no}.in").write_bytes(archive.read(case.input_member))
            (destination / f"{case.case_no}.out").write_bytes(archive.read(case.output_member))


class JudgeDataUnavailable(RuntimeError):
    """测试点内容读不出来。

    调用方**必须**按 judge_failed 处理，绝不能当成空字符串继续判——那正是本函数
    存在之前的行为：ZIP 导入的点 input/output 两列是空串，判题却只读这两列，
    于是所有隐藏测试点都按"空输入→期望空输出"判，不输出任何东西的程序反而满分。
    """


def read_case_content(settings, case) -> tuple[str, str]:
    """取一个测试点的（输入, 期望输出）。

    ``case`` 是一行 TestCase。判断依据是 ``input_file`` 而不是 ``is_sample``：
    ZIP 导入的点内容在磁盘、两个正文列是空串；手工录入的点（含 Python 隐藏点）
    内容在库里、没有文件。手工点也没有 is_sample 之外的标记，用 is_sample 分辨会错。

    放在本模块而不是 exam.py：磁盘布局是这里的知识（write_testdata_files 就在上面），
    而且判题与题库侧的参考代码试跑都要读，路由之间不该互相 import。
    """
    if not case.input_file:
        return case.input or "", case.output or ""
    root = Path(settings.testdata_upload_root).resolve()
    return (
        _read_under_root(root, case.input_file, settings.judge_case_max_bytes),
        _read_under_root(root, case.output_file, settings.judge_case_max_bytes),
    )


def _read_under_root(root: Path, relative: str | None, max_bytes: int) -> str:
    if not relative:
        return ""
    target = (root / relative).resolve()
    # 归属校验：这些值来自数据库不是用户输入，但一次写错的迁移就能让它变成
    # ../../etc/passwd，而这里读到的东西会原样送进沙箱当 stdin。
    if root not in target.parents:
        raise JudgeDataUnavailable(f"测试数据路径越界：{relative}")
    try:
        size = target.stat().st_size
    except OSError as exc:
        raise JudgeDataUnavailable(f"测试数据文件不存在：{relative}") from exc
    # 先看大小再读：先读进内存再判断，等于让一个 2GB 的 .in 把进程撑死之后再报错。
    if size > max_bytes:
        raise JudgeDataUnavailable(f"测试数据文件超过 {max_bytes} 字节：{relative}")
    try:
        raw = target.read_bytes()
    except OSError as exc:
        raise JudgeDataUnavailable(f"测试数据文件读取失败：{relative}") from exc
    # errors="replace"：测试数据偶有非 UTF-8 字节，判题时把它换成 U+FFFD 一起送进去，
    # 比整条判题失败好——真正比对的是学员输出与期望输出，两边同样替换后仍然可比。
    return raw.decode("utf-8", errors="replace")
