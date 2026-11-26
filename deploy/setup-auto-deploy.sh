#!/usr/bin/env bash
# 一次性设置：在服务器上用 root 运行，例如
#   bash /opt/pim/deploy/setup-auto-deploy.sh 107.149.102.74
# 作用：安装部署脚本，生成一把"只能触发部署"的 SSH 密钥，并打印需要填到 GitHub Secrets 的 4 项内容。
set -euo pipefail

[ "$(id -u)" = 0 ] || { echo "请用 root 运行"; exit 1; }
IP=${1:?用法: bash setup-auto-deploy.sh <服务器公网IP>}
PORT=$(sshd -T 2>/dev/null | awk '/^port /{print $2; exit}')
PORT=${PORT:-22}

install -m 755 /opt/pim/deploy/pim-deploy.sh /usr/local/bin/pim-deploy

KEY=/root/.ssh/pim_deploy_ed25519
install -m 700 -d /root/.ssh
[ -f "$KEY" ] || ssh-keygen -q -t ed25519 -N "" -C "github-actions-pim-deploy" -f "$KEY"

# 限制这把密钥：登录后只能执行 pim-deploy，不能开终端、不能端口转发
AUTH=/root/.ssh/authorized_keys
touch "$AUTH" && chmod 600 "$AUTH"
PUB=$(cat "$KEY.pub")
grep -qF "$PUB" "$AUTH" || echo "command=\"/usr/local/bin/pim-deploy\",no-port-forwarding,no-X11-forwarding,no-agent-forwarding,no-pty $PUB" >> "$AUTH"

cat <<MSG

==================================================================
设置完成。请打开 GitHub 仓库 → Settings → Secrets and variables → Actions
→ New repository secret，依次新建下面 4 项（名称照抄，值复制对应内容）：

【DEPLOY_HOST】
$IP

【DEPLOY_PORT】
$PORT

【DEPLOY_KNOWN_HOSTS】（下面几行全部复制）
$(for f in /etc/ssh/ssh_host_*_key.pub; do echo "[$IP]:$PORT $(cut -d' ' -f1,2 "$f")"; done)

【DEPLOY_SSH_KEY】（从 -----BEGIN 到 -----END 整段复制，包括这两行）
$(cat "$KEY")
==================================================================
这把密钥只能触发部署，不能登录终端。不要把它发到聊天或提交到代码里。
MSG
