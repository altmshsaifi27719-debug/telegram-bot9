import asyncio
import html
import io
import json
import logging
import os
import sqlite3
import urllib.parse
from datetime import datetime, timedelta, timezone

import qrcode
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, InputMediaVideo
from telegram.constants import ParseMode
from telegram.error import TelegramError, Forbidden, RetryAfter
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler,
    ContextTypes, ConversationHandler, filters,
)

# ============================================================
# CONFIGURATION
# ============================================================
BOT_TOKEN = "AAEQaHoFVyf6_xEcTQgLVQVT9xh5GXZFIgw"
ADMIN_ID = 9291293881

ADMIN_IDS = {ADMIN_ID}
try:
    ADMIN_IDS.update(int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip())
except ValueError:
    pass

DB_FILE = "bot.sqlite"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(name)

PLAN_NAME, PLAN_PRICE, UPI_ID, CHANNEL_LINK, DEMO_MEDIA, WELCOME_IMAGE, WELCOME_TEXT, BROADCAST_CONTENT, REJECTION_REASON, EDIT_PLAN_NAME, EDIT_PLAN_PRICE, DB_IMPORT, CHOOSE_PHOTO, PRO_PHOTO, USER_SEARCH, WELCOME_VIDEO, WELCOME_VIDEOS, PLAN_LINK = range(18)

DEFAULT_WELCOME = "💎 Welcome to our Premium Service!"
LIFETIME_DAYS = 36500


def set_manual_state(context, state):
    context.user_data["_manual_state"] = state


def clear_manual_state(context):
    context.user_data.pop("_manual_state", None)


def db():
    con = sqlite3.connect(DB_FILE, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    return con


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def esc(value):
    return html.escape("" if value is None else str(value))


def bold(text):
    return f"<b>{text}</b>"


def styled_plan_name(text, style="normal"):
    """Render plan-button labels in a selectable Unicode style."""
    maps = {
        "bold": (0x1D400, 0x1D41A, 0x1D7CE),
        "italic": (0x1D434, 0x1D44E, None),
        "bold_italic": (0x1D468, 0x1D482, None),
        "script": (0x1D49C, 0x1D4B6, None),
        "double": (0x1D538, 0x1D552, 0x1D7D8),
        "mono": (0x1D5D4, 0x1D5EE, 0x1D7F6),
        "sans_bold": (0x1D5D4, 0x1D5EE, 0x1D7F6),
    }
    if style in (None, "normal") or style not in maps:
        return text
    upper, lower, digits = maps[style]
    out = []
    for ch in text:
        if "A" <= ch <= "Z": out.append(chr(upper + ord(ch) - ord("A")))
        elif "a" <= ch <= "z": out.append(chr(lower + ord(ch) - ord("a")))
        elif digits is not None and "0" <= ch <= "9": out.append(chr(digits + ord(ch) - ord("0")))
        else: out.append(ch)
    return "".join(out)


def font_choice_keyboard():
    options = [("normal", "Normal"), ("bold", "𝐁𝐨𝐥𝐝"), ("italic", "𝘐𝘵𝘢𝘭𝘪𝘤"),
               ("bold_italic", "𝑩𝒐𝒍𝒅 𝑰𝒕𝒂𝒍𝒊𝒄"), ("script", "𝓢𝓬𝓻𝓲𝓹𝓽"),
               ("double", "𝔻𝕠𝕦𝕓𝕝𝕖"), ("mono", "𝙼𝚘𝚗𝚘")]
    return InlineKeyboardMarkup([[style_button(label, f"admin:plan:font:{key}", style="primary")]
                                 for key, label in options])


def style_button(text, callback_data=None, url=None, style=None):
    """Create a Telegram inline button, compatible with older PTB installs."""
    kwargs = {"text": text}
    if callback_data is not None:
        kwargs["callback_data"] = callback_data
    if url is not None:
        kwargs["url"] = url
    if style not in {"primary", "success", "danger"}:
        return InlineKeyboardButton(**kwargs)

    try:
        return InlineKeyboardButton(**kwargs, style=style)
    except TypeError as exc:
        if "unexpected keyword argument 'style'" not in str(exc):
            raise
        try:
            return InlineKeyboardButton(**kwargs, api_kwargs={"style": style})
        except TypeError:
            return InlineKeyboardButton(**kwargs)
