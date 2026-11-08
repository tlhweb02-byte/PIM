# 作图自动化中台

设计与运营团队的在线工具，基于 Streamlit，免登录。

| 页面 | 地址 | 作用 |
|---|---|---|
| 表格转化 | `/`（首页） | 运营 Excel → 标准清单 |
| 图片压缩 | `/compress` | 图片或 ZIP 批量压缩，ZIP 保留目录结构 |
| 智能扩图 | `/expand` | 宝尊 ROSS 引擎扩展图片背景 |
| 品牌字体 | `/fonts` | Helvetica Neue · NowText 字体包 |
| 数据统计 | `/stats` | 团队使用数据（Google 表格存储） |

## 运行

```bash
pip install -r requirements.txt
streamlit run app.py
```

配置参考 `.env.example`；部署到 Streamlit Cloud 时写入 Secrets。

## 结构

- `app.py`：页面注册与导航，新增页面只需在 `pages` 列表里加一行
- `modules/`：每个页面一个模块，入口统一为 `render_ui()`
- 视觉：`.streamlit/config.toml` 的 `[theme]`；动效：`assets/motion.css`（系统开启“减少动态效果”时自动关闭）

## 测试

```bash
python -m unittest test_pages test_excel_titles
```
