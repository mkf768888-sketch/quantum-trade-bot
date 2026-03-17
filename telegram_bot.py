"""
QuantumTrade AI - Telegram Bot
Sends Mini App button + trade notifications
"""

import os
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, ContextTypes

BOT_TOKEN   = os.getenv("BOT_TOKEN", "")
MINI_APP_URL = os.getenv("MINI_APP_URL", "https://your-domain.com")


async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "⚛ Открыть QuantumTrade AI",
            web_app=WebAppInfo(url=MINI_APP_URL),
        )
    ]])
    await update.message.reply_text(
        "🚀 *QuantumTrade AI* — квантовый крипто-трейдинг\n\n"
        "• ⚛ Квантовый анализ Origin QC\n"
        "• 🐋 Мониторинг топ-500 кошельков\n"
        "• 🤖 Автопилот KuCoin (Spot + Futures)\n"
        "• 🧠 Самообучающаяся модель\n\n"
        "Нажмите кнопку ниже для запуска:",
        parse_mode="Markdown",
        reply_markup=keyboard,
    )


async def signal_alert(app: Application, signal: dict):
    """Send trade signal notification to user."""
    emoji = "🟢" if signal["action"] == "BUY" else "🔴" if signal["action"] == "SELL" else "🟡"
    text = (
        f"{emoji} *Квантовый сигнал*\n\n"
        f"Пара: `{signal['symbol']}`\n"
        f"Действие: *{signal['action']}*\n"
        f"Уверенность: *{int(signal['confidence']*100)}%*\n"
        f"Q-Score: `{signal.get('q_score', 'N/A')}`\n\n"
        f"_Автопилот исполняет ордер на KuCoin..._"
    )
    chat_id = os.getenv("ALERT_CHAT_ID", "")
    if chat_id:
        await app.bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown")


def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    print("Bot started...")
    app.run_polling()


if __name__ == "__main__":
    main()
