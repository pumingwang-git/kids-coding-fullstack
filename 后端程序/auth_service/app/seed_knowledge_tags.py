"""播种 C++ 竞赛三级知识点标签（category=knowledge，is_system=True，幂等可重复执行）。

用法（在 auth_service 目录下）：
    .venv\\Scripts\\python -m app.seed_knowledge_tags          # 只新增缺失标签
    .venv\\Scripts\\python -m app.seed_knowledge_tags --prune-legacy  # 额外删除不在新体系中的旧 knowledge 标签（会级联解除题目关联，慎用）

说明：
- 标签名已去掉括号注解，括号内容存入 description 列（前端悬浮提示）。
- 若 tags 表还没有 description 列（未跑迁移 0016），脚本会自动 ALTER TABLE 补上。
- 旧标签默认保留（老题目仍引用它们），只是不再显示在三级树中。
"""
import sys
from sqlalchemy import func, inspect, select, text

from app.config import get_settings
from app.database import build_database
from app.models import Base, Tag

KNOWLEDGE_TREE = [
  {"name": "C++ 编程语言基础", "children": [
      {"name": "程序结构与基本语法", "children": [
          {"name": "程序框架", "description": "#include / using namespace std / main函数 / return 0"},
          {"name": "注释规范", "description": "单行// / 多行/* */"},
          {"name": "基本输入输出", "description": "cin / cout / scanf / printf / 格式化输出"}
        ]},
      {"name": "变量、常量与数据类型", "children": [
          {"name": "整型", "description": "int / long long / 范围与溢出 / unsigned"},
          {"name": "浮点型", "description": "float / double / 精度问题 / 科学计数法"},
          {"name": "字符与布尔", "description": "char / ASCII码 / bool / 逻辑值"},
          {"name": "常量", "description": "const / #define / 字面量"},
          {"name": "类型转换", "description": "隐式转换 / 强制转换 / 精度丢失"}
        ]},
      {"name": "运算符与表达式", "children": [
          {"name": "算术运算符", "description": "+ - * / % / 自增自减++ --"},
          {"name": "关系运算符", "description": "== != > < >= <="},
          {"name": "逻辑运算符", "description": "&& || ! / 短路求值"},
          {"name": "赋值运算符", "description": "= / += -= *= /= %="},
          {"name": "运算符优先级与结合性"},
          {"name": "条件运算符", "description": "? : 三目运算符"}
        ]},
      {"name": "控制结构", "children": [
          {"name": "顺序结构", "description": "语句逐条执行"},
          {"name": "分支结构", "description": "if / if-else / if-else if-else / switch-case"},
          {"name": "循环结构", "description": "for / while / do-while / 循环嵌套 / break / continue"}
        ]},
      {"name": "数组与字符串", "children": [
          {"name": "一维数组", "description": "定义 / 初始化 / 遍历 / 边界检查"},
          {"name": "二维数组与多维数组", "description": "定义 / 遍历 / 矩阵操作"},
          {"name": "字符数组与C风格字符串", "description": "char[] / gets/puts / str系列函数"},
          {"name": "string类", "description": "定义 / 输入输出 / 拼接 / 查找 / 截取 / 比较"},
          {"name": "数组与字符串的常用操作", "description": "排序 / 去重 / 反转"}
        ]},
      {"name": "函数", "children": [
          {"name": "函数定义与调用", "description": "返回值 / 参数列表 / 函数原型"},
          {"name": "参数传递", "description": "值传递 / 引用传递 & / 指针传递"},
          {"name": "作用域与生命周期", "description": "局部变量 / 全局变量 / 静态变量"},
          {"name": "函数重载", "description": "同名不同参"},
          {"name": "内联函数", "description": "inline / 宏函数对比"}
        ]},
      {"name": "指针与引用", "children": [
          {"name": "指针基础", "description": "定义 / 取地址& / 解引用* / 空指针NULL/nullptr"},
          {"name": "指针与数组", "description": "数组名即指针 / 指针算术"},
          {"name": "动态内存分配", "description": "new / delete / new[] / delete[]"},
          {"name": "引用", "description": "定义 / 与指针的区别 / 作为函数参数"}
        ]},
      {"name": "结构体与联合体", "children": [
          {"name": "结构体定义与使用", "description": "struct / 成员访问 . / 嵌套结构体"},
          {"name": "结构体数组与指针"},
          {"name": "联合体", "description": "union / 共用内存"}
        ]},
      {"name": "文件操作", "children": [
          {"name": "文件重定向", "description": "freopen / 标准输入输出重定向"},
          {"name": "文件流", "description": "ifstream / ofstream / fstream / 读写操作"},
          {"name": "输入输出优化", "description": "ios::sync_with_stdio(false) / cin.tie(nullptr)"}
        ]}
    ]},
  {"name": "CSP-J 入门级", "children": [
      {"name": "计算机基础知识", "children": [
          {"name": "计算机组成", "description": "CPU / 存储器RAM/ROM/Cache / 输入输出设备"},
          {"name": "存储单位与换算", "description": "bit / Byte / KB / MB / GB / TB"},
          {"name": "数制与编码", "description": "二进制 / 八进制 / 十进制 / 十六进制 / 相互转换"},
          {"name": "原码 / 反码 / 补码", "description": "表示范围 / 补码加减法"},
          {"name": "位运算基础", "description": "& | ^ ~ << >> / 优先级 / 常用技巧"},
          {"name": "计算机网络基础", "description": "OSI模型 / TCP/IP / 域名 / URL"},
          {"name": "操作系统基础", "description": "进程管理 / 文件管理 / 常用Linux命令"},
          {"name": "计算机历史与人物", "description": "冯·诺依曼 / 图灵 / 计算机发展史"}
        ]},
      {"name": "C++ 竞赛语法进阶", "children": [
          {"name": "万能头文件", "description": "#include <bits/stdc++.h>"},
          {"name": "STL 入门容器", "description": "vector / stack / queue / pair"},
          {"name": "STL 常用算法", "description": "sort / reverse / max/min / swap"},
          {"name": "范围for循环", "description": "for (auto x : vec)"}
        ]},
      {"name": "基础数据结构", "children": [
          {"name": "线性表", "description": "数组 / 链表（单链表/双链表） / 增删改查操作"},
          {"name": "栈", "description": "LIFO / 压栈弹栈 / 括号匹配 / 表达式求值"},
          {"name": "队列", "description": "FIFO / 入队出队 / BFS应用 / 双端队列"},
          {"name": "二叉树", "description": "定义 / 度 / 深度 / 叶子节点 / 满二叉树与完全二叉树"},
          {"name": "二叉树的遍历", "description": "前序 / 中序 / 后序 / 层序 —— 递归与迭代"},
          {"name": "哈夫曼树", "description": "带权路径长度 / 哈夫曼编码"},
          {"name": "图的存储", "description": "邻接矩阵 / 邻接表"},
          {"name": "图的遍历", "description": "DFS深度优先 / BFS广度优先 / 连通分量"}
        ]},
      {"name": "基础算法", "children": [
          {"name": "枚举", "description": "穷举法 / 枚举优化 / 状态枚举"},
          {"name": "模拟", "description": "过程模拟 / 场景还原 / 日期推算"},
          {"name": "排序算法", "description": "选择 / 冒泡 / 插入 / 计数排序 / sort自定义比较"},
          {"name": "二分查找", "description": "有序序列 / 二分答案 / lower_bound/upper_bound"},
          {"name": "递推", "description": "斐波那契 / 递推公式 / 递推与递归的转换"},
          {"name": "递归", "description": "递归三要素 / 递归终止条件 / 递归与栈"},
          {"name": "贪心", "description": "局部最优→全局最优 / 活动安排 / 找零钱 / 正确性证明"},
          {"name": "高精度计算", "description": "大整数加减乘除 / 竖式模拟"},
          {"name": "前缀和与差分", "description": "一维/二维前缀和 / 区间加差分"}
        ]},
      {"name": "基础数学", "children": [
          {"name": "质数与合数", "description": "判断质数 / 质因数分解"},
          {"name": "质数筛法", "description": "埃氏筛 / 欧拉筛/线性筛"},
          {"name": "最大公约数与最小公倍数", "description": "GCD / LCM / 欧几里得算法/辗转相除法"},
          {"name": "排列与组合", "description": "排列数A / 组合数C / 加法原理与乘法原理"},
          {"name": "概率与期望基础", "description": "古典概型 / 期望定义与计算"},
          {"name": "集合运算", "description": "交/并/补 / 容斥原理初步"}
        ]},
      {"name": "初赛专项", "children": [
          {"name": "单项选择题", "description": "计算机基础 / C++语法 / 数据结构与算法 / 数学"},
          {"name": "程序阅读题", "description": "阅读代码写输出 / 跟踪变量变化 / 时间复杂度分析"},
          {"name": "完善程序题", "description": "补全代码 / 边界条件 / 算法逻辑填空"}
        ]}
    ]},
  {"name": "CSP-S 提高级", "children": [
      {"name": "进阶数据结构", "children": [
          {"name": "二叉搜索树 BST", "description": "查找 / 插入 / 删除 / 中序有序性"},
          {"name": "堆与优先队列", "description": "大根堆/小根堆 / priority_queue / 堆排序"},
          {"name": "并查集", "description": "路径压缩 / 按秩合并 / 连通性与环检测"},
          {"name": "树状数组", "description": "单点修改 / 区间查询 / 离散化"},
          {"name": "线段树", "description": "区间修改 / 区间查询 / lazy标记 / 动态开点"},
          {"name": "哈希表", "description": "unordered_map / unordered_set / 哈希冲突 / 自定义哈希"},
          {"name": "单调栈与单调队列", "description": "维护极值 / 滑动窗口"},
          {"name": "bitset", "description": "位集合 / 复杂度O(n/w) / 01背包优化"}
        ]},
      {"name": "进阶算法", "children": [
          {"name": "排序进阶", "description": "快速排序 / 归并排序 / 基数排序 / 排序稳定性"},
          {"name": "二分进阶", "description": "二分答案 / 二分查找变体 / 实数二分"},
          {"name": "倍增法", "description": "LCA最近公共祖先 / RMQ区间最值 / 快速幂"},
          {"name": "分治", "description": "归并 / 快速排序 / 最大子段和 / CDQ分治"}
        ]},
      {"name": "动态规划 DP", "children": [
          {"name": "线性DP", "description": "最长上升子序列LIS / 最长公共子序列LCS / 最大子段和"},
          {"name": "背包DP", "description": "0/1背包 / 完全背包 / 多重背包 / 分组背包 / 依赖背包"},
          {"name": "区间DP", "description": "矩阵连乘 / 石子合并 / 括号匹配DP"},
          {"name": "树形DP", "description": "树上最大独立集 / 树上背包 / 换根DP"},
          {"name": "状压DP", "description": "状态压缩 / 集合DP / 旅行商问题TSP"},
          {"name": "数位DP", "description": "数字统计 / 不含某数字的个数 / 按位DP"},
          {"name": "DP优化", "description": "滚动数组 / 单调队列优化 / 斜率优化 / 四边形不等式"}
        ]},
      {"name": "图论", "children": [
          {"name": "图的遍历进阶", "description": "DFS/BFS / 连通分量 / 二分图判定"},
          {"name": "拓扑排序", "description": "DAG / Kahn算法 / 判环"},
          {"name": "最短路径", "description": "Dijkstra / SPFA / Floyd / 负环检测"},
          {"name": "最小生成树", "description": "Prim / Kruskal"},
          {"name": "强连通分量", "description": "Tarjan / Kosaraju / 缩点"},
          {"name": "差分约束", "description": "不等式转最短路"},
          {"name": "最近公共祖先 LCA", "description": "倍增 / 树链剖分 / Tarjan离线"}
        ]},
      {"name": "搜索与回溯", "children": [
          {"name": "DFS深度优先搜索", "description": "剪枝优化 / 记忆化搜索"},
          {"name": "BFS广度优先搜索", "description": "最短路 / 状态搜索 / 双向BFS"},
          {"name": "回溯法", "description": "全排列 / 组合 / 子集 / N皇后"},
          {"name": "迭代加深与A*", "description": "IDA* / A*估价函数"}
        ]},
      {"name": "进阶数学", "children": [
          {"name": "快速幂", "description": "模幂运算 / 矩阵快速幂"},
          {"name": "扩展欧几里得", "description": "exGCD / 不定方程 / 模逆元"},
          {"name": "组合数学", "description": "排列组合计数 / 组合数取模 / 卢卡斯定理Lucas"},
          {"name": "同余与模运算", "description": "同余方程 / 中国剩余定理CRT"},
          {"name": "欧拉函数与欧拉定理"},
          {"name": "矩阵与行列式", "description": "矩阵乘法 / 矩阵快速幂 / 高斯消元"}
        ]},
      {"name": "初赛专项·提高", "description": "CSP-S 第一轮笔试", "children": [
          {"name": "提高级单选", "description": "覆盖入门级+提高级全部理论考点"},
          {"name": "提高级阅读", "description": "复杂代码 / 递归 / 指针 / 复杂度分析"},
          {"name": "提高级完善", "description": "进阶算法填空 / DP/图论/数据结构代码补全"}
        ]}
    ]},
  {"name": "NOIP 全国青少年信息学奥林匹克联赛", "children": [
      {"name": "高级数据结构", "children": [
          {"name": "平衡树", "description": "Treap / Splay / 伸展树"},
          {"name": "树链剖分", "description": "轻重链剖分 / 路径操作 / 子树操作"},
          {"name": "可持久化数据结构", "description": "主席树 / 可持久化线段树 / 可持久化并查集"},
          {"name": "分块与莫队", "description": "分块思想 / 普通莫队 / 带修莫队"},
          {"name": "字符串数据结构", "description": "Trie树 / AC自动机 / 后缀数组 / SAM后缀自动机"}
        ]},
      {"name": "高级算法", "children": [
          {"name": "网络流", "description": "最大流Dinic / 最小割 / 费用流"},
          {"name": "二分图匹配", "description": "匈牙利算法 / KM算法"},
          {"name": "计算几何基础", "description": "点/线/多边形 / 凸包 / 半平面交"},
          {"name": "字符串匹配", "description": "KMP / 扩展KMP / Manacher回文算法"},
          {"name": "随机化算法", "description": "模拟退火 / 爬山算法 / 随机贪心"}
        ]},
      {"name": "动态规划进阶", "children": [
          {"name": "多维状态DP", "description": "三维/四维状态设计"},
          {"name": "DP与数据结构优化", "description": "线段树优化DP / 树状数组优化DP"},
          {"name": "插头DP / 轮廓线DP", "description": "棋盘覆盖 / 连通性DP"}
        ]},
      {"name": "高级图论", "children": [
          {"name": "割点与桥", "description": "Tarjan / 点双连通 / 边双连通"},
          {"name": "2-SAT", "description": "布尔方程求解 / 强连通分量应用"},
          {"name": "树上问题进阶", "description": "树的直径 / 树的重心 / 虚树"}
        ]},
      {"name": "高级数学", "children": [
          {"name": "生成函数与多项式", "description": "FFT快速傅里叶变换 / NTT"},
          {"name": "博弈论", "description": "SG函数 / Nim游戏 / 组合博弈"},
          {"name": "概率与期望DP", "description": "期望递推 / 高斯消元解期望"},
          {"name": "线性基", "description": "异或空间 / 最大异或和"}
        ]},
      {"name": "综合应用能力", "children": [
          {"name": "多知识点融合", "description": "“数学+图论”“数据结构+DP”缝合题型"},
          {"name": "复杂问题建模", "description": "将实际问题抽象为算法模型"},
          {"name": "部分分策略", "description": "针对数据范围设计不同复杂度解法"},
          {"name": "代码调试与对拍", "description": "构造数据 / 暴力对拍 / 边界测试"}
        ]}
    ]}
]


def _ensure_description_column(engine) -> None:
    """迁移 0016 未跑时自动补列（开发库便捷路径；生产建议走 alembic upgrade head）。"""
    inspector = inspect(engine)
    if "tags" in inspector.get_table_names() and "description" not in [c["name"] for c in inspector.get_columns("tags")]:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE tags ADD COLUMN description VARCHAR(500)"))
        print("已自动为 tags 表添加 description 列（建议正式环境改用 alembic upgrade head）。")


def main() -> None:
    prune_legacy = "--prune-legacy" in sys.argv
    settings = get_settings()
    engine, session_factory = build_database(settings.database_url)
    Base.metadata.create_all(engine)  # 生产环境表已由迁移创建，此处无副作用
    _ensure_description_column(engine)

    with session_factory() as db:
        existing = db.scalars(select(Tag).where(Tag.category == "knowledge")).all()
        by_name = {t.name: t for t in existing}
        new_names = set()

        def collect_names(nodes) -> None:
            for node in nodes:
                new_names.add(node["name"])
                if node.get("children"):
                    collect_names(node["children"])

        collect_names(KNOWLEDGE_TREE)
        created = 0

        def add(nodes, parent_id: int | None) -> None:
            nonlocal created
            for node in nodes:
                tag = by_name.get(node["name"])
                if tag is None:
                    tag = Tag(
                        name=node["name"],
                        category="knowledge",
                        parent_id=parent_id,
                        description=node.get("description"),
                        is_system=True,
                    )
                    db.add(tag)
                    db.flush()
                    by_name[node["name"]] = tag
                    created += 1
                elif tag.parent_id != parent_id or tag.description != node.get("description") or not tag.is_system:
                    # 同名复用（或旧名残留）：纠正层级位置与描述，统一为系统标签
                    tag.parent_id = parent_id
                    tag.description = node.get("description")
                    tag.is_system = True
                children = node.get("children")
                if children:
                    add(children, tag.id)

        add(KNOWLEDGE_TREE, None)

        if prune_legacy:
            legacy = [t for t in existing if t.name not in new_names]
            for tag in legacy:
                db.delete(tag)
            print(f"已删除旧 knowledge 标签 {len(legacy)} 个（其题目关联已级联解除）。")

        db.commit()
        total = db.scalar(select(func.count()).select_from(Tag).where(Tag.category == "knowledge"))
        with_desc = db.scalar(select(func.count()).select_from(Tag).where(Tag.category == "knowledge", Tag.description.is_not(None)))
        print(f"知识点播种完成：新增 {created} 个；当前 knowledge 标签共 {total} 个（含说明 {with_desc} 个）。")
        print("刷新管理端后，知识点树按三级结构展示；标签名无括号，悬浮显示说明。")


if __name__ == "__main__":
    main()
