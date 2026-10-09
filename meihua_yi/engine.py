#!/usr/bin/env python3
"""梅花易数起卦核心引擎。

支持两种起卦方法：
- 时间起卦：基于当前时间（年月日时）计算卦象
- 铜钱起卦：模拟3枚硬币抛6次，每次结果不同

依赖:
    lunardate (可选) — 未安装则自动回退到公历数字起卦
"""

from datetime import datetime
import random

try:
    from lunardate import LunarDate
    HAS_LUNAR = True
except ImportError:
    HAS_LUNAR = False

# ─── 八卦数据 ───────────────────────────────────────────────

BAGUA = {
    (1, 1, 1): {"name": "乾", "symbol": "☰", "element": "金"},
    (1, 1, 0): {"name": "兑", "symbol": "☱", "element": "金"},
    (1, 0, 0): {"name": "震", "symbol": "☳", "element": "木"},
    (0, 1, 1): {"name": "巽", "symbol": "☴", "element": "木"},
    (0, 0, 0): {"name": "坤", "symbol": "☷", "element": "土"},
    (0, 0, 1): {"name": "艮", "symbol": "☶", "element": "土"},
    (1, 0, 1): {"name": "离", "symbol": "☲", "element": "火"},
    (0, 1, 0): {"name": "坎", "symbol": "☵", "element": "水"},
}

# 先天八卦序数 → 三爻元组 (下爻, 中爻, 上爻)
XIAN_TIAN = {
    1: (1, 1, 1),  # 乾
    2: (1, 1, 0),  # 兑
    3: (1, 0, 1),  # 离
    4: (1, 0, 0),  # 震
    5: (0, 1, 1),  # 巽
    6: (0, 1, 0),  # 坎
    7: (0, 0, 1),  # 艮
    0: (0, 0, 0),  # 坤
}

# 六十四卦名表 (下卦索引, 上卦索引) → 卦名
# 索引: 0坤 1兑 2震 3巽 4坎 5艮 6离 7乾
GUA_NAMES = {
    (0, 0): "坤为地", (0, 1): "泽地萃", (0, 2): "雷地豫", (0, 3): "风地观",
    (0, 4): "水地比", (0, 5): "山地剥", (0, 6): "火地晋", (0, 7): "天地否",
    (1, 0): "地泽临", (1, 1): "兑为泽", (1, 2): "雷泽归妹", (1, 3): "风泽中孚",
    (1, 4): "水泽节", (1, 5): "山泽损", (1, 6): "火泽睽", (1, 7): "天泽履",
    (2, 0): "地雷复", (2, 1): "泽雷随", (2, 2): "震为雷", (2, 3): "风雷益",
    (2, 4): "水雷屯", (2, 5): "山雷颐", (2, 6): "火雷噬嗑", (2, 7): "天雷无妄",
    (3, 0): "地风升", (3, 1): "泽风大过", (3, 2): "雷风恒", (3, 3): "巽为风",
    (3, 4): "水风井", (3, 5): "山风蛊", (3, 6): "火风鼎", (3, 7): "天风姤",
    (4, 0): "地水师", (4, 1): "泽水困", (4, 2): "雷水解", (4, 3): "风水涣",
    (4, 4): "坎为水", (4, 5): "山水蒙", (4, 6): "火水未济", (4, 7): "天水讼",
    (5, 0): "地山谦", (5, 1): "泽山咸", (5, 2): "雷山小过", (5, 3): "风山渐",
    (5, 4): "水山蹇", (5, 5): "艮为山", (5, 6): "火山旅", (5, 7): "天山遁",
    (6, 0): "地火明夷", (6, 1): "泽火革", (6, 2): "雷火丰", (6, 3): "风火家人",
    (6, 4): "水火既济", (6, 5): "山火贲", (6, 6): "离为火", (6, 7): "天火同人",
    (7, 0): "地天泰", (7, 1): "泽天夬", (7, 2): "雷天大壮", (7, 3): "风天小畜",
    (7, 4): "水天需", (7, 5): "山天大畜", (7, 6): "火天大有", (7, 7): "乾为天",
}


# ─── 辅助函数 ───────────────────────────────────────────────

def get_shichen(hour):
    """小时 → 时辰序数 (1-12)"""
    return ((hour + 1) // 2) % 12 + 1


def get_gua_name(lines):
    """根据六爻获取卦名。

    Args:
        lines: 六爻列表，0=阴, 1=阳，从下到上

    Returns:
        卦名字符串
    """
    bot_map = {
        (0, 0, 0): 0, (1, 1, 0): 1, (1, 0, 0): 2, (0, 1, 1): 3,
        (0, 1, 0): 4, (0, 0, 1): 5, (1, 0, 1): 6, (1, 1, 1): 7,
    }
    bot_idx = bot_map[tuple(lines[0:3])]
    top_idx = bot_map[tuple(lines[3:6])]
    return GUA_NAMES.get((bot_idx, top_idx), "未知")


# ─── 时间起卦 ───────────────────────────────────────────────

def qigua_time(dt=None):
    """梅花易数时间起卦法。

    同一时辰内结果相同。

    Args:
        dt: datetime 对象，默认为当前时间

    Returns:
        (六爻列表, [动爻索引列表])
        六爻列表: 0=阴, 1=阳，从初爻到上爻
        动爻索引: 0-based，时间起卦只有一个动爻
    """
    if dt is None:
        dt = datetime.now()

    if HAS_LUNAR:
        lunar = LunarDate.fromSolarDate(dt.year, dt.month, dt.day)
        year_num = (lunar.year - 4) % 12 + 1
        month_num = abs(lunar.month)
        day_num = lunar.day
    else:
        year_num = (dt.year - 4) % 12 + 1
        month_num = dt.month
        day_num = dt.day

    shichen = get_shichen(dt.hour)

    total = year_num + month_num + day_num
    upper_num = total % 8
    lower_num = (total + shichen) % 8
    moving = (total + shichen) % 6
    if moving == 0:
        moving = 6

    main_lines = list(XIAN_TIAN[lower_num]) + list(XIAN_TIAN[upper_num])
    return main_lines, [moving - 1]


# ─── 铜钱起卦 ───────────────────────────────────────────────

def qigua_coin(coin_results=None):
    """铜钱起卦法（3枚硬币抛6次）。

    规则: 正面(字)=2, 反面(花)=3
    每次3枚总和:
        6 = 老阴 (阴爻, 动)  → 2+2+2
        7 = 少阳 (阳爻, 静)  → 2+2+3
        8 = 少阴 (阴爻, 静)  → 2+3+3
        9 = 老阳 (阳爻, 动)  → 3+3+3

    Args:
        coin_results: 6个整数的列表，每个是3枚硬币的总和(6/7/8/9)。
                      不指定则随机生成。

    Returns:
        (六爻列表, [动爻索引列表], 投掷详情列表)
    """
    if coin_results is None:
        coin_results = [random.choice([6, 7, 8, 9]) for _ in range(6)]

    if len(coin_results) != 6:
        raise ValueError("需要恰好6次投掷结果")

    yao_names = {6: "老阴", 7: "少阳", 8: "少阴", 9: "老阳"}
    main_lines = []
    moving_indices = []
    details = []

    for i, total in enumerate(coin_results):
        if total == 6:  # 老阴 → 阴爻，动
            main_lines.append(0)
            moving_indices.append(i)
            details.append({"yao": i + 1, "sum": total, "name": yao_names[total], "line": "阴", "moving": True})
        elif total == 7:  # 少阳 → 阳爻，静
            main_lines.append(1)
            details.append({"yao": i + 1, "sum": total, "name": yao_names[total], "line": "阳", "moving": False})
        elif total == 8:  # 少阴 → 阴爻，静
            main_lines.append(0)
            details.append({"yao": i + 1, "sum": total, "name": yao_names[total], "line": "阴", "moving": False})
        elif total == 9:  # 老阳 → 阳爻，动
            main_lines.append(1)
            moving_indices.append(i)
            details.append({"yao": i + 1, "sum": total, "name": yao_names[total], "line": "阳", "moving": True})
        else:
            raise ValueError(f"第{i+1}次投掷总和 {total} 无效，必须是 6/7/8/9")

    return main_lines, moving_indices, details


# ─── 卦象计算 ───────────────────────────────────────────────

def compute_hexagrams(main_lines, moving_indices):
    """计算主卦、互卦、变卦、体用关系。

    Args:
        main_lines: 六爻列表，0=阴, 1=阳
        moving_indices: 动爻索引列表（0-based）

    Returns:
        dict 包含 main, mutual, changed, ti, yong, moving_indices
    """
    if isinstance(moving_indices, int):
        moving_indices = [moving_indices]

    # 互卦：取2-4爻为下卦，3-5爻为上卦
    mutual_lines = main_lines[1:4] + main_lines[2:5]

    # 变卦：所有动爻翻转
    changed_lines = list(main_lines)
    for idx in moving_indices:
        changed_lines[idx] = 1 - changed_lines[idx]

    # 体用：以第一个动爻所在卦的对侧为体
    first_moving = moving_indices[0]
    ti_gua = BAGUA[tuple(main_lines[3:6])] if first_moving < 3 else BAGUA[tuple(main_lines[0:3])]
    yong_gua = BAGUA[tuple(main_lines[0:3])] if first_moving < 3 else BAGUA[tuple(main_lines[3:6])]
    changed_yong = BAGUA[tuple(changed_lines[0:3])] if first_moving < 3 else BAGUA[tuple(changed_lines[3:6])]

    return {
        "main": {
            "lines": main_lines,
            "bot": BAGUA[tuple(main_lines[0:3])],
            "top": BAGUA[tuple(main_lines[3:6])],
        },
        "mutual": {
            "lines": mutual_lines,
            "bot": BAGUA[tuple(mutual_lines[0:3])],
            "top": BAGUA[tuple(mutual_lines[3:6])],
        },
        "changed": {
            "lines": changed_lines,
            "bot": BAGUA[tuple(changed_lines[0:3])],
            "top": BAGUA[tuple(changed_lines[3:6])],
        },
        "ti": ti_gua,
        "yong": yong_gua,
        "changed_yong": changed_yong,
        "ti_yong_relation": analyze_ti_yong(ti_gua["element"], yong_gua["element"])[0],
        "bian_relation": analyze_ti_yong(ti_gua["element"], changed_yong["element"])[0],
        "moving_indices": moving_indices,
    }


# ─── 格式化输出 ─────────────────────────────────────────────

def format_hexagram_text(main_lines, moving_indices):
    """格式化卦象文本（供 LLM 解卦使用）。

    Args:
        main_lines: 六爻列表
        moving_indices: 动爻索引列表

    Returns:
        格式化的字符串
    """
    hg = compute_hexagrams(main_lines, moving_indices)
    m, mu, c = hg["main"], hg["mutual"], hg["changed"]

    parts = [
        "【起卦信息】",
        f"主卦: {get_gua_name(main_lines)} — 上{m['top']['name']}({m['top']['element']}) 下{m['bot']['name']}({m['bot']['element']})",
        f"互卦: {get_gua_name(mu['lines'])} — 上{mu['top']['name']}({mu['top']['element']}) 下{mu['bot']['name']}({mu['bot']['element']})",
        f"变卦: {get_gua_name(c['lines'])} — 上{c['top']['name']}({c['top']['element']}) 下{c['bot']['name']}({c['bot']['element']})",
        f"动爻: 第{', '.join(str(i+1) for i in moving_indices)}爻",
        f"体卦: {hg['ti']['name']}({hg['ti']['element']})，用卦: {hg['yong']['name']}({hg['yong']['element']})",
        "",
        "主卦六爻（从下到上）:",
    ]
    for i in range(6):
        yao = "阳爻" if main_lines[i] == 1 else "阴爻"
        mark = " ← 动爻" if i in moving_indices else ""
        parts.append(f"  第{i+1}爻: {yao}{mark}")

    return "\n".join(parts)


def print_hexagrams(main_lines, moving_indices):
    """终端可视化输出卦象。

    Args:
        main_lines: 六爻列表
        moving_indices: 动爻索引列表
    """
    hg = compute_hexagrams(main_lines, moving_indices)
    m, mu, c = hg["main"], hg["mutual"], hg["changed"]

    print("\n================ 起卦结果 ================\n")
    print("      【主卦】          【互卦】          【变卦】")
    print(
        f"上卦: {m['top']['name']}({m['top']['element']}) {m['top']['symbol']}     "
        f"上卦: {mu['top']['name']}({mu['top']['element']}) {mu['top']['symbol']}     "
        f"上卦: {c['top']['name']}({c['top']['element']}) {c['top']['symbol']}"
    )
    print(
        f"下卦: {m['bot']['name']}({m['bot']['element']}) {m['bot']['symbol']}     "
        f"下卦: {mu['bot']['name']}({mu['bot']['element']}) {mu['bot']['symbol']}     "
        f"下卦: {c['bot']['name']}({c['bot']['element']}) {c['bot']['symbol']}\n"
    )

    for i in range(5, -1, -1):
        is_moving = i in moving_indices
        ml_sym = "▅▅▅▅▅" if main_lines[i] == 1 else "▅▅  ▅▅"
        ml = f"{ml_sym} (动)" if is_moving else f"{ml_sym}     "
        mul_sym = "▅▅▅▅▅" if mu["lines"][i] == 1 else "▅▅  ▅▅"
        cl_sym = "▅▅▅▅▅" if c["lines"][i] == 1 else "▅▅  ▅▅"
        print(f"第{i+1}爻: {ml}\t{mul_sym}\t{cl_sym}")
    print("\n==========================================")


# ─── 体用五行生克判断 ───────────────────────────────────────

def analyze_ti_yong(ti_element, yong_element):
    """分析体用五行生克关系。

    Args:
        ti_element: 体卦五行 (金/木/水/火/土)
        yong_element: 用卦五行 (金/木/水/火/土)

    Returns:
        (关系描述, 吉凶判断)
    """
    if ti_element == yong_element:
        return "体用比和", "平顺"

    # 五行相生: 金→水→木→火→土→金
    generates = {"金": "水", "水": "木", "木": "火", "火": "土", "土": "金"}
    # 五行相克: 金→木→土→水→火→金
    overcomes = {"金": "木", "木": "土", "土": "水", "水": "火", "火": "金"}

    if generates.get(ti_element) == yong_element:
        return "体生用（泄气）", "不利"
    if generates.get(yong_element) == ti_element:
        return "用生体（得助）", "大吉"
    if overcomes.get(ti_element) == yong_element:
        return "体克用", "可成但费力"
    if overcomes.get(yong_element) == ti_element:
        return "用克体", "大凶"

    return "未知", "未知"
