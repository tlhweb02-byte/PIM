# -*- coding: utf-8 -*-
"""
宝尊「投放打标管理」（NIKE 官方 outlets 店）Streamlit 界面
========================================================
- 复用登录账号体系（仅注册用户可用），租户固定 NIKE
- 提供两个子页：投放管理（投放策略）与 打标任务（任务 + 分组）
- 支持：状态筛选、关键词搜索、查看详情、取消/结束/删除投放、
        再次投放、新建/复制/重命名/删除打标任务、新建分组
"""
import time as _time
import streamlit as st

from modules import mod_auth

try:
    from .marking_api import BaozunMarkingAPI, DEFAULT_SHOP
except ImportError:
    try:
        from modules.baozun_marking.marking_api import BaozunMarkingAPI, DEFAULT_SHOP
    except ImportError:
        from marking_api import BaozunMarkingAPI, DEFAULT_SHOP

# 投放状态 → 中文
PUSH_STATUS_MAP = {
    "All": "全部",
    "Noset": "待开始",
    "Pushing": "投放中",
    "Ended": "已结束",
    "Cancel": "已取消",
    "Recoverying": "恢复中",
    "Recovery": "已恢复",
    "Uploading": "上传中",
    "NoSubmit": "未提交投放",
}

PUSH_STATUS_OPTIONS = ["All", "Noset", "Pushing", "Ended", "Cancel"]

# 登录会话缓存（会话级）
def _get_api(manual_cookie: str):
    """复用已登录的 API 会话；返回 None 表示正在等待人工输入验证码"""
    if st.session_state.get("marking_otp_pending") is not None:
        return None
    cached = st.session_state.get("marking_api_cache")
    if cached is not None:
        return cached
    api = BaozunMarkingAPI(manual_cookie=manual_cookie)
    if getattr(api, "login_pending", False):
        st.session_state["marking_otp_pending"] = api
        return None
    st.session_state["marking_api_cache"] = api
    return api


def _fmt_time(v):
    if not v:
        return "-"
    s = str(v)
    if len(s) >= 16:
        return s[:16]
    return s


def _render_push_status(status: str) -> str:
    return PUSH_STATUS_MAP.get(status, status or "-")


def _render_push_cards(api, rows):
    """把投放策略列表渲染成卡片式信息 + 操作按钮"""
    for row in rows:
        if not isinstance(row, dict):
            continue
        sid = row.get("strategyId")
        name = row.get("strategyName") or f"策略 {sid}"
        status = row.get("pushStatus", "")
        status_cn = _render_push_status(status)
        info = row.get("info") or row.get("remark") or ""
        image_url = row.get("imageUrl") or ""

        with st.container(border=True):
            c1, c2 = st.columns([1, 3])
            with c1:
                if image_url:
                    try:
                        st.image(image_url, use_container_width=True)
                    except Exception:
                        st.write("🖼️")
                else:
                    st.write("🖼️")
            with c2:
                st.markdown(f"**{name}**")
                st.caption(f"策略ID：{sid} ｜ 状态：**{status_cn}**")
                if info:
                    st.caption(info)
                st.caption(
                    f"生效：{_fmt_time(row.get('effectDate'))} ｜ "
                    f"结束：{_fmt_time(row.get('closeDate'))}"
                )

            action_cols = st.columns(6)
            show_details = row.get("showDetailsFlag", True)
            show_cancel = row.get("showCancelFlag", False)
            show_end = row.get("showEndFlag", False)
            show_delete = row.get("showDeleteFlag", False)

            if action_cols[0].button("📋 详情", key=f"pd_{sid}",
                                     disabled=not show_details,
                                     use_container_width=True):
                st.session_state["marking_push_view_id"] = sid
            if action_cols[1].button("⛔ 取消", key=f"pc_{sid}",
                                     disabled=not show_cancel,
                                     use_container_width=True):
                st.session_state["marking_push_action"] = ("cancel", sid, name)
            if action_cols[2].button("🛑 结束", key=f"pe_{sid}",
                                     disabled=not show_end,
                                     use_container_width=True):
                st.session_state["marking_push_action"] = ("end", sid, name)
            if action_cols[3].button("🗑️ 删除", key=f"pdel_{sid}",
                                     disabled=not show_delete,
                                     use_container_width=True):
                st.session_state["marking_push_action"] = ("delete", sid, name)
            if action_cols[4].button("🔁 再次投放", key=f"pr_{sid}",
                                     use_container_width=True):
                st.session_state["marking_push_action"] = ("repush", sid, name)
            if action_cols[5].button("🔍 投放历史", key=f"ph_{sid}",
                                     use_container_width=True):
                st.session_state["marking_push_action"] = ("history", sid, name)


def _render_push_detail(api, strategy_id):
    """投放策略详情"""
    detail = api.view_push(strategy_id)
    if not detail:
        st.info("未获取到详情数据")
        return
    st.subheader(f"📋 投放策略详情（{strategy_id}）")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("策略ID", str(detail.get("strategyId", strategy_id)))
    with c2:
        st.metric("状态", _render_push_status(detail.get("pushStatus", "")))
    with c3:
        st.metric("任务ID", str(detail.get("taskId", "-")))
    st.write("**策略名称：**", detail.get("strategyName", "-"))
    st.write("**生效时间：**", _fmt_time(detail.get("effectDate")))
    st.write("**结束时间：**", _fmt_time(detail.get("closeDate")))
    if detail.get("remark") or detail.get("info"):
        st.write("**备注：**", detail.get("remark") or detail.get("info"))
    st.json(detail)


def _render_push_history(api, strategy_id):
    rows = api.push_history(strategy_id)
    if not rows:
        st.info("暂无投放历史")
        return
    st.subheader(f"🔍 投放历史（{strategy_id}）")
    for h in rows:
        if isinstance(h, dict):
            st.caption(
                f"生效 {_fmt_time(h.get('effectDate'))} → "
                f"结束 {_fmt_time(h.get('closeDate'))}"
            )


def _render_push_page(api):
    """投放管理：投放策略列表"""
    st.subheader("📦 投放管理")

    c1, c2, c3 = st.columns([2, 3, 1])
    with c1:
        status_label = st.selectbox(
            "投放状态", PUSH_STATUS_OPTIONS,
            format_func=lambda s: PUSH_STATUS_MAP.get(s, s),
            key="marking_push_status",
        )
    with c2:
        keyword = st.text_input("关键词 / 策略ID搜索", key="marking_push_kw",
                                placeholder="输入投放策略名称或ID")
    with c3:
        st.write("")
        st.write("")
        refresh_btn = st.button("🔄 刷新", key="marking_push_refresh",
                                use_container_width=True)

    page = st.session_state.get("marking_push_page", 1)
    page_size = st.session_state.get("marking_push_page_size", 20)

    if refresh_btn:
        page = 1

    with st.spinner("查询投放策略中..."):
        result = api.list_push(
            push_status=status_label,
            keyword=keyword.strip(),
            page=page,
            page_size=page_size,
        )

    total = result.get("total", 0)
    rows = result.get("list", [])
    st.caption(f"共 **{total}** 条投放策略")

    if not rows:
        st.info("暂无投放数据（当前账号/NIKE outlets 店铺下没有投放策略）")
    else:
        _render_push_cards(api, rows)
        # 分页
        pages = max(1, -(-total // page_size))
        if pages > 1:
            col_a, col_b, col_c = st.columns([2, 1, 2])
            with col_b:
                new_page = st.number_input(
                    "页码", min_value=1, max_value=pages, value=page,
                    key="marking_push_page_input",
                )
                if new_page != page:
                    st.session_state["marking_push_page"] = int(new_page)
                    st.rerun()

    # ---- 操作确认 ----
    action = st.session_state.get("marking_push_action")
    if action:
        act, sid, name = action
        if act in ("cancel", "end", "delete"):
            tips = {
                "cancel": "确认要【取消】该投放吗？",
                "end": "确认要【结束】该投放吗？",
                "delete": "确认要【删除】该投放吗？",
            }
            st.warning(f"{tips[act]}\n\n策略：{name}（ID {sid}）")
            c1, c2 = st.columns(2)
            with c1:
                if st.button("✅ 确认执行", key="marking_push_action_ok",
                             type="primary", use_container_width=True):
                    try:
                        if act == "cancel":
                            resp = api.cancel_push(sid)
                        elif act == "end":
                            resp = api.end_push(sid)
                        else:
                            resp = api.delete_push(sid)
                        if isinstance(resp, dict) and resp.get("status") == 200:
                            st.success("操作成功")
                        else:
                            st.error(f"操作失败：{resp}")
                        st.session_state.pop("marking_push_action", None)
                        st.rerun()
                    except Exception as e:
                        st.error(f"操作异常：{e}")
            with c2:
                if st.button("❌ 取消", key="marking_push_action_no",
                             use_container_width=True):
                    st.session_state.pop("marking_push_action", None)
                    st.rerun()
        elif act == "repush":
            st.info(f"🔁 对策略 **{name}**（ID {sid}）再次投放")
            st.caption("再次投放需要任务ID；若列表数据未提供任务ID，请从详情页获取。")
            task_id = st.text_input("任务ID（taskId）", key="marking_repush_taskid")
            push_type = st.radio("投放方式", ["立即投放", "定时投放"],
                                 key="marking_repush_type",
                                 horizontal=True)
            effect_date = ""
            if push_type == "定时投放":
                effect_date = st.text_input(
                    "生效时间（格式 2025-01-01 12:00:00）",
                    key="marking_repush_effect",
                )
            close_date = st.text_input(
                "结束时间（默认 2050-12-31 23:59:59）",
                value="2050-12-31 23:59:59",
                key="marking_repush_close",
            )
            c1, c2 = st.columns(2)
            with c1:
                if st.button("🚀 确认投放", key="marking_repush_ok", type="primary",
                             use_container_width=True) and task_id.strip():
                    try:
                        resp = api.re_push(
                            task_id.strip(),
                            effect_date=effect_date.strip(),
                            close_date=close_date.strip(),
                        )
                        if isinstance(resp, dict) and resp.get("status") == 200:
                            st.success("再次投放设置成功")
                        else:
                            st.error(f"再次投放失败：{resp}")
                        st.session_state.pop("marking_push_action", None)
                        st.rerun()
                    except Exception as e:
                        st.error(f"再次投放异常：{e}")
            with c2:
                if st.button("❌ 取消", key="marking_repush_no",
                             use_container_width=True):
                    st.session_state.pop("marking_push_action", None)
                    st.rerun()
        elif act == "history":
            st.session_state.pop("marking_push_action", None)
            st.session_state["marking_push_history_id"] = sid
            st.rerun()

    # ---- 详情 / 历史展示 ----
    if st.session_state.get("marking_push_view_id"):
        view_id = st.session_state["marking_push_view_id"]
        _render_push_detail(api, view_id)
        if st.button("⬅️ 返回列表", key="marking_push_view_back"):
            st.session_state.pop("marking_push_view_id", None)
            st.rerun()
    if st.session_state.get("marking_push_history_id"):
        hid = st.session_state["marking_push_history_id"]
        _render_push_history(api, hid)
        if st.button("⬅️ 返回列表", key="marking_push_history_back"):
            st.session_state.pop("marking_push_history_id", None)
            st.rerun()


def _flatten_groups(groups, depth=0, out=None):
    """把分组树拍平用于下拉框"""
    if out is None:
        out = []
    for g in groups or []:
        if not isinstance(g, dict):
            continue
        gid = g.get("groupId")
        gname = g.get("groupName")
        count = g.get("count", "")
        label = f"{'　' * depth}{gname}" + (f"（{count}）" if count else "")
        out.append({"groupId": gid, "groupName": label})
        _flatten_groups(g.get("groups") or g.get("children"), depth + 1, out)
    return out


def _render_tasks(api):
    """打标任务列表"""
    st.subheader("🏷️ 打标任务")

    # 分组侧栏
    groups = api.list_groups()
    flat = _flatten_groups(groups)

    c1, c2, c3 = st.columns([3, 3, 1])
    with c1:
        group_opts = [("", "全部")] + [(g["groupId"], g["groupName"]) for g in flat]
        group_labels = {gid: name for gid, name in group_opts}
        cur_group = st.selectbox(
            "任务分组", [gid for gid, _ in group_opts],
            format_func=lambda g: group_labels.get(g, g),
            key="marking_task_group",
        )
    with c2:
        keyword = st.text_input("关键词搜索（任务名称）", key="marking_task_kw")
    with c3:
        st.write("")
        st.write("")
        st.button("🔄 刷新", key="marking_task_refresh", use_container_width=True)

    page = st.session_state.get("marking_task_page", 1)
    page_size = 20

    with st.spinner("查询打标任务中..."):
        result = api.list_tasks(
            group_id=cur_group or "",
            keyword=keyword.strip(),
            page=page,
            page_size=page_size,
        )

    total = result.get("total", 0)
    rows = result.get("list", [])
    st.caption(f"共 **{total}** 个打标任务")

    # 新建任务 / 新建分组
    a1, a2, a3 = st.columns(3)
    with a1:
        if st.button("➕ 新建任务", key="marking_task_new", use_container_width=True):
            st.session_state["marking_task_modal"] = "new"
    with a2:
        if st.button("📁 新建分组", key="marking_group_new", use_container_width=True):
            st.session_state["marking_task_modal"] = "new_group"
    with a3:
        if st.button("🔄 重新加载分组", key="marking_group_reload",
                     use_container_width=True):
            st.session_state.pop("marking_task_modal", None)
            st.rerun()

    # 任务表
    if rows:
        for row in rows:
            if not isinstance(row, dict):
                continue
            tid = row.get("taskId")
            tname = row.get("taskName") or f"任务 {tid}"
            push_status = row.get("pushStatus", "")
            pstatus_cn = ("已提交投放" if push_status and push_status != "NoSubmit"
                          else "未提交投放")
            img_count = row.get("imgCount", row.get("count", "-"))
            creator = row.get("createName", "-")
            update_time = _fmt_time(row.get("updateTime"))

            with st.container(border=True):
                st.markdown(f"**{tname}**　`{tid}`")
                st.caption(
                    f"商品数：{img_count} ｜ 投放状态：**{pstatus_cn}** ｜ "
                    f"创建人：{creator} ｜ 最近修改：{update_time}"
                )
                cols = st.columns(5)
                if cols[0].button("📋 详情", key=f"mt_d_{tid}",
                                  use_container_width=True):
                    st.session_state["marking_task_detail_id"] = tid
                if cols[1].button("📄 复制", key=f"mt_c_{tid}",
                                  use_container_width=True):
                    st.session_state["marking_task_modal"] = ("copy", tid, tname)
                if cols[2].button("✏️ 重命名", key=f"mt_r_{tid}",
                                  use_container_width=True):
                    st.session_state["marking_task_modal"] = ("rename", tid, tname)
                if cols[3].button("🗑️ 删除", key=f"mt_del_{tid}",
                                  use_container_width=True):
                    st.session_state["marking_task_action"] = ("delete", tid, tname)
                if cols[4].button("📦 投放", key=f"mt_push_{tid}",
                                  use_container_width=True):
                    st.session_state["marking_task_modal"] = ("push", tid, tname)

        pages = max(1, -(-total // page_size))
        if pages > 1:
            col_a, col_b, col_c = st.columns([2, 1, 2])
            with col_b:
                new_page = st.number_input(
                    "页码", min_value=1, max_value=pages, value=page,
                    key="marking_task_page_input",
                )
                if new_page != page:
                    st.session_state["marking_task_page"] = int(new_page)
                    st.rerun()
    else:
        st.info("暂无打标任务")

    # ---- 操作确认 ----
    action = st.session_state.get("marking_task_action")
    if action:
        act, tid, tname = action
        if act == "delete":
            st.warning(f"确认要【删除】任务 **{tname}**（{tid}）吗？")
            c1, c2 = st.columns(2)
            with c1:
                if st.button("✅ 确认删除", key="marking_task_del_ok", type="primary",
                             use_container_width=True):
                    try:
                        resp = api.delete_task(tid)
                        if isinstance(resp, dict) and resp.get("status") == 200:
                            st.success("删除成功")
                        else:
                            st.error(f"删除失败：{resp}")
                        st.session_state.pop("marking_task_action", None)
                        st.rerun()
                    except Exception as e:
                        st.error(f"删除异常：{e}")
            with c2:
                if st.button("❌ 取消", key="marking_task_del_no",
                             use_container_width=True):
                    st.session_state.pop("marking_task_action", None)
                    st.rerun()

    # ---- 模态表单 ----
    modal = st.session_state.get("marking_task_modal")
    if modal == "new":
        st.warning("➕ 新建打标任务")
        with st.form("marking_new_task_form"):
            task_name = st.text_input("任务名称 *", key="marking_new_task_name")
            group_id = st.selectbox(
                "所属分组", [("", "不分组")] + [(g["groupId"], g["groupName"]) for g in flat],
                format_func=lambda x: dict([("", "不分组")] + [(g["groupId"], g["groupName"]) for g in flat]).get(x, x),
                key="marking_new_task_group",
            )
            submitted = st.form_submit_button("✅ 创建任务", type="primary")
        if submitted:
            if not task_name.strip():
                st.error("请填写任务名称")
            else:
                try:
                    resp = api.create_task(
                        out_shop_id="", task_name=task_name.strip(),
                        group_id=group_id or "",
                    )
                    if isinstance(resp, dict) and resp.get("status") == 200:
                        data = resp.get("data") or {}
                        st.success(f"创建成功！任务ID：{data.get('taskId', '-')}")
                        st.session_state.pop("marking_task_modal", None)
                        st.rerun()
                    else:
                        st.error(f"创建失败：{resp}")
                except Exception as e:
                    st.error(f"创建异常：{e}")
    elif isinstance(modal, tuple):
        kind, tid, tname = modal
        if kind == "copy":
            st.warning(f"📄 复制任务 **{tname}**")
            with st.form("marking_copy_task_form"):
                new_name = st.text_input(
                    "新任务名称 *", value=f"{tname} 复制",
                    key="marking_copy_task_name",
                )
                submitted = st.form_submit_button("✅ 复制", type="primary")
            if submitted:
                if not new_name.strip():
                    st.error("请填写新任务名称")
                else:
                    try:
                        resp = api.copy_task(tid, new_name.strip())
                        if isinstance(resp, dict) and resp.get("status") == 200:
                            st.success("复制成功")
                            st.session_state.pop("marking_task_modal", None)
                            st.rerun()
                        else:
                            st.error(f"复制失败：{resp}")
                    except Exception as e:
                        st.error(f"复制异常：{e}")
        elif kind == "rename":
            st.warning(f"✏️ 重命名任务 **{tname}**")
            with st.form("marking_rename_task_form"):
                new_name = st.text_input("新名称 *", value=tname,
                                         key="marking_rename_task_name")
                submitted = st.form_submit_button("✅ 保存", type="primary")
            if submitted:
                if not new_name.strip():
                    st.error("请填写新名称")
                else:
                    try:
                        resp = api.rename_task(tid, new_name.strip())
                        if isinstance(resp, dict) and resp.get("status") == 200:
                            st.success("重命名成功")
                            st.session_state.pop("marking_task_modal", None)
                            st.rerun()
                        else:
                            st.error(f"重命名失败：{resp}")
                    except Exception as e:
                        st.error(f"重命名异常：{e}")
        elif kind == "push":
            st.info(f"📦 对任务 **{tname}**（{tid}）设置投放")
            with st.form("marking_task_push_form"):
                push_type = st.radio("投放方式", ["立即投放", "定时投放"],
                                     key="marking_task_push_type", horizontal=True)
                effect_date = ""
                if push_type == "定时投放":
                    effect_date = st.text_input(
                        "生效时间（2025-01-01 12:00:00）",
                        key="marking_task_push_effect",
                    )
                close_date = st.text_input(
                    "结束时间（默认 2050-12-31 23:59:59）",
                    value="2050-12-31 23:59:59",
                    key="marking_task_push_close",
                )
                submitted = st.form_submit_button("🚀 确认投放", type="primary")
            if submitted:
                try:
                    resp = api.re_push(
                        str(tid), effect_date=effect_date.strip(),
                        close_date=close_date.strip(),
                    )
                    if isinstance(resp, dict) and resp.get("status") == 200:
                        st.success("投放设置成功")
                        st.session_state.pop("marking_task_modal", None)
                        st.rerun()
                    else:
                        st.error(f"投放失败：{resp}")
                except Exception as e:
                    st.error(f"投放异常：{e}")
    elif modal == "new_group":
        st.warning("📁 新建分组")
        with st.form("marking_new_group_form"):
            parent_opts = [("", "根目录")] + [(g["groupId"], g["groupName"]) for g in flat]
            parent_id = st.selectbox(
                "所属父级", [p for p, _ in parent_opts],
                format_func=lambda p: dict(parent_opts).get(p, p),
                key="marking_new_group_parent",
            )
            group_name = st.text_input("分组名称 *", key="marking_new_group_name")
            submitted = st.form_submit_button("✅ 创建", type="primary")
        if submitted:
            if not group_name.strip():
                st.error("请填写分组名称")
            else:
                try:
                    resp = api.create_group(group_name.strip(), parent_id=parent_id or "")
                    if isinstance(resp, dict) and resp.get("status") == 200:
                        st.success("分组创建成功")
                        st.session_state.pop("marking_task_modal", None)
                        st.rerun()
                    else:
                        st.error(f"创建失败：{resp}")
                except Exception as e:
                    st.error(f"创建异常：{e}")

    # 任务详情（简单展示）
    detail_id = st.session_state.get("marking_task_detail_id")
    if detail_id:
        st.subheader(f"📋 任务详情（{detail_id}）")
        st.caption("任务详情页涉及画布编辑器，本站暂以列表数据展示；"
                   "详细内容请到宝尊 pim2 原系统查看。")
        if st.button("⬅️ 返回任务列表", key="marking_task_detail_back"):
            st.session_state.pop("marking_task_detail_id", None)
            st.rerun()


def render_ui():
    st.title("🏷️ 宝尊投放打标管理 (NIKE)")
    st.caption(
        "直达 NIKE 官方 outlets 店投放打标管理：投放策略管理 + 打标任务管理。"
        "数据来源为宝尊 design-web 系统，使用公司付费账号（与扩图同账号体系）。"
    )

    # 仅登录用户可用（与扩图一致）
    username = mod_auth.current_user()
    if not username:
        st.warning(
            "🔒 **该功能需要登录后使用**：请在左侧「用户中心」登录或注册"
            "（新用户赠送免费体验次数）。"
        )
        return

    st.info(f"👤 当前用户：**{username}** ｜ 🏪 当前店铺：**{DEFAULT_SHOP['name']}**"
            f"（{DEFAULT_SHOP['code']}），默认 NIKE 官方 outlets 店")

    # 手动 Cookie 高级选项（与扩图一致）
    with st.expander("🔧 高级：手动传入宝尊登录 Cookie（可选）", expanded=False):
        st.caption(
            "一般无需填写。仅当自动登录反复失败时，可登录 pim2.baozun.com 后"
            "从浏览器复制 Cookie 粘贴到此处。"
        )
        manual_cookie = st.text_area(
            "Cookie（key=value; key2=value2）", key="marking_manual_cookie",
            height=80,
        )

    try:
        api = _get_api(manual_cookie.strip() if manual_cookie else "")
    except Exception as e:
        st.error(f"初始化宝尊 API 失败：{e}")
        return

    # 等待人工验证码
    pending = st.session_state.get("marking_otp_pending")
    if pending is not None:
        st.warning(
            "验证码邮件已发送到公司邮箱（自动转发到 QQ）。自动读取超时，"
            "请查看手机/邮箱里的验证码并手动输入："
        )
        code = st.text_input("6 位验证码", key="marking_manual_otp", max_chars=6)
        if st.button("✅ 提交验证码并继续", type="primary", key="marking_otp_submit"):
            code = (code or "").strip()
            if not (len(code) == 6 and code.isdigit()):
                st.error("请输入 6 位数字验证码")
            else:
                try:
                    pending.complete_login_with_otp(code)
                    st.session_state["marking_api_cache"] = pending
                    st.session_state.pop("marking_otp_pending", None)
                    st.rerun()
                except Exception as e:
                    st.error(f"验证码校验失败: {e}")
        return

    if api is None:
        st.error("API 会话初始化失败")
        return

    # 验证登录是否可用
    if not api.token:
        st.error("尚未完成宝尊登录，请稍后重试或检查 Cookie。")
        return

    # ---- 店铺选择器（默认 NIKE 官方 outlets） ----
    cur_shop = api.shop or DEFAULT_SHOP
    st.caption(
        f"当前生效店铺：**{cur_shop.get('name', DEFAULT_SHOP['name'])}**"
        f"（{cur_shop.get('code', DEFAULT_SHOP['code'])}）"
    )
    with st.expander("🏪 切换店铺（默认 NIKE 官方 outlets 店）", expanded=False):
        st.caption("以下为 NIKEOUTLETS 运营域下可见的店铺列表")
        try:
            shop_list = api.fetch_shop_list()
            shop_map = {}
            for s in shop_list:
                key = s.get("code") or ""
                if key:
                    label = f"{s.get('name', key)}（{key}）"
                    shop_map[key] = (label, s)
            cur_code = api.shop.get("code", DEFAULT_SHOP["code"])
            if shop_map:
                chosen = st.selectbox(
                    "选择店铺", list(shop_map.keys()),
                    index=list(shop_map.keys()).index(cur_code)
                    if cur_code in shop_map else 0,
                    format_func=lambda k: shop_map[k][0],
                    key="marking_shop_selector",
                )
                if chosen and chosen != api.shop.get("code"):
                    if st.button("✅ 切换到此店铺", key="marking_shop_switch",
                                 use_container_width=True):
                        api.set_shop(shop_map[chosen][1])
                        st.session_state.pop("marking_push_page", None)
                        st.session_state.pop("marking_task_page", None)
                        st.rerun()
            else:
                st.caption("（未能获取店铺列表，保持默认店铺）")
        except Exception as e:
            st.caption(f"（店铺列表获取失败：{e}）")

    # 主标签页
    tab1, tab2 = st.tabs(["📦 投放管理", "🏷️ 打标任务"])
    with tab1:
        _render_push_page(api)
    with tab2:
        _render_tasks(api)
