import streamlit as st
import os

try:
    from modules import mod_stats
except ImportError:
    import mod_stats

# GitHub 字体文件链接配置
FONT_GITHUB_BLOB_URL = "https://github.com/tlhweb02-byte/excel-convert-tool/blob/main/modules/Helvetica%20Neue%26NowText.zip"
FONT_GITHUB_RAW_URL = "https://github.com/tlhweb02-byte/excel-convert-tool/raw/main/modules/Helvetica%20Neue%26NowText.zip"
LOCAL_FONT_ZIP_PATH = os.path.join(os.path.dirname(__file__), "Helvetica Neue&NowText.zip")

def render_ui():
    st.title("🔤 官方品牌字体在线下载")
    st.caption("设计与运营必备 — 统一品牌视觉规范字体包（Helvetica Neue & NowText）")
    
    st.markdown("---")
    
    col1, col2 = st.columns()
    
    with col1:
        st.subheader("📦 包含字体说明")
        st.info("""
        本字体包内含以下官方品牌常用字体家族：
        - **Helvetica Neue**：国际通用无衬线经典字体，适用于各类标题、正文及海报排版。
        - **NowText**：品牌专有与主视觉配合使用的西文字体，适用于品牌标志与高端视觉呈现。
        """)
        
        st.subheader("⬇️ 字体下载通道")
        
        # 若服务器本地存在该 zip 文件，优先提供本地极速下载
        if os.path.exists(LOCAL_FONT_ZIP_PATH):
            with open(LOCAL_FONT_ZIP_PATH, "rb") as f:
                font_bytes = f.read()
            st.download_button(
                label="🚀 本地极速下载 (Helvetica Neue & NowText.zip)",
                data=font_bytes,
                file_name="Helvetica Neue&NowText.zip",
                mime="application/zip",
                use_container_width=True,
                type="primary"
            )
            st.caption("推荐：优先使用本地高速通道下载。")
        else:
            # 云端直链下载按钮
            st.link_button(
                label="☁️ 官方云端直链一键下载 (.zip)",
                url=FONT_GITHUB_RAW_URL,
                use_container_width=True,
                type="primary"
            )
            st.caption("提示：通过官方云端直链一键获取 zip 压缩包。")

        st.markdown("<br>", unsafe_allow_html=True)
        st.link_button(
            label="🔗 在 GitHub 仓库中查看文件与详情",
            url=FONT_GITHUB_BLOB_URL,
            use_container_width=True
        )

    with col2:
        st.subheader("💡 安装与使用指南")
        st.markdown("""
        **Windows 系统：**
        1. 下载并解压 ZIP 压缩包；
        2. 全选解压出的 `.ttf` / `.otf` 字体文件；
        3. 右键选择 **“为所有用户安装”** 或 **“安装”**。

        **macOS 系统：**
        1. 下载并解压 ZIP 压缩包；
        2. 双击字体文件，在弹出的字体册中点击 **“安装字体”**。

        ⚠️ **注意事项：**
        - 安装完成后，请重启 Figma / Photoshop / Illustrator 等软件以更新字体列表。
        - 品牌字体仅限内部设计及相关运营宣传使用，请遵循品牌视觉规范。
        """)
