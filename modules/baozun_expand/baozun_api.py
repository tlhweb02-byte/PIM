import time
import requests

try:
  from scrapling.fetchers import FetcherSession
except ImportError:
  FetcherSession = None

try:
  from .account_api import BaozunAccountAPI, parse_cookie_string
except ImportError:
  try:
    from modules.baozun_expand.account_api import (
        BaozunAccountAPI,
        parse_cookie_string,
    )
  except ImportError:
    from account_api import BaozunAccountAPI, parse_cookie_string


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
    """万能参数兼容初始化，同时支持 manual_cookie 和 cookie_str 参数名"""
    self.base_url = base_url.rstrip("/")

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

    self.account_mgr = BaozunAccountAPI()

    # 兼容 manual_cookie 与 cookie_str 两种传参名
    cookie_val = manual_cookie or cookie_str

    if cookie_val:
      parsed_cookies = parse_cookie_string(cookie_val)
      if hasattr(self.session, "cookies"):
        self.session.cookies.update(parsed_cookies)
    else:
      self.sync_cookies_from_account_mgr()

  def sync_cookies_from_account_mgr(self, force_refresh: bool = False):
    """自动维护最新有效的宝尊鉴权 Cookie"""
    if force_refresh:
      cookie_str = self.account_mgr.login_and_get_cookie_str()
    else:
      cookie_str = self.account_mgr.get_valid_cookie()

    if cookie_str:
      parsed_cookies = parse_cookie_string(cookie_str)
      if hasattr(self.session, "cookies"):
        self.session.cookies.update(parsed_cookies)

  def upload_image(self, file_bytes: bytes, filename: str) -> str:
    """1. 上传图片到宝尊节点"""
    possible_urls = [
        f"{self.base_url}/iforce/art/image/upload/rename",
        f"{self.base_url}/iforce/art/image/upload",
        f"{self.base_url}/iforce/art/upload/rename",
        f"{self.base_url}/upload/rename",
    ]

    files = {"file": (filename, file_bytes)}

    attempt_logs = []
    for url in possible_urls:
      try:
        resp = self.session.post(url, files=files, timeout=(10, 60))
        if resp.status_code == 200:
          try:
            res_data = resp.json()
          except Exception:
            res_data = resp.text.strip().strip('"')

          if isinstance(res_data, str) and res_data.strip():
            if "UAAC" in res_data or "鉴权" in res_data:
              attempt_logs.append(f"[{url}] UAAC 鉴权失效")
            else:
              return res_data.strip().strip('"')

          elif isinstance(res_data, dict):
            data = res_data.get("data")
            if isinstance(data, str) and data.strip():
              return data.strip().strip('"')

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

    if any("UAAC" in log for log in attempt_logs):
      self.sync_cookies_from_account_mgr(force_refresh=True)
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

    resp = self.session.post(url, json=payload, timeout=15)
    try:
      res_data = resp.json()
    except Exception:
      res_data = resp.text.strip().strip('"')

    if isinstance(res_data, str) and res_data.strip():
      if "UAAC" in res_data or "鉴权" in res_data:
        self.sync_cookies_from_account_mgr(force_refresh=True)
        resp = self.session.post(url, json=payload, timeout=15)
        res_data = resp.json()
      else:
        return res_data.strip().strip('"')

    if isinstance(res_data, dict):
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
          url, params={"recordCode": record_code}, timeout=15
      )

      if resp.status_code == 200:
        try:
          res_data = resp.json()
          data = _safe_get(res_data, "data") or res_data

          if isinstance(data, dict):
            if _safe_get(res_data, "success") is False:
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
            if "UAAC" in str(res_data):
              self.sync_cookies_from_account_mgr(force_refresh=True)
            last_summary = f"返回数据: {res_data}"
        except ValueError as ve:
          raise ve
        except Exception as e:
          last_summary = f"解析数据异常: {e}"

      time.sleep(poll_interval)

    raise TimeoutError(f"扩图任务超时 (3分钟)。宝尊最新状态: {last_summary}")
