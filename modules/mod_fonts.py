import streamlit as st
import os

FONT_GITHUB_RAW_URL = "https://github.com/tlhweb02-byte/excel-convert-tool/raw/main/modules/Helvetica%20Neue%26NowText.zip"
LOCAL_FONT_ZIP_PATH = os.path.join(os.path.dirname(__file__), "Helvetica Neue&NowText.zip")

def render_ui():
    st.title("品牌字体", anchor=False)
    st.write("Helvetica Neue · NowText")

    # 服务器本地有字体包就直接下载，否则走 GitHub 直链
    if os.path.exists(LOCAL_FONT_ZIP_PATH):
        with open(LOCAL_FONT_ZIP_PATH, "rb") as f:
            st.download_button(
                "下载字体包",
                data=f.read(),
                file_name="Helvetica Neue&NowText.zip",
                mime="application/zip",
                type="primary",
                on_click="ignore",
            )
    else:
        st.link_button("下载字体包", url=FONT_GITHUB_RAW_URL, type="primary")
