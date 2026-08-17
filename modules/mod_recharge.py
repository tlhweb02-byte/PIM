# -*- coding: utf-8 -*-
"""
💰 次数充值中心
================
- 展示微信个人收款码（套餐：默认 100 次 = ¥10，可买多份）
- 用户付款后填写微信【交易单号】提交订单
- 管理员（AUTH_ADMIN_USERNAMES）在本页面核实微信账单到账后点「确认到账」
- 确认后次数自动计入用户剩余次数（免费 + 已购 - 已用）
"""
import io

import streamlit as st

from modules import mod_auth

try:
    import qrcode
    QR_OK = True
except ImportError:
    QR_OK = False


def _qr_image_bytes(text: str) -> bytes:
    """把文本生成二维码 PNG 图片字节"""
    img = qrcode.make(text)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def render_ui():
    st.title("💰 次数充值中心")
    st.caption("微信扫码付款后提交交易单号，管理员核实到账后次数立即到账。")

    username = mod_auth.current_user()
    if not username:
        st.warning("🔒 请先在左侧「用户中心」登录后再充值。")
        return

    cfg = mod_auth.get_pay_config()
    price = cfg["price_yuan"]
    quota_per = cfg["quota"]
    code = cfg["wechat_code"]

    # ---------- 当前次数 ----------
    b = mod_auth.get_quota_breakdown(username)
    if b["admin"]:
        st.info("👑 管理员账号，使用不限次数。")
    else:
        st.info(
            f"📊 当前次数：免费 {b['free']} 次 + 已购 {b['paid']} 次 - 已用 "
            f"{b['used']} 次 = **剩余 {b['remaining']} 次**"
        )

    st.markdown("---")
    st.subheader("📦 充值套餐")
    st.success(f"**{quota_per} 次 AI 智能扩图 = ¥{price}**（可购买多份）")

    col_qr, col_form = st.columns([1, 1.3], gap="large")

    with col_qr:
        if not code:
            st.warning("⚠️ 收款码未配置（WECHAT_PAY_CODE），请先在 Secrets 配置")
        elif not QR_OK:
            st.warning("⚠️ 缺少 qrcode 依赖库，无法显示收款码")
        else:
            st.image(
                _qr_image_bytes(code),
                caption="👆 微信扫码支付",
                width=240,
            )
            st.caption("1. 打开微信「扫一扫」付款\n2. 付款后复制微信账单里的【交易单号】")

    with col_form:
        st.write("**填写付款信息**")
        copies = st.number_input(
            "购买份数", min_value=1, max_value=20, value=1, step=1
        )
        copies = int(copies)
        total_amount = price * copies
        total_quota = quota_per * copies
        st.markdown(
            f"应付金额：**¥{total_amount}**　|　获得次数：**{total_quota} 次**"
        )
        tx_id = st.text_input(
            "微信【交易单号】",
            placeholder="例如：4200001234202608xxxxxxxxxxxx",
            help="微信 → 我 → 服务 → 钱包 → 账单 → 找到这笔转账 → 查看详情 → 复制交易单号",
        )
        st.caption("3. 粘贴交易单号后点击下方按钮提交，管理员确认到账后自动加次数")
        if st.button("📤 我已付款，提交订单", type="primary", use_container_width=True):
            ok, msg, oid = mod_auth.create_recharge_order(
                username, total_amount, total_quota, tx_id
            )
            if ok:
                st.success(msg)
            else:
                st.error(msg)

    st.markdown("---")
    st.subheader("🧾 我的充值记录")
    orders, err = mod_auth.get_orders(username=username)
    if err:
        st.warning(f"⚠️ {err}")
    elif orders:
        for o in orders:
            status = str(o.get("status", ""))
            icon = {
                mod_auth.ORDER_STATUS_CONFIRMED: "✅",
                mod_auth.ORDER_STATUS_PENDING: "⏳",
                mod_auth.ORDER_STATUS_CANCELED: "❌",
            }.get(status, "❓")
            with st.expander(
                f"{icon} 订单 {o.get('order_id', '')}｜"
                f"¥{o.get('amount', '')} / {o.get('quota', '')} 次｜{status}"
            ):
                st.write(f"- 交易单号：{o.get('tx_id', '')}")
                st.write(f"- 提交时间：{o.get('created_at', '')}")
                if status == mod_auth.ORDER_STATUS_CONFIRMED:
                    st.write(f"- 确认时间：{o.get('confirmed_at', '')}")
                st.caption("到账规则：管理员确认后，次数立即计入剩余次数")
    else:
        st.write("暂无充值记录")

    # ---------- 管理员确认面板 ----------
    if mod_auth.is_admin(username):
        st.markdown("---")
        st.subheader("🔐 管理员：待确认订单")
        st.caption(
            "确认前请先在微信「钱包 → 账单」核实该笔 ¥10 转账已真实到账，"
            "再点击确认，避免误发次数。"
        )
        pending, perr = mod_auth.get_orders(status=mod_auth.ORDER_STATUS_PENDING)
        if perr:
            st.warning(f"⚠️ {perr}")
        elif pending:
            for o in pending:
                with st.expander(
                    f"⏳ {o.get('order_id', '')}｜用户 {o.get('username', '')}｜"
                    f"¥{o.get('amount', '')} / {o.get('quota', '')} 次｜"
                    f"单号 {o.get('tx_id', '')}｜{o.get('created_at', '')}"
                ):
                    c1, c2 = st.columns(2)
                    with c1:
                        if st.button(
                            "✅ 确认到账", key=f"cf_{o.get('order_id', '')}",
                            type="primary", use_container_width=True,
                        ):
                            ok, msg = mod_auth.confirm_order(o.get("order_id", ""))
                            if ok:
                                st.success(msg)
                                st.rerun()
                            else:
                                st.error(msg)
                    with c2:
                        if st.button(
                            "❌ 取消订单", key=f"cc_{o.get('order_id', '')}",
                            use_container_width=True,
                        ):
                            ok, msg = mod_auth.cancel_order(o.get("order_id", ""))
                            if ok:
                                st.warning(msg)
                                st.rerun()
                            else:
                                st.error(msg)
        else:
            st.write("暂无待确认订单 🎉")
