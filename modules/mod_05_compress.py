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

# 导出供主程序调用的 UI 渲染入口
def render_ui():
    st.header("🖼️ 智能图片压缩与降维")
    st.markdown("支持 PNG 无损转 JPG 降维、画质自动衰减与极限云端压缩。可上传多张图片或单个包含目录结构的 ZIP 压缩包。")

    target_kb = st.slider("🎯 目标文件大小上限 (KB)", min_value=100, max_value=2000, value=500, step=50)

    upload_mode = st.radio("请选择上传模式：", ["多张图片上传", "ZIP 压缩包上传 (保持目录结构)"], horizontal=True)

    if upload_mode == "多张图片上传":
        files = st.file_uploader("📂 选择一张或多张图片", type=["png", "jpg", "jpeg", "webp"], accept_multiple_files=True)
        
        if files:
            if st.button("🚀 开始极速压缩"):
                logs = []
                compressed_files = []
                total_saved_bytes = 0
                compressed_count = 0

                progress_bar = st.progress(0)
                for idx, file in enumerate(files):
                    img_bytes = file.read()
                    out_bytes, out_name, log_msg = compress_single_image(img_bytes, file.name, target_kb)
                    logs.append(log_msg)
                    compressed_files.append((out_name, out_bytes))
                    
                    saved = len(img_bytes) - len(out_bytes)
                    if saved > 0:
                        total_saved_bytes += saved
                    compressed_count += 1

                    progress_bar.progress((idx + 1) / len(files))

                # 统计数据上报记录至 mod_stats
                try:
                    mod_stats.record_image_compression(count=compressed_count, saved_bytes=total_saved_bytes)
                except Exception as e:
                    print(f"Record image compression error: {e}")

                st.success(f"🎉 压缩完成！共处理 {len(files)} 张图片，提效战绩已实时同步。")

                st.subheader("📝 处理日志监控")
                st.code("\n".join(logs), language="text")

                zip_buf = io.BytesIO()
                with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
                    for name, data in compressed_files:
                        zf.writestr(f"compressed_images/{name}", data)
                zip_buf.seek(0)

                st.download_button(
                    label="📥 一键打包下载所有压缩后的图片 (.zip)",
                    data=zip_buf,
                    file_name="compressed_images.zip",
                    mime="application/zip"
                )

    else:
        zip_file = st.file_uploader("📂 上传包含图片文件夹的 ZIP 压缩包", type=["zip"])
        
        if zip_file is not None:
            if st.button("🚀 解压并深度压缩 ZIP 包内所有图片"):
                logs = []
                out_zip_buf = io.BytesIO()
                total_saved_bytes = 0
                compressed_count = 0

                with zipfile.ZipFile(zip_file, "r") as in_zf, zipfile.ZipFile(out_zip_buf, "w", zipfile.ZIP_DEFLATED) as out_zf:
                    file_list = [f for f in in_zf.namelist() if not f.endswith('/') and not f.startswith('__MACOSX')]
                    progress_bar = st.progress(0)

                    for idx, inner_path in enumerate(file_list):
                        file_data = in_zf.read(inner_path)
                        filename = os.path.basename(inner_path)
                        dirname = os.path.dirname(inner_path)

                        ext = os.path.splitext(filename).lower()
                        if ext in ['.jpg', '.jpeg', '.png', '.webp']:
                            out_bytes, out_name, log_msg = compress_single_image(file_data, filename, target_kb)
                            out_inner_path = os.path.join("compressed_images", dirname, out_name) if dirname else os.path.join("compressed_images", out_name)
                            out_zf.writestr(out_inner_path, out_bytes)
                            logs.append(log_msg)

                            saved = len(file_data) - len(out_bytes)
                            if saved > 0:
                                total_saved_bytes += saved
                            compressed_count += 1
                        else:
                            out_inner_path = os.path.join("compressed_images", inner_path)
                            out_zf.writestr(out_inner_path, file_data)
                            logs.append(f"⏩ [原样复制非图片] {filename}")

                        progress_bar.progress((idx + 1) / len(file_list))

                # 统计数据上报记录至 mod_stats
                try:
                    mod_stats.record_image_compression(count=compressed_count, saved_bytes=total_saved_bytes)
                except Exception as e:
                    print(f"Record zip compression error: {e}")

                out_zip_buf.seek(0)
                st.success("🎉 ZIP 压缩包处理完成！已保持原嵌套目录结构，提效战绩已实时同步。")

                st.subheader("📝 处理日志监控")
                st.code("\n".join(logs), language="text")

                st.download_button(
                    label="📥 一键下载精压缩后的 ZIP 压缩包",
                    data=out_zip_buf,
                    file_name="compressed_folder.zip",
                    mime="application/zip"
                )
