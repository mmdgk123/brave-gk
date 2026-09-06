"""Telegram search mini-app backend (DuckDuckGo - free, no API key).
Run: pip install -r requirements.txt && python server.py
Env: BOT_TOKEN=xxx  PUBLIC_URL=https://xxx.onrender.com
"""
import os, re, time, threading, html as ihtml, requests
from urllib.parse import unquote
from fastapi import FastAPI, Query
from fastapi.responses import FileResponse

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
PUBLIC_URL = os.getenv("PUBLIC_URL", "")

app = FastAPI()
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

def clean(t):
    return ihtml.unescape(re.sub(r"<.*?>", "", t)).strip()

def ddg_html(q):
    r = requests.post("https://html.duckduckgo.com/html/",
                      data={"q": q}, headers=UA, timeout=15)
    r.raise_for_status()
    out = []
    for m in re.finditer(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>(.*?)class="result__snippet"[^>]*>(.*?)</',
                         r.text, re.S):
        url, title, _, desc = m.groups()
        um = re.search(r"uddg=([^&]+)", url)
        if um:
            url = unquote(um.group(1))
        out.append({"title": clean(title), "url": url, "desc": clean(desc)})
        if len(out) >= 10:
            break
    return out

def ddg_lite(q):
    r = requests.post("https://lite.duckduckgo.com/lite/",
                      data={"q": q}, headers=UA, timeout=15)
    r.raise_for_status()
    links = re.findall(r"<a rel=\"nofollow\" href=\"(https?://[^\"]+)\" class='result-link'>(.*?)</a>",
                       r.text, re.S)
    snips = re.findall(r"class='result-snippet'>(.*?)</td>", r.text, re.S)
    out = []
    for i, (url, title) in enumerate(links):
        if "duckduckgo.com" in url:
            continue
        out.append({"title": clean(title), "url": url,
                    "desc": clean(snips[i]) if i < len(snips) else ""})
        if len(out) >= 10:
            break
    return out

@app.get("/api/search")
def search(q: str = Query(...)):
    for name, fn in (("html", ddg_html), ("lite", ddg_lite)):
        try:
            res = fn(q)
            if res:
                print(f"search ok via {name}: {len(res)}")
                return {"results": res}
            print(f"search empty via {name}")
        except Exception as e:
            print(f"search {name} failed:", repr(e)[:200])
    return {"results": []}

@app.get("/")
def root():
    return FileResponse("mini-app/index.html")

def tg(method, payload=None):
    try:
        r = requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/{method}",
                          json=payload or {}, timeout=20)
        return r.json()
    except Exception as e:
        print("tg error:", e)
        return {}

def poll():
    """Long-polling ساده بدون کتابخونه اضافه"""
    if not BOT_TOKEN:
        print("no BOT_TOKEN, polling off")
        return
    offset = 0
    while True:
        try:
            r = requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates",
                             params={"timeout": 30, "offset": offset}, timeout=40).json()
            for u in r.get("result", []):
                offset = u["update_id"] + 1
                msg = u.get("message") or {}
                if (msg.get("text") or "").startswith("/start"):
                    chat = msg["chat"]["id"]
                    if PUBLIC_URL.startswith("https://"):
                        tg("sendMessage", {
                            "chat_id": chat,
                            "text": "دکمه زیر رو بزن تا مرورگر داخل تلگرام باز شه 👇",
                            "reply_markup": {"inline_keyboard": [
                                [{"text": "🦁 باز کردن مرورگر", "web_app": {"url": PUBLIC_URL}}]]}})
                    else:
                        tg("sendMessage", {"chat_id": chat,
                                           "text": "ربات هنوز آماده نشده، یکم دیگه امتحان کن ⏳"})
        except Exception as e:
            print("poll error:", e)
            time.sleep(5)

@app.on_event("startup")
def init():
    if PUBLIC_URL.startswith("https://"):
        print("menu:", tg("setChatMenuButton", {
            "menu_button": {"type": "web_app", "text": "🔍 جستجو",
                            "web_app": {"url": PUBLIC_URL}}}))
    else:
        print("skip menu button, PUBLIC_URL:", PUBLIC_URL)
    threading.Thread(target=poll, daemon=True).start()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
