# -*- coding: utf-8 -*-
"""
用户账号注册 / 登录 / 宝尊扩图试用次数管理
================================================
- 账号数据保存在与「提效统计」同一个 Google 表格中（新增「用户账号」工作表）
- 密码仅保存「加盐哈希」（PBKDF2-SHA256），任何情况下都不保存明文密码
- 新用户注册赠送 AUTH_FREE_QUOTA 次免费体验（默认 10 次）
- 管理员（AUTH_ADMIN_USERNAMES，逗号分隔）使用宝尊扩图不受次数限制

表格「用户账号」工作表列结构：
    username | password_hash | salt | created_at | used_count | last_login_at
"""
import datetime
import hashlib
import os
import re
import streamlit as st

try:
    import gspread
    from modules import mod_stats
    SHEETS_OK = True
except ImportError:
    SHEETS_OK = False

# ---------- 可配置项（可通过 .env / Streamlit Secrets 覆盖） ----------
AUTH_VERSION = "1.1.2"           # 账号系统版本（侧边栏显示，用于确认部署是否成功）
DEFAULT_FREE_QUOTA = 10          # 新用户免费体验次数
PBKDF2_ITERATIONS = 120000       # 密码哈希迭代次数（越慢越难被暴力破解）

WORKSHEET_TITLE = "用户账号"
SHEET_HEADERS = [
    "username", "password_hash", "salt",
    "created_at", "used_count", "last_login_at",
]

USERNAME_RE = re.compile(r"^[\w\u4e00-\u9fa5-]{2,20}$")


def _get_secret(name: str, default: str = "") -> str:
    """按优先级读取配置：环境变量 -> Streamlit Secrets -> 默认值"""
    val = os.getenv(name, "").strip()
    if val:
        return val
    try:
        if hasattr(st.secrets, "get"):
            val = st.secrets.get(name, "")
        elif name in st.secrets:
            val = st.secrets[name]
        else:
            val = ""
        if isinstance(val, str):
            return val.strip()
    except Exception:
        pass
    return default


def _free_quota() -> int:
    try:
        return int(_get_secret("AUTH_FREE_QUOTA", str(DEFAULT_FREE_QUOTA)))
    except (ValueError, TypeError):
        return DEFAULT_FREE_QUOTA


def free_quota() -> int:
    """新用户免费体验次数（可被 AUTH_FREE_QUOTA 配置覆盖）"""
    return _free_quota()


def is_admin(username: str) -> bool:
    """管理员名单：AUTH_ADMIN_USERNAMES（多个用英文逗号分隔）"""
    admins = [
        x.strip().lower() for x in _get_secret("AUTH_ADMIN_USERNAMES", "").split(",")
        if x.strip()
    ]
    return (username or "").strip().lower() in admins


# ---------------------------------------------------------------------------
# Google 表格存取
# ---------------------------------------------------------------------------
def _get_worksheet():
    """打开「用户账号」工作表，不存在则自动创建；返回 (ws, err)"""
    if not SHEETS_OK:
        return None, "缺少 gspread 依赖，请检查 requirements.txt"
    client, err = mod_stats.get_gspread_client()
    if client is None:
        return None, err or "Google 表格客户端不可用"
    try:
        sh = client.open(mod_stats.SPREADSHEET_NAME)
        try:
            ws = sh.worksheet(WORKSHEET_TITLE)
        except gspread.exceptions.WorksheetNotFound:
            ws = sh.add_worksheet(
                title=WORKSHEET_TITLE,
                rows=5000,
                cols=len(SHEET_HEADERS),
            )
            ws.append_row(SHEET_HEADERS)
        # 兜底：若首行无表头则补写表头
        try:
            headers = ws.row_values(1)
            if not headers:
                ws.append_row(SHEET_HEADERS)
        except Exception:
            pass
        return ws, None
    except Exception as e:
        return None, f"访问 Google 表格失败: {e}"


def _normalize_username(username: str) -> str:
    return (username or "").strip().lower()


def get_user_record(username: str):
    """按用户名查账号记录（含 used_count 等）；不存在返回 (None, None)"""
    username = _normalize_username(username)
    ws, err = _get_worksheet()
    if ws is None:
        return None, err
    try:
        records = ws.get_all_records()
    except Exception as e:
        return None, f"读取账号表失败: {e}"
    for r in records:
        if _normalize_username(str(r.get("username", ""))) == username:
            return r, None
    return None, None


def _find_row(ws, username: str):
    """返回账号所在行号（含表头为第 1 行）；未找到返回 None"""
    try:
        records = ws.get_all_records()
    except Exception:
        return None
    for i, r in enumerate(records):
        if _normalize_username(str(r.get("username", ""))) == username:
            return i + 2  # 第 0 条记录在第 2 行
    return None


# ---------------------------------------------------------------------------
# 密码安全（加盐哈希，绝不存明文）
# ---------------------------------------------------------------------------
def _new_salt() -> str:
    return os.urandom(16).hex()


def _hash_password(password: str, salt_hex: str) -> str:
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        bytes.fromhex(salt_hex),
        PBKDF2_ITERATIONS,
    )
    return digest.hex()


def validate_username(username: str) -> str:
    """返回错误信息；合法返回空串"""
    username = (username or "").strip()
    if not username:
        return "用户名不能为空"
    if not USERNAME_RE.match(username):
        return "用户名需为 2-20 位，仅限中英文、数字、下划线或横线"
    return ""


def validate_password(password: str) -> str:
    password = password or ""
    if len(password) < 6:
        return "密码至少 6 位"
    if len(password) > 64:
        return "密码过长（最多 64 位）"
    return ""


# ---------------------------------------------------------------------------
# 注册 / 登录 / 会话
# ---------------------------------------------------------------------------
def register_user(username: str, password: str):
    """注册新用户；返回 (ok, message)。成功后账号即写入 Google 表格"""
    username = _normalize_username(username)
    err = validate_username(username)
    if err:
        return False, err
    err = validate_password(password)
    if err:
        return False, err

    ws, werr = _get_worksheet()
    if ws is None:
        return False, werr or "账号表不可用，请稍后再试"

    existing, _ = get_user_record(username)
    if existing:
        return False, "该用户名已被注册，请换一个"

    salt = _new_salt()
    row = [
        username,
        _hash_password(password, salt),
        salt,
        datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        0,
        "",
    ]
    try:
        ws.append_row(row)
        print(f"[auth] 注册成功: [{username}]")
        return True, f"注册成功！已自动登录，赠送 {_free_quota()} 次免费体验"
    except Exception as e:
        print(f"[auth] 注册失败(写入表格): {e}")
        return False, f"写入账号表失败: {e}"


def login_user(username: str, password: str):
    """登录校验；返回 (ok, message, record)"""
    username = _normalize_username(username)
    rec, err = get_user_record(username)
    if err:
        print(f"[auth] 登录失败(读表错误): {err}")
        return False, err, None
    if rec is None:
        print(f"[auth] 登录失败: 账号不存在 [{username}]")
        return False, "用户名或密码不正确", None

    salt = str(rec.get("salt", "") or "")
    pwd_hash = str(rec.get("password_hash", "") or "")
    try:
        pwd_ok = bool(salt and pwd_hash) and _hash_password(password, salt) == pwd_hash
    except (ValueError, TypeError) as e:
        print(f"[auth] 账号 {username} 数据异常(盐值/哈希格式错误): {e}")
        return False, "账号数据异常，请联系管理员重新注册", None
    if not pwd_ok:
        print(f"[auth] 登录失败: 密码不正确 [{username}]")
        return False, "用户名或密码不正确", None

    # 记录最后登录时间（失败不影响登录）
    try:
        ws, _ = _get_worksheet()
        if ws is not None:
            row = _find_row(ws, username)
            if row:
                ws.update_cell(
                    row, 6, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                )
    except Exception:
        pass

    print(f"[auth] 登录成功: [{username}]")
    return True, "登录成功", rec


def set_logged_in(username: str):
    st.session_state["auth_user"] = _normalize_username(username)


def current_user() -> str:
    return st.session_state.get("auth_user", "") or ""


def is_logged_in() -> bool:
    return bool(current_user())


def logout():
    st.session_state.pop("auth_user", None)


def diagnose_auth(username: str = "", password: str = ""):
    """诊断账号系统状态（只读，不修改任何数据），返回 dict。
    用于排查"登录没反应"类问题：表格是否连通、账号是否存在、密码是否匹配"""
    info = {
        "sheet_ok": False,
        "sheet_error": "",
        "account_count": 0,
        "username_exists": False,
        "password_ok": False,
    }
    ws, err = _get_worksheet()
    if ws is None:
        info["sheet_error"] = err or "无法连接 Google 表格"
        return info
    info["sheet_ok"] = True
    try:
        records = ws.get_all_records()
    except Exception as e:
        info["sheet_error"] = f"读取账号表失败: {e}"
        return info
    info["account_count"] = len(records)

    uname = _normalize_username(username)
    rec = None
    for r in records:
        if _normalize_username(str(r.get("username", ""))) == uname:
            rec = r
            break
    info["username_exists"] = rec is not None
    if rec is not None and password:
        try:
            salt = str(rec.get("salt", "") or "")
            pwd_hash = str(rec.get("password_hash", "") or "")
            info["password_ok"] = bool(
                salt and pwd_hash and _hash_password(password, salt) == pwd_hash
            )
        except Exception:
            info["password_ok"] = False
    return info


# ---------------------------------------------------------------------------
# 试用次数（仅宝尊扩图消耗；管理员不限）
# ---------------------------------------------------------------------------
def get_used_count(username: str) -> int:
    rec, _ = get_user_record(username)
    if rec is None:
        return 0
    try:
        return int(rec.get("used_count", 0) or 0)
    except (ValueError, TypeError):
        return 0


def get_remaining(username: str) -> int:
    """剩余免费次数；管理员返回 -1 表示不限"""
    if is_admin(username):
        return -1
    return max(0, _free_quota() - get_used_count(username))


def consume_quota(username: str):
    """宝尊扩图成功一次消耗 1 次（管理员不扣）；返回 (ok, message)"""
    username = _normalize_username(username)
    if is_admin(username):
        return True, ""
    ws, err = _get_worksheet()
    if ws is None:
        return False, err or "账号表不可用"
    try:
        row = _find_row(ws, username)
        if row is None:
            return False, "用户不存在"
        new_used = get_used_count(username) + 1
        ws.update_cell(row, 5, new_used)
        return True, ""
    except Exception as e:
        return False, f"扣减次数失败: {e}"
