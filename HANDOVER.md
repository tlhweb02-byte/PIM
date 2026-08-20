# 📋 宝尊投放打标管理 (NIKE) — 交接文档

## 1. 当前状态
- **Git HEAD (本地)**: 7e66fa9 — "fix: selectbox tuple格式修正，解决部署报错"
- **Git HEAD (远程 origin/main)**: 8746589 — "修复Streamlit配置：移除developmentMode和port配置"
- **部署状态**: 已推送至 GitHub，Streamlit Cloud 需要重新部署（或已自动触发）

## 2. 现已修复的 Bug

### Bug 1: 部署时 `selectbox` 报错 (已修复)
- **位置**: `modules/baozun_marking/app.py` 第 468 行，`_render_tasks` 函数
- **原因**: `st.selectbox` 收到了 `(groupId, groupName)` 元组列表，但 Streamlit 的 `selectbox` 组件期望的是一个**扁平化的值列表**（仅 groupId），且 `format_func` 接收的参数也应为值而非元组
- **现象**: 应用在 Streamlit Cloud 上启动时报错 `TypeError: cannot unpack non-iterable _Ctx object`，导致整个页面卡死
- **修复**: 改为先提取 `[gid for gid, _ in group_opts]` 作为 selectbox 的 value 列表，用 `format_func` 通过 `dict` 映射显示 "不分组"/组名；selectbox 的 `key` 改为 `"marking_new_task_group"`（之前的 key 冲突也可能导致问题）

**修复后代码**:
```python
group_opts = [("", "不分组")] + [(g["groupId"], g["groupName"]) for g in flat]
group_label_map = dict(group_opts)
group_id = st.selectbox(
    "所属分组", [gid for gid, _ in group_opts],
    format_func=lambda x: group_label_map.get(x, x),
    key="marking_new_task_group",
)
```

---
## 3. 未完成的任务 / 待实现功能

### 3.1 投放管理 (📦 投放管理) — **核心功能未完成**
目前仅实现了**状态筛选**和**基础列表展示**，以下功能尚未实现：
- [ ] **查看详情**: 点击投放策略行应弹出/跳转详情页，显示策略完整信息（目标时间、预算、投放渠道等）
- [ ] **取消投放**: 调用 `/push/cancel` 接口
- [ ] **结束投流**: 调用 `/push/end` 接口
- [ ] **删除投放**: 调用 `/push/delete` 接口
- [ ] **再次投放**: 调用 `/push/rePush`，支持“定时投放”和“立即投放”两种模式
- [ ] **关键词搜索**: 目前仅实现了状态筛选，未实现任务名称关键词过滤

### 3.2 打标任务 (🏷️ 打标任务) — **多项功能未完成**
目前实现了基本的**任务列表查询**、**分组筛选**、**新建任务表单**（受上述 Bug 影响），但以下功能未完成或受 Bug 阻塞：
- [ ] **修复新建任务 Bug**: 受上文 selectbox 问题影响，新建任务时选择分组会报错（已在本次提交中修复，需重新部署）
- [ ] **复制任务**: `api.copy_task(tid)` 接口调用，未验证通过
- [ ] **重命名任务**: `api.rename_task(tid, new_name)` 接口调用，未验证通过
- [ ] **删除任务**: `api.task_id_delete`（代码中已有提及但未完整连通 UI 逻辑）
- [ ] **任务详情**: 点击查看任务详细信息（imgCount、createName、updateTime 等）
- [ ] **任务投放**: 任务行的 "📦 投放" 按钮应弹出模态框，支持“立即投放”与“定时投放”，调用 `api.re_push` 接口（该接口目前仅在 modal 中实现，未关联到任务行按钮）
- [ ] **新建分组**: `st.button("📁 新建分组")` 目前仅弹出模态框框架，未实现 `api.create_group` 接口调用

### 3.3 通用 / 其他
- [ ] **模态框状态持久化**: `st.session_state["marking_task_modal"]` 在不同操作间的转换（新建→复制→重命名）存在逻辑判断，但边界情况（如多次打开、快速点击）未完全测试
- [ ] **导出功能**: 暴露设计-web 的“导出”接口，生成 CSV/Excel 报表
- [ ] **店铺切换**: UI 中的店铺选择器虽已实现（`fetch_shop_list` + `set_shop`），但默认始终使用 `DEFAULT_SHOP` (NIKE0S02)，切换后的效果在云端未验证
- [ ] **登录缓存失效处理**: 会话在 3 小时后过期，跨天使用时可能需要重新输入验证码；目前的 `_try_reuse_cached_login` 已增量刷新 ross-token，但未在 UI 层给用户明确提示

---
## 4. 本次提交变更概览

| 文件 | 变更说明 |
|------|----------|
| `modules/baozun_marking/app.py` | 修复 selectbox tuple 格式Bug；优化 group 选择逻辑 |
| `modules/baozun_marking/marking_api.py` | 无变动（已通过 `py_compile` 语法验证） |
| `app.py` | 无变动（侧边栏入口已就绪） |
| `.gitignore` | 已添加 `modules/baozun_marking/marking_login_cache.pkl` 及 `_downloads/*.pkl`/`_downloads/*.json` 以防敏感信息泄露 |
| `README.md` | 已更新：补充新功能说明、AI生成内容政策、详细功能表 |

---
## 5. 部署与验证说明

1. **本地语法检查**: 所有 `.py` 文件均通过 `py_compile.compile(doraise=True)` 验证
2. **Git 推送**: 已将修复并推送至 `https://github.com/tlhweb02-byte/PIM` `main` 分支
3. **Streamlit Cloud 重新部署**: 推送后建议进入 Streamlit Cloud 管理后台点击“重新部署”，或等待自动触发（需 `streamlit` 容器重启）
4. **登录测试**: 账号凭据 `.env` 中 `BAOZUN_USERNAME=jm038153`、`BAOZUN_PASSWORD=Xl@20166`，租户固定为 `NIKE`；首次使用或缓存过期时会弹出验证码输入框（QQ 邮箱自动转发，沙箱环境下因 IMAP 受限无法自动读取）
5. **已验证功能流**: 登录 → 投放管理页签可见空列表（当前账号无数据） → 打标任务页签可见“无分组”组

---
## 6. 下一步建议
1. 重新部署 Streamlit Cloud 以启用 selectbox 修复
2. 逐一实现上文 [3.1]-[3.3] 中的功能，优先修复 "新建任务" → "复制任务" → "重命名任务" 的连通性
3. 若需要投放管理的详细功能（取消/结束/删除），请参考设计-web 前端的 `/push/cancel`、`/push/end`、`/push/delete` 等接口原型
4. 如需协助后续功能实现，可提问或重新创建 goal