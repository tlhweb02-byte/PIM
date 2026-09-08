#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""本地测试脚本 - 验证修复后的代码是否正常运行"""

import sys
import os

print("🔍 开始本地测试...")
print("=" * 60)

# 测试1：检查依赖是否安装
print("\n📦 测试1：检查依赖安装")
try:
    import streamlit as st
    print("✓ streamlit 已安装")
except ImportError as e:
    print(f"✗ streamlit 未安装: {e}")
    print("请运行: pip install streamlit")
    sys.exit(1)

try:
    import pandas as pd
    print("✓ pandas 已安装")
except ImportError as e:
    print(f"✗ pandas 未安装: {e}")
    print("请运行: pip install pandas")
    sys.exit(1)

try:
    import numpy as np
    print("✓ numpy 已安装")
except ImportError as e:
    print(f"✗ numpy 未安装: {e}")
    print("请运行: pip install numpy")
    sys.exit(1)

try:
    import openpyxl
    print("✓ openpyxl 已安装")
except ImportError as e:
    print(f"✗ openpyxl 未安装: {e}")
    print("请运行: pip install openpyxl")
    sys.exit(1)

# 测试2：测试模块导入
print("\n📦 测试2：测试模块导入")
try:
    from modules import mod_07_excel
    print("✓ mod_07_excel 导入成功")
except ImportError as e:
    print(f"✗ mod_07_excel 导入失败: {e}")
    sys.exit(1)

# 测试3：测试组件示例函数
print("\n🧪 测试3：测试组件示例函数")
test_cases = [
    ("男子复古运动鞋", "类型=鞋子静物A（男子）, 模式=跑图"),
    ("幼童经典运动鞋", "类型=鞋子静物A（幼童）, 模式=跑图"),
    ("女子经典卫衣", "类型=上装模特, 模式=跑图"),
    ("男子工装长裤", "类型=下装模特, 模式=跑图"),
    ("婴童宝宝鞋", "类型=鞋子静物A（婴童）, 模式=跑图"),
    ("大童运动鞋", "类型=鞋子静物A（大童）, 模式=跑图"),
    ("女子柔软长裤", "类型=下装模特, 模式=跑图"),
    ("男子速干卫衣", "类型=上装模特, 模式=跑图"),
]

all_passed = True
for name, expected in test_cases:
    result = mod_07_excel.get_component_example(name)
    if result == expected:
        print(f"✓ {name} → {result}")
    else:
        print(f"✗ {name} → {result}")
        print(f"  预期: {expected}")
        all_passed = False

# 测试4：测试NaN处理
print("\n🧪 测试4：测试NaN处理")
nan_test_cases = [
    (None, "类型=静物, 模式=跑图"),
    (float('nan'), "类型=静物, 模式=跑图"),
    ("nan", "类型=静物, 模式=跑图"),
    ("", "类型=静物, 模式=跑图"),
    ("男子运动鞋", "类型=鞋子静物A（男子）, 模式=跑图"),
]

for input_val, expected in nan_test_cases:
    result = mod_07_excel.get_component_example(input_val)
    if result == expected:
        print(f"✓ 输入: {repr(input_val)} → {result}")
    else:
        print(f"✗ 输入: {repr(input_val)} → {result}")
        print(f"  预期: {expected}")
        all_passed = False

# 总结
print("\n" + "=" * 60)
if all_passed:
    print("🎉 所有测试通过！应用应该可以正常运行。")
    print("\n📋 下一步：")
    print("1. 代码已推送到 GitHub")
    print("2. Streamlit Cloud 会自动重新部署")
    print("3. 等待 2-5 分钟后访问 https://pim999.streamlit.app")
else:
    print("❌ 部分测试失败，需要进一步修复")
    sys.exit(1)