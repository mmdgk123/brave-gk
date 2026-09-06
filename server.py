"""Telegram search mini-app backend (DuckDuckGo - free, no API key).
Run: pip install fastapi uvicorn requests python-telegram-bot && python server.py
Env: BOT_TOKEN=xxx  PUBLIC_URL=https://xxx.onrender.com
"""
import os, re, html as ihtml, requests
from fastapi import FastAPI, Query
from fastapi.responses import FileResponse

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
PUBLIC_URL = os.getenv("PUBLIC_URL", "")

app = FastAPI()
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

@app.get("/api/search")
def search(q: str = Query(...)):
    r = requests.post("https://html.duckduckgo.com/html/",
                      data={"q": q}, headers=UA, timeout=15)
    out = []
    for m in re.finditer(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>(.*?)class="result__snippet"[^>]*>(.*?)</',
                         r.text, re.S):
        url, title, _, desc = m.groups()
        title = ihtml.unescape(re.sub(r"<.*?>", "", title)).strip()
        desc = ihtml.unescape(re.sub(r"<.*?>", "", desc)).strip()
        # DDG wraps links as //duckduckgo.com/l/?uddg=<real>
        um = re.search(r"uddg=([^&]+)", url)
        if um:
            from urllib.parse import unquote
            url = unquote(um.group(1))
        out.append({"title": title, "url": url, "desc": desc})
        if len(out) >= 10:
            break
    return {"results": out}

@app.get("/")
def root():
    return FileResponse("mini-app/index.html")

async def setup_bot():
    """دکمه باز کردن وب‌اپ رو روی /start می‌ذاره"""
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
    from telegram.ext import Application, CommandHandler

    async def post_init(app_tg):
        if not PUBLIC_URL.startswith("https://"):
            print("skip menu button, PUBLIC_URL invalid:", PUBLIC_URL)
            return
        try:
            await app_tg.bot.set_chat_menu_button(
                menu_button={"type": "web_app", "text": "🔍 جستجو", "web_app": {"url": PUBLIC_URL}})
            print("menu button set")
        except Exception as e:
            print("menu button failed:", e)

    app_tg = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    async def start(update: Update, ctx):
        if PUBLIC_URL.startswith("https://"):
            kb = [[InlineKeyboardButton("🦁 باز کردن مرورگر", web_app=WebAppInfo(url=PUBLIC_URL))]]
            await update.message.reply_text("دکمه زیر رو بزن تا مرورگر داخل تلگرام باز شه 👇",
                                            reply_markup=InlineKeyboardMarkup(kb))
        else:
            await update.message.reply_text("ربات هنوز آماده نشده، یکم دیگه امتحان کن ⏳")
    app_tg.add_handler(CommandHandler("start", start))
    await app_tg.run_polling()

if __name__ == "__main__":
    import threading, uvicorn
    threading.Thread(target=lambda: uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000"))), daemon=True).start()
    import asyncio
    asyncio.run(setup_bot())
