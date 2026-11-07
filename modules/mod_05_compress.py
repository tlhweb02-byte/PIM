import streamlit as st
import io
import os
import zipfile
from PIL import Image
from modules import mod_stats

try:
    import tinify
    TINIFY_AVAILABLE = True
except ImportError:
    TINIFY_AVAILABLE = False

LOCAL_API_KEYS = [
    "XDzl5YfGBk3HF7PJFlQw9HgzWTFlpH7D",
    "qdD7H1674MLP2MqX7ZDrs1wkXlT8LQBY",
    "t24GDhLWHQHHBG2XNqlH371NbzTR3w7F"
]

def has_actual_transparency(img):
    try:
        if img.mode in ('RGBA', 'LA', 'PA'):
            return img.getchannel('A').getextrema()[0] < 255
        elif img.mode == 'P' and 'transparency' in img.info:
            return True
        return False
    except Exception:
        return False

def compress_single_image(img_bytes, filename, target_kb):
    target_bytes = target_kb * 1024
    orig_size_kb = len(img_bytes) / 1024
    
    if orig_size_kb <= target_kb:
        return img_bytes, filename, f"⏩ [无需压缩] {filename} ({orig_size_kb:.1f}KB已达标)"

    out_name = filename

    try:
        with Image.open(io.BytesIO(img_bytes)) as img:
            fmt = img.format or 'JPEG'
            png_converted = False

            if fmt == 'PNG' and not has_actual_transparency(img):
                img = img.convert('RGB')
                fmt = 'JPEG'
                out_name = os.path.splitext(filename)[0] + '.jpg'
                png_converted = True

            best_bytes = None
            min_size = float('inf')

            if fmt in ['JPEG', 'WEBP']:
                for q in range(95, 40, -5):
                    with io.BytesIO() as buf:
                        img.save(buf, format=fmt, quality=q, optimize=True)
                        b_val = buf.getvalue()
                        b_len = len(b_val)
                        if b_len < min_size:
                            min_size = b_len
                            best_bytes = b_val

                        if b_len <= target_bytes:
                            msg = f"✅ [本地压缩] {filename} -> {out_name} ({orig_size_kb:.1f}KB -> {b_len/1024:.1f}KB, Quality={q})"
                            if png_converted:
                                msg += " (无透明底，强转JPG)"
                            return b_val, out_name, msg

            if TINIFY_AVAILABLE:
                for key in LOCAL_API_KEYS:
                    try:
                        tinify.key = key
                        with io.BytesIO() as buf:
                            img.save(buf, format=fmt, quality=95 if fmt == 'JPEG' else None, optimize=True)
                            source_bytes = buf.getvalue()
                        
                        compressed_data = tinify.from_buffer(source_bytes).to_buffer()
                        c_len = len(compressed_data)
                        msg = f"☁️ [云端深度极限] {filename} -> {out_name} ({orig_size_kb:.1f}KB -> {c_len/1024:.1f}KB)"
                        if png_converted:
                            msg += " (无透明底，强转JPG)"
                        return compressed_data, out_name, msg
                    except Exception:
                        continue

            if best_bytes is not None:
                msg = f"⚠️ [尽力压缩] {filename} -> {out_name} ({orig_size_kb:.1f}KB -> {len(best_bytes)/1024:.1f}KB)"
                return best_bytes, out_name, msg

    except Exception as e:
        return img_bytes, filename, f"❌ [处理失败] {filename}: {e}"

    return img_bytes, filename, f"⏩ [原样输出] {filename}"

IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp")
OUT_DIR = "compressed_images"


def compress_files(files, target_kb):
    """压缩上传的图片和 ZIP（ZIP 内保留目录结构），全部打包成一个 ZIP。

    files: [(文件名, 字节)]；返回 (zip 字节, 日志列表, 处理图片数, 节省字节数)
    """
    logs, count, saved = [], 0, 0
    out_buf = io.BytesIO()

    with zipfile.ZipFile(out_buf, "w", zipfile.ZIP_DEFLATED) as out_zf:
        def add_image(data, inner_dir, filename):
            nonlocal count, saved
            out_bytes, out_name, msg = compress_single_image(data, filename, target_kb)
            out_zf.writestr(os.path.join(OUT_DIR, inner_dir, out_name), out_bytes)
            logs.append(msg)
            count += 1
            saved += max(len(data) - len(out_bytes), 0)

        for name, data in files:
            if not name.lower().endswith(".zip"):
                add_image(data, "", name)
                continue
            with zipfile.ZipFile(io.BytesIO(data)) as in_zf:
                for inner in in_zf.namelist():
                    if inner.endswith("/") or inner.startswith("__MACOSX"):
                        continue
                    inner_data = in_zf.read(inner)
                    inner_dir, filename = os.path.split(inner)
                    if filename.lower().endswith(IMAGE_EXTS):
                        add_image(inner_data, inner_dir, filename)
                    else:
                        out_zf.writestr(os.path.join(OUT_DIR, inner), inner_data)
                        logs.append(f"⏩ [原样复制非图片] {filename}")

    return out_buf.getvalue(), logs, count, saved


def render_ui():
    st.title("图片压缩", anchor=False)

    files = st.file_uploader(
        "图片或 ZIP",
        type=["png", "jpg", "jpeg", "webp", "zip"],
        accept_multiple_files=True,
        label_visibility="collapsed",
    )
    target_kb = st.slider("目标大小 (KB)", min_value=100, max_value=2000, value=500, step=50)

    if not files or not st.button("压缩", type="primary"):
        return

    with st.spinner("压缩中..."):
        zip_bytes, logs, count, saved = compress_files(
            [(f.name, f.getvalue()) for f in files], target_kb
        )
    try:
        mod_stats.record_image_compression(count=count, saved_bytes=saved)
    except Exception as e:
        print(f"Record image compression error: {e}")

    st.download_button(
        f"下载 {count} 张图片 (.zip)",
        data=zip_bytes,
        file_name="compressed_images.zip",
        mime="application/zip",
        type="primary",
        on_click="ignore",
    )
    with st.expander("处理日志"):
        st.code("\n".join(logs), language="text")
