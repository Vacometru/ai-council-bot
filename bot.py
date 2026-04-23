import os
import logging
import asyncio
import httpx
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
GEMINI_KEY     = os.environ.get("GEMINI_KEY", "")
GROK_KEY       = os.environ.get("GROK_KEY", "")

AI_CONFIG = {
    "gemini": {"name": "💎 Gemini", "active": bool(GEMINI_KEY)},
    "grok":   {"name": "⚡ Grok",   "active": bool(GROK_KEY)},
}

SYSTEM_PROMPT = (
    "Ești un asistent AI într-un grup Telegram cu alți AI și utilizatori umani. "
    "Răspunde concis, natural și în contextul conversației. "
    "Fii prietenos și util. Maxim 3-4 propoziții."
)

chat_history = []

def add_to_history(role: str, content: str):
    chat_history.append({"role": role, "content": content})
    if len(chat_history) > 20:
        chat_history.pop(0)

async def ask_gemini(user_text: str) -> str:
    contents = []
    for m in chat_history[:-1]:
        contents.append({
            "role": "model" if m["role"] == "assistant" else "user",
            "parts": [{"text": m["content"]}]
        })
    contents.append({"role": "user", "parts": [{"text": user_text}]})
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}",
            json={
                "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
                "contents": contents,
                "generationConfig": {"maxOutputTokens": 400}
            },
        )
        r.raise_for_status()
        return r.json()["candidates"][0]["content"]["parts"][0]["text"]

async def ask_grok(user_text: str) -> str:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for m in chat_history[:-1]:
        messages.append({"role": m["role"], "content": m["content"]})
    messages.append({"role": "user", "content": user_text})
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            "https://api.x.ai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {GROK_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "grok-3-fast",
                "max_tokens": 400,
                "messages": messages
            },
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    active = [cfg["name"] for cfg in AI_CONFIG.values() if cfg["active"]]
    await update.message.reply_text(
        "🤖 *AI Council Group* — Bun venit!\n\n"
        f"AI-uri active: {', '.join(active) if active else '⚠️ Niciun AI configurat'}\n\n"
        "Scrie orice mesaj și AI-urile vor răspunde!",
        parse_mode="Markdown"
    )

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lines = ["🤖 *Status AI Council:*\n"]
    for cfg in AI_CONFIG.values():
        icon = "✅" if cfg["active"] else "❌"
        lines.append(f"{icon} {cfg['name']}")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if not msg or not msg.text or msg.from_user.is_bot:
        return

    user_text = msg.text
    user_name = msg.from_user.first_name or "User"
    full_text = f"[{user_name}]: {user_text}"

    add_to_history("user", full_text)

    active_ais = {k: v for k, v in AI_CONFIG.items() if v["active"]}
    if not active_ais:
        await msg.reply_text("⚠️ Niciun AI configurat. Verifică variabilele pe Railway.")
        return

    async def respond(ai_id: str, ask_fn):
        try:
            reply = await ask_fn(full_text)
            await msg.reply_text(f"{AI_CONFIG[ai_id]['name']}:\n{reply}")
            add_to_history("assistant", f"[{AI_CONFIG[ai_id]['name']}]: {reply}")
        except Exception as e:
            await msg.reply_text(f"{AI_CONFIG[ai_id]['name']}:\n❌ Eroare: {str(e)[:150]}")

    tasks = []
    if AI_CONFIG["gemini"]["active"]: tasks.append(respond("gemini", ask_gemini))
    if AI_CONFIG["grok"]["active"]:   tasks.append(respond("grok",   ask_grok))

    await asyncio.gather(*tasks)

def main():
    if not TELEGRAM_TOKEN:
        raise ValueError("TELEGRAM_TOKEN lipsește!")
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("🚀 Bot pornit cu: %s", [k for k, v in AI_CONFIG.items() if v["active"]])
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
