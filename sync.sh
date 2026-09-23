#!/bin/bash
# yzzx-content-studio 一键同步：拉最新版 → 覆盖本地插件目录 → 重新注册
# 用法：bash sync.sh
set -e

REPO="https://github.com/tychowu/yzzx-content-studio.git"
PLUGIN_DIR="$HOME/.workbuddy/plugins/marketplaces/my-experts/plugins/yzzx-content-studio"
REG_SCRIPT="/Applications/WorkBuddy.app/Contents/Resources/app.asar.unpacked/resources/plugins/workbuddy-builtin/skills/expert-manager/scripts/register_expert.py"

echo "▶ 从 GitHub 拉取最新版…"
TMP=$(mktemp -d)
git clone -q "$REPO" "$TMP"

echo "▶ 覆盖本地插件目录 ($PLUGIN_DIR)…"
rm -rf "$PLUGIN_DIR"
mkdir -p "$(dirname "$PLUGIN_DIR")"
cp -R "$TMP" "$PLUGIN_DIR"
rm -rf "$TMP"

echo "▶ 重新注册到 WorkBuddy…"
PY="$HOME/.workbuddy/binaries/python/envs/default/bin/python"
if [ ! -x "$PY" ]; then PY="python3"; fi
if [ -f "$REG_SCRIPT" ]; then
  "$PY" "$REG_SCRIPT" "$PLUGIN_DIR" && echo "✅ 注册成功" || echo "⚠️ 注册脚本报错，请到 WorkBuddy 专家中心手动刷新"
else
  echo "⚠️ 未找到 register_expert.py，请到 WorkBuddy 专家中心手动重新注册"
fi

echo "✅ 已更新到最新版。请刷新 WorkBuddy 专家中心（或重启）后使用。"
