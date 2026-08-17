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
  """复用已登录的 API 会话，避免每次点击都重新登录并发验证码邮件"""
  cached = st.session_state.get("baozun_api_cache")
  if (
      cached
      and cached.get("cookie") == (manual_cookie or "")
      and cached.get("is_manual") == bool(manual_cookie)
      and _time.time() - cached.get("ts", 0) < _SESSION_TTL
  ):
    return cached["api"]
  api = BaozunExpandAPI(manual_cookie=manual_cookie)
  st.session_state["baozun_api_cache"] = {
      "api": api,
      "cookie": manual_cookie or "",
      "is_manual": bool(manual_cookie),
      "ts": _time.time(),
  }
  return api


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

  if start_btn and uploaded_file:
    status_box = st.status("正在处理扩图任务...", expanded=True)
    try:
      cookie_to_use = st.session_state.get("baozun_cookie", "")
      if cookie_to_use:
        status_box.write("🔑 正在使用手动传入的 Cookie 凭证进行鉴权...")
      else:
        status_box.write("🔑 正在自动校验/获取后台宝尊账号鉴权...")

      api = _get_api(cookie_to_use)

      status_box.write("正在上传图片到宝尊服务器...")
      attachment_code = api.upload_image(
          uploaded_file.getvalue(), uploaded_file.name
      )

      status_box.write(
          f"正在提交智能扩图任务 (目标画布: {bg_w}x{bg_h}, 原图: {orig_w}x{orig_h})..."
      )
      record_code = api.submit_image_expand(
          original_attachment_code=attachment_code,
          top_distance=top_d,
          bottom_distance=bottom_d,
          left_distance=left_d,
          right_distance=right_d,
          background_weight=bg_w,
          background_height=bg_h,
          original_weight=orig_w,
          original_height=orig_h,
          generated_num=gen_num,
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
