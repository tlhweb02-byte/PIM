# -*- coding: utf-8 -*-
"""用真实模块验证 simplify_title 函数"""
import sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd
from modules import mod_07_excel

# 构造测试行（模拟DataFrame的一行）
def make_row(name, feat=''):
    return pd.Series({'名称': name, '卖点': feat})

cases = [
    "AIR MONARCH IV男子训练鞋老爹鞋IQ9792",
    "男子复古运动鞋",
    "幼童经典运动鞋",
    "女子经典卫衣",
    "女子柔软长裤",
]

for c in cases:
    row = make_row(c)
    res = mod_07_excel.simplify_title(row)
    comp = mod_07_excel.get_component_example(res)
    print(f"名称: {c}")
    print(f"  -> 中文名称: {res}")
    print(f"  -> 组件示例: {comp}")
    print()
