import streamlit as st

# 导入 modules 文件夹下的各个独立模块
from modules import mod_07_excel, mod_05_compress, mod_fonts, mod_stats, ui_theme
from modules.baozun_expand import app as mod_baozun_expand

# 页面基础配置
st.set_page_config(
    page_title="作图自动化中台",
    page_icon="◼️",
    layout="wide",
)

ui_theme.apply_theme()

# 侧边栏：品牌 + 功能导航
ui_theme.sidebar_brand("作图自动化中台", "PIM · Automation Hub")
st.sidebar.markdown('<div class="pim-nav-label">功能模块</div>', unsafe_allow_html=True)

PAGES = {
    "运营表格智能转化": mod_07_excel.render_ui,
    "图片压缩与降维": mod_05_compress.render_ui,
    "宝尊智能扩图": mod_baozun_expand.render_ui,
    "品牌字体下载": mod_fonts.render_ui,
    "团队提效仪表盘": mod_stats.render_ui,
}

nav_choice = st.sidebar.radio(
    "功能模块",
    list(PAGES.keys()),
    label_visibility="collapsed",
)

st.sidebar.markdown(
    '<div class="pim-sidebar-foot">免登录 · 打开即用</div>',
    unsafe_allow_html=True,
)

# 路由渲染
PAGES[nav_choice]()

# 底部统一数据统计面板（仪表盘页面本身已展示完整数据，不再重复）
if nav_choice != "团队提效仪表盘":
    mod_stats.render_bottom_panel()
