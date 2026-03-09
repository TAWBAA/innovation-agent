import os
import time
import json
import requests
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

client = OpenAI(api_key=OPENAI_API_KEY)

SEEN_FILE = "seen_ideas.json"


# =========================
# FILE SETUP
# =========================

if not os.path.exists(SEEN_FILE):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump([], f)


def load_seen():
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                return []
            return json.loads(content)
    except Exception:
        return []


def save_seen(data):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# =========================
# TELEGRAM
# =========================

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    payload = {
        "chat_id": CHAT_ID,
        "text": message
    }

    try:
        response = requests.post(url, data=payload, timeout=30)
        print("TELEGRAM RESPONSE:", response.text)
    except Exception as e:
        print("TELEGRAM ERROR:", e)


# =========================
# OPENAI
# =========================

def generate_innovations():
    prompt = """
أنت خبير ابتكار منتجات وبراندينغ.

أعطني 6 أفكار قوية جدًا لمنتجات مبتكرة.

ركز فقط على:
- تحسين منتجات موجودة
- حل مشاكل حقيقية
- دمج منتجين في منتج واحد
- أفكار قابلة للبيع في الإيكومرس
- أفكار يمكن أن تتحول إلى براند

أكتب بالعربية فقط.

استعمل هذا الشكل بالضبط:

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

print("Innovation Agent Started")

while True:
    try:
        ideas = generate_innovations()
        print("IDEAS GENERATED:")
        print(ideas)

        seen = load_seen()

        if ideas not in seen:
            send_telegram(ideas)
            seen.append(ideas)
            save_seen(seen)
        else:
            print("Duplicate ideas skipped")

    except Exception as e:
        print("ERROR:", e)

    # 6 أفكار كل ساعة = 144 فكرة يوميًا
    time.sleep(3600)