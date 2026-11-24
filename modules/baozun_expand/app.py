"""智能扩图页面：选比例和原图位置 → 预览 → 生成。

任务状态存在 session_state 里：提交成功后立刻记下宝尊的任务编号，
页面中途被打断（用户点了别的控件）也只会继续查结果，不会重复提交扣费。
"""
import io

import streamlit as st
from PIL import Image, ImageOps

from .baozun_api import BaozunExpandAPI, LoginRequired

RATIOS = {"原比例": None, "1:1": (1, 1), "3:4": (3, 4), "4:3": (4, 3), "9:16": (9, 16), "16:9": (16, 9), "自定义": "custom"}
ANCHORS = ["居中", "靠上", "靠下", "靠左", "靠右"]


# ---------------------------------------------------------------------------
# 纯函数（可单独测试）
# ---------------------------------------------------------------------------
LARGE_UPLOAD = 2 * 1024 * 1024  # 超过 2MB 的不透明图片转成 JPEG 再上传


def prepare_image(data: bytes, filename: str):
  """准备上传的图片，返回 (字节, 文件名, 宽, 高)：
  - 按 EXIF 方向转正（手机竖拍照片）；
  - 超过 2MB 且没有透明背景的图片转成高质量 JPEG（分辨率不变），
    海外服务器传到宝尊更快、不易超时。
  其余情况原样上传。"""
  img = Image.open(io.BytesIO(data))
  rotated = img.getexif().get(0x0112, 1) not in (1, None)
  if not rotated and len(data) <= LARGE_UPLOAD:
    return data, filename, img.width, img.height
  if rotated:
    img = ImageOps.exif_transpose(img)
  has_alpha = img.mode in ("RGBA", "LA", "PA") or (img.mode == "P" and "transparency" in img.info)
  if has_alpha and not rotated:
    return data, filename, img.width, img.height  # 透明图保持原样
  buf = io.BytesIO()
  if has_alpha:
    img.save(buf, format="PNG")
    ext = ".png"
  else:
    img.convert("RGB").save(buf, format="JPEG", quality=92)
    ext = ".jpg"
  out = buf.getvalue()
  if not rotated and len(out) >= len(data):
    return data, filename, img.width, img.height
  return out, filename.rsplit(".", 1)[0] + ext, img.width, img.height


def compute_canvas(ow, oh, ratio=None, pad=0.4, anchor="居中", custom=None):
  """根据目标比例 / 扩展幅度 / 原图位置算出画布和四边距。
  返回 dict: bg_w, bg_h, top_d, bottom_d, left_d, right_d"""
  if custom:
    W, H = max(int(custom[0]), ow), max(int(custom[1]), oh)
  else:
    s = 1 + pad
    if ratio:
      r = ratio[0] / ratio[1]
      W = max(ow * s, oh * s * r)
      H = W / r
    else:
      W, H = ow * s, oh * s
    W, H = max(round(W), ow), max(round(H), oh)
  ew, eh = W - ow, H - oh
  left, top = ew // 2, eh // 2
  if anchor == "靠上":
    top = 0
  elif anchor == "靠下":
    top = eh
  elif anchor == "靠左":
    left = 0
  elif anchor == "靠右":
    left = ew
  return {"bg_w": W, "bg_h": H, "top_d": top, "bottom_d": eh - top, "left_d": left, "right_d": ew - left}


def layout_preview(img: Image.Image, c: dict, size: int = 640) -> Image.Image:
  """画出原图在新画布里的位置（灰色部分由 AI 生成）"""
  k = size / max(c["bg_w"], c["bg_h"])
  canvas = Image.new("RGB", (max(1, round(c["bg_w"] * k)), max(1, round(c["bg_h"] * k))), (228, 228, 231))
  thumb = img.convert("RGB").resize((max(1, round(img.width * k)), max(1, round(img.height * k))))
  canvas.paste(thumb, (round(c["left_d"] * k), round(c["top_d"] * k)))
  return canvas


# ---------------------------------------------------------------------------
# 共享登录：所有用户共用一个宝尊会话，同一时间只会有一个登录流程
# ---------------------------------------------------------------------------
@st.cache_resource
def get_api() -> BaozunExpandAPI:
  return BaozunExpandAPI()


def _run_job(job, status):
  """执行（或继续）任务：上传 → 提交 → 等结果。任务编号一拿到就写回 job。"""
  api = get_api()
  if not job.get("record"):
    status.write("上传图片...")
    attachment = api.upload_image(job["file"], job["filename"])
    status.write("提交扩图任务...")
    p = job["params"]
    job["record"] = api.submit_image_expand(
        original_attachment_code=attachment,
        top_distance=p["top_d"], bottom_distance=p["bottom_d"],
        left_distance=p["left_d"], right_distance=p["right_d"],
        background_weight=p["bg_w"], background_height=p["bg_h"],
        original_weight=p["orig_w"], original_height=p["orig_h"],
        generated_num=p["generated_num"],
    )
  status.write("AI 生成中，通常需要 1 分钟左右...")
  waited = st.empty()
  urls = api.get_image_expand_result(
      job["record"], expected_count=job["params"]["generated_num"],
      on_tick=lambda s: waited.caption(f"已等待 {s} 秒"),
  )
  waited.empty()
  return urls


def render_ui():
  st.title("智能扩图", anchor=False)
  state = st.session_state
  job = state.get("exp_job")

  col_left, col_right = st.columns(2)
  with col_right:
    ratio_name = st.segmented_control("目标比例", list(RATIOS), default="原比例", key="exp_ratio")
    ratio = RATIOS.get(ratio_name or "原比例")
    custom = None
    if ratio == "custom":
      c1, c2 = st.columns(2)
      custom = (c1.number_input("画布宽度", min_value=1, value=1200, step=50),
                c2.number_input("画布高度", min_value=1, value=1200, step=50))
      pad = 0.0
    else:
      pad = st.slider("扩展幅度", min_value=10, max_value=100, value=40, step=5, format="%d%%") / 100
    anchor = st.segmented_control("原图位置", ANCHORS, default="居中", key="exp_anchor") or "居中"
    gen_num = st.slider("生成数量", min_value=1, max_value=4, value=1)

  with col_left:
    uploaded = st.file_uploader(
        "图片", type=["jpg", "jpeg", "png", "webp"], label_visibility="collapsed"
    )
    canvas = image = None
    if uploaded:
      data, filename, ow, oh = prepare_image(uploaded.getvalue(), uploaded.name)
      image = Image.open(io.BytesIO(data))
      canvas = compute_canvas(ow, oh, None if ratio == "custom" else ratio, pad, anchor, custom)
      # 竖图预览限制高度约 480px，避免撑出屏幕
      tall = canvas["bg_h"] > canvas["bg_w"]
      st.image(layout_preview(image, canvas),
               width=round(480 * canvas["bg_w"] / canvas["bg_h"]) if tall else "stretch",
               caption=f"{ow} × {oh} → {canvas['bg_w']} × {canvas['bg_h']}")

  no_expand = canvas and canvas["bg_w"] == image.width and canvas["bg_h"] == image.height
  with col_right:
    start = st.button("生成", type="primary", width="stretch",
                      disabled=not uploaded or bool(job) or bool(no_expand))

  if start:
    job = {
        "file": data, "filename": filename, "record": None,
        "params": {**canvas, "orig_w": ow, "orig_h": oh, "generated_num": int(gen_num)},
    }
    state["exp_job"] = job
    state.pop("exp_results", None)

  # ---- 执行 / 继续任务 ----
  if job:
    status = st.status("正在处理扩图任务...", expanded=True)
    try:
      urls = _run_job(job, status)
      state["exp_results"] = urls
      state.pop("exp_job", None)
      status.update(label="扩图完成", state="complete", expanded=False)
    except LoginRequired:
      status.update(label="需要邮箱验证码才能登录宝尊", state="running")
    except Exception as e:
      state.pop("exp_job", None)
      status.update(label=f"扩图失败：{e}", state="error")

  # ---- 人工验证码（自动读取邮箱超时时）----
  api = get_api()
  if api.pending:
    code = st.text_input("邮箱验证码", max_chars=6, key="exp_otp")
    if st.button("继续", type="primary", key="exp_otp_submit"):
      code = (code or "").strip()
      if not (len(code) == 6 and code.isdigit()):
        st.error("请输入 6 位数字验证码")
      else:
        try:
          api.complete_login_with_otp(code)
          st.rerun()
        except Exception as e:
          api.pending = None
          state.pop("exp_job", None)
          st.error(f"验证码校验失败：{e}（重新点击生成会发送新的验证码）")

  # ---- 结果：一直保留到下一次生成 ----
  urls = state.get("exp_results")
  if urls:
    for col, url in zip(st.columns(len(urls)), urls):
      col.image(url, width="stretch")
      col.link_button("下载", url, width="stretch")
