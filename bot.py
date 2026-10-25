import os
import threading
import logging
from flask import Flask
import google.generativeai as genai
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
BOT_NAME = "SCP-SPACE AI"

genai.configure(api_key=GEMINI_API_KEY)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

chat_history = {}
MODEL_NAME = "gemini-2.5-flash"

SYSTEM_PROMPT = f"""You are {BOT_NAME}, a helpful AI assistant. 
Respond in English only. 
Do not use any emojis. 
Use markdown formatting for clarity."""

def get_model():
    return genai.GenerativeModel(
        model_name=MODEL_NAME, 
        system_instruction=SYSTEM_PROMPT
    )

def get_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("Clear History", callback_data="clear"),
            InlineKeyboardButton("Retry", callback_data="retry")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome = (
        f"Hello {update.effective_user.first_name}.\n\n"
        f"I am {BOT_NAME}.\n"
        "You can ask me any question.\n\n"
        "Commands:\n"
        "/start - Start the bot\n"
        "/clear - Clear chat history\n"
        "/help - Show help message"
    )
    await update.message.reply_text(welcome, reply_markup=get_keyboard())

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        f"{BOT_NAME} Help\n\n"
        "Just type your question and I will answer.\n"
        "Use /clear to reset the conversation history."
    )
    await update.message.reply_text(text)

async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_history.pop(update.effective_user.id, None)
    await update.message.reply_text("Conversation history cleared.")

async def retry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    history = chat_history.get(user_id, [])
    
    last_user_msg = next(
        (msg["parts"][0] for msg in reversed(history) if msg["role"] == "user"), 
        None
    )
    
    if not last_user_msg:
        target = update.message if update.message else update.callback_query.message
        await target.reply_text("No previous question to retry.")
        return
        
    if history and history[-1]["role"] == "model":
        history.pop()
        
    await generate_response(update, user_id, last_user_msg, from_retry=True)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text:
        await generate_response(update, update.effective_user.id, update.message.text)

async def generate_response(update: Update, user_id: int, user_text: str, from_retry: bool = False):
    target = update.message if update.message else update.callback_query.message
    await target.chat.send_action("typing")
    
    if user_id not in chat_history:
        chat_history[user_id] = []
    history = chat_history[user_id]
    
    if not from_retry:
        history.append({"role": "user", "parts": [user_text]})
        
    try:
        chat = get_model().start_chat(history=history)
        response = chat.send_message(user_text)
        
        history.append({"role": "model", "parts": [response.text]})
        
        if len(history) > 20:
            chat_history[user_id] = history[-20:]
            
        await target.reply_text(
            response.text, 
            parse_mode="Markdown", 
            reply_markup=get_keyboard()
        )
    except Exception as e:
        logger.error(f"Error: {e}")
        await target.reply_text("An error occurred. Please try again later.")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "clear":
        chat_history.pop(query.from_user.id, None)
        await query.edit_message_text("Conversation history cleared.")
    elif query.data == "retry":
        await retry(update, context)

flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return "SCP-SPACE AI is running!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    flask_app.run(host="0.0.0.0", port=port)

def main():
    threading.Thread(target=run_flask, daemon=True).start()
    
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("clear", clear_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    logger.info("Bot is starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
