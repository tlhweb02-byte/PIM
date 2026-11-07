import os
import json
import base64
import datetime
import streamlit as st

try:
    import gspread
    from google.oauth2.service_account import Credentials
    GSPREAD_AVAILABLE = True
except ImportError:
    GSPREAD_AVAILABLE = False

STATS_FILE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stats_data.json")
SPREADSHEET_NAME = "提效中台数据统计"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

def _safe_int(val):
    try:
        return int(val)
    except (ValueError, TypeError):
        return 0

@st.cache_resource
def get_gspread_client():
    if not GSPREAD_AVAILABLE:
        return None, "缺失 gspread 或 google-auth 依赖库，请检查 requirements.txt"
    try:
        b64_val = None
        if "gcp_service_account_base64" in st.secrets:
            b64_val = str(st.secrets["gcp_service_account_base64"]).strip()
        elif "gcp_service_account" in st.secrets and isinstance(st.secrets["gcp_service_account"], dict) and "gcp_service_account_base64" in st.secrets["gcp_service_account"]:
            b64_val = str(st.secrets["gcp_service_account"]["gcp_service_account_base64"]).strip()
        elif "gcp_service_account" in st.secrets and isinstance(st.secrets["gcp_service_account"], str):
            b64_val = str(st.secrets["gcp_service_account"]).strip()

        if b64_val and len(b64_val) > 100 and not b64_val.startswith("{"):
            decoded_json = base64.b64decode(b64_val).decode("utf-8")
            sec_dict = json.loads(decoded_json)
            creds = Credentials.from_service_account_info(sec_dict, scopes=SCOPES)
            return gspread.authorize(creds), None

        if "gcp_service_account" in st.secrets:
            raw_sec = st.secrets["gcp_service_account"]
            if isinstance(raw_sec, str):
                sec_dict = json.loads(raw_sec)
            else:
                sec_dict = dict(raw_sec)

            if "private_key" in sec_dict and isinstance(sec_dict["private_key"], str):
                pk = sec_dict["private_key"]
                pk = pk.replace("\\n", "\n").strip('"').strip("'")
                if "-----BEGIN PRIVATE KEY-----" in pk and "-----END PRIVATE KEY-----" in pk:
                    lines = [line.strip() for line in pk.split("\n") if line.strip()]
                    pk = "\n".join(lines) + "\n"
                sec_dict["private_key"] = pk

            creds = Credentials.from_service_account_info(sec_dict, scopes=SCOPES)
            return gspread.authorize(creds), None

        return None, "未在 Streamlit Secrets 中找到凭据配置"
    except Exception as e:
        return None, f"Secrets 解析失败: {e}"

def _get_worksheet():
    client, err = get_gspread_client()
    if client:
        try:
            try:
                sh = client.open(SPREADSHEET_NAME)
            except gspread.exceptions.SpreadsheetNotFound:
                return None, f"未找到名为 {SPREADSHEET_NAME} 的 Google 表格，或未共享权限"
            ws = sh.sheet1
            return ws, None
        except Exception as e:
            return None, f"访问表格发生错误: {e}"
    return None, err

@st.cache_data(ttl=30)
def _load_all_records():
    ws, err = _get_worksheet()
    if ws:
        try:
            records = ws.get_all_records()
            stats_dict = {}
            for r in records:
                d = str(r.get("date", "")).strip()
                if d and d.lower() != "date":
                    stats_dict[d] = {
                        "compressed_images": _safe_int(r.get("compressed_images", 0)),
                        "saved_bytes": _safe_int(r.get("saved_bytes", 0)),
                        "excel_cleaned": _safe_int(r.get("excel_cleaned", 0)),
                        "last_updated": str(r.get("last_updated", ""))
                    }
            return stats_dict, None
        except Exception as e:
            return {}, f"读取 Sheet 数据解析失败: {e}"

    if os.path.exists(STATS_FILE_PATH):
        try:
            with open(STATS_FILE_PATH, "r", encoding="utf-8") as f:
                return json.load(f), f"（本地暂存模式: {err}）"
        except Exception:
            return {}, f"（本地暂存模式: {err}）"
    return {}, f"（未连通云端数据库: {err}）"

def _save_stats(data):
    today = get_today_key()
    today_data = data.get(today, {})
    ws, err = _get_worksheet()

    if ws:
        try:
            row_data = [
                today,
                int(today_data.get("compressed_images", 0)),
                int(today_data.get("saved_bytes", 0)),
                int(today_data.get("excel_cleaned", 0)),
                str(today_data.get("last_updated", ""))
            ]
            
            try:
                headers = ws.row_values(1)
                if not headers:
                    ws.append_row(["date", "compressed_images", "saved_bytes", "excel_cleaned", "last_updated"])
            except Exception:
                pass

            try:
                cell = ws.find(today, in_column=1)
            except Exception:
                cell = None

            if cell:
                range_label = f"A{cell.row}:E{cell.row}"
                ws.update(range_name=range_label, values=[row_data])
            else:
                ws.append_row(row_data)
            
            try:
                _load_all_records.clear()
            except Exception:
                pass
            return
        except Exception as e:
            print(f"Save to Sheet Error: {e}")

    try:
        with open(STATS_FILE_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Save local stats error: {e}")

def get_today_key():
    return datetime.date.today().isoformat()

def aggregate_stats_by_prefix(prefix=""):
    all_data, err = _load_all_records()
    compressed_images = 0
    saved_bytes = 0
    excel_cleaned = 0

    for d, row in all_data.items():
        if d.startswith(prefix):
            compressed_images += row.get("compressed_images", 0)
            saved_bytes += row.get("saved_bytes", 0)
            excel_cleaned += row.get("excel_cleaned", 0)

    return {
        "compressed_images": compressed_images,
        "saved_bytes": saved_bytes,
        "excel_cleaned": excel_cleaned
    }, err

def record_image_compression(count=1, saved_bytes=0):
    if count <= 0:
        return
    all_data, _ = _load_all_records()
    today = get_today_key()
    if today not in all_data:
        all_data[today] = {
            "compressed_images": 0,
            "saved_bytes": 0,
            "excel_cleaned": 0,
            "last_updated": ""
        }
    all_data[today]["compressed_images"] += count
    all_data[today]["saved_bytes"] += max(0, int(saved_bytes))
    all_data[today]["last_updated"] = datetime.datetime.now().strftime("%H:%M:%S")
    _save_stats(all_data)

def record_excel_cleaning(count=1):
    if count <= 0:
        return
    all_data, _ = _load_all_records()
    today = get_today_key()
    if today not in all_data:
        all_data[today] = {
            "compressed_images": 0,
            "saved_bytes": 0,
            "excel_cleaned": 0,
            "last_updated": ""
        }
    all_data[today]["excel_cleaned"] += count
    all_data[today]["last_updated"] = datetime.datetime.now().strftime("%H:%M:%S")
    _save_stats(all_data)

def calculate_hours_saved(excel_cleaned, compressed_images):
    hours = (excel_cleaned * 0.5) + (compressed_images * 0.05)
    return round(hours, 2)

def format_bytes_to_gb(saved_bytes):
    gb = saved_bytes / (1024 ** 3)
    if gb >= 0.01:
        return f"{gb:.2f} GB"
    else:
        mb = saved_bytes / (1024 ** 2)
        if mb >= 0.1:
            return f"{mb:.1f} MB ({gb:.3f} GB)"
        else:
            return f"{gb:.3f} GB"

def render_ui():
    st.title("数据统计", anchor=False)

    all_data, err = _load_all_records()
    if err:
        st.warning(f"云端数据库未连接：{err}")

    dates = sorted(all_data.keys(), reverse=True)
    years = sorted({d[:4] for d in dates if len(d) >= 4}, reverse=True) or [get_today_key()[:4]]

    c_y, c_m, _ = st.columns([1, 1, 2])
    year = c_y.selectbox("年份", ["全部年份"] + years, label_visibility="collapsed")
    months = sorted({d[:7] for d in dates if year == "全部年份" or d.startswith(year)}, reverse=True)
    month = c_m.selectbox("月份", ["全部月份"] + months, label_visibility="collapsed")

    if month != "全部月份":
        prefix = month
    elif year != "全部年份":
        prefix = year
    else:
        prefix = ""

    stats, _ = aggregate_stats_by_prefix(prefix)
    excel_cleaned = stats.get("excel_cleaned", 0)
    compressed_images = stats.get("compressed_images", 0)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("压缩图片", f"{compressed_images} 张", border=True)
    c2.metric("节省空间", format_bytes_to_gb(stats.get("saved_bytes", 0)), border=True)
    c3.metric("转化表格", f"{excel_cleaned} 个", border=True)
    c4.metric("节约工时", f"{calculate_hours_saved(excel_cleaned, compressed_images):.1f} 小时", border=True)

    rows = []
    for d in dates:
        if d.startswith(prefix):
            r = all_data[d]
            c_cnt = r.get("compressed_images", 0)
            e_cnt = r.get("excel_cleaned", 0)
            rows.append({
                "日期": d,
                "压缩图片": c_cnt,
                "节省空间": format_bytes_to_gb(r.get("saved_bytes", 0)),
                "转化表格": e_cnt,
                "节约工时": calculate_hours_saved(e_cnt, c_cnt),
                "更新时间": r.get("last_updated", ""),
            })
    if rows:
        import pandas as pd
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
