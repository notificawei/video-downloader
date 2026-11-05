#!/usr/bin/env bash
# 一键把 Chrome 里的抖音登录 Cookie 写到 ~/douyin_cookies.txt
# 用法：在「终端」里运行：
#   cd /path/to/video-downloader
#   bash 导出抖音Cookie.sh
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

PYTHON=""
for candidate in /opt/homebrew/bin/python3.13 /opt/homebrew/bin/python3 /usr/local/bin/python3 python3; do
  if command -v "$candidate" >/dev/null 2>&1 || [ -x "$candidate" ]; then
    PYTHON="$candidate"
    break
  fi
done

if [ -z "$PYTHON" ]; then
  echo "找不到 python3，请先安装 Homebrew Python。"
  exit 1
fi

echo ""
echo "  即将从 Chrome 导出抖音 Cookie → ~/douyin_cookies.txt"
echo "  1) 确认 Chrome 已登录 www.douyin.com"
echo "  2) 最好先：Chrome 菜单 → 退出 Google Chrome"
echo "  3) 钥匙串弹窗请点「允许」"
echo ""

"$PYTHON" export_cookies.py douyin "$@"
echo ""
echo "  导出完成后，重新打开 VideoGet，再粘贴主页链接下载全部作品。"
echo ""
