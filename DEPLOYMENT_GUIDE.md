# 部署说明

网站运行在香港云服务器上（Ubuntu 22.04）。服务器 IP、SSH 端口和登录方式见运维交接文档，**不要写进本仓库**（仓库是公开的）。

## 服务器上的结构

| 内容 | 位置 |
|---|---|
| 项目代码 | `/opt/pim`（从 GitHub 克隆，只跟随 `main` 分支） |
| Python 虚拟环境 | `/opt/pim/.venv`（Python 3.12，用 `uv` 安装依赖） |
| 密钥配置 | `/opt/pim/.streamlit/secrets.toml`（权限 600，不进 Git） |
| 常驻服务 | `systemd` 服务 `pim`，监听 `127.0.0.1:8501`，开机自启、崩溃自动重启 |
| 对外访问 | Nginx 监听 80 端口，反向代理到 8501（已开启 WebSocket 转发） |
| 部署脚本 | `/usr/local/bin/pim-deploy`（来自仓库 `deploy/pim-deploy.sh`） |

## 自动部署

合并到 `main` 后，GitHub Actions（`.github/workflows/deploy.yml`）会：

1. 安装依赖并运行全部测试，**测试不通过就不部署**；
2. 用一把受限 SSH 密钥连上服务器，触发 `pim-deploy`：拉取最新代码 → `requirements.txt` 有变化时安装依赖 → 重启网站 → 检查网站是否正常响应。

部署结果在 GitHub 仓库的 **Actions** 页面查看。也可以在 Actions 页面手动点 **Run workflow** 重新部署。

### 首次设置（只需做一次）

1. 登录服务器，先更新代码，再运行设置脚本（把 IP 换成服务器公网 IP）：

   ```bash
   cd /opt/pim && git pull
   bash /opt/pim/deploy/setup-auto-deploy.sh <服务器公网IP>
   ```

2. 脚本会打印 4 项内容。打开 GitHub 仓库 **Settings → Secrets and variables → Actions → New repository secret**，按名称逐项新建：
   `DEPLOY_HOST`、`DEPLOY_PORT`、`DEPLOY_KNOWN_HOSTS`、`DEPLOY_SSH_KEY`。

3. 在 Actions 页面对「部署到香港服务器」点 **Run workflow**，看到"部署成功"即完成。

这把部署密钥在服务器上被限制为**只能运行 `pim-deploy`**，不能开终端、不能做别的操作。即使泄露，最多只能让服务器重新部署一次 GitHub 上的代码。

> 未配置这 4 项 Secrets 时，部署步骤会跳过并显示提示，不会报错。

## 手动运维

```bash
# 手动部署（等同于自动部署做的事）
pim-deploy

# 查看服务状态 / 日志
systemctl status pim
journalctl -u pim -n 50 --no-pager

# 修改密钥配置后重启生效
nano /opt/pim/.streamlit/secrets.toml && systemctl restart pim

# 修改 Nginx 配置后
nginx -t && systemctl restart nginx
```

**不要直接在服务器上改代码**：改动请走 GitHub。服务器上的代码一旦和 GitHub 不一致，自动部署会停下并提示，不会覆盖。
