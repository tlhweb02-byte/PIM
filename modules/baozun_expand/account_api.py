import base64
import email
import imaplib
import json
import os
import re
import time
import requests

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
  """
  val = os.getenv(name, "").strip()
  if val:
    return val
  try:
    import streamlit as st
    val = st.secrets.get(name, "")
    if isinstance(val, str):
      return val.strip()
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

  def fetch_latest_email_otp(
      self, timeout: int = 120, poll_interval: int = 3
  ) -> str:
    """从 QQ 邮箱提取宝尊发来的 6 位验证码（公司邮箱自动转发到 QQ）"""
    start_time = time.time()
    login_fail_count = 0

    while time.time() - start_time < timeout:
      try:
        mail = imaplib.IMAP4_SSL(self.imap_server, 993)
        mail.login(self.qq_email, self.qq_auth_code)
        login_fail_count = 0
        mail.select("INBOX")

        _, search_data = mail.search(None, "ALL")
        mail_ids = search_data[0].split()[-30:]

        # 给每封候选邮件打分：主题/正文/发件人命中关键词越强越优先
        best_score, best_code = 0, ""
        for mail_id in reversed(mail_ids):
          _, msg_data = mail.fetch(mail_id, "(RFC822)")
          for response_part in msg_data:
            if not isinstance(response_part, tuple):
              continue
            msg = email.message_from_bytes(response_part)
            subject = str(msg.get("Subject", "") or "")
            sender = str(msg.get("From", "") or "")
            body = self._extract_body(msg)

            combined = subject + " " + body
            score = 0
            if re.search(
                r"验证码|UAC|宝尊|baozun|verification|登录", subject, re.I
            ):
              score += 3
            if re.search(
                r"验证码|UAC|宝尊|baozun|verification|登录", body, re.I
            ):
              score += 2
            if "baozun" in sender.lower():
              score += 2
            if score == 0:
              continue
            codes = re.findall(r"(?<!\d)\d{6}(?!\d)", combined)
            if codes and score > best_score:
              best_score, best_code = score, codes[0]

        mail.logout()
        if best_code:
          return best_code
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
      self, otp_code: str = "", otp_timeout: int = 120
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

      otp = otp_code or self.fetch_latest_email_otp(timeout=otp_timeout)
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
