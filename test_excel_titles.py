"""商品标题及 Excel 导出回归测试：python -m unittest test_excel_titles。"""
import io
import unittest
from datetime import datetime, timezone

import pandas as pd

from modules.mod_07_excel import (
    MODULE_VERSION, get_component_example, get_download_filename, process_excel, simplify_title,
)


class ExcelTitleTests(unittest.TestCase):
    CASES = [
        ("女子透气背心FN1001", "", "女子透气背心"),
        ("男子宽松卫裤FN1002", "", "男子宽松长裤"),
        ("女子连衣裙FN1003", "", "女子经典连衣裙"),
        ("男子保暖针织衫FN1004", "", "男子保暖针织衫"),
        ("男子防风外套FN1005", "", "男子防风外套"),
        ("女子速干Ｔ－ＳＨＩＲＴFN1006", "", "女子速干T恤"),
        ("幼童加绒连 裤 裙FN1007", "", "幼童加绒连裤裙"),
        ("男子保暖坎肩FN1008", "", "男子保暖马甲"),
        ("女子百褶裙FN1009", "", "女子经典半身裙"),
        ("男子保暖冬季新品FN1010", "", "男子保暖服装"),
        ("男子运动服装FN1011", "", "男子运动服装"),
        ("马年限定幼童加绒连裤裙秋季女童IU5478", "加绒", "幼童经典连裤裙"),
        ("马年限定幼童加绒连裤裙秋季女童IU5478", "", "幼童加绒连裤裙"),
        ("男子运动衫FN0001", "", "男子经典运动衫"),
        ("女子运动衫FN0001", "", "女子经典运动衫"),
        ("男子运动靴FQ0001", "", "男子经典运动靴"),
        ("女子运动靴FQ0001", "", "女子经典运动靴"),
        ("NIKE WINFLO 11 女子公路跑步鞋IM3381", "", "女子公路跑步鞋"),
        ("NIKE WINFLO 11 女子公路跑步鞋IM3381", "公路缓震", "女子公路跑步鞋"),
        ("男子轻盈越野跑步鞋FQ0001", "越野", "男子轻盈跑步鞋"),
        ("女子专业跑步鞋夏公路透气JOURNEY RUN IR1523", "轻盈", "女子透气跑步鞋"),
        ("女子专业跑步鞋夏公路透气JOURNEY RUN IR1523", "透气", "女子透气跑步鞋"),
        ("男子气柱运动鞋SHOX RIDE 2 IO4296", "回弹", "男子气柱运动鞋"),
        ("男子气柱运动鞋SHOX RIDE 2 IO4296", "气柱", "男子气柱运动鞋"),
        ("男子公路专业跑步鞋透气官方WINFLO 11 IH7328", "", "男子透气跑步鞋"),
        ("INTERACT RUN女公路跑步鞋秋透气轻便运动FD2292", "透气", "女子轻便跑步鞋"),
        ("男子专业跑步鞋夏季公路竞速STREAKFLY 2 IO8268", "回弹", "男子公路跑步鞋"),
        ("女子运动鞋透气轻便缓震支撑抓地舒适HF1233", "日常", "女子透气运动鞋"),
        ("迈柔女子缓震运动鞋复古跑鞋风VOMERO 5 IB7253", "", "女子缓震运动鞋"),
        ("女子透气运动鞋复古跑鞋风跑步LD-1000 IO0179", "复古", "女子透气运动鞋"),
        ("女子公路跑鞋IM3381", "", "女子公路跑步鞋"),
        ("女子跑步鞋IM3381", "", "女子经典跑步鞋"),
        ("THERMA-FIT男子越野跑步马甲冬季棉服保暖FZ0002", "", "男子保暖马甲"),
        ("男子冬季棉服保暖FZ0002", "", "男子保暖夹克"),
        ("女子经典卫衣", "", "女子经典卫衣"),
        ("AIR MONARCH IV男子训练鞋老爹鞋IQ9792", "", "男子经典训练鞋"),
    ]

    def test_titles(self):
        for name, feature, expected in self.CASES:
            with self.subTest(name=name, feature=feature):
                self.assertEqual(simplify_title(pd.Series({'名称': name, '卖点': feature})), expected)

    def test_components(self):
        self.assertEqual(get_component_example("幼童经典连裤裙"), "类型=下装模特, 模式=跑图")
        for title in ["女子经典连衣裙", "男子宽松长裤"]:
            self.assertEqual(get_component_example(title), "类型=下装模特, 模式=跑图")
        for title in ["女子透气背心", "男子保暖针织衫", "男子防风外套"]:
            self.assertEqual(get_component_example(title), "类型=上装模特, 模式=跑图")
        for title in ["男子经典运动衫", "男子保暖马甲"]:
            self.assertEqual(get_component_example(title), "类型=上装模特, 模式=跑图")
        for gender in ["男子", "女子"]:
            self.assertEqual(get_component_example(gender + "经典运动靴"),
                             f"类型=鞋子静物A（{gender}）, 模式=跑图")

    def test_excel_round_trip(self):
        source = pd.DataFrame([["模块", "名称", "商品卖点"]] +
                              [["商品", name, feature] for name, feature, _ in self.CASES])
        uploaded = io.BytesIO()
        source.to_excel(uploaded, index=False, header=False)
        uploaded.seek(0)
        result, exported = process_excel(uploaded)
        expected = [title for _, _, title in self.CASES]
        self.assertEqual(result['中文名称'].tolist(), expected)
        workbook = pd.ExcelFile(exported)
        self.assertEqual(workbook.sheet_names, ['首页线框', '最终视觉稿'])
        self.assertEqual(pd.read_excel(workbook, sheet_name='首页线框')['中文名称'].tolist(), expected)

    def test_download_date_uses_china_timezone(self):
        self.assertEqual(get_download_filename(datetime(2026, 10, 28, 17, tzinfo=timezone.utc)),
                         '10月29日线框提取.xlsx')
        self.assertEqual(get_download_filename(datetime(2026, 12, 31, 17, tzinfo=timezone.utc)),
                         '1月1日线框提取.xlsx')

    def test_page_version(self):
        from streamlit.testing.v1 import AppTest
        app = AppTest.from_string('from modules.mod_07_excel import render_ui\nrender_ui()').run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(app.header[0].value, f'📊 运营表格一键智能转化 {MODULE_VERSION}')


if __name__ == '__main__':
    unittest.main()
