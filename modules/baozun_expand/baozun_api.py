"""宝尊 ROSS 智能扩图接口客户端。

所有用户共用一个实例（见 app.get_api）：同一时间只会有一个登录流程，
所有请求都经过 _request，登录失效时最多自动重新登录一次。
"""
import json
import os
import re
import threading
import time

import requests

try:
  from scrapling.fetchers import FetcherSession
except ImportError:
  FetcherSession = None

from .account_api import (
    BaozunAccountAPI,
    OtpRequiredError,
    _get_secret,
    parse_cookie_string,
)

GATEWAY = "https://union-gateway.baozun.com"

# 登录会话缓存文件：保存 Cookie + 票据，服务重启后直接复用（已被 .gitignore 忽略）
LOGIN_CACHE_FILE = os.path.join(
    os.path.dirname(__file__), "baozun_login_cache.json"
)

# 上传接口：按顺序尝试，只有接口不存在（404/405）时才换下一个
UPLOAD_PATHS = (
    "/iforce/art/image/upload/rename",
    "/iforce/art/image/upload",
    "/iforce/art/upload/rename",
    "/upload/rename",
)

# 宝尊附件编号 / 任务编号的格式：只允许字母数字和 - _ .，防止把错误信息当成编号
_CODE_RE = re.compile(r"[A-Za-z0-9_.\-]{4,128}")


class LoginRequired(Exception):
  """需要人工输入邮箱验证码才能继续（自动读取超时）"""


def _new_session():
  """伪装 Chrome TLS 的会话（Scrapling 优先，回退 requests）"""
  session = FetcherSession(impersonate="chrome") if FetcherSession else requests.Session()
  if hasattr(session, "headers"):
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            " (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
    })
  return session


def _json(resp):
  try:
    return resp.json()
  except Exception:
    return resp.text.strip().strip('"')


def _as_code(value):
  """把接口返回值解析成编号；不像编号的（如报错文字）返回 None"""
  if isinstance(value, (int, float)) and not isinstance(value, bool):
    value = str(value)
  if isinstance(value, str):
    value = value.strip().strip('"')
    return value if _CODE_RE.fullmatch(value) else None
  return None


class BaozunExpandAPI:

  def __init__(self, base_url: str = GATEWAY, account: BaozunAccountAPI = None):
    self.base_url = base_url.rstrip("/")
    self.tenant = _get_secret("BAOZUN_TENANT", "baozun")
    self.app_id = _get_secret("BAOZUN_APPKEY", "ross-modern-api")
    self.account = account or BaozunAccountAPI(tenant=self.tenant, appkey=self.app_id)
    self.session = _new_session()
    self.token = ""
    self.pending = None  # 等待人工验证码的登录（OtpRequiredError）
    # 一把锁串行化所有请求与登录：多人同时使用时只会发一次验证码，会话也不会被并发读写
    self._lock = threading.RLock()

  # ------------------------------------------------------------------
  # 登录
  # ------------------------------------------------------------------
  def ensure_login(self):
    """确保已登录；需要人工输入验证码时抛出 LoginRequired"""
    with self._lock:
      if self.token:
        return
      if self.pending:
        raise LoginRequired()
      if self._reuse_cached_login():
        return
      self._login()

  def _login(self):
    """完整登录：UAAC 密码 + 邮箱验证码 → 票据 → 在网关兑换会话"""
    self.token = ""
    try:
      result = self.account.login_full()
    except OtpRequiredError as e:
      self.pending = e
      raise LoginRequired() from e
    self._apply_login(result)

  def complete_login_with_otp(self, otp_code: str):
    """用人工输入的验证码完成等待中的登录"""
    with self._lock:
      if not self.pending:
        return  # 已被其他人完成
      e = self.pending
      result = self.account.complete_login_with_otp(otp_code, e.session, e.tenant, e.appkey)
      self.pending = None
      self._apply_login(result)

  def _apply_login(self, result: dict):
    self.session = result["session"]
    self.token = result["token"]
    self.tenant = result["tenant"]
    if not self._exchange_login():
      self.token = ""
      raise ValueError("宝尊登录成功，但网关会话兑换失败，请稍后重试")
    self._save_login_cache()

  def _exchange_login(self) -> bool:
    """用 UAAC 票据在网关兑换 ross 与 iforce 应用会话"""
    for path in ("/ross-modern-api/login", "/iforce/login"):
      try:
        resp = self.session.post(
            self.base_url + path, json={}, headers=self._auth_headers(), timeout=15
        )
        if _json(resp).get("success") is not True:
          print(f"兑换登录 {path} 未成功: {resp.text[:120]}")
          return False
      except Exception as e:
        print(f"兑换登录 {path} 异常: {e}")
        return False
    return True

  def _save_login_cache(self):
    try:
      cookies = getattr(self.session, "cookies", {}) or {}
      pairs = cookies.items() if isinstance(cookies, dict) else ((c.name, c.value) for c in cookies)
      with open(LOGIN_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "cookie": "; ".join(f"{k}={v}" for k, v in pairs),
            "token": self.token,
            "tenant": self.tenant,
            "appkey": self.app_id,
            "ts": time.time(),
        }, f)
    except Exception as e:
      print(f"保存登录缓存失败: {e}")

  def _reuse_cached_login(self) -> bool:
    """服务重启后复用磁盘上的登录会话，避免重新走验证码"""
    try:
      with open(LOGIN_CACHE_FILE, "r", encoding="utf-8") as f:
        cache = json.load(f)
    except Exception:
      return False
    if not cache.get("cookie") or not cache.get("token"):
      return False
    if hasattr(self.session, "cookies"):
      self.session.cookies.update(parse_cookie_string(cache["cookie"]))
    self.token = cache["token"]
    self.tenant = cache.get("tenant", self.tenant)
    self.app_id = cache.get("appkey", self.app_id)
    if self._exchange_login():
      print("已复用缓存的登录会话")
      return True
    self.token = ""
    return False

  # ------------------------------------------------------------------
  # 请求
  # ------------------------------------------------------------------
  def _auth_headers(self) -> dict:
    return {
        "token": self.token or "",
        "saasTenantCode": self.tenant or "baozun",
        "saasTenantToken": self.token or "",
        "appId": self.app_id or "ross-modern",
    }

  @staticmethod
  def _is_auth_fail(text: str) -> bool:
    return ("UAAC" in text and "鉴权" in text) or "token失效" in text

  def _request(self, method: str, path: str, **kwargs):
    """发请求；登录失效时重新登录并重试，最多一次"""
    self.ensure_login()
    for attempt in range(2):
      with self._lock:
        used_token = self.token
        resp = getattr(self.session, method)(
            self.base_url + path, headers=self._auth_headers(), **kwargs
        )
      if not self._is_auth_fail(resp.text):
        return resp
      if attempt == 1:
        raise ValueError("宝尊登录已失效，重新登录后仍被拒绝，请稍后重试")
      with self._lock:
        if self.token == used_token:  # 其他人还没刷新过，才由自己重新登录
          self._login()

  # ------------------------------------------------------------------
  # 业务接口
  # ------------------------------------------------------------------
  def upload_image(self, file_bytes: bytes, filename: str) -> str:
    """1. 上传图片，返回附件编号"""
    for path in UPLOAD_PATHS:
      resp = self._request(
          "post", path, files={"file": (filename, file_bytes)}, timeout=(10, 60)
      )
      if resp.status_code in (404, 405):
        continue
      data = _json(resp)
      if isinstance(data, dict):
        if data.get("success") is not True:
          raise ValueError(f"上传图片失败: {data.get('message') or data}")
        inner = data.get("data")
        if isinstance(inner, dict):
          inner = inner.get("attachmentCode") or inner.get("originalAttachmentCode")
        code = _as_code(inner)
      else:
        code = _as_code(data)
      if code:
        return code
      raise ValueError(f"上传图片失败: 宝尊返回内容无法识别 ({str(data)[:120]})")
    raise ValueError("上传图片失败: 宝尊上传接口均不存在 (404)")

  def submit_image_expand(
      self,
      original_attachment_code: str,
      top_distance: int,
      bottom_distance: int,
      left_distance: int,
      right_distance: int,
      background_weight: int,
      background_height: int,
      original_weight: int,
      original_height: int,
      generated_num: int = 1,
  ) -> str:
    """2. 提交扩图任务，返回任务编号"""
    payload = {
        "originalAttachmentCode": original_attachment_code,
        "topDistance": top_distance,
        "bottomDistance": bottom_distance,
        "leftDistance": left_distance,
        "rightDistance": right_distance,
        "backgroundWeight": background_weight,
        "backgroundHeight": background_height,
        "originalWeight": original_weight,
        "originalHeight": original_height,
        "generatedNum": generated_num,
        "ratio": "free",
        "prompt": "",
        "generateChannel": 110,
    }
    data = _json(self._request("post", "/iforce/art/image/imageExpand", json=payload, timeout=15))
    if isinstance(data, dict):
      if data.get("success") is not True:
        raise ValueError(f"提交扩图任务失败: {data.get('message') or data}")
      inner = data.get("data")
      if isinstance(inner, dict):
        inner = inner.get("recordCode") or inner.get("id")
      code = _as_code(inner) or _as_code(data.get("recordCode"))
    else:
      code = _as_code(data)
    if code:
      return code
    raise ValueError(f"提交扩图任务失败: 宝尊返回内容无法识别 ({str(data)[:120]})")

  def get_image_expand_result(
      self,
      record_code: str,
      expected_count: int = 1,
      timeout: int = 180,
      poll_interval: int = 3,
      on_tick=None,
  ) -> list:
    """3. 轮询结果，拿到 expected_count 张图后返回图片地址列表。
    on_tick(已等待秒数) 每轮回调一次，用于界面显示进度。"""
    start = time.time()
    urls, last = [], ""
    while time.time() - start < timeout:
      data = _json(self._request(
          "get", "/iforce/art/image/getImageExpand",
          params={"recordCode": record_code}, timeout=15,
      ))
      if isinstance(data, dict):
        if data.get("success") is False:
          raise ValueError(f"扩图失败: {data.get('message') or data}")
        inner = data.get("data") or {}
        items = inner.get("resultList") if isinstance(inner, dict) else None
        urls = [i["attachmentPath"] for i in items or [] if isinstance(i, dict) and i.get("attachmentPath")]
        if len(urls) >= max(1, int(expected_count)):
          return urls
        last = f"status={inner.get('status') if isinstance(inner, dict) else '?'}，已返回 {len(urls)} 张"
      if on_tick:
        on_tick(int(time.time() - start))
      time.sleep(poll_interval)
    if urls:
      return urls
    raise TimeoutError(f"扩图超时（{timeout // 60} 分钟）。宝尊最新状态: {last}")
