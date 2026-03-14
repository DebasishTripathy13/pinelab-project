"""
SentinelPay Universal AI Assistant — Telegram Bot

A universal AI assistant that can:
- Analyze photos (kitchen/fridge for groceries, outfits for advice, anything)
- Accept voice messages and respond
- Have natural conversations and give advice
- Search the web for products and genuine merchants
- Place orders through SentinelPay security pipeline
- Handle HITL approve/kill flows

Every purchase goes through SentinelPay's 3-layer security check.
"""

import os
import sys
import json
import logging
import base64
import io
import re
import uuid
import tempfile
from datetime import datetime

from dotenv import load_dotenv
load_dotenv()

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)
import httpx

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger("sentinelpay.bot")

# ─── Config ───────────────────────────────────────────────────────────
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
SENTINELPAY_URL = os.getenv("SENTINELPAY_API_URL", "http://localhost:8000")
AGENT_TOKEN = os.getenv("SENTINELPAY_AGENT_TOKEN", "sp_agent_demo_token_2026")

# per-user state
user_state = {}   # chat_id -> { conversation_history, pending_order, ... }

SYSTEM_PROMPT = """You are SentinelPay Assistant — a helpful, universal AI assistant built into a Telegram bot.

You can do ANYTHING a smart assistant can:
- Analyze photos (kitchen scanning for groceries, outfit checks, product identification, etc.)
- Give advice (fashion, interviews, cooking, travel, anything)
- Help users shop for anything — groceries, clothes, electronics, gifts
- Search for genuine merchants and best prices
- Place orders through the SentinelPay secure payment system

IMPORTANT RULES:
1. When the user wants to BUY something, you MUST respond with a structured JSON shopping list inside <order> tags:
   <order>
   {
     "merchant": "store name",
     "merchant_domain": "store-domain.com",
     "items": [{"item": "name", "quantity": "qty", "estimated_price": 100}],
     "total": 500,
     "description": "brief description of the purchase"
   }
   </order>
   Then ALSO include a friendly message asking them to confirm the order.

2. When analyzing a photo of a kitchen/fridge, identify what's low/missing and suggest a grocery order.
3. When analyzing an outfit photo, give honest, helpful fashion advice.
4. For interview prep, give practical tips on appearance, body language, and what to wear.
5. Always be warm, helpful, and proactive. Suggest things the user might need.
6. For shopping, prefer well-known Indian merchants: Blinkit (blinkit.com), BigBasket (bigbasket.com),
   Swiggy Instamart (swiggy.com), Amazon (amazon.in), Flipkart (flipkart.com), Myntra (myntra.com),
   Nykaa (nykaa.com), Zepto (zepto.com).
7. Use INR (₹) for all prices.
8. Keep responses concise but warm. Use emojis naturally.

You are NOT just a grocery bot — you are a full AI assistant that happens to have secure payment superpowers."""


# ─── Gemini API ───────────────────────────────────────────────────────

async def gemini_text(prompt: str, history: list = None) -> str:
    """Send text to Gemini and get response."""
    if not GEMINI_API_KEY:
        return _fallback_response(prompt)

    messages = []
    if history:
        for msg in history[-10:]:  # keep last 10 messages
            messages.append({"role": msg["role"], "parts": [{"text": msg["text"]}]})
    messages.append({"role": "user", "parts": [{"text": prompt}]})

    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
        payload = {
            "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": messages,
            "generationConfig": {"temperature": 0.7, "maxOutputTokens": 4096}
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        logger.error(f"Gemini text error: {e}")
        return f"Sorry, I had trouble thinking about that. Error: {str(e)[:100]}"


async def gemini_vision(prompt: str, image_bytes: bytes, mime_type: str = "image/jpeg") -> str:
    """Send image + text to Gemini Vision."""
    if not GEMINI_API_KEY:
        return _fallback_vision(prompt)

    b64 = base64.b64encode(image_bytes).decode('utf-8')
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
        payload = {
            "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": [{
                "parts": [
                    {"text": prompt},
                    {"inline_data": {"mime_type": mime_type, "data": b64}}
                ]
            }],
            "generationConfig": {"temperature": 0.7, "maxOutputTokens": 4096}
        }
        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        logger.error(f"Gemini vision error: {e}")
        return f"I couldn't analyze the image. Error: {str(e)[:100]}"


async def gemini_audio(prompt: str, audio_bytes: bytes, mime_type: str = "audio/ogg") -> str:
    """Send audio to Gemini for transcription + response."""
    if not GEMINI_API_KEY:
        return "Voice input requires Gemini API key. Please set GEMINI_API_KEY."

    b64 = base64.b64encode(audio_bytes).decode('utf-8')
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
        payload = {
            "system_instruction": {"parts": [{"text": SYSTEM_PROMPT + "\n\nThe user sent a voice message. First transcribe what they said, then respond helpfully. Format: [Transcription: ...]\n\nYour response here."}]},
            "contents": [{
                "parts": [
                    {"text": prompt or "The user sent this voice message. Please listen, understand, and respond:"},
                    {"inline_data": {"mime_type": mime_type, "data": b64}}
                ]
            }],
            "generationConfig": {"temperature": 0.7, "maxOutputTokens": 4096}
        }
        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        logger.error(f"Gemini audio error: {e}")
        return f"Sorry, I couldn't process your voice message. Error: {str(e)[:100]}"


def _fallback_response(prompt: str) -> str:
    p = prompt.lower()
    if any(w in p for w in ["grocery", "groceries", "kitchen", "fridge", "food"]):
        return ("I'd love to help with groceries! Here's what a typical restock looks like:\n\n"
                "<order>\n"
                '{"merchant":"Blinkit","merchant_domain":"blinkit.com","items":[{"item":"Amul Milk 1L","quantity":"2","estimated_price":64},{"item":"Eggs 12pc","quantity":"1","estimated_price":89},{"item":"Bread","quantity":"1","estimated_price":45},{"item":"Tomatoes","quantity":"1 kg","estimated_price":40},{"item":"Onions","quantity":"2 kg","estimated_price":70},{"item":"Rice 5kg","quantity":"1","estimated_price":350}],"total":658,"description":"Weekly grocery restock"}\n'
                "</order>\n\n"
                "Shall I order these from Blinkit? 🛒")
    return ("I'm your SentinelPay assistant! I can help with shopping, photo analysis, "
            "outfit advice, and more. Send me a photo or ask me anything!\n\n"
            "⚠️ For full AI capabilities, set GEMINI_API_KEY in the .env file.")


def _fallback_vision(prompt: str) -> str:
    return ("📸 I can see you sent a photo! To analyze it properly, I need a Gemini API key.\n\n"
            "Set GEMINI_API_KEY in backend/.env and restart the bot.\n\n"
            "For now, here's a demo grocery list:\n\n"
            "<order>\n"
            '{"merchant":"Blinkit","merchant_domain":"blinkit.com","items":[{"item":"Milk 1L","quantity":"2","estimated_price":64},{"item":"Eggs","quantity":"12","estimated_price":89},{"item":"Bread","quantity":"1","estimated_price":45},{"item":"Tomatoes","quantity":"1kg","estimated_price":40},{"item":"Onions","quantity":"2kg","estimated_price":70},{"item":"Bananas","quantity":"1 dozen","estimated_price":50}],"total":358,"description":"Kitchen restock"}\n'
            "</order>\n\n"
            "Want me to order these? 🛒")


# ─── SentinelPay API ─────────────────────────────────────────────────

async def sp_api(method: str, endpoint: str, data: dict = None) -> dict:
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {AGENT_TOKEN}"}
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            if method == "GET":
                r = await client.get(f"{SENTINELPAY_URL}{endpoint}", headers=headers)
            else:
                r = await client.post(f"{SENTINELPAY_URL}{endpoint}", json=data or {}, headers=headers)
            return r.json()
    except Exception as e:
        return {"error": str(e)}


async def ensure_wallet():
    return await sp_api("POST", "/demo/seed")


async def place_order(merchant: str, domain: str, total: float, items: list, description: str) -> dict:
    items_names = [i.get("item", "") for i in items]
    return await sp_api("POST", "/payment/request", {
        "amount": total,
        "merchant": merchant,
        "merchant_domain": domain,
        "description": description,
        "items": items_names,
        "agent_id": "telegram-assistant"
    })


# ─── Order parsing ───────────────────────────────────────────────────

def extract_order(text: str) -> dict:
    """Extract order JSON from <order>...</order> tags in AI response."""
    match = re.search(r'<order>\s*(.*?)\s*</order>', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    return None


def clean_response(text: str) -> str:
    """Remove <order> tags from response for display."""
    return re.sub(r'<order>.*?</order>', '', text, flags=re.DOTALL).strip()


def format_order_msg(order: dict) -> str:
    """Format order into a nice Telegram message."""
    items = order.get("items", [])
    total = order.get("total", 0)
    merchant = order.get("merchant", "Unknown Store")

    msg = f"🛒 <b>Order Summary — {merchant}</b>\n"
    msg += "━━━━━━━━━━━━━━━━━━━━━━━━\n"
    for i, item in enumerate(items, 1):
        price = item.get("estimated_price", 0)
        qty = item.get("quantity", "1")
        msg += f"  {i}. {item['item']} × {qty} — ₹{price}\n"
    msg += "━━━━━━━━━━━━━━━━━━━━━━━━\n"
    msg += f"💰 <b>Total: ₹{total}</b>\n"
    msg += f"🏪 Store: {merchant}\n"
    return msg


# ─── Conversation history ────────────────────────────────────────────

def get_state(chat_id: int) -> dict:
    if chat_id not in user_state:
        user_state[chat_id] = {"history": [], "pending_order": None}
    return user_state[chat_id]


def add_history(chat_id: int, role: str, text: str):
    state = get_state(chat_id)
    state["history"].append({"role": role, "text": text})
    # Keep last 20
    if len(state["history"]) > 20:
        state["history"] = state["history"][-20:]


# ─── Handlers ─────────────────────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    os.environ["TELEGRAM_CHAT_ID"] = str(chat_id)
    wallet = await ensure_wallet()

    await update.message.reply_text(
        "🛡️ <b>SentinelPay AI Assistant</b>\n\n"
        "I'm your universal AI assistant with secure payment superpowers!\n\n"
        "Here's what I can do:\n"
        "📸 <b>Photos</b> — Send a photo of anything and I'll analyze it\n"
        "   • Kitchen/fridge → grocery list + order\n"
        "   • Outfit → style advice + shopping suggestions\n"
        "   • Products → find best prices online\n\n"
        "🎤 <b>Voice</b> — Send a voice message and I'll listen & respond\n\n"
        "💬 <b>Chat</b> — Ask me anything! Interview tips, recipes, advice...\n\n"
        "🛒 <b>Shopping</b> — I can order from Blinkit, Amazon, Flipkart, Myntra, etc.\n"
        "   Every payment is secured by SentinelPay's 3-layer security.\n\n"
        f"💰 Wallet ready: <code>{wallet.get('wallet_id', 'N/A')[:8]}...</code>\n\n"
        "Just send me a message, photo, or voice note to get started!",
        parse_mode="HTML"
    )


async def cmd_balance(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    w = await sp_api("GET", "/wallet/balance")
    if "error" in w:
        await update.message.reply_text(f"❌ {w['error']}")
        return
    frozen = "🔴 FROZEN" if w.get("is_frozen") else "🟢 Active"
    await update.message.reply_text(
        f"💰 <b>Wallet</b>\n\n"
        f"Status: {frozen}\n"
        f"Balance: <b>₹{w.get('balance',0):,.2f}</b>\n"
        f"Limit/tx: ₹{w.get('spend_limit',0):,.0f}\n"
        f"Weekly left: ₹{w.get('weekly_remaining',0):,.0f}",
        parse_mode="HTML"
    )


async def cmd_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    root = await sp_api("GET", "/")
    w = await sp_api("GET", "/wallet/balance")
    await update.message.reply_text(
        f"🛡️ <b>System Status</b>\n\n"
        f"SentinelPay: {root.get('status','?')} v{root.get('version','?')}\n"
        f"Pine Labs: {root.get('pine_labs','?')}\n"
        f"Wallet: {'🟢' if not w.get('is_frozen') else '🔴'} ₹{w.get('balance',0):,.2f}\n"
        f"Gemini: {'🟢' if GEMINI_API_KEY else '🟡 demo mode'}",
        parse_mode="HTML"
    )


async def cmd_approve(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("Usage: /approve <approval_id>")
        return
    r = await sp_api("POST", "/hitl/approve", {"approval_id": ctx.args[0], "action": "approved"})
    await update.message.reply_text(f"✅ Approved: {r.get('status','done')}")


async def cmd_kill(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("Usage: /kill <approval_id>")
        return
    r = await sp_api("POST", "/hitl/approve", {"approval_id": ctx.args[0], "action": "killed"})
    await update.message.reply_text(f"🔴 Killed. Death switch may have fired.")


async def cmd_unfreeze(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    seed = await ensure_wallet()
    wid = ctx.args[0] if ctx.args else seed.get("wallet_id", "")
    if wid:
        r = await sp_api("POST", f"/wallet/unfreeze/{wid}")
        await update.message.reply_text(f"🔓 Wallet unfrozen: {r.get('status','done')}")


# ─── Photo handler ────────────────────────────────────────────────────

async def handle_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await update.message.reply_text("🔍 Analyzing your photo...")

    # Download photo
    photo = update.message.photo[-1]
    file = await ctx.bot.get_file(photo.file_id)
    buf = io.BytesIO()
    await file.download_to_memory(buf)
    photo_bytes = buf.getvalue()

    # Caption as context
    caption = update.message.caption or ""

    # Build prompt based on context
    history = get_state(chat_id)["history"]
    recent_context = " ".join([m["text"] for m in history[-3:]])

    prompt = f"""The user sent a photo. Their caption: "{caption}"
Recent conversation context: {recent_context}

Analyze this photo thoroughly.

If it's a kitchen, fridge, or pantry: identify what's running low or missing and create a grocery shopping list with prices in INR. Include the order in <order> tags.

If it's an outfit or the person asking how they look: give honest, specific fashion/style advice. If they mention an interview, give interview-specific grooming and outfit tips. If they could benefit from buying something (like a tie, shoes, belt), suggest it with an <order> tag.

If it's a product: identify it, suggest where to buy, and include an <order> tag with the best price.

For ANY photo: be helpful, specific, and actionable. If shopping would help, include an <order> tag."""

    response = await gemini_vision(prompt, photo_bytes)

    add_history(chat_id, "user", f"[Sent a photo] {caption}")
    add_history(chat_id, "model", response)

    # Check if there's an order suggestion
    order = extract_order(response)
    display_text = clean_response(response)

    if order:
        state = get_state(chat_id)
        state["pending_order"] = order

        # Send analysis
        if display_text:
            await update.message.reply_text(display_text)

        # Send order summary with buttons
        order_msg = format_order_msg(order)
        keyboard = [
            [
                InlineKeyboardButton("✅ Order Now", callback_data="order_confirm"),
                InlineKeyboardButton("❌ Cancel", callback_data="order_cancel"),
            ],
            [InlineKeyboardButton("📸 Rescan", callback_data="order_rescan")]
        ]
        await update.message.reply_text(
            order_msg, parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await update.message.reply_text(display_text or response)


# ─── Voice handler ────────────────────────────────────────────────────

async def handle_voice(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await update.message.reply_text("🎤 Listening to your voice message...")

    # Download voice
    voice = update.message.voice or update.message.audio
    file = await ctx.bot.get_file(voice.file_id)
    buf = io.BytesIO()
    await file.download_to_memory(buf)
    audio_bytes = buf.getvalue()

    # Determine mime type
    mime = "audio/ogg"
    if voice.mime_type:
        mime = voice.mime_type

    history = get_state(chat_id)["history"]
    recent = " ".join([m["text"] for m in history[-3:]])
    prompt = f"Recent context: {recent}\n\nThe user sent a voice message. Listen, transcribe, and respond helpfully."

    response = await gemini_audio(prompt, audio_bytes, mime)

    add_history(chat_id, "user", "[Voice message]")
    add_history(chat_id, "model", response)

    # Check for order
    order = extract_order(response)
    display_text = clean_response(response)

    if order:
        state = get_state(chat_id)
        state["pending_order"] = order
        if display_text:
            await update.message.reply_text(display_text)
        order_msg = format_order_msg(order)
        keyboard = [
            [
                InlineKeyboardButton("✅ Order Now", callback_data="order_confirm"),
                InlineKeyboardButton("❌ Cancel", callback_data="order_cancel"),
            ]
        ]
        await update.message.reply_text(order_msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text(display_text or response)


# ─── Text handler ─────────────────────────────────────────────────────

async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = update.message.text.strip()

    if not text:
        return

    add_history(chat_id, "user", text)

    # Send typing indicator
    await ctx.bot.send_chat_action(chat_id=chat_id, action="typing")

    # Get AI response with conversation history
    history = get_state(chat_id)["history"]
    response = await gemini_text(text, history)

    add_history(chat_id, "model", response)

    # Check for order
    order = extract_order(response)
    display_text = clean_response(response)

    if order:
        state = get_state(chat_id)
        state["pending_order"] = order
        if display_text:
            await update.message.reply_text(display_text)
        order_msg = format_order_msg(order)
        keyboard = [
            [
                InlineKeyboardButton("✅ Order Now", callback_data="order_confirm"),
                InlineKeyboardButton("❌ Cancel", callback_data="order_cancel"),
            ]
        ]
        await update.message.reply_text(order_msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        # Split long messages (Telegram 4096 char limit)
        msg = display_text or response
        if len(msg) > 4000:
            for i in range(0, len(msg), 4000):
                await update.message.reply_text(msg[i:i+4000])
        else:
            await update.message.reply_text(msg)


# ─── Callback handler (buttons) ──────────────────────────────────────

async def handle_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id
    data = query.data

    if data == "order_confirm":
        state = get_state(chat_id)
        order = state.get("pending_order")
        if not order:
            await query.edit_message_text("⚠️ Order expired. Just tell me what you need!")
            return

        await query.edit_message_text("🔄 Processing payment through SentinelPay security...")
        await ensure_wallet()

        result = await place_order(
            merchant=order.get("merchant", "Unknown"),
            domain=order.get("merchant_domain", "unknown.com"),
            total=order.get("total", 0),
            items=order.get("items", []),
            description=order.get("description", "Order via SentinelPay Assistant")
        )

        status = result.get("status", "UNKNOWN")

        if status == "APPROVED":
            items_text = "\n".join([f"  • {i['item']} ({i.get('quantity','1')})" for i in order.get("items", [])])
            await query.message.reply_text(
                f"✅ <b>Order Placed!</b>\n\n"
                f"🛡️ SentinelPay: APPROVED (risk: {result.get('risk_score',0):.0%})\n"
                f"🏪 {order.get('merchant','Store')}\n"
                f"💰 ₹{order.get('total',0)}\n"
                f"📦 Order: <code>{result.get('order_id','N/A')}</code>\n\n"
                f"<b>Items:</b>\n{items_text}\n\n"
                f"🚚 On its way! 🎉",
                parse_mode="HTML"
            )
            state["pending_order"] = None

        elif status == "PENDING_HUMAN":
            aid = result.get("approval_id", "")
            reasons = result.get("reasons", [])
            keyboard = [
                [
                    InlineKeyboardButton("✅ Approve", callback_data=f"hitl_approve:{aid}"),
                    InlineKeyboardButton("🚫 Kill", callback_data=f"hitl_kill:{aid}"),
                ]
            ]
            await query.message.reply_text(
                f"⚠️ <b>Security Review Required</b>\n\n"
                f"₹{order.get('total',0)} → {order.get('merchant','')}\n"
                f"Risk: {result.get('risk_score',0):.0%}\n\n"
                f"<b>Flagged:</b>\n" + "\n".join([f"• {r}" for r in reasons[:5]]) +
                f"\n\n⏱️ Auto-kill in 5 min.",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

        elif status == "BLOCKED":
            ds = result.get("death_switch", False)
            await query.message.reply_text(
                f"🔴 <b>Payment Blocked</b>\n\n"
                f"Risk: {result.get('risk_score',0):.0%}\n"
                f"Reason: {result.get('reason','Security policy')}\n"
                + ("⚡ <b>DEATH SWITCH</b> — Wallet frozen!\n" if ds else "")
                + "\n✅ Your real money is safe.",
                parse_mode="HTML"
            )
            state["pending_order"] = None
        else:
            await query.message.reply_text(f"⚠️ Unexpected: {json.dumps(result)[:500]}")

    elif data == "order_cancel":
        state = get_state(chat_id)
        state["pending_order"] = None
        await query.edit_message_text("❌ Order cancelled. Just let me know if you need anything else!")

    elif data == "order_rescan":
        state = get_state(chat_id)
        state["pending_order"] = None
        await query.edit_message_text("📸 Send me another photo and I'll take a fresh look!")

    elif data.startswith("hitl_approve:"):
        aid = data.split(":")[1]
        await sp_api("POST", "/hitl/approve", {"approval_id": aid, "action": "approved"})
        await query.edit_message_text(f"✅ Payment APPROVED\n\n{query.message.text}")

    elif data.startswith("hitl_kill:"):
        aid = data.split(":")[1]
        await sp_api("POST", "/hitl/approve", {"approval_id": aid, "action": "killed"})
        await query.edit_message_text(f"🔴 Payment KILLED — wallet frozen for safety")


# ─── Document/file handler ────────────────────────────────────────────

async def handle_document(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle documents (images sent as files)."""
    doc = update.message.document
    if doc.mime_type and doc.mime_type.startswith("image/"):
        # Treat as photo
        await update.message.reply_text("🔍 Analyzing your image...")
        file = await ctx.bot.get_file(doc.file_id)
        buf = io.BytesIO()
        await file.download_to_memory(buf)

        caption = update.message.caption or "Analyze this image and help me."
        response = await gemini_vision(caption, buf.getvalue(), doc.mime_type)

        chat_id = update.effective_chat.id
        add_history(chat_id, "user", f"[Image] {caption}")
        add_history(chat_id, "model", response)

        order = extract_order(response)
        display_text = clean_response(response)

        if order:
            get_state(chat_id)["pending_order"] = order
            if display_text:
                await update.message.reply_text(display_text)
            keyboard = [[
                InlineKeyboardButton("✅ Order Now", callback_data="order_confirm"),
                InlineKeyboardButton("❌ Cancel", callback_data="order_cancel"),
            ]]
            await update.message.reply_text(format_order_msg(order), parse_mode="HTML",
                                            reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await update.message.reply_text(display_text or response)
    else:
        await update.message.reply_text("📄 I can analyze images, voice messages, and text. Send me one of those!")


# ─── Main ─────────────────────────────────────────────────────────────

def main():
    if not BOT_TOKEN:
        print("ERROR: Set TELEGRAM_BOT_TOKEN in backend/.env")
        sys.exit(1)

    print("🛡️  SentinelPay Universal AI Assistant")
    print(f"   Gemini: {'✅ Ready' if GEMINI_API_KEY else '⚠️  Demo mode (set GEMINI_API_KEY)'}")
    print(f"   SentinelPay: {SENTINELPAY_URL}")
    print(f"   Starting bot...")

    app = Application.builder().token(BOT_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("balance", cmd_balance))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("approve", cmd_approve))
    app.add_handler(CommandHandler("kill", cmd_kill))
    app.add_handler(CommandHandler("unfreeze", cmd_unfreeze))

    # Media
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    # Buttons
    app.add_handler(CallbackQueryHandler(handle_callback))

    # Text (last - catch all)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    print("   ✅ Bot is live! Send /start to your bot on Telegram.")
    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
