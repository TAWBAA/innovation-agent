import os
import re
import time
import json
import random
import hashlib
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

client = OpenAI(api_key=OPENAI_API_KEY)

SEEN_FILE = "seen_ideas.json"
CHECK_INTERVAL_SECONDS = 3600
IDEAS_PER_CYCLE = 6

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept-Language": "en-US,en;q=0.9",
}

RESEARCH_TOPICS = [
    "portable blender",
    "mini vacuum cleaner",
    "cat litter box",
    "drawer organizer",
    "shoe organizer",
    "electric lunch box",
    "water bottle",
    "facial cleansing brush",
    "portable neck massager",
    "kitchen storage",
    "pet grooming tool",
    "car interior cleaner",
    "cable organizer",
    "smart pill organizer",
    "portable fan",
    "travel organizer bag",
    "desk lamp",
    "hair remover tool",
    "fridge organizer",
    "portable humidifier",
]


# =========================
# FILES
# =========================

def ensure_seen_file():
    if not os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, "w", encoding="utf-8") as f:
            json.dump({"idea_names": [], "last_cycle_hashes": []}, f, ensure_ascii=False, indent=2)


def load_seen():
    ensure_seen_file()
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                return {"idea_names": [], "last_cycle_hashes": []}
            data = json.loads(content)
            if not isinstance(data, dict):
                return {"idea_names": [], "last_cycle_hashes": []}
            data.setdefault("idea_names", [])
            data.setdefault("last_cycle_hashes", [])
            return data
    except Exception:
        return {"idea_names": [], "last_cycle_hashes": []}


def save_seen(data):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def normalize_text(text: str) -> str:
    text = (text or "").strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text


# =========================
# TELEGRAM
# =========================

def send_telegram(message: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message[:4000]
    }

    try:
        response = requests.post(url, data=payload, timeout=30)
        print("TELEGRAM RESPONSE:", response.text)
    except Exception as e:
        print("TELEGRAM ERROR:", e)


# =========================
# WEB HELPERS
# =========================

def safe_get(url, timeout=25):
    try:
        response = requests.get(url, headers=HEADERS, timeout=timeout)
        if response.status_code == 200:
            return response.text
    except Exception:
        pass
    return ""


def safe_get_json(url, timeout=25):
    try:
        response = requests.get(url, headers=HEADERS, timeout=timeout)
        if response.status_code == 200:
            return response.json()
    except Exception:
        pass
    return None


def duckduckgo_snippets(query, limit=6):
    url = f"https://html.duckduckgo.com/html/?q={quote(query)}"
    html_text = safe_get(url)
    if not html_text:
        return []

    soup = BeautifulSoup(html_text, "html.parser")
    snippets = []

    for block in soup.select(".result"):
        title_el = block.select_one(".result__title")
        snippet_el = block.select_one(".result__snippet")
        title = title_el.get_text(" ", strip=True) if title_el else ""
        snippet = snippet_el.get_text(" ", strip=True) if snippet_el else ""
        text = f"{title} — {snippet}".strip(" —")
        text = re.sub(r"\s+", " ", text)
        if 10 <= len(text) <= 300 and text not in snippets:
            snippets.append(text)
        if len(snippets) >= limit:
            break

    return snippets


# =========================
# AMAZON REVIEW SIGNALS
# =========================

def get_amazon_review_signals(topic: str):
    queries = [
        f'site:amazon.com "{topic}" review',
        f'site:amazon.com "{topic}" customer review',
        f'site:amazon.com "{topic}" complaints',
    ]

    signals = []
    for q in queries:
        signals.extend(duckduckgo_snippets(q, limit=4))

    cleaned = []
    for s in signals:
        low = normalize_text(s)
        if "amazon" in low and s not in cleaned:
            cleaned.append(s)

    return cleaned[:10]


# =========================
# REDDIT SIGNALS
# =========================

def get_reddit_post_comments(permalink: str, limit=6):
    url = f"https://www.reddit.com{permalink}.json?limit=10"
    data = safe_get_json(url)
    if not data or not isinstance(data, list) or len(data) < 2:
        return []

    comments = []
    try:
        children = data[1]["data"]["children"]
        for child in children:
            body = child.get("data", {}).get("body", "")
            body = re.sub(r"\s+", " ", body).strip()
            if 20 <= len(body) <= 350 and body not in comments:
                comments.append(body)
            if len(comments) >= limit:
                break
    except Exception:
        pass

    return comments


def get_reddit_signals(topic: str):
    url = f"https://www.reddit.com/search.json?q={quote(topic)}&sort=top&limit=5"
    data = safe_get_json(url)

    if not data:
        return []

    signals = []

    try:
        posts = data.get("data", {}).get("children", [])
        for post in posts:
            pdata = post.get("data", {})
            title = pdata.get("title", "").strip()
            selftext = pdata.get("selftext", "").strip()
            permalink = pdata.get("permalink", "")

            if title:
                signals.append(f"POST TITLE: {title}")

            if selftext:
                signals.append(f"POST BODY: {selftext[:300]}")

            if permalink:
                comments = get_reddit_post_comments(permalink, limit=4)
                for c in comments:
                    signals.append(f"COMMENT: {c}")

    except Exception:
        pass

    cleaned = []
    for s in signals:
        s = re.sub(r"\s+", " ", s).strip()
        if 10 <= len(s) <= 400 and s not in cleaned:
            cleaned.append(s)

    return cleaned[:15]


# =========================
# TIKTOK PUBLIC SIGNALS
# =========================

def get_tiktok_signals(topic: str):
    queries = [
        f'site:tiktok.com "{topic}" review',
        f'site:tiktok.com "{topic}" problem',
        f'site:tiktok.com "{topic}" worth it',
        f'"{topic}" tiktok comments',
    ]

    signals = []
    for q in queries:
        signals.extend(duckduckgo_snippets(q, limit=3))

    creative_center_url = "https://ads.tiktok.com/business/creativecenter/inspiration/topads/pc/en"
    html_text = safe_get(creative_center_url)

    if html_text:
        soup = BeautifulSoup(html_text, "html.parser")
        for el in soup.select("span, h1, h2, h3, a"):
            txt = el.get_text(" ", strip=True)
            txt = re.sub(r"\s+", " ", txt)
            low = normalize_text(txt)
            if any(word in low for word in normalize_text(topic).split()):
                if 6 <= len(txt) <= 150:
                    signals.append(f"TIKTOK SIGNAL: {txt}")

    cleaned = []
    for s in signals:
        s = re.sub(r"\s+", " ", s).strip()
        if 10 <= len(s) <= 300 and s not in cleaned:
            cleaned.append(s)

    return cleaned[:10]


# =========================
# PROBLEM MINER
# =========================

def build_problem_report(topic: str):
    amazon_signals = get_amazon_review_signals(topic)
    reddit_signals = get_reddit_signals(topic)
    tiktok_signals = get_tiktok_signals(topic)

    prompt = f"""
أنت محلل مشاكل منتجات في الإيكومرس.

المنتج/المجال:
{topic}

إشارات من Amazon reviews:
{amazon_signals}

إشارات من Reddit:
{reddit_signals}

إشارات من TikTok:
{tiktok_signals}

المطلوب:
استخرج فقط JSON بهذا الشكل:
{{
  "topic": "{topic}",
  "top_problems": ["...", "...", "..."],
  "missing_features": ["...", "...", "..."],
  "user_frustrations": ["...", "...", "..."],
  "why_people_complain": "..."
}}

القواعد:
- استخرج مشاكل حقيقية ومحددة
- لا تخترع مشاكل غير منطقية
- إذا كانت الإشارات ضعيفة، استخرج فقط أكثر ما يظهر من الشكاوى
- لا تكتب أي شيء خارج JSON
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "أنت خبير تحليل مشاكل منتجات وتعيد JSON فقط."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3
        )
        text = response.choices[0].message.content.strip()
        return json.loads(text)
    except Exception as e:
        print(f"PROBLEM REPORT ERROR for {topic}:", e)
        return {
            "topic": topic,
            "top_problems": [],
            "missing_features": [],
            "user_frustrations": [],
            "why_people_complain": ""
        }


# =========================
# INNOVATION BUILDER
# =========================

def extract_seen_idea_names(data):
    names = data.get("idea_names", [])
    return names[-80:]


def parse_idea_names(text: str):
    matches = re.findall(r"اسم الفكرة:\s*(.+)", text)
    cleaned = []
    for m in matches:
        name = m.strip()
        if name and name not in cleaned:
            cleaned.append(name)
    return cleaned


def hash_cycle_text(text: str):
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def generate_innovations_from_reports(problem_reports, old_idea_names):
    prompt = f"""
أنت خبير Brand Innovation و Product Innovation.

اعتمادًا على تقارير مشاكل سوق حقيقية من:
- Amazon reviews
- Reddit
- TikTok signals

هذه التقارير:
{json.dumps(problem_reports, ensure_ascii=False, indent=2)}

هذه أسماء أفكار قديمة يجب عدم تكرارها:
{old_idea_names}

المطلوب:
أعطني {IDEAS_PER_CYCLE} أفكار ابتكار قوية جدًا.

كل فكرة يجب أن تكون واحدة من الأنواع التالية:
- تحسين منتج موجود
- دمج منتجين في منتج واحد
- إضافة ميزة ناقصة إلى منتج

أكتب بالعربية فقط.
لا تكرر أي فكرة قديمة.
لا تعطيني أفكارًا خيالية غير قابلة للبيع.
اجعلها مناسبة للإيكومرس وبراندينغ.

استخدم هذا الشكل بالضبط:

💡 Innovation Idea #1

اسم الفكرة:
...

المنتج الأصلي:
...

المشكلة:
...

الحل:
...

نوع الابتكار:
...

أصل الفكرة:
...

قوة الفرصة:
...

━━━━━━━━━━━━

💡 Innovation Idea #2

اسم الفكرة:
...

المنتج الأصلي:
...

المشكلة:
...

الحل:
...

نوع الابتكار:
...

أصل الفكرة:
...

قوة الفرصة:
...

━━━━━━━━━━━━
"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "أنت خبير ابتكار منتجات وتكتب بالعربية فقط."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.8
    )

    return response.choices[0].message.content


# =========================
# MAIN LOOP
# =========================

def pick_topics():
    return random.sample(RESEARCH_TOPICS, 4)


def main():
    print("Innovation Agent Started")

    while True:
        try:
            seen = load_seen()
            old_idea_names = extract_seen_idea_names(seen)

            selected_topics = pick_topics()
            print("SELECTED TOPICS:", selected_topics)

            reports = []
            for topic in selected_topics:
                report = build_problem_report(topic)
                reports.append(report)
                print("REPORT BUILT FOR:", topic)

            ideas = generate_innovations_from_reports(reports, old_idea_names)
            print("IDEAS GENERATED:")
            print(ideas)

            current_hash = hash_cycle_text(ideas)
            last_hashes = seen.get("last_cycle_hashes", [])

            if current_hash in last_hashes:
                print("Duplicate cycle skipped")
            else:
                send_telegram(ideas)

                new_names = parse_idea_names(ideas)
                seen["idea_names"].extend(new_names)
                seen["idea_names"] = seen["idea_names"][-200:]

                seen["last_cycle_hashes"].append(current_hash)
                seen["last_cycle_hashes"] = seen["last_cycle_hashes"][-30:]

                save_seen(seen)

        except Exception as e:
            print("MAIN LOOP ERROR:", e)

        time.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()