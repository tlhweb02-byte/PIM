# 作图自动化中台

面向设计与运营团队的在线提效工具，基于 Streamlit 构建，**免登录、打开即用**。

## 功能模块

| 模块 | 说明 |
|---|---|
| 运营表格智能转化 | 上传原始运营 Excel，自动截取有效区域、缩减商品标题并输出标准清单 |
| 图片压缩与降维 | PNG 转 JPG、画质自动衰减与云端压缩，支持多图或保留目录结构的 ZIP |
| 宝尊智能扩图 | 调用宝尊 ROSS 引擎扩展图片背景，公司账号鉴权由后台自动维护 |
| 品牌字体下载 | Helvetica Neue & NowText 官方字体包 |
| 团队提效仪表盘 | 按年 / 月 / 日统计团队提效数据（Google 表格存储） |

## 本地运行

```bash
pip install -r requirements.txt
streamlit run app.py
```

配置项参考 `.env.example`（宝尊账号、邮箱验证码等）；部署到 Streamlit Cloud 时写入 Secrets。

## 界面

- 全局视觉主题在 `modules/ui_theme.py`（字体、配色、卡片、导航样式）；
- Streamlit 基础主题色在 `.streamlit/config.toml` 的 `[theme]` 中配置。
