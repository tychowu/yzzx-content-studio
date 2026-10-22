#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
口播稿字数校验（yzzx-content-studio）

用途：写手交稿前、终审前，各跑一次，结果直接贴回传。
目的：消灭「同一份稿被报出 8 个不同字数」的口径分歧。

═══════════════════════════════════════════════════════════════
【判定分级】—— 只有一条是硬红线，其余一律不拦（2026-10-22 改）
═══════════════════════════════════════════════════════════════
  🔴 硬上限  口径 B > 700            → 必须改（唯一阻塞项）
  🟡 结构配比 某层严重跑偏（超警戒线）→ 建议调一次
  ⚪ 层内偏离 band 区间              → **通过，不必改**
  ⚪ 尾注字数与实测差 ≤ 20 字        → **通过（四舍五入）**

  改这一版的原因：上一批 6 条稿因字数来回改了 7 轮，根因是
  「逐层 band 偏离就报 ⚠️」——写手为消警告反复微调每层的字数，
  改完又触发别层超限，来回追赶。**现在普通偏离一律静默。**

口径定义（唯一权威，别再自创）：
  口径 A（内容量）= 汉字 + 阿拉伯数字的字符数（不含标点、空格、换行、层标行）
  口径 B（占屏  ）= 全部非空白字符数（含标点、含【】内文字、已剔除层标行）
  硬上限：口径 B ≤ 700（任何 IP 无例外）

层标行：形如 `【钩子层】0–8 秒` 的整行是元数据，计入会让字数虚高，剔除。
      `【】` 语气标记本身算正文，保留。

尾注行（`字数：` / `预计时长` / `口播建议：` / `来源`）不计入正文，
      但脚本会**自动比对**尾注写的字数与实测值，差 >20 字才提示回填。

用法：
  python3 check_wordcount.py <稿件文件路径> [更多文件...]
  python3 check_wordcount.py --stdin < 稿件正文      # 从标准输入读
退出码：0 = 全部通过；1 = 有未通过项（仅口径 B 超上限 / 层结构严重跑偏）
"""

import re
import sys
import os

HARD_LIMIT = 700      # 口径 B 硬上限（唯一的硬失败条件）
RECOMMEND_LOW = 560   # 低于此值才提示「可能偏短」（不拦）
TAILNOTE_TOL = 20     # 尾注字数与实测的容差（四舍五入级，不计错）
SPEED_LO, SPEED_HI = 360, 440  # 字/分钟，用于自动推算时长

# ── 五层参考区间（口径 B）────────────────────────────────────────
# 2026-10-22 放宽：旧值（25-40 / 75-130 / 290-405 / 20-50 / 95-120）
# 太窄，每稿必偏离，偏离又触发返工。现在是**纯参考**，普通偏离静默。
BANDS = [
    ("钩子层", 20, 50),
    ("铺垫层", 60, 150),
    ("主体层", 250, 450),
    ("升华层", 15, 60),
    ("引导层", 80, 140),
]

# ── 结构警戒线：只有越过这两条，才算「层跑偏」需要调 ──────────────
# 这是本次唯一会提示「层」的问题（普通偏离不再提示）。
GUARDS = [
    ("钩子层", 15, 60),    # 钩子写太长 → 开头拖沓；太短 → 没抓住人
    ("铺垫层", 45, 180),
    ("主体层", 200, 500),  # 主体是核心，超 500 通常在灌水
    ("升华层", 10, 80),
    ("引导层", 65, 170),
]

LAYER_RE = re.compile(r"^\s*【[^】]*层】")
HAN_RE = re.compile(r"[\u4e00-\u9fff]")
DIGIT_RE = re.compile(r"[0-9]")

# 元数据行：绝不计入正文口径
META_RE = re.compile(r"^\s*(字数\s*[:：]|预计时长|口播建议\s*[:：]|来源\s*[:：]|事实备注|备注\s*[:：])")
# 分隔线（稿件之间的 ───── 分割）
SEP_RE = re.compile(r"^\s*[-─—=_]{8,}\s*$")
# 选题标题行（T2-b｜给3万块催生…）
TITLE_RE = re.compile(r"^\s*T\d+\s*[-–—]?\s*[a-zA-Z]\s*[｜|]")
# 尾注里声明的字数（用于自动比对）
DECLARED_RE = re.compile(r"字数\s*[:：]\s*(\d+)")


def strip_meta(text):
    """剔除元数据行（尾注 / 分隔线 / 选题标题），返回 (正文, 剔除条数)"""
    body_lines, dropped = [], 0
    for ln in text.splitlines():
        s = ln.strip()
        if META_RE.match(ln) or SEP_RE.match(ln) or TITLE_RE.match(ln):
            dropped += 1
        else:
            body_lines.append(ln)
    return "\n".join(body_lines), dropped


def count_kou_a(text):
    """口径 A：汉字 + 阿拉伯数字"""
    return len(HAN_RE.findall(text)) + len(DIGIT_RE.findall(text))


def count_kou_b(text):
    """口径 B：全部非空白字符"""
    return len(re.sub(r"\s", "", text))


def split_layers(body):
    """按层标切分正文 -> [(层名, 该层文本)]，层标行整行剔除（含秒数标注）"""
    layers, cur_name, cur_lines = [], None, []
    for ln in body.splitlines():
        m = LAYER_RE.match(ln)
        if m:
            if cur_name is not None:
                layers.append((cur_name, "\n".join(cur_lines)))
            name = m.group(0).strip().strip("【】")
            name = re.sub(r"\d.*$", "", name).strip() or name
            cur_name, cur_lines = name, []
        else:
            cur_lines.append(ln)
    if cur_name is not None:
        layers.append((cur_name, "\n".join(cur_lines)))
    return layers


def split_scripts(text):
    """按选题标题行（T2-b｜…）把文件切成多篇稿；没有标题行则整份当一篇"""
    blocks, cur = [], []
    for ln in text.splitlines():
        if TITLE_RE.match(ln) and cur:
            blocks.append("\n".join(cur))
            cur = [ln]
        else:
            cur.append(ln)
    if cur and "\n".join(cur).strip():
        blocks.append("\n".join(cur))
    return blocks or [text]


def find_band(name):
    for b in BANDS:
        if name.startswith(b[0][:2]):
            return b
    return None


def find_guard(name):
    for g in GUARDS:
        if name.startswith(g[0][:2]):
            return g
    return None


def check_script(label, text):
    """检查单篇稿，返回 (是否通过, 口径A, 口径B, 各层明细, 声明字数)"""
    body_all, _ = strip_meta(text)
    declared = None
    dm = DECLARED_RE.search(text)
    if dm:
        declared = int(dm.group(1))

    layers = split_layers(body_all)
    if not layers:
        a, b = count_kou_a(body_all), count_kou_b(body_all)
        return b <= HARD_LIMIT, a, b, [("（无层标）", b, None, None, None, None)], declared

    cleaned = []
    for name, raw in layers:
        t, _ = strip_meta(raw)
        cleaned.append((name, t))
    body = "\n".join(t for _, t in cleaned)
    a, b = count_kou_a(body), count_kou_b(body)

    detail = []
    structural_bad = False
    for name, t in cleaned:
        c = count_kou_b(t)
        band = find_band(name)
        guard = find_guard(name)
        lo = band[1] if band else None
        hi = band[2] if band else None
        g_lo = guard[1] if guard else None
        g_hi = guard[2] if guard else None
        bad = False
        if guard is not None and not (g_lo <= c <= g_hi):
            bad = True
            structural_bad = True
        detail.append((name, c, lo, hi, g_lo, g_hi, bad))
    return (b <= HARD_LIMIT and not structural_bad), a, b, detail, declared


def fmt_time(b):
    lo = b / SPEED_HI * 60
    hi = b / SPEED_LO * 60
    return "%d:%02d ~ %d:%02d" % (int(lo // 60), int(lo % 60), int(hi // 60), int(hi % 60))


def check_one(path, text):
    blocks = split_scripts(text)
    print(f"\n===== {path} =====")
    print(f"识别到 {len(blocks)} 篇稿 ｜ 硬上限：口径 B ≤ {HARD_LIMIT}（每篇各算）")
    all_ok = True
    for i, blk in enumerate(blocks, 1):
        ok, a, b, detail, declared = check_script(f"第{i}篇", blk)
        all_ok = all_ok and ok
        title = blk.strip().splitlines()[0] if blk.strip() else ""
        print(f"\n  ── 第{i}篇 {title[:38]}")
        print(f"     口径 A（汉字+数字）: {a}")
        if b <= HARD_LIMIT:
            print(f"     口径 B（含标点）   : {b}  / {HARD_LIMIT}  ✅ 通过（余量 {HARD_LIMIT - b} 字）")
        else:
            print(f"     口径 B（含标点）   : {b}  / {HARD_LIMIT}  ❌ 超上限，必须改")
        if b < RECOMMEND_LOW:
            print(f"     ⚠️ 低于建议下限 {RECOMMEND_LOW}，信息量可能偏少（不拦，可自便）")
        if b <= HARD_LIMIT:
            print(f"     预计时长（{SPEED_LO}–{SPEED_HI} 字/分）: 约 {fmt_time(b)}")

        print("     ── 各层字数（参考区间，普通偏离不必改）──")
        for name, c, lo, hi, g_lo, g_hi, bad in detail:
            if lo is None:
                print(f"     {name}: {c} 字")
            elif bad:
                print(f"     {name}: {c} 字  参考 {lo}–{hi}  ⚠️ 跑偏（警戒 {g_lo}–{g_hi}）→ 建议调一次")
            else:
                print(f"     {name}: {c} 字  参考 {lo}–{hi}")

        if declared is not None:
            diff = declared - b
            if abs(diff) > TAILNOTE_TOL:
                print(f"     ⚠️ 尾注写的 {declared} 字与实测 {b} 差 {diff:+d} 字 → 尾注回填成 {b}")
            else:
                print(f"     尾注字数 {declared} 与实测 {b} 基本一致（差 {diff:+d}，容差 {TAILNOTE_TOL}）")

    print(f"\n--- 总结论：{len(blocks)} 篇稿 {'全部通过' if all_ok else '存在未通过项，按上面的提示改'} ---")
    return all_ok


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 1
    if args[0] == "--stdin":
        text = sys.stdin.read()
        ok = check_one("<stdin>", text)
    else:
        ok = True
        for p in args:
            if not os.path.exists(p):
                print(f"\n===== {p} =====\n❌ 文件不存在")
                ok = False
                continue
            with open(p, encoding="utf-8") as f:
                ok = check_one(p, f.read()) and ok
    print("\n" + ("✅ 全部通过" if ok else "❌ 存在未通过项，按上面的提示改"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
