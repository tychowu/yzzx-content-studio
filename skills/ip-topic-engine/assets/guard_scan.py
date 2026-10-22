#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""合规扫描脚本（规则层）—— 把郑无虞二查 / 三查里能机器化的部分一次扫完

🔻 **这个脚本替代什么**（2026-10-22 用户定：精简人数）
合规官的三查里，**二查（平台敏感词与限流风险）和三查（港险宣传红线）全是规则匹配**，
机器扫不会漏、不会看走眼。凡是本脚本命中的，**直接进「必改清单」，不需要合规官逐词比对**。
合规官只保留**一查（口径一致性）** —— 那是唯一不可规则化的一类。

**合规官仍需人工裁决的三类（脚本查不出）**：
  1. 口径转写 —— 数字对但换了分母 / 换了主语（「保费占比 29%」→「这批人里近三成」）
  2. 语义升格 —— 把「在讨论」写成「在落地」（字面全合规，意思变了）
  3. 语境判断 —— 同一个「保证」是修饰风险还是承诺收益

用法：
  python3 guard_scan.py --script 胡子哥口播稿-2026-10-22.txt
  python3 guard_scan.py --script 合集.txt --dir /tmp/guard-md --titles /tmp/发布包-校验.json
  python3 guard_scan.py --script 合集.txt --strict     # 有命中就非零退出（可做 CI）

参数：
  --script  稿件 txt（单篇或多篇合集，用 ─── 分隔线 + "T1-d｜标题" 开头）
  --dir     可选：md-out 目录，连标签条数上限一起查
  --titles  可选：发布包 json，校验标题 ≤10 字 / 简介 ≤40 字 / 数量 / 🌟推荐唯一
  --strict  有命中时 exit 1
  --quiet   只输出命中项，不输出 OK 行
"""

import argparse
import json
import os
import re
import sys

SEP = re.compile(r'\n─{5,}\n')

# ════════════════════════════════════════════════════════════
# 词表 A：三词禁令（voice-playbook §6.9，硬禁令 · 三平台都算）
# ════════════════════════════════════════════════════════════
CTA_BAN = [
    ('微信', 'CTA 三词禁令（硬）'),
    ('私信', 'CTA 三词禁令（硬）'),
    ('评论区', 'CTA 三词禁令（硬）'),
]
# 组合变体
CTA_BAN_VARIANTS = [
    '微信号', '加微信', '加我微信', 'vx', 'VX', '威信', '扣在',
    '私信我', '私信聊', '留言', '评论区留言', '扣我', '戳我', '二维码', '公众号',
]

# ════════════════════════════════════════════════════════════
# 词表 B：引流词（平台会判定为导流，压推荐流量）
# ════════════════════════════════════════════════════════════
DIVERSION = [
    '加我', '主页', '简介', '戳我', '扫码', '关注我看', '下方链接',
    '点击链接', '详情咨询', '联系我们',
]

# ════════════════════════════════════════════════════════════
# 词表 C：承诺 / 绝对化（港险宣传红线：不得承诺收益、不得保证）
# ════════════════════════════════════════════════════════════
PROMISE = [
    '保本', '保息', '稳赚', '躺赚', '包赚', '刚性兑付', '刚性兑',
    '零风险', '无风险', '100%', '百分百', '百分之百',
    '保证', '确保', '肯定能', '一定能', '必定', '绝对',
    '稳赢', '稳定收益', '固定收益',
]
# 需要判断语境的「弱承诺」—— 命中只是提醒，不一定是违规
PROMISE_SOFT = ['最好的', '最好的选择', '一定会', '几乎不', '风险很低', '低风险']

# ════════════════════════════════════════════════════════════
# 词表 D：恐吓营销 / 制造焦虑（港险宣传红线）
# ════════════════════════════════════════════════════════════
FRIGHTEN = [
    '不买就亏', '亏死', '血本无归', '倾家荡产', '跳楼', '活不下去',
    '最后一天', '错过就没有', '再不买', '最后一次机会', '赶紧买', '马上买',
    '不然就', '被割', '韭菜',
]

# ════════════════════════════════════════════════════════════
# 词表 E：具体产品名 / 公司名（不得出现）
# ════════════════════════════════════════════════════════════
BRAND = [
    '保诚', '友邦', '安盛', '宏利', '安达', '富通', '忠意', '万通',
    'AEON', 'AIA', 'Prudential', 'Manulife',
]

# ════════════════════════════════════════════════════════════
# 词表 F：平台限流敏感词（ip-topic-engine 第六节替换表）
#   只在「标题 / 简介 / 标签」层是硬命中；口播正文层是提醒
# ════════════════════════════════════════════════════════════
FLOW_LIMIT_REPLACE = {
    '保险': '兜底 / Plan B / 安全垫 / 确定性安排',
    '投保': '兜底 / Plan B / 安全垫',
    '理赔': '兜底 / 确定性安排',
    '保单': 'Plan B / 兜底',
    '险种': '确定性安排',
    '收益率': '购买力 / 时间成本 / 长期代价',
    '回报率': '购买力 / 时间成本 / 长期代价',
    '理财': '选择权 / 现金流 / 抗风险能力',
    '投资': '选择权 / 现金流',
    '暴富': '现金流 / 抗风险能力',
    '复利': '时间成本 / 长期代价',
    '年化': '长期代价',
    '分红': '确定性安排（口播层可用，标题层慎用）',
}

META_RE = re.compile(r'^\s*(字数\s*[:：]|预计时长|口播建议\s*[:：]|备注\s*[:：]|来源\s*[:：]|链接\s*[:：]|媒体\s*[:：])')
TAG_RE = re.compile(r'#[\w\u4e00-\u9fff]+')
CTA_CANON = '我是胡子哥，关注我，带你用香港视角看趋势与选择！'

# ════════════════════════════════════════════════════════════
# 否定语境识别 —— 合规写法本身就是「否定承诺」
#   「非保证」「不是保证」「不等于保证收益」「红利不保证」= 合规
#   裸用「保证」= 可能违规
#   规则：命中词前 6 字内出现否定词 → 降级为「提醒」并标注「否定语境」
# ════════════════════════════════════════════════════════════
NEGATIONS = ['非', '不', '没', '未', '勿', '免', '拒绝', '并非', '不是', '不等于', '不代表', '谈不上']
NEG_WINDOW = 6

# ════════════════════════════════════════════════════════════
# 正当术语白名单 —— 这些是制度/金融术语，不是承诺收益
#   「弱方兑换保证」= 香港联汇制度的正式说法
#   「保证利率」/「保证现金价值」= 保险合同里的「保证与非保证」分类术语
#   命中这些不算违规
# ════════════════════════════════════════════════════════════
TERM_WHITELIST = {
    '保证': ['弱方兑换保证', '保证利率', '保证现金价值', '保证利益', '保证与非保证',
             '保证部分', '保证给付', '保证收益', '保证与非保证收益', '最低保证'],
}


def strip_meta(text):
    """去掉稿尾元信息行与层标行，只留正文（用于扫词）"""
    out = []
    for ln in text.split('\n'):
        if META_RE.match(ln):
            continue
        out.append(ln)
    return '\n'.join(out)


def split_scripts(text):
    parts = SEP.split(text)
    return [p for p in parts if p.strip()]


def is_negated(body, pos, word):
    """判断命中位置是否处于否定语境（如「非保证」「不等于保证收益」）

    返回 True = 否定语境 = 合规写法，降级为提醒
    """
    left = body[max(0, pos - NEG_WINDOW):pos]
    for neg in NEGATIONS:
        if neg in left:
            return True
    return False


def is_term(body, pos, word):
    """判断命中位置是否属于正当术语（如「弱方兑换保证」= 联汇制度正式说法）

    返回 True = 制度/合同术语，不是承诺收益
    """
    for phrase in TERM_WHITELIST.get(word, []):
        if body[max(0, pos - len(phrase) + len(word)):pos + len(word)] == phrase:
            return True
    return False


def scan_text(s, label, hits, counters):
    """在正文里扫词。hits: [(严重度, 篇目, 类别, 词, 建议)]"""
    body = strip_meta(s)
    for w, cat in CTA_BAN:
        n = body.count(w)
        if n:
            hits.append(('必改', label, cat, w, f'「{w}」×{n} — 平台判引流，直接压推荐。改写句子绕开'))
    for w in CTA_BAN_VARIANTS:
        n = body.lower().count(w.lower())
        if n:
            hits.append(('必改', label, '引流词/组合变体', w, f'「{w}」×{n} — 同上，属三词禁令变体'))
    for w in DIVERSION:
        n = body.count(w)
        if n:
            hits.append(('必改', label, '引流词', w, f'「{w}」×{n} — 引流话术，改成价值承诺（"下条讲 XXX"）'))
    for w in PROMISE:
        # 逐个出现位置判断否定语境 / 正当术语
        naked, negated, termed = 0, 0, 0
        start = 0
        while True:
            p = body.find(w, start)
            if p < 0:
                break
            if is_negated(body, p, w):
                negated += 1
            elif is_term(body, p, w):
                termed += 1
            else:
                naked += 1
            start = p + len(w)
        if naked:
            extra = ''
            if negated:
                extra += f'（另有 {negated} 处是「非{w}」这类否定语境，合规，不算）'
            if termed:
                extra += f'（另有 {termed} 处是「弱方兑换保证」这类制度术语，合规，不算）'
            hits.append(('必改', label, '承诺/绝对化（港险红线）', w,
                         f'裸用「{w}」×{naked} — 改大概率/历史上/通常/某种程度上' + extra))
        elif negated or termed:
            bits = []
            if negated:
                bits.append(f'{negated} 处否定写法')
            if termed:
                bits.append(f'{termed} 处制度术语')
            hits.append(('提醒', label, '承诺词（否定/术语语境）', w,
                         f'「{w}」×{negated + termed} — ' + '、'.join(bits) + '，属合规，确认无漏改即可'))
    for w in PROMISE_SOFT:
        n = body.count(w)
        if n:
            hits.append(('提醒', label, '弱承诺（需语境判断）', w,
                         f'「{w}」×{n} — 字面未必违规，但请确认不是承诺收益'))
    for w in FRIGHTEN:
        n = body.count(w)
        if n:
            hits.append(('必改', label, '恐吓营销（港险红线）', w,
                         f'「{w}」×{n} — 删掉，港险宣传不得制造焦虑'))
    for w in BRAND:
        n = body.count(w)
        if n:
            hits.append(('必改', label, '具体公司名（不得出现）', w,
                         f'「{w}」×{n} — 改成"有资格投的机构"这类泛指'))
    counters['cta_full'] += s.count(CTA_CANON)
    counters['cta_prefix'] += s.count('我是胡子哥，关注我，')


def scan_publish(titles_path, hits, counters):
    """扫发布包：标题 ≤10 字 / 简介 ≤40 字 / 数量 / 🌟推荐唯一"""
    try:
        d = json.load(open(titles_path, encoding='utf-8'))
    except Exception as e:
        hits.append(('提醒', '发布包', '读取失败', os.path.basename(titles_path), str(e)))
        return
    for tid, v in d.items():
        tlist = v.get('标题', [])
        slist = v.get('简介', [])
        if len(tlist) != 10:
            hits.append(('提醒', tid, '标题数量', f'{len(tlist)} 个', '标准是 10 个（可按需减，但要在交付说明里写清）'))
        if len(slist) != 5:
            hits.append(('提醒', tid, '简介数量', f'{len(slist)} 个', '标准是 5 个'))
        for i, s in enumerate(tlist):
            # 🌟推荐 是 make_pack.py 贴的标记（4 个字符），不计入标题字数
            bare = s.replace('🌟推荐', '').replace('🌟', '')
            if len(bare) > 10:
                hits.append(('必改', tid, f'标题[{i}] 超长', f'{len(bare)} 字',
                             f'「{bare}」压到 ≤10 字'))
        for i, s in enumerate(slist):
            if len(s) > 40:
                hits.append(('必改', tid, f'简介[{i}] 超长', f'{len(s)} 字',
                             f'压到 ≤40 字'))
        # 🌟推荐唯一性
        # 原始「发布包.json」不带 🌟（那是 make_pack.py 加的），只有「发布包-校验.json」带。
        # → 只有当这份包**整体一个 🌟 都没有**时，才提示"你可能传错了文件"；
        #   有 🌟 但数量不对，才是真问题。
        star = sum(1 for s in tlist if '🌟' in s)
        counters['topics'] += 1
        if star == 0:
            counters['no_star_topics'] += 1
        elif star != 1:
            hits.append(('必改', tid, '🌟推荐标记', f'{star} 个', '必须恰好 1 个'))
        # 标题层的平台敏感词（硬）
        for i, s in enumerate(tlist):
            for w, sug in FLOW_LIMIT_REPLACE.items():
                if w in s:
                    hits.append(('提醒', tid, f'标题[{i}] 限流敏感词', w,
                                 f'标题层建议换成：{sug}'))
        # 三词禁令也要查标题 / 简介 / 标签
        for field, arr in (('标题', tlist), ('简介', slist)):
            for i, s in enumerate(arr):
                for w in ('微信', '私信', '评论区'):
                    if w in s:
                        hits.append(('必改', tid, f'{field}[{i}] 三词禁令', w, f'「{s}」含 {w}'))
        tags = v.get('标签', {})
        if isinstance(tags, dict):
            for plat, arr in tags.items():
                if plat in ('抖音',):
                    if len(arr) > 5:
                        hits.append(('必改', tid, f'{plat}标签超上限', f'{len(arr)} 个', '抖音 ≤5 个'))
                else:
                    if len(arr) > 8:
                        hits.append(('必改', tid, f'{plat}标签超上限', f'{len(arr)} 个', '视频号/小红书 ≤8 个'))


def scan_md(md_dir, hits):
    """扫 md-out：标签条数 / 层名残留 / toggle 语法"""
    if not os.path.isdir(md_dir):
        return
    for fn in sorted(os.listdir(md_dir)):
        if not fn.endswith('.md'):
            continue
        tid = fn[:-3]
        t = open(os.path.join(md_dir, fn), encoding='utf-8').read()
        if '【钩子层】' in t or '【主体层】' in t or '【引导层】' in t:
            hits.append(('必改', tid, '层名残留', '【XX层】', '发布页里不应出现层标行'))
        n_toggle = t.count('<toggle')
        n_old = t.count('{toggle="true"}')
        if n_old:
            hits.append(('必改', tid, '旧版 toggle 语法', f'{n_old} 处', '应统一为 <toggle heading="h4">'))
        if n_toggle != 5:
            hits.append(('提醒', tid, 'toggle 数量', f'{n_toggle} 个', '标准是 5 个板块'))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--script')
    ap.add_argument('--dir')
    ap.add_argument('--titles')
    ap.add_argument('--strict', action='store_true')
    ap.add_argument('--quiet', action='store_true')
    args = ap.parse_args()

    if not args.script and not args.dir and not args.titles:
        print(__doc__)
        sys.exit(2)

    hits = []
    counters = {'cta_full': 0, 'cta_prefix': 0, 'topics': 0, 'no_star_topics': 0}

    if args.script:
        s = open(args.script, encoding='utf-8').read()
        parts = split_scripts(s)
        for p in parts:
            st = p.strip()
            title = st.split('\n')[0].strip()[:70]
            scan_text(st, title, hits, counters)
        if not args.quiet:
            print(f'📄 稿件 {len(parts)} 篇已扫：{os.path.basename(args.script)}')

    if args.titles:
        scan_publish(args.titles, hits, counters)
        if not args.quiet:
            print(f'📦 发布包已扫：{os.path.basename(args.titles)}（{counters["topics"]} 个选题）')
        if counters['topics'] and counters['no_star_topics'] == counters['topics']:
            print('ℹ️  这份发布包一个 🌟 都没有 → 多半传的是原始「发布包.json」。'
                  '\n   带 🌟 的是 make_pack.py 产出的「发布包-校验.json」（Notion 写入要用那份）。')

    if args.dir:
        scan_md(args.dir, hits)
        if not args.quiet:
            print(f'📁 md-out 已扫：{args.dir}')

    # CTA 统计
    if counters['cta_full'] == 0 and args.script:
        hits.append(('提醒', 'CTA', '结尾 CTA 缺失', '0 处',
                     f'未见标准 CTA「{CTA_CANON}」'))

    must = [h for h in hits if h[0] == '必改']
    soft = [h for h in hits if h[0] == '提醒']

    print()
    if must:
        print(f'🚫 必改 {len(must)} 项')
        for sev, who, cat, what, how in must:
            print(f'  [{who}] {cat}：{what}')
            print(f'      → {how}')
        print()
    if soft:
        print(f'⚠️  提醒 {len(soft)} 项（多为语境判断，需人工裁决）')
        for sev, who, cat, what, how in soft:
            print(f'  [{who}] {cat}：{what}')
            print(f'      → {how}')
        print()

    if not must and not soft:
        print('✅ 合规扫描全绿：规则层零命中')
    elif not must:
        print(f'✅ 无必改项（{len(soft)} 条提醒留给合规官判断语境）')

    print()
    print('ℹ️ 本脚本只覆盖规则层。合规官仍须人工审：**口径转写**（数字换了分母）、'
          '\n   **语义升格**（把"在讨论"写成"在落地"）、**语境判断**（同一个"保证"是修饰还是承诺）。')

    if args.strict and must:
        sys.exit(1)


if __name__ == '__main__':
    main()