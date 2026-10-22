#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
口播稿字数校验（yzzx-content-studio）

用途：写手交稿前、终审前，各跑一次，结果直接贴回传。
目的：消灭「同一份稿被报出 8 个不同字数」的口径分歧。

口径定义（唯一权威，别再自创）：
  口径 A（内容量）= 汉字 + 阿拉伯数字的字符数（不含标点、空格、换行、层标行）
  口径 B（占屏  ）= 全部非空白字符数（含标点、含【】内文字、已剔除层标行）
  硬上限：口径 B ≤ 700（任何 IP 无例外）

层标行：形如 `【钩子层】0–8 秒` 的整行是元数据，计入会让字数虚高，剔除。
      `【】` 语气标记本身算正文，保留。

用法：
  python3 check_wordcount.py <稿件文件路径> [更多文件...]
  python3 check_wordcount.py --stdin < 稿件正文      # 从标准输入读
退出码：0 = 全部通过；1 = 有未通过项（超上限 / 超出 band / 缺层标）
"""

import re
import sys
import os

HARD_LIMIT = 700  # 口径 B 硬上限（唯一的硬失败条件）

# 五层参考区间（口径 B，含标点）—— 2026-10-21 按 4 份实际交付稿实测重标定
# 注意：这是「参考区间」，偏离只提示、不拦截；真正的硬门槛只有 口径 B ≤ 700。
# 2026-09-22 定的旧理想配比（钩子 45-55 / 铺垫 120-145 / 主体 325-375 / 升华 58-68 / 引导 45-55）
# 实际没人照做（引导层普遍 100+ 字、升华层普遍 30+ 字），已被实测值取代，不再作废稿理由。
BANDS = [
    ("钩子层", 25, 40),
    ("铺垫层", 75, 130),
    ("主体层", 290, 405),
    ("升华层", 20, 50),
    ("引导层", 95, 120),
]

LAYER_RE = re.compile(r"^\s*【[^】]*层】")
HAN_RE = re.compile(r"[\u4e00-\u9fff]")
DIGIT_RE = re.compile(r"[0-9]")

# 元数据行：绝不计入正文口径
#   字数：695 字｜ 预计时长：约 1 分 40 秒
#   口播建议：……
#   来源：……（2026-10-22 起，事实备注已取消，改为来源直采）
META_RE = re.compile(r"^\s*(字数\s*[:：]|预计时长|口播建议\s*[:：]|来源\s*[:：]|事实备注|备注\s*[:：])")
# 分隔线（稿件之间的 ───── 分割）
SEP_RE = re.compile(r"^\s*[-─—=_]{8,}\s*$")
# 选题标题行（T2-b｜给3万块催生…）
TITLE_RE = re.compile(r"^\s*T\d+\s*[-–—]?\s*[a-zA-Z]\s*[｜|]")


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


def split_layers(text):
    """按层标切分原文 -> [(层名, 该层原始文本)]"""
    layers, cur_name, cur_lines = [], None, []
    for ln in text.splitlines():
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


def count_kou_a(text):
    """口径 A：汉字 + 阿拉伯数字"""
    return len(HAN_RE.findall(text)) + len(DIGIT_RE.findall(text))


def count_kou_b(text):
    """口径 B：全部非空白字符"""
    return len(re.sub(r"\s", "", text))


def split_layers(body):
    """按层标切分正文 -> [(层名, 该层文本)]，层标本身已剔除"""
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


def check_script(label, text):
    """检查单篇稿，返回 (是否通过, 口径A, 口径B, 各段明细)"""
    layers = split_layers(text)
    if not layers:
        body, _ = strip_meta(text)
        a, b = count_kou_a(body), count_kou_b(body)
        return b <= HARD_LIMIT, a, b, [("（无层标）", b, None, None)]

    cleaned = []
    for name, raw in layers:
        t, _ = strip_meta(raw)
        cleaned.append((name, t))
    body = "\n".join(t for _, t in cleaned)
    a, b = count_kou_a(body), count_kou_b(body)
    detail = []
    for name, t in cleaned:
        c = count_kou_b(t)
        band = next((b2 for b2 in BANDS if name.startswith(b2[0][:2])), None)
        detail.append((name, c, band[1] if band else None, band[2] if band else None))
    return b <= HARD_LIMIT, a, b, detail


def check_one(path, text):
    blocks = split_scripts(text)
    print(f"\n===== {path} =====")
    print(f"识别到 {len(blocks)} 篇稿 ｜ 硬上限：口径 B ≤ {HARD_LIMIT}（每篇各算）")
    all_ok = True
    for i, blk in enumerate(blocks, 1):
        ok, a, b, detail = check_script(f"第{i}篇", blk)
        all_ok = all_ok and ok
        title = blk.strip().splitlines()[0] if blk.strip() else ""
        print(f"\n  ── 第{i}篇 {title[:38]}")
        print(f"     口径 A（汉字+数字）: {a}")
        print(f"     口径 B（含标点）   : {b}  / {HARD_LIMIT}  {'✅ 通过' if ok else '❌ 超上限，必须改'}")
        for name, c, lo, hi in detail:
            if lo is None:
                print(f"     {name}: {c} 字  （无参考区间）")
            else:
                good = lo <= c <= hi
                print(f"     {name}: {c} 字  参考 {lo}–{hi}  {'✅' if good else '⚠️ 偏离（不拦截）'}")
    print(f"\n--- 总结论：{len(blocks)} 篇稿 {'全部通过' if all_ok else '存在超上限稿，必须改'} ---")
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
