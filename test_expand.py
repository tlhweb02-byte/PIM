"""智能扩图回归测试（全部用假的宝尊接口 / 假邮箱，不会调用真实账号）：
python -m unittest test_expand"""
import email.message
import email.utils
import io
import json
import os
import tempfile
import threading
import time
import unittest
from unittest import mock

from PIL import Image

from modules.baozun_expand import baozun_api
from modules.baozun_expand.account_api import BaozunAccountAPI
from modules.baozun_expand.app import compute_canvas, prepare_image
from modules.baozun_expand.baozun_api import BaozunExpandAPI

AUTH_FAIL = {"code": "30100", "success": "false", "data": "[x]UAAC鉴权验证失败!", "message": "系统异常"}


class FakeResp:
    def __init__(self, body, status=200):
        self.status_code = status
        self.text = body if isinstance(body, str) else json.dumps(body, ensure_ascii=False)
        self._body = body

    def json(self):
        if isinstance(self._body, str):
            raise ValueError("not json")
        return self._body


class FakeGateway:
    """按路径返回响应；handler(token) -> body 或 (body, status)"""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []
        self.cookies = {}

    def _do(self, url, headers=None, **_):
        path = url.replace(baozun_api.GATEWAY, "")
        self.calls.append(path)
        out = self.routes.get(path, lambda t: ({"success": True}, 200))(headers.get("token"))
        body, status = out if isinstance(out, tuple) else (out, 200)
        return FakeResp(body, status)

    post = get = _do


class FakeAccount:
    def __init__(self, gateway):
        self.gateway = gateway
        self.logins = 0
        self.lock = threading.Lock()

    def login_full(self):
        with self.lock:
            self.logins += 1
            n = self.logins
        time.sleep(0.05)
        return {"session": self.gateway, "token": f"T{n}", "tenant": "baozun"}


def make_api(routes):
    gw = FakeGateway(routes)
    acc = FakeAccount(gw)
    api = BaozunExpandAPI(account=acc)
    return api, gw, acc


class ApiTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.mkdtemp()
        patcher = mock.patch.object(baozun_api, "LOGIN_CACHE_FILE", os.path.join(tmp, "cache.json"))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_expired_login_relogs_once_then_succeeds(self):
        # T1 已失效，T2 有效
        upload = lambda t: AUTH_FAIL if t == "T1" else {"success": True, "data": "ATT123"}
        api, gw, acc = make_api({"/iforce/art/image/upload/rename": upload})
        self.assertEqual(api.upload_image(b"x", "a.jpg"), "ATT123")
        self.assertEqual(acc.logins, 2)

    def test_auth_error_text_is_never_taken_as_attachment_code(self):
        api, gw, acc = make_api({"/iforce/art/image/upload/rename": lambda t: AUTH_FAIL})
        with self.assertRaises(ValueError):
            api.upload_image(b"x", "a.jpg")
        self.assertEqual(acc.logins, 2)  # 初次登录 + 仅一次重新登录，不会无限递归

    def test_unrecognised_reply_is_rejected(self):
        api, _, _ = make_api({"/iforce/art/image/upload/rename": lambda t: {"success": True, "data": "<html>error page</html>"}})
        with self.assertRaises(ValueError):
            api.upload_image(b"x", "a.jpg")

    def test_falls_back_to_next_upload_path_only_on_404(self):
        api, gw, _ = make_api({
            "/iforce/art/image/upload/rename": lambda t: ("not found", 404),
            "/iforce/art/image/upload": lambda t: {"success": True, "data": {"attachmentCode": "ATT9"}},
        })
        self.assertEqual(api.upload_image(b"x", "a.jpg"), "ATT9")
        fail = lambda t: {"success": False, "message": "文件过大"}
        api, gw, _ = make_api({"/iforce/art/image/upload/rename": fail})
        with self.assertRaisesRegex(ValueError, "文件过大"):
            api.upload_image(b"x", "a.jpg")
        self.assertNotIn("/iforce/art/image/upload", gw.calls)

    def test_concurrent_users_trigger_a_single_relogin(self):
        api, _, acc = make_api({"/iforce/art/image/getImageExpand": lambda t: (
            AUTH_FAIL if t == "T1" else {"success": True, "data": {"resultList": [{"attachmentPath": "u1"}]}})})
        api.ensure_login()
        results = []
        threads = [threading.Thread(target=lambda: results.append(api.get_image_expand_result("R1"))) for _ in range(4)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        self.assertEqual(results, [["u1"]] * 4)
        self.assertEqual(acc.logins, 2)

    def test_upload_retries_once_on_network_error(self):
        import requests
        calls = {"n": 0}

        def flaky(token):
            calls["n"] += 1
            if calls["n"] == 1:
                raise requests.ConnectionError("Connection aborted: write operation timed out")
            return {"success": True, "data": "ATT5"}

        api, _, _ = make_api({"/iforce/art/image/upload/rename": flaky})
        self.assertEqual(api.upload_image(b"x" * 10, "a.jpg"), "ATT5")

        def dead(token):
            raise requests.ConnectionError("Connection aborted")

        api, _, _ = make_api({"/iforce/art/image/upload/rename": dead})
        with self.assertRaisesRegex(ValueError, "上传图片超时"):
            api.upload_image(b"x" * 10, "a.jpg")

    def test_submit_and_poll(self):
        api, _, _ = make_api({
            "/iforce/art/image/imageExpand": lambda t: {"success": True, "data": "REC42"},
            "/iforce/art/image/getImageExpand": lambda t: {"success": True, "data": {"resultList": [
                {"attachmentPath": "a"}, {"attachmentPath": "b"}]}},
        })
        rec = api.submit_image_expand("ATT", 1, 1, 1, 1, 10, 10, 8, 8, 2)
        self.assertEqual(rec, "REC42")
        self.assertEqual(api.get_image_expand_result(rec, expected_count=2), ["a", "b"])


class CanvasTests(unittest.TestCase):
    def test_original_ratio_centered(self):
        self.assertEqual(compute_canvas(800, 800, None, 0.4, "居中"),
                         {"bg_w": 1120, "bg_h": 1120, "top_d": 160, "bottom_d": 160, "left_d": 160, "right_d": 160})

    def test_square_ratio_bottom_anchor(self):
        c = compute_canvas(400, 300, (1, 1), 0.2, "靠下")
        self.assertEqual((c["bg_w"], c["bg_h"]), (480, 480))
        self.assertEqual((c["top_d"], c["bottom_d"], c["left_d"], c["right_d"]), (180, 0, 40, 40))

    def test_wide_ratio_keeps_whole_original(self):
        c = compute_canvas(300, 900, (16, 9), 0.1)
        self.assertEqual((c["bg_w"], c["bg_h"]), (1760, 990))
        self.assertEqual(c["left_d"] + c["right_d"] + 300, c["bg_w"])
        self.assertEqual(c["top_d"] + c["bottom_d"] + 900, c["bg_h"])

    def test_custom_smaller_than_original_is_clamped(self):
        c = compute_canvas(1000, 800, custom=(500, 500))
        self.assertEqual((c["bg_w"], c["bg_h"]), (1000, 800))
        self.assertEqual(min(c["top_d"], c["bottom_d"], c["left_d"], c["right_d"]), 0)


class ExifTests(unittest.TestCase):
    def test_portrait_phone_photo_is_rotated_upright(self):
        img = Image.new("RGB", (200, 100), "red")
        exif = img.getexif()
        exif[0x0112] = 6  # 手机竖拍：需顺时针转 90°
        buf = io.BytesIO()
        img.save(buf, format="JPEG", exif=exif)
        data, name, w, h = prepare_image(buf.getvalue(), "photo.jpeg")
        self.assertEqual((w, h), (100, 200))
        self.assertEqual(Image.open(io.BytesIO(data)).size, (100, 200))
        self.assertEqual(name, "photo.jpg")

    def test_normal_image_uploaded_unchanged(self):
        buf = io.BytesIO()
        Image.new("RGB", (60, 40)).save(buf, format="PNG")
        data, name, w, h = prepare_image(buf.getvalue(), "a.png")
        self.assertEqual((data, name, w, h), (buf.getvalue(), "a.png", 60, 40))


class LargeImageTests(unittest.TestCase):
    @staticmethod
    def _noisy_png(mode, size):
        img = Image.frombytes(mode, (size, size), os.urandom(size * size * len(mode)))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    def test_large_opaque_image_fits_upload_target(self):
        from modules.baozun_expand.app import UPLOAD_TARGET
        data = self._noisy_png("RGB", 2600)  # 随机噪点：最难压缩的情况
        out, name, w, h = prepare_image(data, "shoe.png")
        self.assertLessEqual(len(out), UPLOAD_TARGET)
        self.assertEqual(name, "shoe.jpg")
        self.assertEqual(Image.open(io.BytesIO(out)).size, (w, h))
        self.assertEqual(w, h)

    def test_large_transparent_image_keeps_alpha(self):
        data = self._noisy_png("RGBA", 1400)
        out, name, w, h = prepare_image(data, "cut.png")
        self.assertEqual(name, "cut.png")
        self.assertEqual(Image.open(io.BytesIO(out)).mode, "RGBA")

    def test_small_image_untouched(self):
        buf = io.BytesIO()
        Image.new("RGB", (300, 300), "white").save(buf, format="JPEG")
        self.assertEqual(prepare_image(buf.getvalue(), "s.jpg")[:2], (buf.getvalue(), "s.jpg"))


class FakeImap:
    """模拟 QQ 邮箱：第 3 轮时验证码邮件才到达"""
    instances = 0

    def __init__(self, *a):
        FakeImap.instances += 1
        self.polls = 0
        self.fetched = []

    def login(self, *a):
        pass

    def list(self):
        return "OK", [b'(\\HasNoChildren) "/" "INBOX"', b'(\\HasNoChildren) "/" "Sent Messages"', b'(\\HasNoChildren) "/" "Junk"']

    def select(self, folder, readonly=False):
        self.folder = folder
        return "OK", [b"1"]

    def search(self, *a):
        if self.folder == '"INBOX"':
            self.polls += 1
        ids = b"1 2" if self.polls < 3 else b"1 2 3"
        return "OK", [ids if self.folder == '"INBOX"' else b""]

    def fetch(self, mail_id, _):
        self.fetched.append((self.folder, mail_id))
        msg = email.message.EmailMessage()
        msg["From"] = "noreply@baozun.com"
        msg["Date"] = email.utils.formatdate(time.time())
        msg["Subject"] = "宝尊登录验证码" if mail_id == b"3" else "周报"
        msg.set_content("您的验证码是 483920" if mail_id == b"3" else "没有内容")
        return "OK", [(b"1", msg.as_bytes())]

    def logout(self):
        pass


class OtpMailboxTests(unittest.TestCase):
    def test_single_connection_and_each_mail_fetched_once(self):
        FakeImap.instances = 0
        acc = BaozunAccountAPI(qq_email="x@qq.com", qq_auth_code="y")
        with mock.patch("imaplib.IMAP4_SSL", FakeImap), mock.patch("time.sleep"):
            code = acc.fetch_latest_email_otp(timeout=30, after_ts=time.time() - 5)
        self.assertEqual(code, "483920")
        self.assertEqual(FakeImap.instances, 1)


class ExpandPageTests(unittest.TestCase):
    def test_interrupted_job_resumes_polling_without_resubmitting(self):
        from streamlit.testing.v1 import AppTest

        def script():
            import streamlit as st
            from modules.baozun_expand import app as m

            class Api:
                pending = None

                def upload_image(self, *a):
                    raise AssertionError("不应重新上传")

                def submit_image_expand(self, **kw):
                    raise AssertionError("不应重新提交")

                def get_image_expand_result(self, record, **kw):
                    st.session_state["polled"] = record
                    return ["https://example.com/a.png", "https://example.com/b.png"]

            m.get_api = lambda: Api()
            if "seeded" not in st.session_state:  # 模拟：已提交（有任务编号）但页面被打断
                st.session_state["seeded"] = True
                st.session_state["exp_job"] = {"file": b"x", "filename": "a.jpg", "record": "REC7",
                                               "params": {"generated_num": 2}}
            m.render_ui()

        at = AppTest.from_function(script).run(timeout=30)
        self.assertEqual(len(at.exception), 0)
        self.assertEqual(at.session_state["polled"], "REC7")
        self.assertNotIn("exp_job", at.session_state)
        # 结果在之后的页面刷新中仍然保留
        at.run(timeout=30)
        self.assertEqual(at.session_state["exp_results"], ["https://example.com/a.png", "https://example.com/b.png"])
        self.assertEqual(len([b for b in at.get("link_button")]), 2)


class NewJobTests(unittest.TestCase):
    def test_new_job_calls_real_api_signatures(self):
        """从"点击生成"开始走完整流程；假接口按真实方法签名校验参数，防止传错参数名"""
        import inspect
        from streamlit.testing.v1 import AppTest

        def script():
            import inspect
            import streamlit as st
            from modules.baozun_expand import app as m
            from modules.baozun_expand.baozun_api import BaozunExpandAPI as Real

            class Api:
                pending = None

                def upload_image(self, *a, **kw):
                    inspect.signature(Real.upload_image).bind(None, *a, **kw)
                    return "ATT1"

                def submit_image_expand(self, *a, **kw):
                    inspect.signature(Real.submit_image_expand).bind(None, *a, **kw)
                    st.session_state["submitted"] = kw
                    return "REC1"

                def get_image_expand_result(self, *a, **kw):
                    inspect.signature(Real.get_image_expand_result).bind(None, *a, **kw)
                    return ["https://example.com/a.png"]

            m.get_api = lambda: Api()
            if "seeded" not in st.session_state:
                st.session_state["seeded"] = True
                c = m.compute_canvas(400, 400, None, 0.4, "居中")
                st.session_state["exp_job"] = {"file": b"x", "filename": "a.jpg", "record": None,
                                               "params": {**c, "orig_w": 400, "orig_h": 400, "generated_num": 1}}
            m.render_ui()

        at = AppTest.from_function(script).run(timeout=30)
        self.assertEqual(len(at.exception), 0)
        self.assertEqual(at.session_state["exp_results"], ["https://example.com/a.png"])
        sub = at.session_state["submitted"]
        self.assertEqual((sub["background_weight"], sub["background_height"], sub["top_distance"],
                          sub["left_distance"], sub["original_weight"], sub["generated_num"]),
                         (560, 560, 80, 80, 400, 1))


if __name__ == "__main__":
    unittest.main()
