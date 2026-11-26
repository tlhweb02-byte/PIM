#!/usr/bin/env bash
# 服务器端部署脚本：拉取 main → 依赖有变化时安装 → 重启 → 健康检查。
# 由 GitHub Actions 通过受限 SSH 密钥触发（该密钥只能运行本脚本），也可在服务器上手动运行：pim-deploy
set -euo pipefail

APP=${PIM_APP:-/opt/pim}
UV=${PIM_UV:-/root/.local/bin/uv}
cd "$APP"

old=$(git rev-parse HEAD)
git fetch --quiet origin main
# 只做快进更新：服务器上如果有人改过代码，停下来，而不是覆盖掉
if ! git merge --ff-only --quiet origin/main 2>/dev/null; then
  echo "部署已停止：服务器 $APP 里的代码和 GitHub 不一致（可能有人直接在服务器上改过代码）。"
  echo "请登录服务器，在 $APP 运行 git status 查看改动；确认不需要后运行 git reset --hard origin/main，再重新部署。"
  exit 1
fi
new=$(git rev-parse HEAD)

if [ "$old" = "$new" ]; then
  echo "已是最新版本：$(git log -1 --format='%h %s')"
  exit 0
fi

if ! git diff --quiet "$old" "$new" -- requirements.txt; then
  echo "requirements.txt 有变化，安装依赖..."
  "$UV" pip install --python "$APP/.venv/bin/python" -r requirements.txt
fi

systemctl restart pim
for _ in $(seq 1 30); do
  if curl -fsS -o /dev/null http://127.0.0.1:8501/_stcore/health; then
    echo "部署成功：$(git log -1 --format='%h %s')"
    exit 0
  fi
  sleep 2
done

echo "网站重启后 60 秒内没有正常响应，最近日志："
journalctl -u pim -n 40 --no-pager
exit 1
