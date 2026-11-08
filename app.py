from pathlib import Path

import streamlit as st

from modules import mod_07_excel, mod_05_compress, mod_fonts, mod_stats
from modules.baozun_expand import app as mod_baozun_expand

st.set_page_config(page_title="作图自动化中台", page_icon="assets/nike.svg", layout="wide")
st.logo("assets/nike.svg", size="large")
st.html(Path(__file__).parent / "assets" / "motion.css")

# 每个页面有独立网址，可直接访问，例如 /compress
pages = [
    st.Page(mod_07_excel.render_ui, title="表格转化", url_path="excel", default=True),
    st.Page(mod_05_compress.render_ui, title="图片压缩", url_path="compress"),
    st.Page(mod_baozun_expand.render_ui, title="智能扩图", url_path="expand"),
    st.Page(mod_fonts.render_ui, title="品牌字体", url_path="fonts"),
    st.Page(mod_stats.render_ui, title="数据统计", url_path="stats"),
]

st.navigation(pages, position="top").run()
