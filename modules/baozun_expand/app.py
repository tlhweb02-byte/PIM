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
        record_code,
        poll_interval=3,
        timeout=180,
        expected_count=p["gen_num"],
    )

    status_box.update(
        label="🎉 扩图生成完成！", state="complete", expanded=False
    )

    for col, url in zip(st.columns(len(result_urls)), result_urls):
      col.image(url, use_container_width=True)
      col.link_button("下载", url, use_container_width=True)
  except Exception as e:
    status_box.update(label=f"❌ 扩图失败: {str(e)}", state="error")


def render_ui():
  st.title("智能扩图", anchor=False)

  col_left, col_right = st.columns(2)

  with col_left:
    # 大小上限由 .streamlit/config.toml 的 maxUploadSize 统一限制
    uploaded_file = st.file_uploader(
        "图片", type=["jpg", "jpeg", "png", "webp"], label_visibility="collapsed"
    )
    orig_w, orig_h = 800, 800
    if uploaded_file:
      image = Image.open(uploaded_file)
      orig_w, orig_h = image.size
      st.image(image, caption=f"{orig_w} × {orig_h}", use_container_width=True)

  with col_right:
    m1, m2, m3, m4 = st.columns(4)
    top_d = m1.number_input("上边距", value=140, step=10)
    bottom_d = m2.number_input("下边距", value=140, step=10)
    left_d = m3.number_input("左边距", value=205, step=10)
    right_d = m4.number_input("右边距", value=205, step=10)

    # 画布默认 = 原图 + 边距，可手动覆盖
    c1, c2 = st.columns(2)
    bg_w = c1.number_input(
        "画布宽度",
        value=orig_w + left_d + right_d if uploaded_file else 800,
        min_value=orig_w,
        step=50,
    )
    bg_h = c2.number_input(
        "画布高度",
        value=orig_h + top_d + bottom_d if uploaded_file else 800,
        min_value=orig_h,
        step=50,
    )
    gen_num = st.slider("生成数量", min_value=1, max_value=4, value=1)
    start_btn = st.button(
        "生成", type="primary", disabled=not uploaded_file, use_container_width=True
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
    api = None
    failed = False
    try:
      api = _get_api(task["cookie"])
    except Exception as e:
      status_box.update(label=f"❌ 扩图失败: {str(e)}", state="error")
      st.session_state.pop("baozun_task", None)
      failed = True
    if not failed:
      if api is None:
        # 等待人工输入验证码（界面下方会显示输入框）
        status_box.update(
            label="请输入邮箱验证码",
            state="running",
        )
      else:
        _run_expand_task(status_box, task, api)
        del st.session_state["baozun_task"]

  # ============ 手动验证码输入 ============
  pending_api = st.session_state.get("baozun_otp_pending_api")
  if pending_api is not None:
    code = st.text_input("邮箱验证码", key="baozun_manual_otp", max_chars=6)
    if st.button("继续", type="primary", key="baozun_otp_submit"):
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
