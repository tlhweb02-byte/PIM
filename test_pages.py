"""页面冒烟测试与图片压缩回归测试：python -m unittest test_pages。"""
import io
import unittest
import zipfile

from PIL import Image
from streamlit.testing.v1 import AppTest

from modules.mod_05_compress import compress_files

PAGES = {
    "modules.mod_07_excel": "表格转化",
    "modules.mod_05_compress": "图片压缩",
    "modules.baozun_expand.app": "智能扩图",
    "modules.mod_fonts": "品牌字体",
    "modules.mod_stats": "数据统计",
}


def _jpg(size=(1200, 1200)):
    import random
    img = Image.new("RGB", size)
    img.putdata([(random.randrange(256),) * 3 for _ in range(size[0] * size[1])])
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=100)
    return buf.getvalue()


class PageTests(unittest.TestCase):
    def test_every_page_renders(self):
        for module, title in PAGES.items():
            with self.subTest(module=module):
                app = AppTest.from_string(f"from {module} import render_ui\nrender_ui()").run(timeout=30)
                self.assertEqual(len(app.exception), 0)
                self.assertEqual(app.title[0].value, title)

    def test_app_navigation_runs(self):
        app = AppTest.from_file("app.py").run(timeout=30)
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(app.title[0].value, "作图自动化中台")
        # 首页每个章节都有标题，并带粒子脚本
        self.assertEqual([h.value for h in app.header], ["表格转化", "图片压缩", "智能扩图", "数据统计"])


class CompressTests(unittest.TestCase):
    def test_images_and_zip_in_one_upload(self):
        inner = io.BytesIO()
        with zipfile.ZipFile(inner, "w") as zf:
            zf.writestr("款式A/主图.jpg", _jpg())
            zf.writestr("款式A/说明.txt", b"hello")
            zf.writestr("__MACOSX/._x", b"junk")

        out, logs, count, saved = compress_files(
            [("单图.jpg", _jpg()), ("素材.zip", inner.getvalue())], target_kb=100
        )
        names = sorted(zipfile.ZipFile(io.BytesIO(out)).namelist())
        self.assertEqual(names, [
            "compressed_images/单图.jpg",
            "compressed_images/款式A/主图.jpg",
            "compressed_images/款式A/说明.txt",
        ])
        self.assertEqual(count, 2)
        self.assertGreater(saved, 0)
        self.assertEqual(len(logs), 3)

    def test_small_image_kept_as_is(self):
        small = _jpg((50, 50))
        out, _, count, saved = compress_files([("小图.jpg", small)], target_kb=500)
        self.assertEqual(zipfile.ZipFile(io.BytesIO(out)).read("compressed_images/小图.jpg"), small)
        self.assertEqual((count, saved), (1, 0))


if __name__ == "__main__":
    unittest.main()
