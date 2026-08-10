import email
import imaplib
import json
import os
import re
import time
import requests

# 导入 Scrapling 防封锁会话组件
try:
  from scrapling.fetchers import FetcherSession
except ImportError:
  FetcherSession = None

COOKIE_CACHE_FILE = os.path.join(
    os.path.dirname(__file__), "baozun_cookie_cache.json"
)


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


class BaozunAccountAPI:

  def __init__(
      self,
      username: str = "jm038153",  # 宝尊账号
      password: str = "Xl@20177",  # 宝尊密码
      qq_email: str = "805559297@qq.com",  # QQ 邮箱
      qq_auth_code: str = "ucsmhjdaxhvwbcge",  # QQ 授权码
      imap_server: str = "imap.qq.com",
  ):
    self.username = username
    self.password = password
    self.qq_email = qq_email
    self.qq_auth_code = qq_auth_code
    self.imap_server = imap_server
    self.base_url = "https://union-gateway.baozun.com"

  def fetch_latest_email_otp(
      self, timeout: int = 60, poll_interval: int = 3
  ) -> str:
    """从 QQ 邮箱秒级提取 Outlook 自动转发过来的宝尊 6 位验证码"""
    start_time = time.time()

    while time.time() - start_time < timeout:
      try:
        mail = imaplib.IMAP4_SSL(self.imap_server, 993)
        mail.login(self.qq_email, self.qq_auth_code)
        mail.select("INBOX")

        _, search_data = mail.search(None, "ALL")
        mail_ids = search_data[0].split()[-5:]

        for mail_id in reversed(mail_ids):
          _, msg_data = mail.fetch(mail_id, "(RFC822)")
          for response_part in msg_data:
            if isinstance(response_part, tuple):
              msg = email.message_from_bytes(response_part)

              body = ""
              if msg.is_multipart():
                for part in msg.walk():
                  if part.get_content_type() in ["text/plain", "text/html"]:
                    body += part.get_payload(decode=True).decode(
                        "utf-8", errors="ignore"
                    )
              else:
                body = msg.get_payload(decode=True).decode(
                    "utf-8", errors="ignore"
                )

              if "验证码" in body or "UAC" in body or "宝尊" in body:
                codes = re.findall(r"\b\d{6}\b", body)
                if codes:
                  mail.logout()
                  return codes[0]

        mail.logout()
      except Exception as e:
        print(f"读取邮件验证码中: {e}")

      time.sleep(poll_interval)

    raise TimeoutError("自动读取邮件验证码超时，请检查 Outlook 转发配置")

  def login_and_get_cookie_str(self) -> str:
    """使用 Scrapling 伪装 Chrome TLS 会话完成鉴权登录"""
    if FetcherSession is not None:
      session = FetcherSession(impersonate="chrome")
    else:
      session = requests.Session()

    # 1. 提交账号密码触发验证码
    login_url = f"{self.base_url}/uaac/login"
    payload = {"username": self.username, "password": self.password}
    session.post(login_url, json=payload, timeout=15)

    # 2. 从 QQ 邮箱获取 6 位验证码
    otp = self.fetch_latest_email_otp(timeout=45)

    # 3. 提交验证码完成二次鉴权
    verify_url = f"{self.base_url}/uaac/login/verify"
    verify_payload = {"username": self.username, "code": otp}
    verify_resp = session.post(verify_url, json=verify_payload, timeout=15)

    # 提取完整 Cookie 字符串
    cookie_dict = (
        session.cookies.get_dict()
        if hasattr(session, "cookies")
        else verify_resp.cookies.get_dict()
    )
    cookie_str = "; ".join([f"{k}={v}" for k, v in cookie_dict.items()])

    self.save_cached_cookie(cookie_str)
    return cookie_str

  def get_valid_cookie(self) -> str:
    """优先使用本地缓存 Cookie，失效时自动刷新"""
    cached_cookie = self.load_cached_cookie()
    if cached_cookie and self.check_cookie_valid(cached_cookie):
      return cached_cookie

    return self.login_and_get_cookie_str()

  def check_cookie_valid(self, cookie_str: str) -> bool:
    """检验 Cookie 当前是否有效"""
    try:
      headers = {
          "Cookie": cookie_str,
          "User-Agent": (
              "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
          ),
      }
      resp = requests.get(
          f"{self.base_url}/iforce/art/image/getImageExpand",
          params={"recordCode": "test"},
          headers=headers,
          timeout=5,
      )
      if resp.status_code == 200 and "UAAC" not in resp.text:
        return True
    except Exception:
      pass
    return False

  def save_cached_cookie(self, cookie_str: str):
    try:
      with open(COOKIE_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump({"cookie": cookie_str, "update_time": time.time()}, f)
    except Exception:
      pass

  def load_cached_cookie(self) -> str:
    if os.path.exists(COOKIE_CACHE_FILE):
      try:
        with open(COOKIE_CACHE_FILE, "r", encoding="utf-8") as f:
          data = json.load(f)
          return data.get("cookie", "")
      except Exception:
        pass
    return ""
