"""文小星 — Streamlit time-divination page."""
from datetime import datetime
from html import escape
from pathlib import Path
import sys

# Also works with a portable Python whose ._pth omits the script directory.
APP_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(APP_DIR))

import streamlit as st
from core import (BEIJING, FOOTER, InputError, ReadingError,
                  build_chart, hexagram_html, ask_model, reading_for_display)
from settings import load_model_config, SettingsError

st.set_page_config(page_title="文小星 · 梅花象数", page_icon="☯", layout="centered")
st.markdown('<style>' + (APP_DIR / 'style.css').read_text(encoding='utf-8') + '</style>', unsafe_allow_html=True)
TAIJI = '<svg viewBox="0 0 100 100" class="taiji" aria-hidden="true"><circle cx="50" cy="50" r="46"/><path d="M50 4 A23 23 0 0 1 50 50 A23 23 0 0 0 50 96"/><circle cx="50" cy="27" r="4"/><circle cx="50" cy="73" r="4"/></svg>'
st.markdown(f'<header class="page-heading"><div class="title-wrap">{TAIJI}<h1>文小星</h1></div><p class="subtitle">观阴阳之象，随星光寻思</p></header>', unsafe_allow_html=True)

now = datetime.now(BEIJING)
with st.form("question_form", border=False):
    st.markdown('<div class="section-kicker">起念 · 问时</div>', unsafe_allow_html=True)
    st.markdown('<h2 class="section-title">请输入公历时间</h2>', unsafe_allow_html=True)
    st.caption("北京时间 · 24小时制 · 默认为当前小时，可自行修改")
    with st.container(key="date_fields"):
        cols = st.columns(4)
        year = cols[0].number_input("年", min_value=1900, max_value=2099, value=now.year, step=1)
        month = cols[1].number_input("月", min_value=1, max_value=12, value=now.month, step=1)
        day = cols[2].number_input("日", min_value=1, max_value=31, value=now.day, step=1)
        hour = cols[3].selectbox("时段", options=list(range(24)), index=now.hour,
                                 format_func=lambda h: f"{h:02d}:00–{h:02d}:59", key="hour_select")
    question = st.text_input("你想梳理的问题", placeholder="例如：面对两个学习方向，我该关注哪些因素？", max_chars=500)
    background = st.text_area("补充背景（选填）", placeholder="说说当下的处境、你的顾虑，或你已经考虑过的选择。", max_chars=1500, height=92)
    run_btn = st.form_submit_button("开始推演", type="primary", width="stretch")
    st.caption("推演时，问题、补充背景与卦象将交由 DeepSeek 生成意象解读。")

try:
    model_config = load_model_config()
except SettingsError:
    model_config = None

if run_btn:
    st.session_state.pop("chart", None)
    st.session_state.pop("reading", None)
    st.session_state.pop("reading_error", None)
    loader = st.empty()
    loader.markdown(f'<div class="loading" role="status">{TAIJI}<span>正在整理卦象</span><span class="little-star">✧</span></div>', unsafe_allow_html=True)
    try:
        st.session_state.chart = build_chart(year, month, day, hour, question, background)
        st.session_state.pop("input_error", None)
    except InputError as exc:
        st.session_state.input_error = str(exc)
    finally:
        loader.empty()

if "input_error" in st.session_state:
    st.warning(st.session_state.input_error)

chart = st.session_state.get("chart")
if chart:
    with st.container(key="chart_card"):
        st.markdown('<div class="section-kicker">观象 · 明意</div><h2 class="section-title">象数卦象</h2>', unsafe_allow_html=True)
        time_range = chart["datetime"].strftime("%Y年%m月%d日 %H:00–%H:59")
        st.markdown(f'<div class="result-context">{escape(time_range)} · 北京时间 · {chart["shichen"]}<br><span>{escape(chart["question"])}</span></div>', unsafe_allow_html=True)
        result = chart["result"]
        cards = ''.join(hexagram_html(label, result[key], chart["moving"] if key == "main" else ()) for label, key in (("本卦", "main"), ("互卦", "mutual"), ("变卦", "changed")))
        st.markdown(f'<div class="hexagram-grid">{cards}</div>', unsafe_allow_html=True)
        moving_text = "、".join(str(i+1) for i in chart["moving"])
        ti, yong = result["ti"], result["yong"]
        st.markdown(f'<div class="ti-yong">体卦：{ti["name"]}（{ti["element"]}）<span>｜</span>用卦：{yong["name"]}（{yong["element"]}）<br><small>第{moving_text}爻动 · 浅金色圆点标记动爻</small></div>', unsafe_allow_html=True)
        st.markdown(f'<p class="relation-note">{escape(chart["relation"])}</p>', unsafe_allow_html=True)
        with st.expander("查看卦象文字"):
            st.text(chart["hexagram_text"])
        st.download_button("保存卦象文字", data=chart["datetime"].strftime("公历时间（北京时间）：%Y-%m-%d %H:00\n") + "求问事项：" + chart["question"] + "\n\n" + chart["hexagram_text"], file_name="文小星-卦象.txt", mime="text/plain")

    with st.container(key="reading_card"):
        st.markdown(f'<div class="reading-decoration">{TAIJI}</div><div class="section-kicker">循象 · 寻思</div><h2 class="section-title">意象解读</h2>', unsafe_allow_html=True)
        if model_config is None and not st.session_state.get("reading"):
            st.markdown('<p class="empty-reading">卦象已备好。<br>意象解读服务暂未就绪，你可以先观察本卦、互卦与变卦。</p>', unsafe_allow_html=True)
        retry = st.button("重新生成解读" if st.session_state.get("reading") else "生成意象解读", disabled=model_config is None, key="generate_reading")
        if (run_btn and model_config is not None) or retry:
            st.session_state.pop("reading", None)
            st.session_state.pop("reading_error", None)
            loader = st.empty()
            loader.markdown(f'<div class="loading" role="status">{TAIJI}<span>正在生成意象解读</span><span class="little-star">✧</span><span class="little-star second">✧</span></div>', unsafe_allow_html=True)
            try:
                st.session_state.reading = ask_model(chart, model_config)
            except ReadingError as exc:
                st.session_state.reading_error = str(exc)
            finally:
                loader.empty()
        if st.session_state.get("reading_error"):
            st.info(st.session_state.reading_error)
        if st.session_state.get("reading"):
            with st.container(key="reading_content"):
                st.markdown(reading_for_display(st.session_state.reading), unsafe_allow_html=False)

st.markdown(f'<footer class="footer-note">{FOOTER}</footer>', unsafe_allow_html=True)
with st.expander("时间与使用说明"):
    st.write("输入公历年月日和24小时制的0—23时，按北京时间解释，分钟和秒设为0。凌晨3点为03:00（寅时），下午3点为15:00（申时）。未时是13:00至14:59，申时是15:00至16:59。库按时辰起卦，同一时辰内分钟不影响结果。农历转换、起卦、互卦、变卦和体用计算均交给库完成。")
    st.write("沿用库现有规则：23时属于子时，但不提前更换日期；闰月沿用月号。本工具只提供梅花时间起卦。")
    st.write("页面解读依次展示总断、卦象大意、分析、应期和建议。公司画像、匹配度和应期属于象征性推断，需结合现实信息核验。")
