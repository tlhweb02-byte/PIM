import base64
import email
import email.utils as email_utils
import imaplib
import json
import os
import re
import time
import requests
from datetime import datetime, timezone

# 加载项目根目录下的 .env 文件（敏感配置存放处，已被 .gitignore 忽略）
try:
  from dotenv import load_dotenv
  load_dotenv()
except ImportError:
  pass

# 导入 Scrapling 防封锁会话组件
try:
  from scrapling.fetchers import FetcherSession
except ImportError:
  FetcherSession = None

COOKIE_CACHE_FILE = os.path.join(
    os.path.dirname(__file__), "baozun_cookie_cache.json"
)

# 宝尊 UAAC 统一认证中心（真实接口，已通过逆向前端 + 实机验证）
UAAC_BASE = "https://api-base-ecs.baozun.com"


def _get_secret(name: str, default: str = "") -> str:
  """按优先级读取敏感配置：
  1) 环境变量（本地 .env 经 load_dotenv 注入 / 云端平台注入）
  2) Streamlit st.secrets（Community Cloud 的密钥管理）
  3) 默认值
  只有取到非空值才返回；Secrets 未配置/为空时回落到 default
  """
  val = os.getenv(name, "").strip()
  if val:
    return val
  try:
    import streamlit as st
    val = st.secrets.get(name, "")
    if isinstance(val, str):
      val = val.strip()
      if val:
        return val
  except Exception:
    pass
  return default


def parse_cookie_string(cookie_str: str) -> dict:
  """解析 Cookie 字符串为字典"""
  cookies = {}
  if not cookie_str:
    return cookies
  for item in cookie_str.split(";"):
    if "=" in item:
      key, val = item.strip().split("=", 1)
      cookies[key.strip()] = val.strip()
  return cookies


class OtpRequiredError(Exception):
  """验证码已发送但自动读取失败，需要人工在界面上输入验证码"""

  def __init__(self, message: str, session=None, tenant: str = "",
               appkey: str = ""):
    super().__init__(message)
    self.session = session
    self.tenant = tenant
    self.appkey = appkey


# ---------------------------------------------------------------------------
# RSA 加密（纯 Python 实现，无第三方依赖；与前端 JSEncrypt 输出一致：base64）
# ---------------------------------------------------------------------------
def _der_read(data: bytes, pos: int):
  tag = data[pos]
  pos += 1
  ln = data[pos]
  pos += 1
  if ln & 0x80:
    cnt = ln & 0x7F
    ln = int.from_bytes(data[pos:pos + cnt], "big")
    pos += cnt
  return tag, data[pos:pos + ln], pos + ln


def _parse_rsa_public_key(pem_text: str):
  """解析 PEM 格式 RSA 公钥，返回 (模数 n, 指数 e)"""
  b64 = re.sub(r"-----.*?-----", "", pem_text, flags=re.S).strip()
  der = base64.b64decode(b64)
  _, spki, _ = _der_read(der, 0)
  _, _, p = _der_read(spki, 0)
  _, bitstr, _ = _der_read(spki, p)
  rpk = bitstr[1:]  # 跳过 BIT STRING 的 0x00 头
  _, seq, _ = _der_read(rpk, 0)
  _, n_bytes, p = _der_read(seq, 0)
  _, e_bytes, _ = _der_read(seq, p)
  return int.from_bytes(n_bytes, "big"), int.from_bytes(e_bytes, "big")


def _rsa_encrypt_base64(text: bytes, n: int, e: int) -> str:
  """RSA PKCS#1 v1.5 加密，输出 base64（与宝尊前端 JSEncrypt 一致）"""
  k = (n.bit_length() + 7) // 8
  ps_len = k - len(text) - 3
  ps = bytearray()
  while len(ps) < ps_len:
    rnd = os.urandom(ps_len - len(ps))
    ps.extend(b for b in rnd if b != 0)
    if len(ps) > ps_len:
      del ps[ps_len:]
  em = b"\x00\x02" + bytes(ps) + b"\x00" + text
  m = int.from_bytes(em, "big")
  ct = pow(m, e, n).to_bytes(k, "big")
  return base64.b64encode(ct).decode()


class BaozunAccountAPI:

  def __init__(
      self,
      username: str = "",
      password: str = "",
      qq_email: str = "",
      qq_auth_code: str = "",
      imap_server: str = "",
      tenant: str = "",
      appkey: str = "",
  ):
    # 敏感配置从环境变量 / Streamlit Secrets 读取，代码仓库中不保存任何明文凭据
    self.username = username or _get_secret("BAOZUN_USERNAME")
    self.password = password or _get_secret("BAOZUN_PASSWORD")
    self.qq_email = qq_email or _get_secret("BAOZUN_QQ_EMAIL")
    self.qq_auth_code = qq_auth_code or _get_secret("BAOZUN_QQ_AUTH_CODE")
    self.imap_server = imap_server or _get_secret(
        "BAOZUN_IMAP_SERVER", "imap.qq.com"
    )
    # 登录后选择的租户（登录接口会返回可选租户列表，如 baozun / NIKE）
    self.tenant = tenant or _get_secret("BAOZUN_TENANT", "baozun")
    # 应用标识（ROSS 前端固定为 ross-modern-api）
    self.appkey = appkey or _get_secret("BAOZUN_APPKEY", "ross-modern-api")

  def _new_session(self):
    """创建伪装 Chrome TLS 的会话（Scrapling 优先，回退 requests）"""
    if FetcherSession is not None:
      session = FetcherSession(impersonate="chrome")
    else:
      session = requests.Session()
    default_headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            " (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
    }
    if hasattr(session, "headers"):
      session.headers.update(default_headers)
    return session

  @staticmethod
  def _extract_body(msg) -> str:
    """提取邮件正文（HTML 转纯文本、反转义）"""
    import html as _html
    body = ""
    if msg.is_multipart():
      for part in msg.walk():
        if part.get_content_type() in ["text/plain", "text/html"]:
          try:
            decoded = part.get_payload(decode=True).decode(
                "utf-8", errors="ignore"
            )
          except Exception:
            continue
          if part.get_content_type() == "text/html":
            decoded = re.sub(r"<[^>]+>", " ", decoded)
            decoded = _html.unescape(decoded)
          body += " " + decoded
    else:
      try:
        body = msg.get_payload(decode=True).decode("utf-8", errors="ignore")
      except Exception:
        body = ""
    return body

  @staticmethod
  def _extract_otp(text: str) -> str:
    """从文本中提取验证码：优先取「验证码」等关键词后紧跟的 6 位数字；
    兜底取独立成词的 6 位数字（排除被字母包裹的，如账号 jm038153 里的 038153）"""
    m = re.search(
        r"(?:验证码|动态口令|安全码|校验码|登录码"
        r"|verification\s*code|security\s*code|one-?time\s*password|OTP)"
        r"[^\d]{0,12}(\d{6})",
        text,
        re.I,
    )
    if m:
      return m.group(1)
    codes = re.findall(r"(?<![\dA-Za-z])\d{6}(?![\dA-Za-z])", text)
    return codes[0] if codes else ""

  def fetch_latest_email_otp(
      self, timeout: int = 180, poll_interval: int = 3, after_ts: float = None
  ) -> str:
    """从 QQ 邮箱提取宝尊发来的 6 位验证码（公司邮箱自动转发到 QQ）。
    after_ts: 只认该时间戳之后到达的邮件（避免抓到历史验证码）"""
    start_time = time.time()
    login_fail_count = 0

    while time.time() - start_time < timeout:
      try:
        mail = imaplib.IMAP4_SSL(self.imap_server, 993)
        mail.login(self.qq_email, self.qq_auth_code)
        login_fail_count = 0
        code = self._scan_mailbox_for_otp(mail, after_ts=after_ts)
        mail.logout()
        if code:
          return code
      except imaplib.IMAP4.error as e:
        login_fail_count += 1
        print(f"QQ邮箱IMAP错误: {e}")
        if login_fail_count >= 3:
          raise ValueError(
              f"QQ 邮箱 IMAP 登录失败({e})。请检查："
              f"1) QQ邮箱→设置→账户→IMAP/SMTP 服务是否开启; "
              f"2) BAOZUN_QQ_AUTH_CODE 是否为 IMAP 授权码（非登录密码）; "
              f"3) 云端 IP 是否被 QQ 风控拦截"
          )
      except Exception as e:
        print(f"读取邮件验证码中: {e}")

      time.sleep(poll_interval)

    return ""

  def _scan_mailbox_for_otp(self, mail, after_ts: float = None) -> str:
    """扫描收件箱及其它文件夹，按「到达时间优先 + 关键词加权」找验证码"""
    folders = ["INBOX"]
    try:
      _, raw_list = mail.list()
      for line in raw_list:
        m = re.search(rb'"([^"]*)"\s*$', line)
        if m:
          name = m.group(1).decode("ascii", errors="ignore")
          if name and name not in folders:
            folders.append(name)
    except Exception:
      pass

    best_code, best_score = "", -1
    for folder in folders:
      try:
        status, _ = mail.select(folder)
        if status != "OK":
          continue
        _, search_data = mail.search(None, "ALL")
        mail_ids = search_data[0].split()[-40:]

        for mail_id in reversed(mail_ids):
          _, msg_data = mail.fetch(mail_id, "(RFC822)")
          for response_part in msg_data:
            if not isinstance(response_part, tuple):
              continue
            msg = email.message_from_bytes(response_part[1])
            code, score = self._score_email_for_otp(msg, after_ts=after_ts)
            if code and score > best_score:
              best_code, best_score = code, score
      except Exception:
        continue

    if not best_code:
      print("[验证码扫描] 未在邮箱中找到验证码")
    return best_code

  def _score_email_for_otp(self, msg, after_ts: float = None):
    """给邮件打分：到达时间越新分越高，关键词/发件人命中额外加分。
    after_ts: 过滤该时间戳之前的邮件（历史验证码）。
    返回 (验证码, 分数)；无 6 位验证码则返回 ('', 0)"""
    subject = str(msg.get("Subject", "") or "")
    sender = str(msg.get("From", "") or "")
    body = self._extract_body(msg)
    combined = subject + " " + body
    otp = self._extract_otp(combined)
    if not otp:
      return "", 0

    score = 0
    # 关键词（验证码类 + 宝尊品牌）
    keywords = (
        r"验证码|动态口令|安全码|校验码|登录码|UAC|宝尊|baozun"
        r"|verification|security code|one-?time|登录"
    )
    if re.search(keywords, subject, re.I):
      score += 8
    if re.search(keywords, body, re.I):
      score += 5
    if "baozun" in sender.lower():
      score += 5

    # 到达时间新鲜度（最强信号：验证码邮件刚到达）
    try:
      dt = email_utils.parsedate_to_datetime(msg.get("Date", "") or "")
      if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
      dt_ts = dt.timestamp()
      # 只认发码之后到达的邮件（容忍 60 秒时钟偏差）
      if after_ts is not None and dt_ts < after_ts - 60:
        return "", 0
      age = (datetime.now(timezone.utc) - dt).total_seconds()
      if 0 <= age < 300:
        score += 30      # 5 分钟内到达
      elif age < 900:
        score += 20      # 15 分钟内
      elif age < 3600:
        score += 8       # 1 小时内
      elif age < 86400:
        score += 2       # 24 小时内
    except Exception:
      pass

    return otp, score

  def _fetch_ticket(self, session) -> str:
    """获取租户访问票据 token；需要二次认证时返回空串"""
    resp = session.get(
        f"{UAAC_BASE}/api/uaac/account/token",
        params={"saasTenantCode": self.tenant, "appkey": self.appkey},
        timeout=15,
    ).json()
    code = str(resp.get("code", ""))
    if code in ("0", "200", "00000"):
      return resp.get("data") or ""
    if code == "40001":  # 需要进行二次认证
      return ""
    if code == "01":  # 租户参数无效（常见原因：BAOZUN_TENANT 配置了占位符或错误值）
      raise ValueError(
          f"获取宝尊访问票据失败(租户参数无效): 当前 BAOZUN_TENANT={self.tenant!r} "
          f"不可用，请检查 Streamlit Secrets / .env 中的配置（可用值: baozun / NIKE）"
      )
    raise ValueError(f"获取宝尊访问票据失败: {resp.get('message')}")

  def login_full(
      self, otp_code: str = "", otp_timeout: int = 180
  ) -> dict:
    """完整 UAAC 登录流程（已按真实接口验证）：
    1) RSA 公钥加密密码 → 密码登录
    2) 发送邮箱验证码 → 从 QQ 邮箱读取（或传入 otp_code 直接使用）→ 校验
    3) 获取租户访问票据 token
    自动读取验证码超时时抛出 OtpRequiredError（可用 complete_login_with_otp 补交）
    返回: {session, token, tenant, appkey}
    """
    session = self._new_session()

    # 1. 获取 RSA 公钥并加密密码
    pk_resp = session.get(f"{UAAC_BASE}/api/uaac/account/publicKey", timeout=15)
    if pk_resp.status_code != 200:
      raise ValueError(f"获取宝尊加密公钥失败: HTTP {pk_resp.status_code}")
    n, e = _parse_rsa_public_key(pk_resp.json()["data"])
    enc_pwd = _rsa_encrypt_base64(self.password.encode(), n, e)

    # 2. 密码登录（字段名为 loginName + password）
    login_resp = session.post(
        f"{UAAC_BASE}/api/uaac/account/login",
        json={"loginName": self.username, "password": enc_pwd},
        timeout=15,
    ).json()
    code = str(login_resp.get("code", ""))
    if code not in ("0", "200", "00000"):
      raise ValueError(
          f"宝尊登录失败: {login_resp.get('message')} "
          f"(请检查账号密码是否填写正确)"
      )

    # 2.1 租户自动校正：登录响应会返回可用租户列表，
    # 若配置的 BAOZUN_TENANT 不在其中（常见于填了占位符/拼写错误），自动切换
    tenants = login_resp.get("data") or []
    tenant_codes = [
        t.get("saasTenantCode") for t in tenants
        if isinstance(t, dict) and t.get("saasTenantCode")
    ]
    if tenant_codes and self.tenant not in tenant_codes:
      print(
          f"提示: BAOZUN_TENANT={self.tenant!r} 不在可用租户 {tenant_codes} 中，"
          f"自动切换为 {tenant_codes[0]}"
      )
      self.tenant = tenant_codes[0]

    # 3. 先尝试直接拿票据（部分账号可能无需二次认证）
    ticket = self._fetch_ticket(session)

    # 4. 需要二次认证：邮件验证码
    if not ticket:
      send_ts = time.time()
      send_resp = session.get(
          f"{UAAC_BASE}/api/uaac/account/twoFactor/sendCode",
          params={"type": "email", "saasTenantCode": self.tenant},
          timeout=15,
      ).json()
      code = str(send_resp.get("code", ""))
      if code not in ("0", "200", "00000"):
        raise ValueError(
            f"发送验证码失败: {send_resp.get('message')} "
            f"(可能发送过于频繁，请稍后再试)"
        )

      otp = otp_code or self.fetch_latest_email_otp(
          timeout=otp_timeout, after_ts=send_ts
      )
      if not otp:
        raise OtpRequiredError(
            "验证码已发送但自动读取超时，请在界面上手动输入邮箱收到的验证码",
            session=session,
            tenant=self.tenant,
            appkey=self.appkey,
        )

      verify_resp = session.get(
          f"{UAAC_BASE}/api/uaac/account/twoFactor/verifyCode",
          params={
              "type": "email",
              "saasTenantCode": self.tenant,
              "code": otp,
          },
          timeout=15,
      ).json()
      code = str(verify_resp.get("code", ""))
      if code not in ("0", "200", "00000"):
        raise ValueError(f"验证码校验失败: {verify_resp.get('message')}")

      ticket = self._fetch_ticket(session)

    if not ticket:
      raise RuntimeError("未能获取宝尊访问票据 token，请稍后重试")

    return {
        "session": session,
        "token": ticket,
        "tenant": self.tenant,
        "appkey": self.appkey,
    }

  def diagnose_mailbox(self) -> dict:
    """诊断 QQ 邮箱读取：返回文件夹列表与最近邮件，用于排查验证码读取失败"""
    result = {"ok": False, "error": "", "folders": [], "emails": []}
    try:
      mail = imaplib.IMAP4_SSL(self.imap_server, 993)
      mail.login(self.qq_email, self.qq_auth_code)
      result["ok"] = True

      try:
        _, raw_list = mail.list()
        for line in raw_list:
          m = re.search(rb'"([^"]*)"\s*$', line)
          if m:
            result["folders"].append(
                m.group(1).decode("ascii", errors="ignore")
            )
      except Exception as e:
        result["folders"].append(f"(列表失败: {e})")

      try:
        mail.select("INBOX")
        _, data = mail.search(None, "ALL")
        ids = data[0].split()[-10:]
        for mid in reversed(ids):
          _, msg_data = mail.fetch(mid, "(RFC822)")
          for rp in msg_data:
            if not isinstance(rp, tuple):
              continue
            msg = email.message_from_bytes(rp[1])
            subject = str(msg.get("Subject", "") or "")
            sender = str(msg.get("From", "") or "")
            otp = self._extract_otp(subject + " " + self._extract_body(msg))
            age = ""
            try:
              dt = email_utils.parsedate_to_datetime(
                  msg.get("Date", "") or ""
              )
              if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
              age = f"{int((datetime.now(timezone.utc) - dt).total_seconds())}秒前"
            except Exception:
              pass
            result["emails"].append({
                "subject": subject[:60],
                "sender": sender[:50],
                "age": age,
                "codes": [otp] if otp else [],
            })
      except Exception as e:
        result["emails"].append({
            "subject": f"(收件箱读取失败: {e})", "sender": "", "age": "", "codes": []
        })

      mail.logout()
    except Exception as e:
      result["error"] = str(e)
    return result

  def complete_login_with_otp(
      self, otp_code: str, session, tenant: str = "", appkey: str = ""
  ) -> dict:
    """自动读取验证码失败后，用人工输入的验证码完成登录"""
    self.tenant = tenant or self.tenant
    self.appkey = appkey or self.appkey

    verify_resp = session.get(
        f"{UAAC_BASE}/api/uaac/account/twoFactor/verifyCode",
        params={
            "type": "email",
            "saasTenantCode": self.tenant,
            "code": otp_code,
        },
        timeout=15,
    ).json()
    code = str(verify_resp.get("code", ""))
    if code not in ("0", "200", "00000"):
      raise ValueError(
          f"验证码校验失败: {verify_resp.get('message')}"
          f"（验证码可能已过期，请重新点击生成）"
      )

    ticket = self._fetch_ticket(session)
    if not ticket:
      raise RuntimeError("未能获取宝尊访问票据 token，请稍后重试")

    return {
        "session": session,
        "token": ticket,
        "tenant": self.tenant,
        "appkey": self.appkey,
    }
