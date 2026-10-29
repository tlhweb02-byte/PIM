"""商品标题及 Excel 导出回归测试：python -m unittest test_excel_titles。"""
import io
import unittest

import pandas as pd

from modules.mod_07_excel import get_component_example, process_excel, simplify_title


class ExcelTitleTests(unittest.TestCase):
    CASES = [
        ("男子运动衫FN0001", "", "男子经典运动衫"),
        ("女子运动衫FN0001", "", "女子经典运动衫"),
        ("男子运动靴FQ0001", "", "男子经典运动靴"),
        ("女子运动靴FQ0001", "", "女子经典运动靴"),
        ("NIKE WINFLO 11 女子公路跑步鞋IM3381", "", "女子公路跑步鞋"),
        ("NIKE WINFLO 11 女子公路跑步鞋IM3381", "公路缓震", "女子公路跑步鞋"),
        ("男子轻盈越野跑步鞋FQ0001", "越野", "男子越野跑步鞋"),
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


if __name__ == '__main__':
    unittest.main()
