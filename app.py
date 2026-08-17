import streamlit as st

# 导入 modules 文件夹下的各个独立模块
from modules import mod_07_excel, mod_05_compress, mod_fonts, mod_stats
from modules.baozun_expand import app as mod_baozun_expand

# 页面基础配置
st.set_page_config(
    page_title="作图自动化在线中台",
    page_icon="⚡",
    layout="wide"
)

# 侧边栏功能导航
st.sidebar.title("⚡ 自动化中台")
nav_choice = st.sidebar.radio(
    "请选择功能模块：",
    [
        "📊 运营表格一键智能转化",
        "🖼️ 智能图片压缩与降维",
        "🎨 宝尊智能扩图 (ROSS)",
        "🔤 官方品牌字体在线下载",
        "🏆 团队提效仪表盘"
    ]
)

# 路由渲染
if nav_choice == "📊 运营表格一键智能转化":
    mod_07_excel.render_ui()

elif nav_choice == "🖼️ 智能图片压缩与降维":
    mod_05_compress.render_ui()

elif nav_choice == "🎨 宝尊智能扩图 (ROSS)":
    mod_baozun_expand.render_ui()

elif nav_choice == "🔤 官方品牌字体在线下载":
    mod_fonts.render_ui()

elif nav_choice == "🏆 团队提效仪表盘":
    mod_stats.render_ui()

# 底部统一数据统计面板 (Data Dashboard)
mod_stats.render_bottom_panel()
