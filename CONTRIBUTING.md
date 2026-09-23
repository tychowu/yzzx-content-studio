# 协作约定（yzzx-content-studio 专家包）

这是一个**团队共用的专家包源码仓库**。每个人在本地修改后，通过 Git 把改动汇聚到这里，再分发给所有人。这样人人都能用上最新版。

## 仓库
- 地址：`https://github.com/tychowu/yzzx-content-studio`（私有，需胡子哥邀请才能访问）
- 本机插件目录：`~/.workbuddy/plugins/marketplaces/my-experts/plugins/yzzx-content-studio/`

## 你属于哪类？

### A. 只想要最新版（纯使用）
直接跑仓库里的同步脚本（克隆最新 → 覆盖本地 → 重新注册）：
```bash
bash sync.sh
```
跑完刷新 WorkBuddy 专家中心即可。

> ⚠️ `sync.sh` 会**覆盖**本地插件目录。如果你自己改过且还没提交，先备份或改用下方 B 流程。

### B. 改了想让大家用（贡献者）
```bash
git clone https://github.com/tychowu/yzzx-content-studio.git
cd yzzx-content-studio
# …改文件…
git pull            # 先拉别人的最新改动，避免覆盖
git add -A
git commit -m "改了什么：例如 新增 IP 卡 / 收紧合规词"
git push
```
首次 clone 前先 `gh auth login`（或用 GitHub 账号密码 / token），否则拉不下来私有库。

## 协作红线
1. **改前先 `git pull`**，别闷头覆盖别人。
2. 小改动（文案润色、选题公式微调、补 IP 卡）直接 push 到 `main`。
3. 大改动（成员结构、技能重构、版本升级）开 **Pull Request**，胡子哥 review 后合并。
4. **头像等二进制（`avatars/*.png`）只在 `main` 由胡子哥改**，其他人别动，否则合并会冲突。
5. **绝不提交密钥 / token / 个人敏感文件**。
6. commit message 写清改了什么（中文即可）。

## 改完必须重注册
专家包是本地注册制的——改完文件不等于生效：
- 纯使用者：跑 `sync.sh` 已自动重注册。
- 贡献者本地自测：改完跑一次 `sync.sh`，或到 WorkBuddy 专家中心手动刷新 / 重注册。
