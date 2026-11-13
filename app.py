from pathlib import Path

import streamlit as st

from modules import mod_home, mod_07_excel, mod_05_compress, mod_fonts, mod_stats
from modules.baozun_expand import app as mod_baozun_expand

st.set_page_config(page_title="作图自动化中台", page_icon="assets/nike.svg", layout="wide")
st.logo("assets/nike.svg", size="large")
st.html(Path(__file__).parent / "assets" / "motion.css")

# 每个页面有独立网址，可直接访问，例如 /compress
tools = [
    st.Page(mod_07_excel.render_ui, title="表格转化", icon=":material/table_chart:", url_path="excel"),
    st.Page(mod_05_compress.render_ui, title="图片压缩", icon=":material/compress:", url_path="compress"),
    st.Page(mod_baozun_expand.render_ui, title="智能扩图", icon=":material/open_in_full:", url_path="expand"),
    st.Page(mod_fonts.render_ui, title="品牌字体", icon=":material/font_download:", url_path="fonts"),
    st.Page(mod_stats.render_ui, title="数据统计", icon=":material/bar_chart:", url_path="stats"),
]


def home():
    mod_home.render_ui({p.title: p for p in tools})


pages = [st.Page(home, title="首页", icon=":material/home:", url_path="home", default=True), *tools]
st.navigation(pages, position="top").run()
