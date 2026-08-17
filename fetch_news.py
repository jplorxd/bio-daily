#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生物晨报 · 每日资讯聚合脚本
抓取多个中文生物资讯源，自动分类，生成:
  - data/news.json     结构化数据
  - site/index.html    静态晨报网页（GitHub Pages 部署用）
"""
import json, os, re, sys, time
from datetime import datetime, timedelta
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36 BioDailyBot/1.0",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Accept": "text/html,application/xhtml+xml",
}
TIMEOUT = 20
MAX_ITEMS_PER_SOURCE = 50
MAX_AGE_DAYS = 7
DATE_PATTERNS = [
    re.compile(r"(20\d{2})[-/年](\d{1,2})[-/月](\d{1,2})日?"),
    re.compile(r"(\d{1,2})[-/月](\d{1,2})日"),
]
CATEGORY_RULES = [
    ("疾病与治疗", ["癌症","肿瘤","癌","白血病","淋巴瘤","免疫治疗","CAR-T","抗体","疫苗","药物","新药","临床","获批","FDA","NMPA","患者","治疗","疗法","阿尔茨海默","帕金森","糖尿病","心血管","肝","肾","疟疾","感染","病毒"]),
    ("产业与公司", ["融资","收购","并购","上市","合作","签约","成立","发布","推出","投资","战略","布局","财报","营收","公司","集团","制药","生物医药","license","License","管线","商业化","产能","工厂","合同","订单"]),
    ("科研前沿", ["Science","Nature","Cell","论文","研究","揭示","发现","机制","首次","课题组","团队","科学家","新发现","突破","进展","成果","解析","证实","基因组","基因","CRISPR","编辑","单细胞","测序","多组学","蛋白","结构"]),
    ("技术突破", ["AI","人工智能","大模型","机器学习","深度学习","类器官","器官芯片","合成生物","合成生物学","发酵","酶","生物制造","细胞工厂","3D打印","生物材料","纳米","芯片","自动化","高通量","机器人"]),
    ("综合", []),
]
IRRELEVANT_KEYWORDS = [
    "地铁","房地产","房价","楼市","稀土","电网","居民用电","用电量","光伏","风电",
    "碳排放","碳中和","汽车","锂电","电池","钢铁","股市","股票","基金","黄金",
    "石油","期货","货币政策","央行","电竞","游戏","电影","电视剧","综艺","体育",
    "足球","篮球","人工智能大会","数字经济","数据要素","算力","大模型竞赛",
]
BIO_MUST_KEYWORDS = [
    "生物","细胞","基因","蛋白","核酸","RNA","DNA","CRISPR","基因组","肿瘤","癌症",
    "癌","免疫","疫苗","药物","临床","疾病","感染","细菌","病毒","真菌","微生物",
    "酶","代谢","神经","脑","心脏","肝","肾","肺","肠道","菌群","抗体","治疗",
    "疗法","患者","生态","进化","物种","植物","动物","昆虫","海洋生物","合成生物",
    "类器官","器官芯片","干细胞","测序","单细胞","多组学","表观遗传","线粒体",
    "溶酶体","蛋白质","受体","信号通路","脂质","发酵",
]

def fetch_html(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        r.encoding = r.apparent_encoding or "utf-8"
        return BeautifulSoup(r.text, "lxml")
    except Exception as e:
        print(f"  [warn] 抓取失败 {url}: {e}")
        return None

def extract_date(text, now):
    if not text:
        return now.strftime("%Y-%m-%d")
    for pat in DATE_PATTERNS:
        m = pat.search(text)
        if m:
            g = m.groups()
            if len(g) == 3:
                y, mo, d = int(g[0]), int(g[1]), int(g[2])
            else:
                mo, d = int(g[0]), int(g[1]); y = now.year
            try:
                return datetime(y, mo, d).strftime("%Y-%m-%d")
            except ValueError:
                pass
    return now.strftime("%Y-%m-%d")

def is_recent(date_str, now, max_days=MAX_AGE_DAYS):
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d")
        return 0 <= (now - d).days <= max_days
    except ValueError:
        return False

def is_relevant(title, strict=False):
    if any(kw in title for kw in IRRELEVANT_KEYWORDS):
        return False
    if strict:
        return any(kw in title for kw in BIO_MUST_KEYWORDS)
    return True

def classify(title, summary=""):
    text = f"{title} {summary}"
    for cat, kws in CATEGORY_RULES:
        if cat == "综合":
            return cat
        for kw in kws:
            if kw in text:
                return cat
    return "综合"

def crawl_bioon():
    print(">> 抓取 生物谷 (bioon.com)")
    soup = fetch_html("https://www.bioon.com/")
    if soup is None: return []
    now = datetime.now(); items = []; seen = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "news.bioon.com/article/" not in href: continue
        url = urljoin("https://www.bioon.com/", href)
        if url in seen: continue
        title = a.get_text(" ", strip=True)
        if len(title) < 8: continue
        seen.add(url)
        date_text = ""; parent = a
        for _ in range(4):
            parent = parent.parent
            if parent is None: break
            date_text = parent.get_text(" ", strip=True)
            if re.search(r"20\d{2}", date_text): break
        date = extract_date(date_text, now)
        if not is_recent(date, now): continue
        if not is_relevant(title, strict=False): continue
        items.append({"title": title, "url": url, "date": date, "source": "生物谷", "category": classify(title), "summary": ""})
        if len(items) >= MAX_ITEMS_PER_SOURCE: break
    print(f"  获取 {len(items)} 条")
    return items

def crawl_ebiotrade():
    print(">> 抓取 生物通 (ebiotrade.com)")
    soup = fetch_html("https://www.ebiotrade.com/newsf/")
    if soup is None: return []
    now = datetime.now(); items = []; seen = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "ebiotrade.com/newsf/" not in href: continue
        url = urljoin("https://www.ebiotrade.com/", href)
        if url in seen: continue
        title = a.get_text(" ", strip=True)
        if len(title) < 8: continue
        seen.add(url)
        date_text = ""; parent = a
        for _ in range(4):
            parent = parent.parent
            if parent is None: break
            date_text = parent.get_text(" ", strip=True)
            if re.search(r"20\d{2}", date_text): break
        date = extract_date(date_text, now)
        if not is_recent(date, now): continue
        if not is_relevant(title, strict=True): continue
        items.append({"title": title, "url": url, "date": date, "source": "生物通", "category": classify(title), "summary": ""})
        if len(items) >= MAX_ITEMS_PER_SOURCE: break
    print(f"  获取 {len(items)} 条")
    return items

def render_html(meta, grouped, items):
    today = meta["date"]
    cards_html = []
    for cat in ["科研前沿","疾病与治疗","产业与公司","技术突破","综合"]:
        cat_items = grouped.get(cat, [])
        if not cat_items: continue
        cat_cards = []
        for it in cat_items:
            summary_html = f'<p class="summary">{it["summary"]}</p>' if it.get("summary") else ""
            cat_cards.append(f'''<article class="card">
<div class="card-head"><span class="tag tag-{cat}">{cat}</span><span class="source">{it["source"]}</span><span class="date">{it["date"]}</span></div>
<h3><a href="{it["url"]}" target="_blank" rel="noopener">{it["title"]}</a></h3>{summary_html}</article>''')
        cards_html.append(f'<section class="section" id="{cat}"><h2 class="section-title">{cat} <span class="count">{len(cat_items)}</span></h2><div class="cards">{"".join(cat_cards)}</div></section>')
    nav_html = "".join(f'<a href="#{cat}">{cat}</a>' for cat in grouped.keys())
    total = len(items)
    return f'''<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>生物晨报 · {today}</title>
<meta name="description" content="每日中文生物资讯晨报">
<style>
:root {{ --bg:#f6f8fa; --card:#fff; --ink:#1f2937; --muted:#6b7280; --accent:#16a34a; --accent2:#0ea5e9; --border:#e5e7eb; }}
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family:-apple-system,"PingFang SC","Microsoft YaHei","Noto Sans SC",sans-serif; background:var(--bg); color:var(--ink); line-height:1.7; }}
.container {{ max-width:860px; margin:0 auto; padding:0 20px; }}
header.hero {{ background:linear-gradient(135deg,#065f46 0%,#0ea5e9 100%); color:#fff; padding:48px 20px 36px; text-align:center; }}
header.hero h1 {{ font-size:2rem; letter-spacing:2px; }}
header.hero .date-line {{ margin-top:10px; opacity:.92; font-size:.95rem; }}
header.hero .meta-line {{ margin-top:6px; font-size:.82rem; opacity:.75; }}
nav.tabs {{ display:flex; flex-wrap:wrap; gap:8px; justify-content:center; padding:16px 20px; background:var(--card); border-bottom:1px solid var(--border); position:sticky; top:0; z-index:10; }}
nav.tabs a {{ text-decoration:none; color:var(--muted); font-size:.88rem; padding:5px 14px; border-radius:999px; border:1px solid var(--border); transition:all .2s; }}
nav.tabs a:hover {{ color:var(--accent); border-color:var(--accent); }}
main {{ padding:28px 20px 60px; }}
.section {{ margin-bottom:36px; }}
.section-title {{ font-size:1.15rem; margin-bottom:14px; display:flex; align-items:center; gap:8px; }}
.section-title::before {{ content:""; width:5px; height:20px; border-radius:3px; background:var(--accent); display:inline-block; }}
.section-title .count {{ font-size:.78rem; background:#e0f2fe; color:#0369a1; padding:1px 9px; border-radius:999px; }}
.cards {{ display:grid; grid-template-columns:1fr; gap:14px; }}
.card {{ background:var(--card); border:1px solid var(--border); border-radius:14px; padding:16px 18px; transition:box-shadow .2s,transform .2s; }}
.card:hover {{ box-shadow:0 4px 16px rgba(0,0,0,.07); transform:translateY(-2px); }}
.card-head {{ display:flex; gap:10px; align-items:center; font-size:.78rem; margin-bottom:6px; }}
.tag {{ padding:1px 10px; border-radius:999px; font-size:.75rem; }}
.tag-科研前沿 {{ background:#dbeafe; color:#1d4ed8; }}
.tag-疾病与治疗 {{ background:#fce7f3; color:#be185d; }}
.tag-产业与公司 {{ background:#dcfce7; color:#15803d; }}
.tag-技术突破 {{ background:#fef3c7; color:#b45309; }}
.tag-综合 {{ background:#f3f4f6; color:#4b5563; }}
.source {{ color:var(--accent2); font-weight:600; }}
.date {{ color:var(--muted); margin-left:auto; }}
.card h3 {{ font-size:.98rem; line-height:1.55; }}
.card h3 a {{ color:var(--ink); text-decoration:none; }}
.card h3 a:hover {{ color:var(--accent); }}
.summary {{ color:var(--muted); font-size:.86rem; margin-top:6px; }}
footer {{ text-align:center; color:var(--muted); font-size:.8rem; padding:24px 20px 40px; border-top:1px solid var(--border); }}
@media (min-width:640px) {{ .cards {{ grid-template-columns:1fr 1fr; }} .card:nth-child(3n+1) {{ grid-column:1/-1; }} }}
</style></head>
<body>
<header class="hero"><h1>🧬 生物晨报</h1><div class="date-line">🌿 {today} · 共 {total} 条资讯</div><div class="meta-line">聚合 生物谷 · 生物通 ｜ 每天自动更新</div></header>
<nav class="tabs">{nav_html}</nav>
<main class="container">{"".join(cards_html)}</main>
<footer>本页面由「生物晨报」自动生成 · 内容版权归原始来源所有 · 数据仅供参考<br>生成时间: {meta["generated_at"]} ｜ 数据源: 生物谷 / 生物通</footer>
</body></html>'''

def main():
    print("=" * 50); print("  生物晨报 · 每日资讯聚合"); print("=" * 50)
    all_items = []
    for crawler in (crawl_bioon, crawl_ebiotrade):
        try: all_items.extend(crawler())
        except Exception as e: print(f"  [warn] 源抓取异常: {e}")
        time.sleep(1)
    if not all_items:
        print("!! 未获取到任何资讯"); sys.exit(1)
    seen_titles = set(); unique = []
    for it in all_items:
        norm_title = re.sub(r"[!！?？\s]+$", "", it["title"])
        key = norm_title[:60]
        if key in seen_titles: continue
        seen_titles.add(key); it["title"] = norm_title; unique.append(it)
    unique.sort(key=lambda x: x["date"], reverse=True)
    grouped = {}
    for it in unique: grouped.setdefault(it["category"], []).append(it)
    now = datetime.now()
    meta = {"date": now.strftime("%Y-%m-%d"), "generated_at": now.strftime("%Y-%m-%d %H:%M:%S")}
    os.makedirs("data", exist_ok=True); os.makedirs("site", exist_ok=True)
    with open("data/news.json", "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "items": unique}, f, ensure_ascii=False, indent=2)
    html = render_html(meta, grouped, unique)
    with open("site/index.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("-" * 50); print(f"  共 {len(unique)} 条资讯")
    for cat, its in grouped.items(): print(f"    {cat}: {len(its)} 条")
    print("  数据已写入 data/news.json"); print("  页面已生成 site/index.html")

if __name__ == "__main__":
    main()