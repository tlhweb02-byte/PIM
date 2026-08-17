from PIL import Image
import time as _time
import streamlit as st

try:
  from .baozun_api import BaozunExpandAPI
except ImportError:
  try:
    from modules.baozun_expand.baozun_api import BaozunExpandAPI
  except ImportError:
    from baozun_api import BaozunExpandAPI

try:
  from .account_api import BaozunAccountAPI
except ImportError:
  try:
    from modules.baozun_expand.account_api import BaozunAccountAPI
  except ImportError:
    from account_api import BaozunAccountAPI

# 自动登录会话复用时长（秒）：期间内不重复登录、不重复发送验证码邮件
_SESSION_TTL = 2 * 3600


def _get_api(manual_cookie: str):
  """复用已登录的 API 会话；返回 None 表示正在等待人工输入验证码"""
  # 已有待人工验证码的登录 → 直接返回 None（避免重复登录、重复发邮件）
  if st.session_state.get("baozun_otp_pending_api") is not None:
    return None
  cached = st.session_state.get("baozun_api_cache")
  if (
      cached
      and cached.get("cookie") == (manual_cookie or "")
      and cached.get("is_manual") == bool(manual_cookie)
      and _time.time() - cached.get("ts", 0) < _SESSION_TTL
  ):
    return cached["api"]
  api = BaozunExpandAPI(manual_cookie=manual_cookie)
  if getattr(api, "login_pending", False):
    # 验证码已发送但自动读取超时，进入人工输入流程
    st.session_state["baozun_otp_pending_api"] = api
    return None
  st.session_state["baozun_api_cache"] = {
      "api": api,
      "cookie": manual_cookie or "",
      "is_manual": bool(manual_cookie),
      "ts": _time.time(),
  }
  return api


def _run_expand_task(status_box, task, api):
  """执行上传 → 提交扩图 → 轮询结果"""
  file_bytes = task["file"]
  filename = task["filename"]
  p = task["params"]
  try:
    if task["cookie"]:
      status_box.write("🔑 正在使用手动传入的 Cookie 凭证进行鉴权...")
    else:
      status_box.write("🔑 正在自动校验/获取后台宝尊账号鉴权...")

    status_box.write("正在上传图片到宝尊服务器...")
    attachment_code = api.upload_image(file_bytes, filename)

    status_box.write(
        f"正在提交智能扩图任务 (目标画布: {p['bg_w']}x{p['bg_h']}, "
        f"原图: {p['orig_w']}x{p['orig_h']})..."
    )
    record_code = api.submit_image_expand(
        original_attachment_code=attachment_code,
        top_distance=p["top_d"],
        bottom_distance=p["bottom_d"],
        left_distance=p["left_d"],
        right_distance=p["right_d"],
        background_weight=p["bg_w"],
        background_height=p["bg_h"],
        original_weight=p["orig_w"],
        original_height=p["orig_h"],
        generated_num=p["gen_num"],
    )

    status_box.write("AI 正在渲染生成图片（正在实时查询进度，预估 1~2 分钟）...")
    result_urls = api.get_image_expand_result(
        record_code, poll_interval=3, timeout=180
    )

    status_box.update(
        label="🎉 扩图生成完成！", state="complete", expanded=False
    )

    st.subheader("3. 生成结果")
    grid_cols = st.columns(len(result_urls))
    for idx, url in enumerate(result_urls):
      with grid_cols[idx]:
        st.image(url, caption=f"方案 {idx + 1}", use_container_width=True)
        st.markdown(
            f"[点击下载图片]({url})", unsafe_allow_html=True
        )
  except Exception as e:
    status_box.update(label=f"❌ 扩图失败: {str(e)}", state="error")


def render_ui():
  st.title("🎨 宝尊智能扩图 (ROSS)")
  st.caption("全自动智能扩图中台，自动维护鉴权并调用宝尊 ROSS 引擎扩展背景。")

  # 手动 Cookie 备用通道
  with st.expander(
      "🔑 宝尊账号鉴权配置 (手动 Cookie 备用通道)", expanded=False
  ):
    st.markdown("""
        **当邮件自动化发信延迟时，可在此粘贴宝尊 Cookie 作为备用通道：**
        * **1 秒极速提取 Cookie 方法**：在已登录的 ROSS 网页按 `F12`，切换到 **Console（控制台）** 粘贴下方代码回车，Cookie 就会自动复制到剪贴板！
        ```javascript
        copy(document.cookie); alert("Cookie 已复制到剪贴板！");
        ```
        """)
    manual_cookie = st.text_area(
        "请粘贴 Cookie 字符串：",
        value=st.session_state.get("baozun_cookie", ""),
        placeholder="例如: SESSION=xxxx; UAAC=xxxx; ...",
        help="为空时会自动使用后台账号邮件自动化登录",
    )
    if manual_cookie:
      st.session_state["baozun_cookie"] = manual_cookie.strip()

  # 邮箱读取诊断
  with st.expander("🔍 诊断：测试 QQ 邮箱验证码读取", expanded=False):
    if st.button("运行邮箱读取诊断", key="baozun_diag_btn"):
      mgr = BaozunAccountAPI()
      with st.spinner("正在连接 QQ 邮箱并读取最近邮件..."):
        report = mgr.diagnose_mailbox()
      if not report["ok"]:
        st.error(f"IMAP 连接失败: {report['error']}")
      else:
        st.success("IMAP 连接成功")
        st.write(
            "**邮箱文件夹**: ",
            ", ".join(report["folders"]) if report["folders"] else "无",
        )
        st.write("**收件箱最近邮件**:")
        if report["emails"]:
          for e in report["emails"]:
            codes = "、".join(e["codes"]) if e["codes"] else "—"
            st.write(
                f"- [{e['age']}] {e['subject']} | 发件人: {e['sender']} "
                f"| 6位数字: {codes}"
            )
        else:
          st.write("(收件箱为空)")

  col_left, col_right = st.columns(2)

  with col_left:
    st.subheader("1. 上传图片")
    uploaded_file = st.file_uploader(
        "选择图片", type=["jpg", "jpeg", "png", "webp"]
    )

    orig_w, orig_h = 800, 800
    if uploaded_file:
      image = Image.open(uploaded_file)
      orig_w, orig_h = image.size
      st.image(
          image,
          caption=f"原图预览 ({orig_w}x{orig_h})",
          use_container_width=True,
      )

  with col_right:
    st.subheader("2. 扩图参数设置")

    st.write("**扩展边距增加距离 (px)**")
    m_col1, m_col2 = st.columns(2)
    with m_col1:
      top_d = st.number_input("上边距 (topDistance)", value=140, step=10)
      left_d = st.number_input("左边距 (leftDistance)", value=205, step=10)
    with m_col2:
      bottom_d = st.number_input("下边距 (bottomDistance)", value=140, step=10)
      right_d = st.number_input("右边距 (rightDistance)", value=205, step=10)

    calc_bg_w = orig_w + left_d + right_d if uploaded_file else 800
    calc_bg_h = orig_h + top_d + bottom_d if uploaded_file else 800

    bg_w = st.number_input(
        "目标画布总宽度 (px)",
        value=calc_bg_w,
        min_value=orig_w,
        step=50,
        help="自动计算：原图宽度 + 左边距 + 右边距",
    )
    bg_h = st.number_input(
        "目标画布总高度 (px)",
        value=calc_bg_h,
        min_value=orig_h,
        step=50,
        help="自动计算：原图高度 + 上边距 + 下边距",
    )

    gen_num = st.slider("生成图片数量", min_value=1, max_value=4, value=1)

    start_btn = st.button(
        "✨ 立即生成", type="primary", disabled=(not uploaded_file)
    )

  # ============ 任务状态机 ============
  # 点击"立即生成"→ 记录任务 → rerun → 执行（可能等待人工验证码）
  if start_btn and uploaded_file:
    st.session_state["baozun_task"] = {
        "cookie": st.session_state.get("baozun_cookie", ""),
        "file": uploaded_file.getvalue(),
        "filename": uploaded_file.name,
        "params": {
            "bg_w": int(bg_w),
            "bg_h": int(bg_h),
            "orig_w": orig_w,
            "orig_h": orig_h,
            "top_d": int(top_d),
            "bottom_d": int(bottom_d),
            "left_d": int(left_d),
            "right_d": int(right_d),
            "gen_num": int(gen_num),
        },
    }
    st.session_state.pop("baozun_otp_pending_api", None)
    st.rerun()

  task = st.session_state.get("baozun_task")
  if task:
    status_box = st.status("正在处理扩图任务...", expanded=True)
    api = _get_api(task["cookie"])
    if api is None:
      # 等待人工输入验证码（界面下方会显示输入框）
      status_box.update(
          label="📩 验证码已发送到邮箱，自动读取超时，请在下方手动输入",
          state="running",
      )
    else:
      _run_expand_task(status_box, task, api)
      del st.session_state["baozun_task"]

  # ============ 手动验证码输入 ============
  pending_api = st.session_state.get("baozun_otp_pending_api")
  if pending_api is not None:
    st.warning(
        "验证码邮件已发送到公司邮箱（自动转发到 QQ）。自动读取超时，"
        "请查看手机/邮箱里的验证码并手动输入："
    )
    code = st.text_input("6 位验证码", key="baozun_manual_otp", max_chars=6)
    if st.button("✅ 提交验证码并继续", type="primary", key="baozun_otp_submit"):
      code = (code or "").strip()
      if not (len(code) == 6 and code.isdigit()):
        st.error("请输入 6 位数字验证码")
      else:
        try:
          pending_api.complete_login_with_otp(code)
          # 登录完成，写入会话缓存，稍后 rerun 时直接复用
          st.session_state["baozun_api_cache"] = {
              "api": pending_api,
              "cookie": (task or {}).get("cookie", ""),
              "is_manual": bool((task or {}).get("cookie", "")),
              "ts": _time.time(),
          }
          st.session_state.pop("baozun_otp_pending_api", None)
          st.rerun()
        except Exception as e:
          st.error(f"验证码校验失败: {e}")
