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

def bing(q):
    import base64
    r = requests.get("https://www.bing.com/search", params={"q": q},
                     headers={**UA, "Accept-Language": "fa,en;q=0.9"}, timeout=15)
    r.raise_for_status()
    out = []
    for b in re.findall(r'<li class="b_algo".*?</li>', r.text, re.S):
        m = re.search(r'<h2.*?<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', b, re.S)
        if not m:
            continue
        url, title = m.groups()
        url = ihtml.unescape(url)
        um = re.search(r"[?&]u=a1([A-Za-z0-9%+/=_-]+)", url)
        if um:
            try:
                s = um.group(1)
                s += "=" * (-len(s) % 4)
                url = base64.b64decode(s).decode("utf-8", "replace")
            except Exception:
                continue
        if not url.startswith("http") or "bing.com" in url or "microsoft.com" in url:
            continue
        p = re.search(r'<div class="b_caption"><p[^>]*>(.*?)</p>', b, re.S)
        out.append({"title": clean(title), "url": url,
                    "desc": clean(p.group(1)) if p else ""})
        if len(out) >= 10:
            break
    return out

@app.get("/api/search")
def search(q: str = Query(...)):
    for name, fn in (("html", ddg_html), ("lite", ddg_lite), ("bing", bing)):
        try:
            res = fn(q)
            if res:
                print(f"search ok via {name}: {len(res)}")
                return {"results": res}
            print(f"search empty via {name}")
        except Exception as e:
            print(f"search {name} failed:", repr(e)[:200])
    return {"results": []}

@app.get("/api/page")
def page(url: str = Query(...)):
    """متن صفحه رو استخراج می‌کنه برای نمایش داخل ربات"""
    try:
        r = requests.get(url, headers=UA, timeout=12)
        r.raise_for_status()
        h = re.sub(r"<script.*?</script>|<style.*?</style>|<svg.*?</svg>|<nav.*?</nav>|<header.*?</header>|<footer.*?</footer>",
                   " ", r.text, flags=re.S | re.I)
        t = re.search(r"<title[^>]*>(.*?)</title>", h, re.S | re.I)
        title = clean(t.group(1)) if t else url
        paras = re.findall(r"<p[^>]*>(.*?)</p>", h, re.S | re.I)
        txt = "\n\n".join(clean(p) for p in paras)
        txt = re.sub(r"\n{3,}", "\n\n", txt).strip()[:8000]
        if len(txt) < 200:
            body = re.sub(r"<script.*?</script>|<style.*?</style>|<nav.*?</nav>|<footer.*?</footer>",
                          " ", h, flags=re.S | re.I)
            txt = re.sub(r"\s+", " ", clean(body)).strip()[:8000]
        return {"title": title, "text": txt or "متن قابل نمایش نیست — دکمه 🌐 رو بزن"}
    except Exception as e:
        print("page failed:", repr(e)[:200])
        return {"title": url, "text": "باز نشد — دکمه 🌐 رو بزن"}

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
                wad = msg.get("web_app_data")
                if wad:
                    chat = msg["chat"]["id"]
                    try:
                        import json
                        d = json.loads(wad.get("data") or "{}")
                        items = d.get("items") or []
                        kb = {"inline_keyboard": [
                            [{"text": (x.get("t") or "لینک")[:60], "url": x.get("u")}]
                            for x in items[:5] if x.get("u")]}
                        if kb["inline_keyboard"]:
                            tg("sendMessage", {
                                "chat_id": chat,
                                "text": f"🔍 نتایج «{(d.get('q') or '')[:50]}» — بزن روشون، تو خود تلگرام باز می‌شن 👇",
                                "reply_markup": kb})
                        else:
                            tg("sendMessage", {"chat_id": chat, "text": "نتیجه‌ای نبود 😕"})
                    except Exception as e:
                        print("web_app_data error:", e)
                    continue
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
