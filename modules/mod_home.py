"""首页：分屏滚动介绍各工具，背景为随滚动变化的 Nike 粒子画布（assets/particles.js）。"""
from pathlib import Path

import streamlit as st

ASSETS = Path(__file__).resolve().parent.parent / "assets"

# (标题, 一句话说明)；顺序与粒子形态一一对应：网格 / 球体 / 圆环 / 柱状图
SECTIONS = [
    ("表格转化", "上传运营 Excel，自动生成标准清单。"),
    ("图片压缩", "批量压缩图片与 ZIP，保留目录结构。"),
    ("智能扩图", "AI 扩展图片背景，一次生成多张。"),
    ("数据统计", "团队使用数据，按年、月、日追溯。"),
]


def render_ui(pages):
    """pages: {工具标题: st.Page}，用于跳转链接。"""
    st.html(ASSETS / "home.css")

    with st.container(key="home-sec-0"):
        st.title("作图自动化中台", anchor=False)
        st.write("设计与运营的自动化工具。")
        st.page_link(pages["表格转化"], label="开始使用", icon=":material/arrow_forward:")

    for i, (title, desc) in enumerate(SECTIONS, start=1):
        with st.container(key=f"home-sec-{i}"):
            st.header(title, anchor=False)
            st.write(desc)
            st.page_link(pages[title], label="打开", icon=":material/arrow_forward:")

    js = (ASSETS / "particles.js").read_text(encoding="utf-8")
    st.html(f"<script>{js}</script>", unsafe_allow_javascript=True)
