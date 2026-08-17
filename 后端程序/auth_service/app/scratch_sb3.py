"""`.sb3` 结构检查、`project.json` 解析与内容寻址落盘。

《21、Scratch 图形化编程模块》§7.2 安全线 + 任务书 21b「不在 FastAPI 请求进程直接
无限运行用户项目」的落地面：本模块**只做静态检查**——它打开 ZIP 目录、读一个
`project.json`、解析成字典，此外不解压任何素材、不执行任何东西。

## 为什么每一条检查都不能省

`.sb3` 就是一个学生可以任意构造的 ZIP。三类攻击对应三道闸：

1. **zip bomb**：42KB 的包解压出 4GB。所以先读 ZIP 目录里声明的 `file_size` 累加，
   超过 `scratch_sb3_unpacked_max_bytes` 直接拒——**在解压之前**判，解压之后判等于
   已经被打穿了。条目数上限同理，挡的是"十万个空文件"那种目录爆炸。
2. **路径穿越**：条目名写成 `../../etc/passwd`。本模块目前根本不解压素材，
   但仍然拒收——将来任何一处加上"解压缩略图"的需求时，这道闸已经在了；
   等那天再补，就是典型的补不上。
3. **伪装**：`project.json` 缺失 / 不是 JSON / 没有 targets。这类包 Studio 打不开，
   放进库里只会变成一条"学生说保存成功、老师点开是坏文件"的悬案。

## 落盘

内容寻址 `<root>/<sha256[:2]>/<sha256>.sb3`，与题干配图（admin_media.media_relative_path）
同构。两点差异要记住：

- **不挂静态服务**。图片的 URL 无鉴权、靠哈希不可枚举；作品是私有内容，
  一律走 `/api/scratch/...` 逐次课时门控后由应用读文件下发。
- **不做引用计数删除**。同一份字节可能被同一学生的多个版本、甚至不同学生
  （同一个初始项目改都没改就交了）共同指向，删文件必须先扫全表，本期不做。
"""
from __future__ import annotations

import hashlib
import json
import zipfile
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path

PROJECT_JSON = "project.json"


class Sb3Invalid(Exception):
    """结构检查失败。`message` 直接面向学生展示，不要写内部细节。"""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


@dataclass
class Sb3Summary:
    """`project.json` 的结构摘要。判定规则与作品列表都只认这里的字段。

    `targets` 保留原始字典列表：规则匹配要遍历 blocks，摘要没法提前压缩掉。
    """

    sprite_count: int = 0
    extensions: list[str] = field(default_factory=list)
    targets: list[dict] = field(default_factory=list)
    block_count: int = 0
    variable_count: int = 0

    @property
    def stage(self) -> dict | None:
        for target in self.targets:
            if target.get("isStage"):
                return target
        return None

    @property
    def sprites(self) -> list[dict]:
        return [t for t in self.targets if not t.get("isStage")]


def _reject_entry_name(name: str) -> None:
    """条目名安全检查：绝对路径、盘符、`..` 一律拒。"""
    if name.startswith("/") or name.startswith("\\"):
        raise Sb3Invalid("项目文件结构异常（含绝对路径条目），请在 Scratch 中重新导出。")
    if ":" in name.split("/", 1)[0] and len(name.split("/", 1)[0]) == 2:
        raise Sb3Invalid("项目文件结构异常（含盘符路径），请在 Scratch 中重新导出。")
    parts = name.replace("\\", "/").split("/")
    if ".." in parts:
        raise Sb3Invalid("项目文件结构异常（含上级目录条目），请在 Scratch 中重新导出。")


def inspect_sb3(raw: bytes, settings) -> Sb3Summary:
    """结构检查 + 解析摘要。任何不合规都抛 `Sb3Invalid`（调用方转 400）。

    只读 ZIP 中央目录与 `project.json` 这一个条目；素材字节碰都不碰。
    """
    if not raw:
        raise Sb3Invalid("上传内容为空。")
    try:
        archive = zipfile.ZipFile(BytesIO(raw))
    except zipfile.BadZipFile as exc:
        raise Sb3Invalid("这不是有效的 .sb3 文件（ZIP 结构损坏）。") from exc

    with archive:
        infos = archive.infolist()
        if len(infos) > settings.scratch_sb3_max_entries:
            raise Sb3Invalid(
                f"项目内文件过多（超过 {settings.scratch_sb3_max_entries} 个），请精简素材。"
            )
        total_unpacked = 0
        project_info = None
        for info in infos:
            _reject_entry_name(info.filename)
            # flag_bits 位 0 = 该条目被加密。加密条目读不出来，且是明显的伪装信号。
            if info.flag_bits & 0x1:
                raise Sb3Invalid("项目文件包含加密条目，无法读取。")
            total_unpacked += info.file_size
            if total_unpacked > settings.scratch_sb3_unpacked_max_bytes:
                raise Sb3Invalid("项目解压后体积过大，请精简素材后重试。")
            if info.filename == PROJECT_JSON:
                project_info = info
        if project_info is None:
            raise Sb3Invalid("项目文件缺少 project.json，请在 Scratch 中重新导出。")
        if project_info.file_size > settings.scratch_project_json_max_bytes:
            raise Sb3Invalid("项目结构文件过大，请精简积木或角色后重试。")
        try:
            payload = json.loads(archive.read(PROJECT_JSON).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError, OSError) as exc:
            raise Sb3Invalid("项目结构文件无法解析，请在 Scratch 中重新导出。") from exc

    if not isinstance(payload, dict):
        raise Sb3Invalid("项目结构文件格式不正确。")
    targets = payload.get("targets")
    if not isinstance(targets, list) or not targets:
        raise Sb3Invalid("项目里没有任何角色或舞台，请检查后重新导出。")
    clean_targets = [t for t in targets if isinstance(t, dict)]
    if not clean_targets:
        raise Sb3Invalid("项目里没有任何角色或舞台，请检查后重新导出。")

    extensions = [e for e in (payload.get("extensions") or []) if isinstance(e, str)]
    block_count = sum(
        len(t.get("blocks") or {}) for t in clean_targets if isinstance(t.get("blocks"), dict)
    )
    variable_count = sum(
        len(t.get("variables") or {}) for t in clean_targets if isinstance(t.get("variables"), dict)
    )
    return Sb3Summary(
        sprite_count=sum(1 for t in clean_targets if not t.get("isStage")),
        extensions=extensions,
        targets=clean_targets,
        block_count=block_count,
        variable_count=variable_count,
    )


def sb3_relative_path(digest: str) -> str:
    """内容寻址相对路径：`ab/abcd….sb3`。与 media_relative_path 同构（两级散列）。"""
    return f"{digest[:2]}/{digest}.sb3"


def store_sb3(raw: bytes, settings) -> tuple[str, str]:
    """把字节写进受控根目录，返回 (sb3_key, sha256)。同内容重复保存不重复占盘。

    先写 `.part` 再 `replace`：直接写目标路径的话，写一半崩了会留下一个大小对不上
    的文件，而它的文件名是哈希——看起来完全正常，永远不会被重新写入覆盖
    （与 admin_media.upload_image 同一条理由）。
    """
    digest = hashlib.sha256(raw).hexdigest()
    relative = sb3_relative_path(digest)
    root = Path(settings.scratch_upload_root).resolve()
    target = (root / relative).resolve()
    if root not in target.parents:
        raise Sb3Invalid("作品存储目录配置无效。")
    if target.exists() and target.stat().st_size == len(raw):
        return relative, digest
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".sb3.part")
    try:
        temporary.write_bytes(raw)
        temporary.replace(target)
    except OSError as exc:
        temporary.unlink(missing_ok=True)
        raise Sb3Invalid("作品保存失败，请稍后重试。") from exc
    return relative, digest


def read_sb3(sb3_key: str, settings) -> bytes | None:
    """按 key 读回字节。**key 不是权限凭证**：调用方必须已经过完课时门控。

    路径逃逸兜底：key 来自库里的行，理论上一定是 `ab/<64 hex>.sb3`，但下发文件这条
    路径值得多一次 resolve 比对——一次错误的迁移或人工改库就能把它变成 `../../.env`。
    """
    root = Path(settings.scratch_upload_root).resolve()
    target = (root / sb3_key).resolve()
    if root not in target.parents or not target.is_file():
        return None
    return target.read_bytes()


def read_project_json(raw: bytes) -> dict:
    """只解出 `project.json` 一个条目（批改台画积木图用），返回完整字典。

    与 `inspect_sb3` 的差别：那里要的是结构摘要（sprite_count / extensions / targets），
    这里要的是原始 payload 本身——前端 `parse-sb3-blocks` 按 `targets[].blocks` 逐角色
    转 scratchblocks 文本，别的字段（monitors / meta）留着无妨。

    复用同一条安全闸（条目名 / 加密条目），但不重复做体积与条目数上限——那些在
    `inspect_sb3` 落盘时已经验过，这里读的是库里的成品。
    """
    if not raw:
        raise Sb3Invalid("上传内容为空。")
    try:
        archive = zipfile.ZipFile(BytesIO(raw))
    except zipfile.BadZipFile as exc:
        raise Sb3Invalid("这不是有效的 .sb3 文件（ZIP 结构损坏）。") from exc
    with archive:
        for info in archive.infolist():
            _reject_entry_name(info.filename)
            if info.flag_bits & 0x1:
                raise Sb3Invalid("项目文件包含加密条目，无法读取。")
            if info.filename != PROJECT_JSON:
                continue
            try:
                payload = json.loads(archive.read(PROJECT_JSON).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError, OSError) as exc:
                raise Sb3Invalid("项目结构文件无法解析，请在 Scratch 中重新导出。") from exc
            if isinstance(payload, dict):
                return payload
            raise Sb3Invalid("项目结构文件格式不正确。")
    raise Sb3Invalid("项目文件缺少 project.json，请在 Scratch 中重新导出。")
