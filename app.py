import streamlit as st

# 导入各功能模块
from modules import mod_05_compress, mod_07_excel, mod_stats

try:
  from modules.baozun_expand import app as mod_baozun_expand
except ImportError:
  from baozun_expand import app as mod_baozun_expand

st.set_page_config(page_title="作图自动化在线中台", page_icon="⚡", layout="wide")

# 侧边栏功能导航
st.sidebar.title("⚡ 自动化中台")
nav_choice = st.sidebar.radio(
    "请选择功能模块：",
    [
        "📊 运营表格一键智能转化",
        "🖼️ 智能图片压缩与降维",
        "🎨 宝尊智能扩图 (ROSS)",
        "🏆 团队提效仪表盘",
    ],
)

# 路由渲染
if nav_choice == "📊 运营表格一键智能转化":
  mod_07_excel.render_ui()

elif nav_choice == "🖼️ 智能图片压缩与降维":
  mod_05_compress.render_ui()

elif nav_choice == "🎨 宝尊智能扩图 (ROSS)":
  mod_baozun_expand.render_ui()

elif nav_choice == "🏆 团队提效仪表盘":
  mod_stats.render_ui()

# 底部数据面板
mod_stats.render_bottom_panel()
