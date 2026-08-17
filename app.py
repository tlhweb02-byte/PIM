import streamlit as st

# 导入 modules 文件夹下的各个独立模块
from modules import mod_07_excel, mod_05_compress, mod_fonts, mod_stats, mod_auth, mod_recharge
from modules.baozun_expand import app as mod_baozun_expand

# 页面基础配置
st.set_page_config(
    page_title="作图自动化在线中台",
    page_icon="⚡",
    layout="wide"
)

# ============ 侧边栏：用户中心（注册 / 登录 / 退出） ============
def render_auth_panel():
    """渲染侧边栏用户中心；未登录时提供注册与登录表单"""
    st.sidebar.markdown("---")
    st.sidebar.subheader("👤 用户中心")

    if mod_auth.is_logged_in():
        username = mod_auth.current_user()
        st.sidebar.success(f"✅ 当前用户：**{username}**")
        if mod_auth.is_admin(username):
            st.sidebar.caption("👑 管理员账号（宝尊扩图不限次数）")
        else:
            remaining = mod_auth.get_remaining(username)
            st.sidebar.caption(
                f"🎨 宝尊扩图剩余次数：**{remaining}** 次"
            )
            if remaining <= 0:
                st.sidebar.caption("💡 次数用尽？去「💰 充值中心」充值")
        if st.sidebar.button("🚪 退出登录", use_container_width=True):
            mod_auth.logout()
            # 退出后把账号操作切回「登录」，避免下次停留在注册模式造成困惑
            st.session_state["auth_panel_mode"] = "登录"
            st.rerun()
        return

    auth_mode = st.sidebar.radio(
        "账号操作",
        ["登录", "注册新账号"],
        key="auth_panel_mode",
        label_visibility="collapsed",
    )

    auth_password2 = ""  # 注册模式下才存在，先兜底初始化防止残留状态报错
    with st.sidebar.form("auth_form", clear_on_submit=True):
        auth_username = st.text_input("用户名", key="auth_username")
        auth_password = st.text_input("密码", type="password", key="auth_password")
        if auth_mode == "注册新账号":
            auth_password2 = st.text_input(
                "确认密码", type="password", key="auth_password2"
            )
            st.caption(f"注册即赠送 {mod_auth.free_quota()} 次免费体验 🎁")
        submit_label = "🔑 登录" if auth_mode == "登录" else "🎉 注册并开始体验"
        submitted = st.form_submit_button(
            submit_label, type="primary", use_container_width=True
        )

    if submitted:
        try:
            if auth_mode == "登录":
                ok, msg, _ = mod_auth.login_user(auth_username, auth_password)
                if ok:
                    # 关键：登录成功必须写入登录会话，否则 rerun 后又回到未登录状态
                    mod_auth.set_logged_in(auth_username)
            else:
                if auth_password != auth_password2:
                    st.sidebar.error("两次输入的密码不一致")
                    return
                ok, msg = mod_auth.register_user(auth_username, auth_password)
                if ok:
                    mod_auth.set_logged_in(auth_username)
            if ok:
                st.sidebar.success(msg)
                try:
                    st.toast("✅ " + msg)
                except Exception:
                    pass
                # 注意：不能在这里写 st.session_state["auth_panel_mode"]，
                # 单选按钮已渲染，Streamlit 会抛 "cannot be modified after the widget" 异常。
                # 退出登录时（单选按钮未渲染）再重置模式即可。
                st.rerun()
            else:
                st.sidebar.error(msg)
        except Exception as e:
            st.sidebar.error(f"操作异常：{type(e).__name__}: {e}")

    # 诊断面板：登录没反应时点这里查看具体原因
    with st.sidebar.expander("🔧 登录没反应？点这里诊断", expanded=False):
        st.caption("输入上面的用户名/密码后点「运行诊断」，可查看每一步是否正常")
        if st.button("🔍 运行诊断", key="auth_diag_btn"):
            diag = mod_auth.diagnose_auth(auth_username, auth_password)
            if diag["sheet_ok"]:
                st.write(f"✅ Google 表格连接正常（账号表共 {diag['account_count']} 条记录）")
            else:
                st.write(f"❌ Google 表格连接失败：{diag['sheet_error']}")
            uname = (auth_username or "").strip().lower()
            st.write(f"账号「{uname}」：{'✅ 存在' if diag['username_exists'] else '❌ 不存在（注意：用户名会自动转为小写）'}")
            if diag["username_exists"]:
                st.write(f"密码校验：{'✅ 正确' if diag['password_ok'] else '❌ 不正确'}")

    st.sidebar.caption(f"账号系统 v{mod_auth.AUTH_VERSION}")


render_auth_panel()

# 侧边栏功能导航
st.sidebar.title("⚡ 自动化中台")
nav_choice = st.sidebar.radio(
    "请选择功能模块：",
    [
        "📊 运营表格一键智能转化",
        "🖼️ 智能图片压缩与降维",
        "🎨 宝尊智能扩图 (ROSS)",
        "💰 次数充值中心",
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
    # 宝尊扩图使用公司付费账号，仅对登录用户开放（未登录时锁定）
    if mod_auth.is_logged_in():
        mod_baozun_expand.render_ui()
    else:
        st.warning(
            "🔒 **宝尊智能扩图需要使用公司付费账号，仅对注册用户开放**\n\n"
            "新用户注册即赠送 **10 次免费体验**，请先在左侧「用户中心」"
            "登录或注册。"
        )

elif nav_choice == "💰 次数充值中心":
    # 充值需要登录（确认到账后次数加到登录账号上）
    if mod_auth.is_logged_in():
        mod_recharge.render_ui()
    else:
        st.warning(
            "🔒 充值次数会加到登录账号上，请先在左侧「用户中心」登录。"
        )

elif nav_choice == "🔤 官方品牌字体在线下载":
    mod_fonts.render_ui()

elif nav_choice == "🏆 团队提效仪表盘":
    mod_stats.render_ui()

# 底部统一数据统计面板 (Data Dashboard)
mod_stats.render_bottom_panel()
