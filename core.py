"""Input contract, boundary checks, library adapter, and optional model client."""
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path
import json
import re
import unicodedata

import requests
from meihua_yi import engine

BEIJING = timezone(timedelta(hours=8))
DISCLAIMER = "以上为易经象征性解读，仅供文化参考与决策辅助，不能替代现实信息核验。"
FOOTER = "文小星为中华传统象数文化数字化研习项目，推演结果仅作为思绪参考，作文史审美娱乐，不构成任何预判定论，请理性看待传统文化。"
DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
BLOCK_PATTERNS = (
    ("生死", r"生死|死亡|去世|寿命|活多久|活到几岁|死期|自杀|自残|轻生|生命危险|会不会死|还能活"),
    ("诊疗与健康预后", r"重大疾病|癌症|肿瘤|诊断|诊疗|治疗|疗效|手术|病情|病症|预后|治愈|病能|能痊愈|健康.*(?:好转|结果|走向)|用药|停药|吃什么药"),
    ("法律诉讼", r"诉讼|官司|量刑|刑期|案件|判决|判刑|法院|起诉|坐牢|胜诉|败诉|会被拘留"),
)
HEADINGS = ("读卦复核", "总断", "体用生克", "卦名与卦象", "动爻爻辞", "互卦看过程",
            "变卦看结果", "结合用户问题", "应期", "建议", "局限声明")


class InputError(ValueError):
    pass


class ReadingError(RuntimeError):
    pass


def normalize(text):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text)).lower()


def blocked_topic(text):
    normalized = normalize(text)
    for category, pattern in BLOCK_PATTERNS:
        if re.search(pattern, normalized):
            return category
    return None


def validate_question(question, background="", companies=""):
    question, background, companies = question.strip(), background.strip(), companies.strip()
    if not question:
        raise InputError("请先写下你想梳理的问题。")
    if len(question) > 500 or len(background) > 1500 or len(companies) > 3000:
        raise InputError("问题请控制在500字以内，补充背景在1500字以内，候选公司信息在3000字以内。")
    category = blocked_topic(question + "\n" + background + "\n" + companies)
    if category:
        raise InputError(f"这类问题涉及{category}，文小星不进行象数解读。请依据现实信息，并寻求相应的专业支持。")
    return question, background


def make_datetime(year, month, day, hour):
    values = (year, month, day, hour)
    if any(isinstance(v, bool) or not isinstance(v, int) for v in values):
        raise InputError("年、月、日、时需要填写整数。")
    try:
        dt = datetime(year, month, day, hour, 0, 0)
    except ValueError:
        raise InputError("这个日期或小时不存在，请检查月份、天数和小时。") from None
    # LunarDate's documented supported lunar years are 1900..2099;
    # this conservative solar boundary avoids dates outside that conversion table.
    if not datetime(1900, 1, 31) <= dt < datetime(2100, 1, 1):
        raise InputError("支持的公历日期为1900年1月31日至2099年12月31日。")
    return dt


RELATIONS = {
    "体用比和": "体用比和：两者属性相近，可关注彼此的协调与节奏。",
    "用生体（得助）": "用生体：可以留意环境中的支持条件。",
    "体生用（泄气）": "体生用：可以留意投入与消耗的平衡。",
    "体克用": "体克用：可以关注主动调整与协调的空间。",
    "用克体": "用克体：可以关注外部压力及自身边界。",
}


def build_chart(year, month, day, hour, question, background="", companies=""):
    question, background = validate_question(question, background, companies)
    dt = make_datetime(year, month, day, hour)
    if not engine.HAS_LUNAR:
        raise InputError("农历转换组件未就绪，暂时无法排盘，请安装项目依赖后重新启动。")
    try:
        # Only the library performs solar -> lunar conversion and divination.
        lines, moving = engine.qigua_time(dt)
        result = engine.compute_hexagrams(lines, moving)
        text = engine.format_hexagram_text(lines, moving)
        relation, _ = engine.analyze_ti_yong(result["ti"]["element"], result["yong"]["element"])
    except (ValueError, IndexError, AttributeError) as exc:
        raise InputError("该日期无法完成农历转换或排盘，请核对日期和项目依赖。") from exc
    return {
        "datetime": dt,
        "shichen": "子丑寅卯辰巳午未申酉戌亥"[engine.get_shichen(dt.hour) - 1] + "时",
        "question": question,
        "background": background,
        "companies": companies.strip(),
        "lines": lines,
        "moving": moving,
        "result": result,
        "hexagram_text": text,
        "relation": RELATIONS.get(relation, "体用关系待核对。"),
    }


# King Wen order for Unicode glyphs; this maps labels for display, not divination.
KING_WEN = "乾为天,坤为地,水雷屯,山水蒙,水天需,天水讼,地水师,水地比,风天小畜,天泽履,地天泰,天地否,天火同人,火天大有,地山谦,雷地豫,泽雷随,山风蛊,地泽临,风地观,火雷噬嗑,山火贲,山地剥,地雷复,天雷无妄,山天大畜,山雷颐,泽风大过,坎为水,离为火,泽山咸,雷风恒,天山遁,雷天大壮,火地晋,地火明夷,风火家人,火泽睽,水山蹇,雷水解,山泽损,风雷益,泽天夬,天风姤,泽地萃,地风升,泽水困,水风井,泽火革,火风鼎,震为雷,艮为山,风山渐,雷泽归妹,雷火丰,火山旅,巽为风,兑为泽,风水涣,水泽节,风泽中孚,雷山小过,水火既济,火水未济".split(",")
GLYPHS = {name: chr(0x4DC0 + index) for index, name in enumerate(KING_WEN)}
TRIGRAM_MEANINGS = {"乾为天": "乾", "坤为地": "坤", "震为雷": "震", "巽为风": "巽",
                    "坎为水": "坎", "离为火": "离", "艮为山": "艮", "兑为泽": "兑"}


def chart_facts(chart):
    """Provide role-bound names from the library, never from model output."""
    result = chart["result"]
    facts = {
        label: {"卦名": engine.get_gua_name(result[part]["lines"]),
                "上卦": result[part]["top"]["name"], "下卦": result[part]["bot"]["name"]}
        for label, part in (("本卦", "main"), ("互卦", "mutual"), ("变卦", "changed"))
    }
    facts.update({"体卦": result["ti"]["name"], "用卦": result["yong"]["name"],
                  "动爻": [i + 1 for i in chart["moving"]]})
    return facts


def validate_hexagram_names(text, chart):
    facts = chart_facts(chart)
    role_names = {label: facts[label]["卦名"] for label in ("本卦", "互卦", "变卦")}
    role_names["主卦"] = role_names["本卦"]
    # Remove presentation marks so bolded titles cannot evade role checks.
    plain = unicodedata.normalize("NFKC", re.sub(r"[*_`#]", "", text))
    names_pattern = "|".join(re.escape(name) for name in sorted(KING_WEN, key=len, reverse=True))
    separators = r"[\s:：\-—()（）\[\]【】‘’“”\"《》]*"
    claims = re.compile(r"(本卦|主卦|互卦|变卦)(?:卦名)?" + separators
                        + r"(?:(?:为|是|叫|称为)" + separators + r")?(" + names_pattern + r")")
    for match in claims.finditer(plain):
        role, name = match.groups()
        if name != role_names[role]:
            raise ReadingError(f"解读把{role}写成了“{name}”，本次排盘的{role}是“{role_names[role]}”。已停止展示，请重新生成。")

    expected_names = set(role_names.values())
    present_trigrams = {facts[label][position] for label in ("本卦", "互卦", "变卦") for position in ("上卦", "下卦")}
    for match in re.finditer(names_pattern, plain):
        name = match.group()
        if name in expected_names:
            continue
        # These eight phrases also describe THREE-line trigram imagery.
        # Permit the trigrams actually present, after rejecting wrong six-line
        # role claims above; other six-line names remain disallowed.
        if TRIGRAM_MEANINGS.get(name) in present_trigrams:
            continue
        expected = "、".join(role_names[label] for label in ("本卦", "互卦", "变卦"))
        raise ReadingError(f"解读提到了“{name}”，与本次排盘的卦象不一致（本卦／互卦／变卦：{expected}）。已停止展示，请重新生成。")


def hexagram_html(label, gua, moving=()):
    name = engine.get_gua_name(gua["lines"])
    rows = []
    for i in range(5, -1, -1):
        marker = '<span class="moving-dot" title="动爻"></span>' if i in moving else ""
        segment = '<span class="yao-segment"></span>'
        rows.append(f'<div class="yao-row{" moving" if i in moving else ""}" aria-label="第{i+1}爻，{"阳" if gua["lines"][i] else "阴"}爻{",动爻" if i in moving else ""}">{segment if gua["lines"][i] else segment + segment}{marker}</div>')
    return f'<div class="hexagram"><div class="hexagram-label">{escape(label)}</div><div class="gua-name">{escape(name)} <span class="gua-symbol">{GLYPHS.get(name, "")}</span></div><div class="yao-stack">{"".join(rows)}</div><div class="trigram-note">上{escape(gua["top"]["name"])} · 下{escape(gua["bot"]["name"])}</div></div>'


SYSTEM_PROMPT = (Path(__file__).resolve().parent / "prompts" / "reading_system.txt").read_text(encoding="utf-8")


@dataclass(frozen=True)
class ModelConfig:
    api_key: str = field(repr=False)
    model: str = "deepseek-chat"


def reading_payload(chart):
    result = chart["result"]
    def describe(gua):
        name = engine.get_gua_name(gua["lines"])
        return {"name": name, "symbol": GLYPHS[name], "upper": gua["top"]["name"],
                "lower": gua["bot"]["name"], "upper_wuxing": gua["top"]["element"],
                "lower_wuxing": gua["bot"]["element"], "lines_bottom_to_top": list(gua["lines"])}
    # Relations are calculated in the library; this only removes explanatory
    # parentheticals for the JSON labels (e.g. 体生用（泄气） -> 体生用).
    relation_label = lambda s: re.sub(r"（.*?）", "", s)
    gua_data = {
        "ben_gua": describe(result["main"]), "hu_gua": describe(result["mutual"]),
        "bian_gua": describe(result["changed"]), "dong_yao": chart["moving"][0] + 1,
        "moving_lines": [i + 1 for i in chart["moving"]],
        "ti_gua": result["ti"]["name"], "yong_gua": result["yong"]["name"],
        "ti_wuxing": result["ti"]["element"], "yong_wuxing": result["yong"]["element"],
        "ti_yong_relation": relation_label(result["ti_yong_relation"]),
        "bian_yong_gua": result["changed_yong"]["name"],
        "bian_yong_wuxing": result["changed_yong"]["element"],
        "bian_relation": relation_label(result["bian_relation"]),
        "yao_ci": None, "gua_ci": None, "missing_fields": ["yao_ci", "gua_ci"],
        "extra": chart["hexagram_text"],
    }
    return {"question": chart["question"], "time": chart["datetime"].strftime("%Y-%m-%d %H:00"),
            "time_range": chart["datetime"].strftime("%H:00–%H:59"), "time_precision": "hour",
            "timezone": "Asia/Shanghai", "shichen": chart["shichen"],
            "method": "梅花易数时间起卦", "gua_data": gua_data,
            "context": chart["background"], "companies": chart.get("companies", "")}


def messages_for(chart):
    data = reading_payload(chart)
    return [{"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(data, ensure_ascii=False)}]


def reading_sections(text):
    headings = list(re.finditer(r"(?m)^[ \t]{0,3}#{1,6}[ \t]+([^\n]+)", text))
    found = []
    for match in headings:
        title = match.group(1)
        section = next((name for name in HEADINGS if name in title), None)
        if section:
            found.append((section, match))
    if [name for name, _ in found] != list(HEADINGS):
        raise ReadingError("解读没有按约定的11步顺序完整返回，已停止展示，请重新生成。")
    return {name: text[match.end():found[index + 1][1].start() if index + 1 < len(found) else len(text)].strip()
            for index, (name, match) in enumerate(found)}


def reading_for_display(text):
    """Project the validated 11-section reply into five visible sections.

    The original reply, evidence and hidden sections remain in session state.
    Retained body paragraphs are not summarized or rewritten.
    """
    sections = reading_sections(text)
    citation = r"(?:【\s*依据\s*[:：][^】]*】|\[\s*依据\s*[:：][^\]]*\])"
    def visible_body(body):
        body = re.sub(r"(?P<wrap>\*\*|__)" + citation + r"(?P=wrap)", "", body)
        body = re.sub(citation, "", body)
        return body.strip()
    groups = (("总断", ("总断",)),
              ("卦象大意", ("体用生克", "卦名与卦象", "动爻爻辞", "互卦看过程", "变卦看结果")),
              ("分析", ("结合用户问题",)),
              ("应期", ("应期",)), ("建议", ("建议",)))
    return "\n\n".join("## " + label + "\n\n" + "\n\n".join(visible_body(sections[name]) for name in names)
                        for label, names in groups)


def validate_reading(text, chart):
    if not isinstance(text, str) or not text.strip():
        raise ReadingError("模型没有返回有效的解读文字，请稍后重试。")
    text = text.strip()
    sections = reading_sections(text)
    if any(not re.search(r"【依据[：:][^】]+】", sections[name]) for name in HEADINGS[1:-1]):
        raise ReadingError("解读中的关键分析缺少依据标注，已停止展示，请重新生成。")
    if "缺失" not in sections["动爻爻辞"]:
        raise ReadingError("本次数据没有提供爻辞，但解读未说明缺失，已停止展示。")
    if re.search(r"【依据[：:][^】]*(?:爻辞|卦辞)[^】]*】", text):
        raise ReadingError("解读引用了本次数据未提供的爻辞或卦辞，已停止展示。")
    if re.search(r"公司|offer|求职|入职|跳槽|岗位", chart["question"], re.I) or chart.get("companies"):
        if any(label not in sections["结合用户问题"] for label in ("最可能去", "最适合", "最需要谨慎")):
            raise ReadingError("公司解读没有区分最可能去、最适合与最需要谨慎，已停止展示，请重新生成。")
    validate_hexagram_names(text, chart)
    if re.search(r"<[^>]+>|https?://|```", text):
        raise ReadingError("这次解读格式不符合要求，请重新生成。")
    # Ensure exactly one fixed footer, always at the end.
    text = text.replace(DISCLAIMER, "").rstrip() + "\n\n" + DISCLAIMER
    if len(text) > 12000:
        raise ReadingError("解读篇幅异常，已停止展示，请重新生成。")
    return text


def ask_model(chart, config):
    validate_question(chart["question"], chart["background"], chart.get("companies", ""))
    if not config.api_key.strip() or not config.model.strip():
        raise ReadingError("解读服务配置未就绪，排盘已保留，请稍后再试。")
    if len(config.model) > 200 or "\n" in config.model or "\n" in config.api_key:
        raise ReadingError("模型设置格式不正确，请检查后重试。")
    payload = {"model": config.model.strip(), "messages": messages_for(chart),
               "max_tokens": 4000, "stream": False, "temperature": 0.6, "top_p": 0.9}
    try:
        response = requests.post(DEEPSEEK_URL,
            headers={"Authorization": "Bearer " + config.api_key.strip(), "Content-Type": "application/json"},
            json=payload, timeout=(10, 120), allow_redirects=False)
        if response.status_code in (401, 403):
            raise ReadingError("模型服务没有接受凭据，请检查 API Key 和模型权限。")
        if response.status_code == 429:
            raise ReadingError("模型服务暂时限流或余额不足，请稍后重试或检查账户。")
        if not 200 <= response.status_code < 300:
            raise ReadingError("模型服务暂时无法完成请求，排盘已保留，可以稍后重试解读。")
        data = response.json()
        choice = data["choices"][0]
        if choice.get("finish_reason") == "length":
            raise ReadingError("模型输出未完整结束，请重试或选择适合文本解读的模型。")
        return validate_reading(choice["message"]["content"], chart)
    except requests.exceptions.Timeout:
        raise ReadingError("解读等待超时，排盘已保留，你可以稍后重试。") from None
    except requests.exceptions.RequestException:
        raise ReadingError("暂时无法连接模型服务，排盘已保留，请检查网络后重试。") from None
    except (ValueError, KeyError, IndexError, TypeError):
        raise ReadingError("模型接口返回格式不完整，请检查模型设置或稍后重试。") from None
