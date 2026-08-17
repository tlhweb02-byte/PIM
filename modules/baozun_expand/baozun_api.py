import time
import requests

try:
  from scrapling.fetchers import FetcherSession
except ImportError:
  FetcherSession = None

from .account_api import (
    BaozunAccountAPI,
    _get_secret,
    parse_cookie_string,
)


def _safe_get(obj, key, default=None):
  if isinstance(obj, dict):
    return obj.get(key, default)
  return default


class BaozunExpandAPI:

  def __init__(
      self,
      base_url: str = "https://union-gateway.baozun.com",
      manual_cookie: str = "",
      cookie_str: str = "",
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

    if cookie_val:
      parsed_cookies = parse_cookie_string(cookie_val)
      if hasattr(self.session, "cookies"):
        self.session.cookies.update(parsed_cookies)
    else:
      self.account_mgr = BaozunAccountAPI(
          tenant=self.saas_tenant_code, appkey=self.app_id
      )
      self.sync_login_from_account()

  # ------------------------------------------------------------------
  # 自动登录（UAAC 密码 + 邮箱验证码 + 网关票据兑换）
  # ------------------------------------------------------------------
  def sync_login_from_account(self, force_refresh: bool = False):
    """完整自动登录：UAAC 登录拿票据 → 在 union-gateway 兑换应用会话"""
    if self.is_using_manual_cookie:
      return

    result = self.account_mgr.login_full()
    self.session = result["session"]  # 继承 UAAC 会话 Cookie（含 SECURITY_ID）
    self.token = result["token"]
    self.saas_tenant_code = result["tenant"]
    self._exchange_login()

  def _exchange_login(self):
    """用 UAAC 票据在 union-gateway 上兑换 ross 与 iforce 应用会话"""
    headers = self._auth_headers()
    for path in ("/ross-modern-api/login", "/iforce/login"):
      try:
        resp = self.session.post(
            self.base_url + path, json={}, headers=headers, timeout=15
        )
        data = _safe_get(resp.json(), "success")
        if data is not True:
          print(f"兑换登录 {path} 未成功: {resp.text[:120]}")
      except Exception as e:
        print(f"兑换登录 {path} 异常: {e}")

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
      self, record_code: str, poll_interval: int = 3, timeout: int = 180
  ) -> list:
    """3. 轮询扩图生成结果"""
    url = f"{self.base_url}/iforce/art/image/getImageExpand"
    start_time = time.time()
    last_summary = ""

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
              if urls:
                return urls

            status = _safe_get(data, "status") or _safe_get(res_data, "status")
            last_summary = f"生成状态 status={status}"
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

    raise TimeoutError(f"扩图任务超时 (3分钟)。宝尊最新状态: {last_summary}")
