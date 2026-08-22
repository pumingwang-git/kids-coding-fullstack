"""学习专区的初始目录与通用校验常量。

初始目录只负责补齐缺失项：管理员改过的名称、说明、排序和状态不会在启动时被覆盖。
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from .models import (
    CourseCategory,
    CourseTag,
    CourseType,
    LearningArea,
    LearningAreaModule,
)

AREA_STATUSES = {"planning", "active", "hidden"}
MODULE_STATUSES = {"available", "planning", "hidden"}

# 工作台能力注册表。implemented=False 表示学生端还没有真实页面，只能配成规划中或隐藏——
# 否则管理端标着「可使用」，学生点进去看到的却是「功能尚未开放」的占位页，状态与事实相反。
MODULE_REGISTRY = {
    "overview": {"label": "学习首页", "implemented": True},
    "courses": {"label": "课程", "implemented": True},
    "tasks": {"label": "学习任务", "implemented": True},
    "explore": {"label": "探索创作", "implemented": True},
    "question-bank": {"label": "题库", "implemented": True},
    "toolbox": {"label": "工具箱", "implemented": True},
    "paths": {"label": "学习路线", "implemented": False},
    "projects": {"label": "实战项目", "implemented": False},
}
MODULE_KEYS = set(MODULE_REGISTRY)

AREA_SEEDS = [
    {
        "key": "kids",
        "name": "少儿编程",
        "description": "面向 8–14 岁学习者，从图形化编程逐步进入代码、算法与科创实践。",
        "audience": "8–14 岁学生",
        "theme_key": "kids",
        "status": "active",
        "sort_order": 10,
        "modules": [
            ("overview", "学习首页", "available", 10),
            ("courses", "课程", "available", 20),
            # 这两项有真实页面（TasksHome / ExploreHome、我的作品），标 planning 会被
            # 路由守卫挡进占位页。planning 的含义是「运营暂不开放」，不是「页面没做完」。
            ("tasks", "学习任务", "available", 30),
            ("explore", "探索创作", "available", 40),
            # 题库和工具箱原先是前端硬编码兜底，后端不认这两个 key，导致后台想配也配不了。
            # 收进种子后前端兜底才能删掉，导航数据源收敛到后端一处。
            ("question-bank", "题库", "available", 50),
            ("toolbox", "工具箱", "available", 60),
        ],
    },
    {
        "key": "programmer",
        "name": "程序员专区",
        "description": "围绕职业开发能力组织路线、课程与项目实践，覆盖开发、数据、运维和 AI 应用。",
        "audience": "希望系统提升开发能力的学习者",
        "theme_key": "programmer",
        "status": "planning",
        "sort_order": 20,
        "modules": [
            ("overview", "概览", "planning", 10),
            ("paths", "学习路线", "planning", 20),
            ("courses", "课程", "planning", 30),
            ("projects", "实战项目", "planning", 40),
            # 前端兜底原本对所有专区生效，两个专区都要补，删兜底后行为才不变。
            ("question-bank", "题库", "available", 50),
            ("toolbox", "工具箱", "available", 60),
        ],
    },
]

TAXONOMY_SEEDS = {
    "kids": [
        ("visual", "图形化编程", ["Scratch", "Blockly/MakeCode", "游戏与动画", "算法启蒙"]),
        ("python-kids", "Python 启蒙", ["语法基础", "Turtle 创意绘图", "小游戏", "基础数据处理"]),
        ("cpp", "C/C++", ["C++ 基础", "算法与数据结构", "信息学竞赛", "C++ 项目实践"]),
        ("maker", "科创实践", ["micro:bit", "Arduino", "机器人", "物联网启蒙", "3D 设计与打印", "科学实验"]),
        ("ai-kids", "AI 启蒙", ["图像与语音识别", "生成式 AI", "智能作品", "AI 素养与安全"]),
        ("web-kids", "Web 创意", ["HTML/CSS", "JavaScript 互动", "个人网页"]),
    ],
    "programmer": [
        ("frontend", "前端开发", ["HTML/CSS 前端", "JavaScript/TypeScript", "Vue", "React", "工程化与性能"]),
        ("backend", "后端开发", ["API 设计", "FastAPI/Django", "Node.js/Nest", "Java/Spring", "Go"]),
        ("python-pro", "Python 专项", ["Python 进阶", "网络爬虫", "办公自动化", "数据分析"]),
        ("database", "数据库", ["SQL", "MySQL/PostgreSQL", "Redis", "数据建模", "数据库性能优化"]),
        ("devops", "运维与云原生", ["Linux/Shell", "Nginx", "Docker", "CI/CD", "Kubernetes", "监控"]),
        ("engineering", "软件工程", ["Git", "自动化测试", "设计模式", "系统架构", "安全", "部署与排错"]),
        ("ai-app", "AI 应用开发", ["大模型 API", "提示词", "RAG", "Agent 工作流", "MCP"]),
        ("mobile", "移动与跨端", ["Flutter", "React Native", "Android", "iOS", "小程序"]),
    ],
}

TYPE_SEEDS = [
    ("systematic", "系统课程", "按稳定顺序持续学习", 10),
    ("special", "专题课程", "围绕一个主题集中学习", 20),
]

TAG_SEEDS = {
    "kids": [
        ("project-based", "项目制"), ("game-creation", "游戏创作"),
        ("animation-story", "动画故事"), ("creative-drawing", "创意绘图"),
        ("hardware-creation", "硬件创作"), ("competition-prep", "竞赛准备"),
        ("materials-included", "含素材包"), ("parent-child", "亲子共学"),
    ],
    "programmer": [
        ("project-based", "项目制"), ("engineering-practice", "工程实践"),
        ("project-retrospective", "项目复盘"), ("portfolio", "作品集"),
        ("interview-prep", "面试准备"), ("release", "部署上线"),
        ("teamwork", "团队协作"), ("source-reading", "源码精读"),
        ("performance", "性能优化"), ("debugging", "排错实战"),
        ("code-included", "含配套代码"), ("environment-setup", "含环境配置"),
    ],
}


def _key_from_name(prefix: str, index: int) -> str:
    return f"{prefix}-{index + 1}"


def ensure_learning_catalog(session_factory: sessionmaker) -> None:
    """幂等补齐首批专区目录，不覆盖任何已存在记录。"""
    db: Session = session_factory()
    try:
        for area_seed in AREA_SEEDS:
            area = db.get(LearningArea, area_seed["key"])
            if area is None:
                area = LearningArea(**{k: v for k, v in area_seed.items() if k != "modules"})
                db.add(area)
                db.flush()
            for module_key, label, status, sort_order in area_seed["modules"]:
                exists = db.scalar(select(LearningAreaModule).where(
                    LearningAreaModule.area_key == area.key,
                    LearningAreaModule.module_key == module_key,
                ))
                if exists is None:
                    db.add(LearningAreaModule(
                        area_key=area.key, module_key=module_key, label=label,
                        status=status, sort_order=sort_order,
                    ))

            for kind_key, name, description, sort_order in TYPE_SEEDS:
                exists = db.scalar(select(CourseType).where(
                    CourseType.area_key == area.key, CourseType.key == kind_key,
                ))
                if exists is None:
                    db.add(CourseType(
                        area_key=area.key, key=kind_key, name=name,
                        description=description, sort_order=sort_order,
                    ))

        db.flush()
        for area_key, directions in TAXONOMY_SEEDS.items():
            for direction_index, (direction_key, direction_name, topics) in enumerate(directions):
                direction = db.scalar(select(CourseCategory).where(
                    CourseCategory.area_key == area_key,
                    CourseCategory.parent_id.is_(None),
                    CourseCategory.key == direction_key,
                ))
                if direction is None:
                    direction = CourseCategory(
                        area_key=area_key, key=direction_key, name=direction_name,
                        sort_order=(direction_index + 1) * 10,
                    )
                    db.add(direction)
                    db.flush()
                for topic_index, topic_name in enumerate(topics):
                    topic_key = _key_from_name(direction_key, topic_index)
                    exists = db.scalar(select(CourseCategory).where(
                        CourseCategory.area_key == area_key,
                        CourseCategory.parent_id == direction.id,
                        CourseCategory.key == topic_key,
                    ))
                    if exists is None:
                        db.add(CourseCategory(
                            area_key=area_key, parent_id=direction.id, key=topic_key,
                            name=topic_name, sort_order=(topic_index + 1) * 10,
                        ))

        for area_key, tags in TAG_SEEDS.items():
            for index, (key, name) in enumerate(tags):
                exists = db.scalar(select(CourseTag).where(
                    CourseTag.area_key == area_key, CourseTag.key == key,
                ))
                if exists is None:
                    db.add(CourseTag(
                        area_key=area_key, key=key, name=name, sort_order=(index + 1) * 10,
                    ))
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
