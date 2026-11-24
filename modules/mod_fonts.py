import streamlit as st

FONT_DOWNLOAD_URL = "https://pan.baidu.com/s/19twFj8pWxlj2SzWHMNLxTA?pwd=tcss"


def render_ui():
    st.title("品牌字体", anchor=False)
    st.write("Helvetica Neue · NowText")
    st.link_button("下载字体包", url=FONT_DOWNLOAD_URL, type="primary")
    st.caption("百度网盘 · 提取码 tcss")
