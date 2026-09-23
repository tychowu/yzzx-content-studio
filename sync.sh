#!/bin/bash
# yzzx-content-studio 一键同步脚本
#
# 用法：
#   bash sync.sh            # 安全模式（默认）：本地有未提交改动就停下，绝不覆盖
#   bash sync.sh --check    # 只检查本地 / 远程版本差异，什么都不改
#   bash sync.sh --reset    # 强制模式：丢弃本地改动，硬对齐远程（危险）
#
# 说明：只处理「拉取 + 重新注册」，不动你在仓库里的提交历史。
set -e

REPO="https://github.com/tychowu/yzzx-content-studio.git"
PLUGIN_DIR="$HOME/.workbuddy/plugins/marketplaces/my-experts/plugins/yzzx-content-studio"
REG_SCRIPT="/Applications/WorkBuddy.app/Contents/Resources/app.asar.unpacked/resources/plugins/workbuddy-builtin/skills/expert-manager/scripts/register_expert.py"

MODE="${1:-}"

re_register() {
  echo "▶ 重新注册到 WorkBuddy…"
  PY="$HOME/.workbuddy/binaries/python/envs/default/bin/python"
  [ -x "$PY" ] || PY="python3"
  if [ -f "$REG_SCRIPT" ]; then
    "$PY" "$REG_SCRIPT" "$PLUGIN_DIR" && echo "✅ 注册成功" || echo "⚠️ 注册脚本报错，请到 WorkBuddy 专家中心手动刷新"
  else
    echo "⚠️ 未找到 register_expert.py，请到 WorkBuddy 专家中心手动重新注册"
  fi
}

local_version() {
  grep -m1 '"version"' "$1/.codebuddy-plugin/plugin.json" | sed 's/.*: *"//;s/".*//'
}

# ---------------------------------------------------------------
# 本地已是 git 仓库：增量更新（保留提交历史与本地改动）
# ---------------------------------------------------------------
if [ -d "$PLUGIN_DIR/.git" ]; then
  BRANCH=$(git -C "$PLUGIN_DIR" symbolic-ref --short HEAD 2>/dev/null || echo main)
  OLD_V=$(local_version "$PLUGIN_DIR")
  echo "▶ 检查版本（当前 v$OLD_V，分支 $BRANCH）…"
  git -C "$PLUGIN_DIR" fetch --quiet origin
  LOCAL=$(git -C "$PLUGIN_DIR" rev-parse HEAD)
  REMOTE=$(git -C "$PLUGIN_DIR" rev-parse "origin/$BRANCH")

  if [ "$LOCAL" = "$REMOTE" ]; then
    echo "✅ 已是最新版 v$OLD_V，无需更新。"
    exit 0
  fi

  echo "⬆️ 远程有新版本。"
  if [ "$MODE" = "--check" ]; then
    echo "   （--check 模式：未做任何改动。执行 bash sync.sh 即可更新）"
    exit 0
  fi

  if [ "$MODE" = "--reset" ]; then
    echo "⚠️ --reset：丢弃本地改动，硬对齐 origin/$BRANCH"
    git -C "$PLUGIN_DIR" reset --hard "origin/$BRANCH"
    re_register
    echo "✅ 已强制对齐：v$OLD_V → v$(local_version "$PLUGIN_DIR")"
    exit 0
  fi

  DIRTY=$(git -C "$PLUGIN_DIR" status --porcelain)
  if [ -n "$DIRTY" ]; then
    echo "⚠️ 本机有未提交的改动，已停止，不会覆盖你："
    echo "$DIRTY"
    echo
    echo "   想保留： git -C \"$PLUGIN_DIR\" add -A && git -C \"$PLUGIN_DIR\" commit -m \"…\""
    echo "   想丢弃： bash sync.sh --reset"
    exit 1
  fi

  echo "▶ 拉取最新版…"
  git -C "$PLUGIN_DIR" pull --ff-only
  re_register
  echo "✅ 已更新：v$OLD_V → v$(local_version "$PLUGIN_DIR")。刷新 WorkBuddy 专家中心后生效。"
  exit 0
fi

# ---------------------------------------------------------------
# 本机没有仓库：首次安装（clone 一份）
# ---------------------------------------------------------------
if [ "$MODE" = "--check" ]; then
  echo "ℹ️ 本机还没有插件目录（$PLUGIN_DIR）。执行 bash sync.sh 可安装。"
  exit 0
fi

echo "▶ 本机没有插件目录，执行首次安装…"
TMP=$(mktemp -d)
git clone -q "$REPO" "$TMP"
rm -rf "$PLUGIN_DIR"
mkdir -p "$(dirname "$PLUGIN_DIR")"
cp -R "$TMP" "$PLUGIN_DIR"
rm -rf "$TMP"
re_register
echo "✅ 已安装 v$(local_version "$PLUGIN_DIR")。刷新 WorkBuddy 专家中心（或重启）后使用。"
