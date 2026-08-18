# -*- coding: utf-8 -*-
"""
宝尊「投放打标管理」API 客户端（design-web / design-marking 服务）
==================================================================
- 复用 baozun_expand 的 UAAC 登录体系（同账号密码，租户固定 NIKE）
- 登录链路：UAAC 密码 + 邮箱验证码 → 票据 token → findSaas 拿 saasTenantToken
  → ross-token 换 Bearer 票据 → 携带店铺上下文调用 design-marking 接口
- 目标店铺：NIKE 官方 outlets（shopInfo_NIKE0S02 → id=971706, code=NIKE0S02）
"""
import json
import os
import pickle
import time

import requests

try:
    from scrapling.fetchers import FetcherSession
except ImportError:
    FetcherSession = None

from ..baozun_expand.account_api import (
    BaozunAccountAPI,
    OtpRequiredError,
    _get_secret,
)

# 租户与接口配置
TENANT = "NIKE"                 # 宝尊 NIKE 租户
APPKEY = "pim2"                 # pim2 前端应用标识（与菜单接口一致）
ROSS_GATEWAY = "https://ross-api.baozun.com"   # design-web 的 ROSS 网关
UAAC_BASE = "https://api-base-ecs.baozun.com"
ROSS_AUTH = "https://ross-auth.baozun.com"

# 默认店铺：NIKE 官方 outlets 店
DEFAULT_SHOP = {
    "id": 971706,
    "code": "NIKE0S02",
    "name": "nike官方outlets店",
    "financialCode": "NIKE0S02",
    "platformCode": "TMALL",
    "platformName": "TMALL",
    "platformDesc": "天猫",
    "opDomainCode": "NIKEOUTLETS",
    "opDomainName": "NIKEOUTLETS",
    "lessee": "NIKE",
    "saasTenantCode": "NIKE",
}

# 登录会话缓存文件（Cookie + 票据 + ross-token）
LOGIN_CACHE_FILE = os.path.join(os.path.dirname(__file__), "marking_login_cache.pkl")

# 登录会话复用时长（秒）
_SESSION_TTL = 3 * 3600


def _safe_get(obj, key, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return default


class BaozunMarkingAPI:
    """投放打标管理 API 客户端（只读查询 + 投放/打标任务操作）"""

    def __init__(self, manual_cookie: str = ""):
        self.base_url = ROSS_GATEWAY.rstrip("/")
        self.is_using_manual_cookie = bool(manual_cookie)
        self.login_pending = False
        self._pending_login = None
        self.token = ""            # UAAC 票据
        self.saas_token = ""       # findSaas 返回的 saasTenantToken
        self.ross_token = ""       # Bearer JWT
        self.shop = dict(DEFAULT_SHOP)
        self._ts = 0.0

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

        if manual_cookie:
            from ..baozun_expand.account_api import parse_cookie_string
            parsed = parse_cookie_string(manual_cookie)
            if hasattr(self.session, "cookies"):
                self.session.cookies.update(parsed)
            self.is_using_manual_cookie = True
            self._ts = time.time()
            # 手动 Cookie 模式：浏览器 Cookie 里通常带 ross_token，可作 Bearer
            self.ross_token = parsed.get("ross_token", "")
            self.token = parsed.get("token", "")
            self.saas_token = parsed.get("saasTenantToken", "")
        else:
            self.account_mgr = BaozunAccountAPI(tenant=TENANT, appkey=APPKEY)
            if not self._try_reuse_cached_login():
                self._start_login()

    # ------------------------------------------------------------------
    # 登录
    # ------------------------------------------------------------------
    def _start_login(self):
        """发起完整登录；验证码自动读取失败时进入人工输入流程"""
        try:
            self.sync_login_from_account()
        except OtpRequiredError as e:
            self.login_pending = True
            self._pending_login = e

    def sync_login_from_account(self, force_refresh: bool = False):
        """UAAC 登录 → 票据 → findSaas → ross-token"""
        result = self.account_mgr.login_full()
        self.session = result["session"]
        self.token = result["token"]
        self._fetch_saas_and_ross()
        self._save_cache()

    def complete_login_with_otp(self, otp_code: str):
        """人工输入验证码后完成登录"""
        if not self._pending_login:
            raise ValueError("当前没有待完成的登录，请重新操作")
        e = self._pending_login
        self._pending_login = None
        self.login_pending = False
        result = self.account_mgr.complete_login_with_otp(
            otp_code, e.session, e.tenant, e.appkey
        )
        self.session = result["session"]
        self.token = result["token"]
        self._fetch_saas_and_ross()
        self._save_cache()
        return self

    def _fetch_saas_and_ross(self):
        """findSaas → saasTenantToken；ross-token → Bearer"""
        try:
            r = self.session.post(
                UAAC_BASE + "/api/uaac/account/findSaas",
                json={},
                headers={"token": self.token, "saasTenantCode": TENANT,
                         "saasTenantToken": self.token, "appId": APPKEY},
                timeout=20,
            ).json()
            data = r.get("data") or {}
            self.saas_token = (
                data.get("saasTenantToken") or data.get("sassTenantToken") or ""
            )
        except Exception as e:
            print(f"[marking] findSaas 失败: {e}")
            self.saas_token = ""

        try:
            r1 = self.session.get(
                self.base_url + "/tmpl/ross-token",
                headers=self._auth_headers(), timeout=20,
            )
            rt = r1.json().get("data") or ""
            if rt and not str(rt).startswith("["):
                self.ross_token = str(rt)
        except Exception as e:
            print(f"[marking] ross-token 失败: {e}")
            self.ross_token = ""

    # ------------------------------------------------------------------
    # 缓存复用
    # ------------------------------------------------------------------
    def _cookies_to_str(self) -> str:
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

    def _save_cache(self):
        try:
            data = {
                "cookie": self._cookies_to_str(),
                "token": self.token,
                "saas_token": self.saas_token,
                "ross_token": self.ross_token,
                "shop": self.shop,
                "ts": time.time(),
            }
            with open(LOGIN_CACHE_FILE, "wb") as f:
                pickle.dump(data, f)
        except Exception as e:
            print(f"[marking] 保存登录缓存失败: {e}")

    def _try_reuse_cached_login(self) -> bool:
        try:
            with open(LOGIN_CACHE_FILE, "rb") as f:
                cache = pickle.load(f)
        except Exception:
            return False
        if not cache or not cache.get("cookie"):
            return False
        if time.time() - cache.get("ts", 0) > _SESSION_TTL:
            return False
        from ..baozun_expand.account_api import parse_cookie_string
        parsed = parse_cookie_string(cache["cookie"])
        if hasattr(self.session, "cookies"):
            self.session.cookies.update(parsed)
        self.token = cache.get("token", "")
        self.saas_token = cache.get("saas_token", "")
        self.ross_token = cache.get("ross_token", "")
        self.shop = cache.get("shop") or dict(DEFAULT_SHOP)
        self._ts = cache.get("ts", time.time())

        # 校验票据是否仍有效（重新 findSaas + 刷新 ross-token）
        try:
            r = self.session.post(
                UAAC_BASE + "/api/uaac/account/findSaas",
                json={},
                headers={"token": self.token, "saasTenantCode": TENANT,
                         "saasTenantToken": self.token, "appId": APPKEY},
                timeout=20,
            ).json()
            if r.get("code") == "0":
                data = r.get("data") or {}
                self.saas_token = (
                    data.get("saasTenantToken") or data.get("sassTenantToken") or ""
                )
                # 刷新 ross-token（可能过期）
                try:
                    r1 = self.session.get(
                        self.base_url + "/tmpl/ross-token",
                        headers=self._auth_headers(), timeout=20,
                    )
                    rt = r1.json().get("data") or ""
                    if rt and not str(rt).startswith("["):
                        self.ross_token = str(rt)
                except Exception:
                    pass
                self._ts = time.time()
                return True
        except Exception:
            pass
        return False

    # ------------------------------------------------------------------
    # 请求封装
    # ------------------------------------------------------------------
    def _auth_headers(self) -> dict:
        h = {
            "token": self.token or "",
            "saasTenantToken": self.saas_token or self.token or "",
            "saasTenantCode": TENANT,
            "tenantCode": TENANT,
            "X-ROSS-APP": "design",
            "platform": self.shop.get("platformCode", ""),
            "catalog": self.shop.get("opDomainCode", ""),
            "opDomain": self.shop.get("opDomainCode", ""),
            "opd": self.shop.get("opDomainCode", ""),
            "financialCode": self.shop.get("financialCode", ""),
            "current-shop-code": self.shop.get("code", ""),
            "current-shop-id": str(self.shop.get("id", "")),
            "Content-Type": "application/json",
        }
        if self.ross_token:
            h["authorization"] = "Bearer " + self.ross_token
        return h

    def _request(self, method: str, path: str, payload=None, params=None, timeout=25):
        """带自动重登的请求封装"""
        url = path if path.startswith("http") else self.base_url + path
        for attempt in (1, 2):
            try:
                resp = self.session.request(
                    method, url,
                    json=payload if payload is not None else None,
                    params=params,
                    headers=self._auth_headers(),
                    timeout=timeout,
                )
                try:
                    data = resp.json()
                except Exception:
                    return {"status": resp.status_code, "raw": resp.text[:500]}

                # UAAC 鉴权失效 → 重新登录后重试一次
                if resp.status_code == 200 and isinstance(data, dict):
                    code = str(data.get("code", ""))
                    msg = str(data.get("message", "")) + str(data.get("data", ""))
                    if code == "30100" and ("UAAC" in msg or "鉴权" in msg) \
                            and attempt == 1 and not self.is_using_manual_cookie:
                        try:
                            self.sync_login_from_account(force_refresh=True)
                        except OtpRequiredError:
                            self.login_pending = True
                            return {"status": 0, "error": "需要重新登录（验证码）",
                                    "otp_required": True}
                        continue
                return data
            except Exception as e:
                if attempt == 2 or self.is_using_manual_cookie:
                    return {"error": str(e), "status": 0}
        return {"error": "unknown", "status": 0}

    def _post(self, path, payload=None):
        return self._request("POST", path, payload=payload)

    def _get(self, path, params=None):
        return self._request("GET", path, params=params)

    # ------------------------------------------------------------------
    # 店铺
    # ------------------------------------------------------------------
    def fetch_shop_list(self) -> list:
        """按 opDomain 获取店铺列表（含投放/打标任务数，用于店铺选择器）"""
        op_domain = self.shop.get("opDomainCode") or DEFAULT_SHOP["opDomainCode"]
        try:
            r = self.session.post(
                self.base_url + "/design-marking/adapter/findOminiTaskCounts",
                json={"opDomainCode": op_domain},
                headers=self._auth_headers(), timeout=20,
            ).json()
            results = r.get("data") or r.get("results") or []
            out = []
            if isinstance(results, dict):
                results = results.get("results") or []
            for group in results:
                if not isinstance(group, dict):
                    continue
                for s in group.get("shops") or []:
                    if isinstance(s, dict) and s.get("shopCode"):
                        out.append({
                            "id": s.get("id"), "code": s.get("shopCode"),
                            "name": s.get("shopName") or s.get("name"),
                            "financialCode": s.get("financialCode"),
                            "platformCode": group.get("platform") or s.get("platformCode"),
                            "opDomainCode": op_domain,
                            "lessee": TENANT,
                            "pushTaskCount": s.get("pushTaskCount"),
                            "pushStrategyCount": s.get("pushStrategyCount"),
                        })
            # 兜底：至少包含默认店铺
            if not out:
                out.append(dict(DEFAULT_SHOP))
            return out
        except Exception as e:
            print(f"[marking] 获取店铺列表失败: {e}")
            return [dict(DEFAULT_SHOP)]

    def set_shop(self, shop: dict):
        """切换当前店铺"""
        self.shop = dict(shop)
        self._save_cache()

    # ------------------------------------------------------------------
    # 投放管理（投放策略 / push）
    # ------------------------------------------------------------------
    def list_push(self, shop_code: str = "", push_status: str = "All",
                  keyword: str = "", page: int = 1, page_size: int = 20) -> dict:
        """投放策略分页查询"""
        payload = {
            "pageNum": page,
            "pageSize": page_size,
            "data": {
                "shopId": shop_code or self.shop["code"],
                "pushStatus": push_status or "All",
            },
        }
        if keyword:
            payload["data"]["pushStrategyName"] = keyword
        data = self._post("/design-marking/push/page", payload)
        body = data.get("data") if isinstance(data, dict) else None
        if isinstance(body, dict):
            return {
                "total": body.get("total", 0),
                "list": body.get("list", []) or [],
                "pageNum": body.get("pageNum", page),
                "pageSize": body.get("pageSize", page_size),
            }
        return {"total": 0, "list": [], "error": str(data)[:300]}

    def view_push(self, strategy_id) -> dict:
        """投放策略详情"""
        data = self._post("/design-marking/push/view", {"strategyId": strategy_id})
        if isinstance(data, dict):
            return data.get("data") or data
        return {}

    def push_history(self, strategy_id) -> list:
        """投放历史"""
        data = self._get(f"/design-marking/push/pushHistory/{strategy_id}")
        if isinstance(data, dict):
            return data.get("data") or []
        return []

    def cancel_push(self, strategy_id) -> dict:
        """取消投放"""
        return self._post("/design-marking/push/cancel", {"strategyId": strategy_id})

    def end_push(self, strategy_id) -> dict:
        """结束投放"""
        return self._post("/design-marking/push/end", {"strategyId": strategy_id})

    def delete_push(self, strategy_id) -> dict:
        """删除投放"""
        return self._post("/design-marking/push/delete", {"strategyId": strategy_id})

    def re_push(self, task_id, effect_date="", close_date="2050-12-31 23:59:59",
                page: int = 1, page_size: int = 20) -> dict:
        """再次投放（定时/立即）"""
        payload = {
            "pageNum": page,
            "pageSize": page_size,
            "data": {
                "taskId": task_id,
                "closeDate": close_date or "2050-12-31 23:59:59",
            },
        }
        if effect_date:
            payload["data"]["effectDate"] = effect_date
        return self._post("/design-marking/push/rePush", payload)

    def search_latest_strategy_time(self) -> dict:
        """查询最新策略时间"""
        return self._get("/design-marking/push/searchLatestStrategyTime")

    def get_job_result(self, payload: dict) -> dict:
        """查询投放任务结果"""
        return self._post("/design-marking/push/getJobResult", payload)

    # ------------------------------------------------------------------
    # 打标任务（marking task）
    # ------------------------------------------------------------------
    def list_tasks(self, shop_code: str = "", group_id: str = "",
                   keyword: str = "", page: int = 1, page_size: int = 20,
                   task_type: str = "main") -> dict:
        """打标任务分页查询（与前端 MarkingMngUNEX.query 一致）"""
        payload = {
            "pageNum": page,
            "pageSize": page_size,
            "data": {
                "outShopId": shop_code or self.shop["code"],
                "taskType": task_type or "main",
                "taskName": keyword or "",
                "groupId": group_id or "",
            },
            "orderBy": "update_time desc",
        }
        data = self._post("/design-marking/task/list", payload)
        body = data.get("data") if isinstance(data, dict) else None
        if isinstance(body, dict):
            return {
                "total": body.get("total", 0),
                "list": body.get("list", []) or [],
                "pageNum": body.get("pageNum", page),
                "pageSize": body.get("pageSize", page_size),
            }
        return {"total": 0, "list": [], "error": str(data)[:300]}

    def create_task(self, out_shop_id: str, task_name: str, group_id: str = "",
                    shop_name: str = "") -> dict:
        """新建打标任务"""
        payload = {
            "outShopId": out_shop_id or self.shop["code"],
            "shopName": shop_name or self.shop.get("name", ""),
            "taskName": task_name,
            "taskType": "main",
            "groupId": group_id or "",
        }
        return self._post("/design-marking/task/save", payload)

    def copy_task(self, task_id, copy_task_name: str) -> dict:
        """复制打标任务"""
        return self._post("/design-marking/task/copy",
                          {"taskId": task_id, "copyTaskName": copy_task_name})

    def rename_task(self, task_id, task_name: str) -> dict:
        """重命名打标任务"""
        return self._post("/design-marking/task/update",
                          {"taskId": task_id, "taskName": task_name})

    def delete_task(self, task_id) -> dict:
        """删除打标任务"""
        return self._post("/design-marking/task/delete", {"taskId": task_id})

    def list_groups(self, shop_code: str = "") -> list:
        """分组列表（树形）"""
        data = self._post("/design-marking/group/list",
                          {"shopId": shop_code or self.shop["code"]})
        if isinstance(data, dict):
            return data.get("data") or []
        return []

    def level_list_groups(self, shop_code: str = "") -> list:
        """分组层级列表（用于创建/移动）"""
        data = self._post("/design-marking/group/levelList",
                          {"shopId": shop_code or self.shop["code"]})
        if isinstance(data, dict):
            return data.get("data") or []
        return []

    def create_group(self, group_name: str, parent_id: str = "") -> dict:
        """新建分组"""
        payload = {"groupName": group_name}
        if parent_id:
            payload["groupParentId"] = parent_id
        return self._post("/design-marking/group/save", payload)

    def delete_group(self, group_id) -> dict:
        """删除分组"""
        return self._post("/design-marking/group/modify",
                          {"groupId": group_id, "deleteFlag": True})

    def move_task_to_group(self, group_id, task_ids: list) -> dict:
        """移动任务到分组"""
        return self._post("/design-marking/task/updateGroup",
                          {"groupId": group_id, "taskIds": task_ids})

    # ------------------------------------------------------------------
    # 导出
    # ------------------------------------------------------------------
    def export_all_excel_before(self, payload: dict) -> dict:
        """导出前校验"""
        return self._post("/design-marking/wordy/exportAllExcelBefore", payload)


# 便捷别名
BaozunMarkingAPI.get_push_list = BaozunMarkingAPI.list_push
BaozunMarkingAPI.get_task_list = BaozunMarkingAPI.list_tasks
