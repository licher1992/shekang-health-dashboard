#!/bin/bash
# 自动更新部署：拉取飞书多维表 -> 更新 index.html -> 推送到 GitHub Pages（公网自动更新）
set -e
cd "$(dirname "$0")"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] 开始拉取飞书数据..."
python3 scripts/pull_bitable.py || { echo "拉取失败"; exit 1; }
# 接口年龄同步（token 有效时自动执行；token 过期会提示重新登录，跳过不影响飞书数据更新）
echo "[$(date '+%Y-%m-%d %H:%M:%S')] 尝试同步接口精确年龄..."
python3 scripts/sync_age.py sync 2>&1 | tail -3 || echo "年龄同步跳过（token 可能过期）"
# 推送 GitHub Pages
gh auth setup-git >/dev/null 2>&1 || true
git add index.html
if git diff --cached --quiet; then
  echo "数据无变化，无需推送"
else
  git -c user.email="licher1992@users.noreply.github.com" -c user.name="licher1992" commit -m "数据更新 $(date '+%Y-%m-%d %H:%M')"
  git push -q origin main && echo "已推送 GitHub Pages，公网地址自动更新"
fi
# 向飞书【MVP管理群】发送简短经营总结
echo "[$(date '+%Y-%m-%d %H:%M:%S')] 发送群总结..."
python3 scripts/send_summary.py || echo "群总结发送失败（不影响数据更新）"
echo "完成"
