import streamlit as st
import pandas as pd
import numpy as np
import io
import re

try:
    from modules import mod_stats
except ImportError:
    import mod_stats

def simplify_title(row):
    name_str = str(row.get('名称', '')).strip() if pd.notna(row.get('名称')) else ""
    feat_str = str(row.get('卖点', '')).strip() if pd.notna(row.get('卖点')) and str(row.get('卖点')).strip().lower() != 'nan' else ""

    if not name_str or name_str.lower() == 'nan':
        return ""

    if "耐高系列男女童大童速干双面穿篮球球衣" in name_str:
        return "大童速干篮球衣"

    # 1. 提取性别/年龄前缀 (prefix)
    prefix = ""
    if "大童" in name_str:
        prefix = "大童"
    elif "幼童" in name_str:
        prefix = "幼童"
    elif "婴童" in name_str or "宝宝" in name_str:
        prefix = "婴童"
    elif "男女童" in name_str or "男童" in name_str or "女童" in name_str or "儿童" in name_str:
        prefix = "大童"
    elif "男女" in name_str or "情侣" in name_str:
        prefix = "男女"
    elif "女子" in name_str or "女" in name_str:
        prefix = "女子"
    elif "男子" in name_str or "男" in name_str:
        prefix = "男子"
    else:
        prefix = "男子"

    # 2. 提取品类后缀 (suffix)
    suffix = ""
    if "篮球球衣" in name_str or "篮球衣" in name_str:
        suffix = "篮球衣"
    elif "球衣" in name_str:
        suffix = "球衣"
    elif "连体衣" in name_str:
        suffix = "连体衣"
    elif "半身裙" in name_str:
        suffix = "半身裙"
    elif "凉鞋" in name_str:
        suffix = "凉鞋"
    elif "紧身裤" in name_str:
        suffix = "紧身裤"
    elif "短裤" in name_str:
        suffix = "短裤"
    elif "长裤" in name_str or "运动裤" in name_str:
        suffix = "长裤"
    elif "卫衣" in name_str or "连帽衫" in name_str:
        suffix = "卫衣"
    elif "夹克" in name_str or "羽绒" in name_str or "棉服" in name_str:
        suffix = "夹克"
    elif "衬衫" in name_str:
        suffix = "衬衫"
    elif "POLO" in name_str.upper() or "翻领" in name_str:
        suffix = "T恤"
    elif "T恤" in name_str or "短袖" in name_str or "半袖" in name_str:
        suffix = "T恤"
    elif "上衣" in name_str:
        suffix = "上衣"
    elif "内衣" in name_str:
        suffix = "内衣"
    elif "跑步鞋" in name_str or "竞速" in name_str:
        suffix = "跑步鞋"
    elif "篮球鞋" in name_str:
        suffix = "篮球鞋"
    elif "童鞋" in name_str:
        suffix = "童鞋"
    elif "运动鞋" in name_str or "跑鞋" in name_str or "老爹鞋" in name_str or "气垫鞋" in name_str or "板鞋" in name_str or "鞋" in name_str:
        suffix = "运动鞋"
    else:
        suffix = "服装"

    # 扩展修饰词库（包含材质、款式、功能等词汇）
    keywords = [
        "摇粒绒", "灯芯绒", "工装", "长袖", "短袖", "羽绒", "加绒", "拒水", "防风",
        "复古", "修身", "宽松", "速干", "纯棉", "休闲", "柔软", "舒适", "轻便", 
        "百搭", "干爽", "轻盈", "弹性", "耐穿", "随性", "短款", "梭织", "轻松", 
        "导湿", "中腰", "高腰", "顺滑", "贴合", "双面", "印花", "空军", "透气", 
        "机能", "赛博", "缓震", "防水", "稳程", "实战", "包头", "防晒", "时尚",
        "经典", "日常", "运动", "简约", "保暖"
    ]

    # 判断是否与卖点词重合的核心判断函数
    def is_overlapping_with_feat(kw, feat):
        if not feat or feat.lower() == 'nan':
            return False
        return (kw in feat) or (feat in kw)

    mid = ""

    # 3. 优先从原名称中寻找修饰词，并跳过与卖点重合的词
    for kw in keywords:
        if kw in name_str and kw not in prefix and kw not in suffix:
            if not is_overlapping_with_feat(kw, feat_str):
                mid = kw
                break

    # 4. 校正卖点重合机制（保底校验）
    # 若 mid 为空或与卖点发生重合，自动选用不重合的备用词
    if not mid or is_overlapping_with_feat(mid, feat_str):
        mid = ""
        backup_candidates = ["经典", "日常", "时尚", "运动", "休闲", "简约", "百搭", "舒适"]
        for candidate in backup_candidates:
            if not is_overlapping_with_feat(candidate, feat_str) and candidate not in prefix and candidate not in suffix:
                mid = candidate
                break

    res = prefix + mid + suffix

    # 5. 补齐字数限制（6~7字），补全词同样校验不与卖点重合
    if len(res) < 6:
        for kw in keywords:
            if kw not in res and not is_overlapping_with_feat(kw, feat_str):
                candidate = prefix + mid + kw + suffix
                if len(candidate) >= 6:
                    res = candidate
                    break

    if len(res) < 6:
        for fill in ["时尚", "运动", "经典", "休闲", "百搭", "日常", "简约"]:
            if fill not in res and not is_overlapping_with_feat(fill, feat_str):
                candidate = prefix + fill + mid + suffix
                if len(candidate) >= 6:
                    res = candidate
                    break

    if len(res) > 7:
        res = res[:7]

    return res

def process_excel(uploaded_file):
    df_raw = pd.read_excel(uploaded_file, header=None)
    
    start_row, start_col = None, None
    for r in range(len(df_raw)):
        for c in range(len(df_raw.columns)):
            val = str(df_raw.iloc[r, c]).replace('\n', '').replace('\r', '').strip()
            if '模块' in val:
                start_row, start_col = r, c
                break
        if start_row is not None:
            break
            
    if start_row is None:
        raise ValueError("未在表格中找到包含 '模块' 关键词的单元格！")

    end_col = None
    for c in range(start_col, len(df_raw.columns)):
        val = str(df_raw.iloc[start_row, c]).replace('\n', '').replace('\r', '').strip()
        if '商品卖点' in val or '卖点' in val:
            end_col = c
            break
            
    if end_col is None:
        end_col = len(df_raw.columns) - 1

    end_row = len(df_raw)
    for r in range(start_row + 1, len(df_raw)):
        row_str = ' '.join([str(x) for x in df_raw.iloc[r].values if pd.notna(x)])
        if '热门分类导航' in row_str:
            end_row = r
            break

    headers = [str(df_raw.iloc[start_row, c]).replace('\n', '').replace('\r', '').strip() for c in range(start_col, end_col + 1)]
    df = df_raw.iloc[start_row + 1:end_row, start_col:end_col + 1].copy()
    df.columns = headers

    valid_cols = [c for c in df.columns if '热门分类导航' not in str(c)]
    df = df[valid_cols]

    rename_map = {}
    for col in df.columns:
        if col in ['图片链接', '产品图']:
            rename_map[col] = '商品图'
        elif col in ['商品卖点']:
            rename_map[col] = '卖点'
    df = df.rename(columns=rename_map)

    if '名称' in df.columns:
        df['中文名称'] = df.apply(simplify_title, axis=1)
        cols = list(df.columns)
        if '中文名称' in cols:
            cols.remove('中文名称')
            idx_name = cols.index('名称')
            cols.insert(idx_name + 1, '中文名称')
            df = df[cols]

    output_buffer = io.BytesIO()
    with pd.ExcelWriter(output_buffer, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='首页线框', index=False)
        workbook = writer.book
        workbook.create_sheet('最终视觉稿')
        writer.sheets['首页线框'].views.sheetView[0].tabSelected = True
        if '最终视觉稿' in writer.sheets:
            writer.sheets['最终视觉稿'].views.sheetView[0].tabSelected = False

    output_buffer.seek(0)
    return df, output_buffer

# 导出供主程序调用的 UI 渲染入口
def render_ui():
    st.header("📊 运营表格一键智能转化")
    st.markdown("上传原始运营 Excel 表格，自动截取有效区域、智能缩减商品标题（6~7字），并格式化输出标准清单。")

    uploaded_file = st.file_uploader("📂 请选择需要转化的 Excel 文件 (.xlsx, .xls)", type=["xlsx", "xls"])

    if uploaded_file is not None:
        try:
            with st.spinner("正在智能转换表格，请稍候..."):
                df_result, output_buffer = process_excel(uploaded_file)
                
                try:
                    mod_stats.record_excel_cleaning(1)
                except Exception as e:
                    print(f"Record excel cleaning error: {e}")

            st.success("🎉 表格转化成功！提效战绩已实时同步。")
            st.subheader("📋 转换数据预览 (前 10 行)")
            st.dataframe(df_result.head(10), use_container_width=True)
            
            st.download_button(
                label="📥 点击下载转化后的标准清单 Excel",
                data=output_buffer,
                file_name="生成的标准转化清单.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        except Exception as e:
            st.error(f"❌ 转换过程中发生错误: {e}")
