"""全站统一视觉主题：简约、克制、留白充足的中性色设计。"""
import streamlit as st

_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Noto+Sans+SC:wght@400;500;600;700&display=swap');

:root {
  --pim-bg: #F7F7F5;
  --pim-surface: #FFFFFF;
  --pim-border: #E8E8E4;
  --pim-text: #18181B;
  --pim-muted: #71717A;
  --pim-accent: #18181B;
  --pim-accent-soft: #F1F1EE;
  --pim-radius: 12px;
}

html, body, [class*="css"], .stApp, button, input, textarea, select {
  font-family: 'Inter', 'Noto Sans SC', -apple-system, BlinkMacSystemFont, 'PingFang SC', sans-serif !important;
  -webkit-font-smoothing: antialiased;
}
/* 保留 Streamlit 图标字体 */
[data-testid="stIconMaterial"], .material-symbols-rounded, [class*="material-symbols"] {
  font-family: 'Material Symbols Rounded' !important;
}

.stApp { background: var(--pim-bg); color: var(--pim-text); }

/* 隐藏默认页眉 / 菜单 / 页脚 */
#MainMenu, footer, [data-testid="stDecoration"] { display: none !important; }
header[data-testid="stHeader"] { background: transparent; }

.block-container { padding-top: 2.6rem; padding-bottom: 4rem; max-width: 1180px; }

/* 标题层级 */
h1, h2, h3, h4 { color: var(--pim-text); letter-spacing: -0.02em; font-weight: 600 !important; }
h2 { font-size: 1.25rem !important; }
h3 { font-size: 1.05rem !important; margin-top: .4rem; }
p, li, label { color: var(--pim-text); }
[data-testid="stCaptionContainer"], .stCaption { color: var(--pim-muted) !important; }
hr { border: none !important; border-top: 1px solid var(--pim-border) !important; margin: 2rem 0 !important; }

/* 页面标题 */
.pim-header { margin-bottom: 1.8rem; padding-bottom: 1.4rem; border-bottom: 1px solid var(--pim-border); }
.pim-eyebrow { font-size: .72rem; font-weight: 600; letter-spacing: .14em; text-transform: uppercase; color: var(--pim-muted); margin-bottom: .55rem; }
.pim-header h1.pim-title { font-size: 1.85rem !important; padding: 0 !important; font-weight: 650 !important; letter-spacing: -0.03em; color: var(--pim-text); line-height: 1.2; margin: 0; }
.pim-subtitle { font-size: .95rem; color: var(--pim-muted); margin-top: .55rem; line-height: 1.65; max-width: 720px; }
.pim-tag { display: inline-block; margin-left: .6rem; padding: .12rem .5rem; font-size: .7rem; font-weight: 500;
  vertical-align: middle; border: 1px solid var(--pim-border); border-radius: 999px; color: var(--pim-muted); letter-spacing: 0; }
.pim-section { font-size: .78rem; font-weight: 600; letter-spacing: .12em; text-transform: uppercase; color: var(--pim-muted);
  margin: 2.4rem 0 1rem; }

/* 侧边栏 */
section[data-testid="stSidebar"] { background: var(--pim-surface); border-right: 1px solid var(--pim-border); }
section[data-testid="stSidebar"] .block-container, section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] { padding-top: 1.6rem; }
.pim-brand { display: flex; align-items: center; gap: .7rem; padding: 0 .2rem 1.4rem; margin-bottom: 1rem; border-bottom: 1px solid var(--pim-border); }
.pim-brand-mark { width: 34px; height: 34px; border-radius: 9px; background: var(--pim-accent); color: #fff;
  display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: .95rem; letter-spacing: -.02em; }
.pim-brand-name { font-weight: 600; font-size: .98rem; color: var(--pim-text); line-height: 1.2; }
.pim-brand-sub { font-size: .72rem; color: var(--pim-muted); letter-spacing: .04em; }
.pim-nav-label { font-size: .7rem; font-weight: 600; letter-spacing: .14em; text-transform: uppercase; color: var(--pim-muted); margin: .2rem .2rem .5rem; }
.pim-sidebar-foot { font-size: .72rem; color: var(--pim-muted); padding: 1.2rem .2rem 0; margin-top: 1.4rem; border-top: 1px solid var(--pim-border); }

/* 侧边栏导航：单选框改造成菜单列表 */
section[data-testid="stSidebar"] [data-testid="stElementContainer"]:has([data-testid="stRadio"]),
section[data-testid="stSidebar"] [data-testid="stRadio"], section[data-testid="stSidebar"] [data-testid="stRadioGroup"] { width: 100% !important; }
section[data-testid="stSidebar"] div[role="radiogroup"] { gap: 2px; width: 100%; display: flex; flex-direction: column; }
section[data-testid="stSidebar"] [data-testid="stRadioOption"] {
  width: 100%; padding: .62rem .8rem; border-radius: 8px; margin: 0; cursor: pointer; transition: background .15s ease;
}
section[data-testid="stSidebar"] [data-testid="stRadioOption"]:hover { background: var(--pim-accent-soft); }
section[data-testid="stSidebar"] [data-testid="stRadioOption"] p { font-size: .9rem; color: var(--pim-muted); font-weight: 500; }
section[data-testid="stSidebar"] [data-testid="stRadioOption"][data-selected="true"] { background: var(--pim-accent-soft); }
section[data-testid="stSidebar"] [data-testid="stRadioOption"][data-selected="true"] p { color: var(--pim-text); font-weight: 600; }

/* 隐藏单选圆点（导航与分段控件） */
section[data-testid="stSidebar"] [data-testid="stRadioOption"] div:has(+ [data-testid="stMarkdownContainer"]),
[data-testid="stMain"] [data-testid="stRadioOption"] div:has(+ [data-testid="stMarkdownContainer"]) { display: none !important; }

/* 按钮 */
.stButton > button, .stDownloadButton > button, .stFormSubmitButton > button, .stLinkButton > a {
  border-radius: 8px !important; border: 1px solid var(--pim-border) !important; background: var(--pim-surface) !important;
  color: var(--pim-text) !important; font-weight: 500 !important; box-shadow: none !important; padding: .5rem 1.1rem !important;
  transition: all .15s ease;
}
.stButton > button:hover, .stDownloadButton > button:hover, .stLinkButton > a:hover { border-color: #C9C9C3 !important; background: #FAFAF8 !important; }
.stButton > button[kind="primary"], .stDownloadButton > button[kind="primary"], .stFormSubmitButton > button[kind="primary"] {
  background: var(--pim-accent) !important; color: #fff !important; border-color: var(--pim-accent) !important;
}
.stButton > button[kind="primary"]:hover, .stDownloadButton > button[kind="primary"]:hover { background: #3F3F46 !important; border-color: #3F3F46 !important; }
.stButton > button[kind="primary"] p, .stDownloadButton > button[kind="primary"] p { color: #fff !important; }
.stButton > button:disabled { opacity: .45; }
.stLinkButton a[data-testid="stBaseLinkButton-primary"] { background: var(--pim-accent) !important; color: #fff !important; border-color: var(--pim-accent) !important; }
.stLinkButton a[data-testid="stBaseLinkButton-primary"] p { color: #fff !important; }
.stLinkButton a[data-testid="stBaseLinkButton-primary"]:hover { background: #3F3F46 !important; }
div[data-baseweb="select"] > div { border: 1px solid var(--pim-border) !important; }

/* 输入控件 */
.stTextInput input, .stNumberInput input, .stTextArea textarea, div[data-baseweb="select"] > div {
  border-radius: 8px !important; background: var(--pim-surface) !important;
}
div[data-baseweb="input"], div[data-baseweb="base-input"], div[data-baseweb="select"] > div { border-color: var(--pim-border) !important; }

/* 上传区 */
[data-testid="stFileUploaderDropzone"] {
  background: var(--pim-surface); border: 1.5px dashed #D4D4CF; border-radius: var(--pim-radius); padding: 1.6rem;
}
[data-testid="stFileUploaderDropzone"]:hover { border-color: #A1A1AA; }

/* 指标卡片 */
[data-testid="stMetric"] {
  background: var(--pim-surface); border: 1px solid var(--pim-border); border-radius: var(--pim-radius); padding: 1.1rem 1.25rem;
}
[data-testid="stMetricLabel"] p { font-size: .8rem !important; color: var(--pim-muted) !important; font-weight: 500; }
[data-testid="stMetricValue"] { font-size: 1.65rem !important; font-weight: 600; letter-spacing: -0.02em; color: var(--pim-text); }

/* 提示框 */
[data-testid="stAlert"], div[data-testid="stAlertContainer"] { border-radius: 10px !important; }
[data-testid="stAlert"] > div { border: none; }

/* 容器 / 展开 / 状态 / 表格 */
[data-testid="stExpander"] details, [data-testid="stExpander"] { border-radius: var(--pim-radius) !important; border-color: var(--pim-border) !important; background: var(--pim-surface); }
[data-testid="stVerticalBlockBorderWrapper"] { border-radius: var(--pim-radius); }
[data-testid="stDataFrame"] { border: 1px solid var(--pim-border); border-radius: var(--pim-radius); overflow: hidden; }
[data-testid="stImage"] img { border-radius: 10px; }

/* 主区域单选改成分段控件 */
[data-testid="stMain"] div[role="radiogroup"] {
  gap: 4px; background: #EDEDEA; padding: 4px; border-radius: 10px; display: inline-flex; flex-wrap: wrap; width: auto;
}
[data-testid="stMain"] [data-testid="stRadioOption"] { padding: .38rem .95rem; border-radius: 7px; margin: 0 !important; cursor: pointer; }
[data-testid="stMain"] [data-testid="stRadioOption"] p { font-size: .85rem; color: var(--pim-muted); }
[data-testid="stMain"] [data-testid="stRadioOption"][data-selected="true"] { background: var(--pim-surface); box-shadow: 0 1px 2px rgba(0,0,0,.06); }
[data-testid="stMain"] [data-testid="stRadioOption"][data-selected="true"] p { color: var(--pim-text); font-weight: 600; }

/* 滑块与选中色 */
.stSlider [role="slider"] { background: var(--pim-accent) !important; box-shadow: none !important; }

@media (max-width: 640px) {
  .block-container { padding-left: 1rem; padding-right: 1rem; padding-top: 1.6rem; }
  .pim-header h1.pim-title { font-size: 1.5rem !important; }
}
</style>
"""


def apply_theme():
    """注入全局样式，每次页面渲染时调用一次。"""
    st.markdown(_CSS, unsafe_allow_html=True)


def page_header(title, subtitle="", eyebrow="", tag=""):
    """统一页面标题：小号分类标签 + 主标题 + 说明文字。"""
    eyebrow_html = f'<div class="pim-eyebrow">{eyebrow}</div>' if eyebrow else ""
    tag_html = f'<span class="pim-tag">{tag}</span>' if tag else ""
    sub_html = f'<div class="pim-subtitle">{subtitle}</div>' if subtitle else ""
    st.markdown(
        f'<div class="pim-header">{eyebrow_html}'
        f'<h1 class="pim-title">{title}{tag_html}</h1>{sub_html}</div>',
        unsafe_allow_html=True,
    )


def section_title(text):
    """模块内的小节标题（大写字距风格）。"""
    st.markdown(f'<div class="pim-section">{text}</div>', unsafe_allow_html=True)


def sidebar_brand(name, sub):
    st.sidebar.markdown(
        f'<div class="pim-brand"><div class="pim-brand-mark">P</div>'
        f'<div><div class="pim-brand-name">{name}</div>'
        f'<div class="pim-brand-sub">{sub}</div></div></div>',
        unsafe_allow_html=True,
    )
