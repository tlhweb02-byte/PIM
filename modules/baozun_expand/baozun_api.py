import json
import os
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


def _safe_get(obj, key, default=None):
  if isinstance(obj, dict):
    return obj.get(key, default)
  return default


# 登录会话缓存文件：保存 Cookie + 票据，下次运行直接复用（类似浏览器记住登录态）
LOGIN_CACHE_FILE = os.path.join(
    os.path.dirname(__file__), "baozun_login_cache.json"
)


class BaozunExpandAPI:

  def __init__(
      self,
      base_url: str = "https://union-gateway.baozun.com",
      manual_cookie: str = "",
      cookie_str: str = "",
      auth_result: dict = None,
      **kwargs,
  ):
    self.base_url = base_url.rstrip("/")
    cookie_val = manual_cookie or cookie_str
    self.is_using_manual_cookie = bool(cookie_val)

    if FetcherSession is not None:
      self.session = FetcherSession(impersonate="chrome")
    else:
      self.session = requests.Session()

    default_headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            " (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
    }
    if hasattr(self.session, "headers"):
      self.session.headers.update(default_headers)

    # 认证上下文（token / 租户 / 应用标识）
    self.token = ""
    self.saas_tenant_code = _get_secret("BAOZUN_TENANT", "baozun")
    self.app_id = _get_secret("BAOZUN_APPKEY", "ross-modern-api")
    # 自动登录是否在等待人工验证码
    self.login_pending = False
    self._pending_login = None

    if cookie_val:
      parsed_cookies = parse_cookie_string(cookie_val)
      if hasattr(self.session, "cookies"):
        self.session.cookies.update(parsed_cookies)
    elif auth_result:
      self.is_using_manual_cookie = False
      self._apply_login(auth_result)
    else:
      self.is_using_manual_cookie = False
      self.account_mgr = BaozunAccountAPI(
          tenant=self.saas_tenant_code, appkey=self.app_id
      )
      # 优先复用磁盘缓存的登录会话（避免每次都走密码+验证码）
      if not self._try_reuse_cached_login():
        try:
          self.sync_login_from_account()
        except OtpRequiredError as e:
          # 验证码已发送但自动读取超时：进入"等待人工输入验证码"状态
          self.login_pending = True
          self._pending_login = e

  # ------------------------------------------------------------------
  # 自动登录（UAAC 密码 + 邮箱验证码 + 网关票据兑换）
  # ------------------------------------------------------------------
  def sync_login_from_account(self, force_refresh: bool = False):
    """完整自动登录：UAAC 登录拿票据 → 在 union-gateway 兑换应用会话"""
    if self.is_using_manual_cookie:
      return

    result = self.account_mgr.login_full()
    self._apply_login(result)
    self._exchange_login()
    self._save_login_cache()

  def complete_login_with_otp(self, otp_code: str):
    """自动读取验证码超时后，用人工输入的验证码完成登录并继续"""
    if not self._pending_login:
      raise ValueError("当前没有待完成的登录，请重新点击生成")
    e = self._pending_login
    self._pending_login = None
    self.login_pending = False
    result = self.account_mgr.complete_login_with_otp(
        otp_code, e.session, e.tenant, e.appkey
    )
    self._apply_login(result)
    self._exchange_login()
    self._save_login_cache()
    return self

  def _apply_login(self, result: dict):
    """应用登录结果：继承 UAAC 会话 + 保存票据/租户"""
    self.session = result["session"]
    self.token = result["token"]
    self.saas_tenant_code = result["tenant"]

  def _cookies_to_str(self) -> str:
    """把会话 Cookie 序列化为字符串（用于持久化缓存）"""
    cj = getattr(self.session, "cookies", None)
    if cj is None:
      return ""
    parts = []
    try:
      if isinstance(cj, dict):
        for k, v in cj.items():
          parts.append(f"{k}={v}")
      else:
        for c in cj:
          parts.append(f"{c.name}={c.value}")
    except Exception:
      pass
    return "; ".join(parts)

  def _save_login_cache(self):
    """持久化登录会话（Cookie + 票据 + 租户），供下次运行复用"""
    try:
      data = {
          "cookie": self._cookies_to_str(),
          "token": self.token,
          "tenant": self.saas_tenant_code,
          "appkey": self.app_id,
          "ts": time.time(),
      }
      with open(LOGIN_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f)
    except Exception as e:
      print(f"保存登录缓存失败: {e}")

  def _try_reuse_cached_login(self) -> bool:
    """尝试复用磁盘缓存登录态：还原 Cookie + 票据，再兑换会话验证有效性"""
    try:
      with open(LOGIN_CACHE_FILE, "r", encoding="utf-8") as f:
        cache = json.load(f)
    except Exception:
      return False

    cookie_str = cache.get("cookie", "")
    token = cache.get("token", "")
    tenant = cache.get("tenant", "baozun")
    appkey = cache.get("appkey", "ross-modern-api")
    if not cookie_str or not token:
      return False

    parsed = parse_cookie_string(cookie_str)
    if hasattr(self.session, "cookies"):
      self.session.cookies.update(parsed)
    self.token = token
    self.saas_tenant_code = tenant
    self.app_id = appkey

    if self._exchange_login():
      print("已复用缓存的登录会话，无需重新验证")
      return True

    # 缓存失效：清空，走完整登录
    self.token = ""
    return False

  def _exchange_login(self) -> bool:
    """用 UAAC 票据在 union-gateway 上兑换 ross 与 iforce 应用会话；返回是否全部成功"""
    headers = self._auth_headers()
    ok = True
    for path in ("/ross-modern-api/login", "/iforce/login"):
      try:
        resp = self.session.post(
            self.base_url + path, json={}, headers=headers, timeout=15
        )
        data = _safe_get(resp.json(), "success")
        if data is not True:
          ok = False
          print(f"兑换登录 {path} 未成功: {resp.text[:120]}")
      except Exception as e:
        ok = False
        print(f"兑换登录 {path} 异常: {e}")
    return ok

  def _auth_headers(self) -> dict:
    """所有 union-gateway 请求都必须携带的认证头"""
    return {
        "token": self.token or "",
        "saasTenantCode": self.saas_tenant_code or "baozun",
        "saasTenantToken": self.token or "",
        "appId": self.app_id or "ross-modern",
    }

  def _is_auth_fail(self, resp_text: str) -> bool:
    """判断响应是否为鉴权失败（需要重新登录）"""
    return (
        "UAAC" in resp_text and "鉴权" in resp_text
    ) or "token失效" in resp_text

  # ------------------------------------------------------------------
  # 业务接口
  # ------------------------------------------------------------------
  def upload_image(self, file_bytes: bytes, filename: str) -> str:
    """1. 上传图片到宝尊节点"""
    possible_urls = [
        f"{self.base_url}/iforce/art/image/upload/rename",
        f"{self.base_url}/iforce/art/image/upload",
        f"{self.base_url}/iforce/art/upload/rename",
        f"{self.base_url}/upload/rename",
    ]

    files = {"file": (filename, file_bytes)}
    headers = self._auth_headers()

    attempt_logs = []
    for url in possible_urls:
      try:
        resp = self.session.post(url, files=files, headers=headers,
                                 timeout=(10, 60))
        if resp.status_code == 200:
          try:
            res_data = resp.json()
          except Exception:
            res_data = resp.text.strip().strip('"')

          if isinstance(res_data, str) and res_data.strip():
            if self._is_auth_fail(res_data):
              attempt_logs.append(f"[{url}] UAAC 鉴权失效")
            else:
              return res_data.strip().strip('"')

          elif isinstance(res_data, dict):
            if res_data.get("success") is True:
              code = (
                  _safe_get(res_data.get("data"), "attachmentCode")
                  or _safe_get(res_data, "data")
              )
              if isinstance(code, dict):
                code = _safe_get(code, "attachmentCode")
              if code and str(code) != "None":
                return str(code)

            data = res_data.get("data")
            if isinstance(data, str) and data.strip():
              return data.strip().strip('"')

            if self._is_auth_fail(resp.text):
              attempt_logs.append(f"[{url}] UAAC 鉴权失效")
              continue

            code = (
                _safe_get(data, "originalAttachmentCode")
                or _safe_get(res_data, "originalAttachmentCode")
                or _safe_get(res_data, "code")
            )
            if code:
              return str(code)

            attempt_logs.append(f"[{url}] 未包含 Code: {res_data}")
        else:
          attempt_logs.append(f"[{url}] HTTP状态码 {resp.status_code}")
      except Exception as e:
        attempt_logs.append(f"[{url}] 请求失败: {str(e)}")

    if any("鉴权失效" in log for log in attempt_logs):
      if self.is_using_manual_cookie:
        raise ValueError(
            "手动传入的 Cookie 鉴权失败！请从 ROSS 页面重新复制包含"
            " SESSION/UAAC/token 的登录凭证。"
        )
      self.sync_login_from_account(force_refresh=True)
      return self.upload_image(file_bytes, filename)

    raise ValueError(
        "所有上传接口路由均未成功返回 Code。日志: " + " | ".join(attempt_logs)
    )

  def submit_image_expand(
      self,
      original_attachment_code: str,
      top_distance: int = 140,
      bottom_distance: int = 140,
      left_distance: int = 205,
      right_distance: int = 205,
      background_weight: int = 800,
      background_height: int = 800,
      original_weight: int = 390,
      original_height: int = 520,
      generated_num: int = 4,
      ratio: str = "free",
      prompt: str = "",
  ) -> str:
    """2. 提交扩图任务"""
    url = f"{self.base_url}/iforce/art/image/imageExpand"

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
        "ratio": ratio,
        "prompt": prompt,
        "generateChannel": 110,
    }

    resp = self.session.post(
        url, json=payload, headers=self._auth_headers(), timeout=15
    )
    try:
      res_data = resp.json()
    except Exception:
      res_data = resp.text.strip().strip('"')

    if isinstance(res_data, str) and res_data.strip():
      if self._is_auth_fail(res_data):
        if self.is_using_manual_cookie:
          raise ValueError(
              "手动传入的 Cookie 鉴权验证失败！请从 ROSS 页面重新复制有效的登录 Cookie。"
          )
        self.sync_login_from_account(force_refresh=True)
        resp = self.session.post(
            url, json=payload, headers=self._auth_headers(), timeout=15
        )
        res_data = resp.json()
      else:
        return res_data.strip().strip('"')

    if isinstance(res_data, dict):
      if res_data.get("success") is True:
        data = res_data.get("data")
        if isinstance(data, str) and data.strip():
          return data.strip().strip('"')
        record_code = (
            _safe_get(data, "recordCode")
            or _safe_get(res_data, "recordCode")
            or _safe_get(res_data, "id")
        )
        if record_code:
          return str(record_code)

      if self._is_auth_fail(resp.text):
        if self.is_using_manual_cookie:
          raise ValueError(
              "手动传入的 Cookie 鉴权验证失败！请从 ROSS 页面重新复制有效的登录 Cookie。"
          )
        self.sync_login_from_account(force_refresh=True)
        resp = self.session.post(
            url, json=payload, headers=self._auth_headers(), timeout=15
        )
        res_data = resp.json()
        data = res_data.get("data") if isinstance(res_data, dict) else None
        record_code = (
            _safe_get(data, "recordCode")
            or _safe_get(res_data, "recordCode")
            or _safe_get(res_data, "id")
        )
        if record_code:
          return str(record_code)

      data = res_data.get("data")
      record_code = (
          _safe_get(data, "recordCode")
          or _safe_get(res_data, "recordCode")
          or _safe_get(res_data, "id")
      )
      if record_code:
        return str(record_code)

    raise ValueError(f"提交扩图任务失败: {res_data}")

  def get_image_expand_result(
      self,
      record_code: str,
      poll_interval: int = 3,
      timeout: int = 180,
      expected_count: int = 1,
  ) -> list:
    """3. 轮询扩图生成结果（等待返回 expected_count 张图后结束）"""
    url = f"{self.base_url}/iforce/art/image/getImageExpand"
    start_time = time.time()
    last_summary = ""
    collected_urls = []

    while time.time() - start_time < timeout:
      resp = self.session.get(
          url,
          params={"recordCode": record_code},
          headers=self._auth_headers(),
          timeout=15,
      )

      if resp.status_code == 200:
        try:
          res_data = resp.json()
          data = _safe_get(res_data, "data") or res_data

          if isinstance(data, dict):
            if _safe_get(res_data, "success") is False:
              if self._is_auth_fail(resp.text):
                if self.is_using_manual_cookie:
                  raise ValueError(
                      "手动输入的 Cookie 鉴权失败！请从 ROSS 页面重新复制登录凭证。"
                  )
                self.sync_login_from_account(force_refresh=True)
                continue
              raise ValueError(
                  "处理失败: " + str(_safe_get(res_data, "message"))
              )

            result_list = _safe_get(data, "resultList", [])
            if result_list and isinstance(result_list, list):
              urls = [
                  _safe_get(item, "attachmentPath")
                  for item in result_list
                  if isinstance(item, dict)
                  and _safe_get(item, "attachmentPath")
              ]
              collected_urls = urls
              # 生成数量达到预期即返回；否则继续轮询等待剩余图片
              if len(urls) >= max(1, int(expected_count)):
                return urls

            status = _safe_get(data, "status") or _safe_get(res_data, "status")
            last_summary = (
                f"生成状态 status={status}, 已返回 {len(collected_urls)} 张"
            )
          else:
            if self._is_auth_fail(str(res_data)):
              if self.is_using_manual_cookie:
                raise ValueError(
                    "手动输入的 Cookie 鉴权失败！请从 ROSS 页面重新复制登录凭证。"
                )
              self.sync_login_from_account(force_refresh=True)
              continue
            last_summary = f"返回数据: {res_data}"
        except ValueError as ve:
          raise ve
        except Exception as e:
          last_summary = f"解析数据异常: {e}"

      time.sleep(poll_interval)

    # 超时：若已拿到部分图片则返回，否则报错
    if collected_urls:
      return collected_urls
    raise TimeoutError(f"扩图任务超时 (3分钟)。宝尊最新状态: {last_summary}")
