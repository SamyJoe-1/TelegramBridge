"""
Telegram Userbot Bridge
------------------------
Exposes a small HTTP API in front of a Telethon client logged in as a
personal (Premium) Telegram account, so it can send messages containing
custom_emoji entities to channels — something the Bot API can't do
without a Fragment username.

Run with:
    uvicorn main:app --host 0.0.0.0 --port 8000

Required environment variables (see .env.example):
    TG_API_ID          - from https://my.telegram.org
    TG_API_HASH        - from https://my.telegram.org
    TG_SESSION_STRING  - generated once via login.py
    BRIDGE_API_KEY      - a secret you invent, required in X-API-Key header
"""

import os
import io
import asyncio
import logging
import urllib.request
from typing import List, Optional

from PIL import Image

from dotenv import load_dotenv
load_dotenv()  # reads .env in the same folder and sets the env vars automatically

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import (
    MessageEntityCustomEmoji,
    MessageEntityBold,
    MessageEntityItalic,
    MessageEntityUnderline,
    MessageEntityStrike,
    MessageEntityCode,
    MessageEntityPre,
    MessageEntitySpoiler,
    MessageEntityBlockquote,
    MessageEntityTextUrl,
)
from telethon.errors import FloodWaitError, AuthKeyUnregisteredError, RPCError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("telegram-userbot-bridge")

REQUIRED_ENV = ["TG_API_ID", "TG_API_HASH", "TG_SESSION_STRING", "BRIDGE_API_KEY"]
missing = [v for v in REQUIRED_ENV if not os.environ.get(v)]
if missing:
    raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")

API_ID = int(os.environ["TG_API_ID"])
API_HASH = os.environ["TG_API_HASH"]
SESSION_STRING = os.environ["TG_SESSION_STRING"]
BRIDGE_API_KEY = os.environ["BRIDGE_API_KEY"]

app = FastAPI(title="Telegram Userbot Bridge")
client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)


class EmojiEntity(BaseModel):
    type: str  # "custom_emoji", "bold", "italic", "code", "pre", "underline",
               # "strikethrough", "spoiler", "blockquote", "text_link", etc.
    offset: int
    length: int
    custom_emoji_id: Optional[str] = None   # only present for type == "custom_emoji"
    url: Optional[str] = None               # only present for type == "text_link"
    language: Optional[str] = None          # only present for type == "pre"


class SendMessageRequest(BaseModel):
    chat_id: str  # e.g. "@your_channel_username" or numeric chat id
    text: str
    entities: Optional[List[EmojiEntity]] = []


class SendMessageResponse(BaseModel):
    success: bool
    message_id: Optional[int] = None
    error: Optional[str] = None


@app.on_event("startup")
async def startup():
    await client.connect()
    if not await client.is_user_authorized():
        logger.error(
            "Session is NOT authorized. Re-run login.py to regenerate "
            "TG_SESSION_STRING, then restart this service."
        )
        return

    # Telethon can only resolve a bare numeric chat_id (e.g. -1003984081449)
    # if it already has that entity's access_hash cached. That cache is only
    # populated once this account has "seen" the chat — e.g. by being a
    # member of it. Pulling the dialog list on startup hydrates the cache
    # for every channel/group this account currently belongs to, so posts
    # sent right after startup don't fail with "Cannot find any entity...".
    try:
        dialogs = await client.get_dialogs()
        logger.info("Hydrated entity cache with %d dialogs.", len(dialogs))
    except Exception:
        logger.exception("Failed to hydrate entity cache via get_dialogs()")


@app.on_event("shutdown")
async def shutdown():
    await client.disconnect()


def _check_api_key(x_api_key: Optional[str]):
    if not x_api_key or x_api_key != BRIDGE_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key header")


def _resolve_chat_id(chat_id: str):
    """Telethon only decodes the Bot-API-style marked ID format
    (e.g. "-1001234567890" for a channel/supergroup) when it's passed
    as an int. Passed as a str, it's treated as a username/phone/invite
    link instead, and a numeric-looking string matches none of those -
    hence "Cannot find any entity corresponding to ...". Convert here so
    every caller gets this for free."""
    s = chat_id.strip()
    if s.lstrip("-").isdigit():
        return int(s)
    return s


def _build_entities(entities: List[EmojiEntity]):
    tl_entities = []
    for e in entities:
        if e.type == "custom_emoji":
            if not e.custom_emoji_id:
                logger.warning("Skipping custom_emoji entity with no custom_emoji_id: %s", e)
                continue
            try:
                doc_id = int(e.custom_emoji_id)
            except ValueError:
                raise HTTPException(status_code=422, detail=f"Invalid custom_emoji_id: {e.custom_emoji_id}")
            tl_entities.append(
                MessageEntityCustomEmoji(offset=e.offset, length=e.length, document_id=doc_id)
            )
        elif e.type == "bold":
            tl_entities.append(MessageEntityBold(offset=e.offset, length=e.length))
        elif e.type == "italic":
            tl_entities.append(MessageEntityItalic(offset=e.offset, length=e.length))
        elif e.type == "underline":
            tl_entities.append(MessageEntityUnderline(offset=e.offset, length=e.length))
        elif e.type in ("strikethrough", "strike"):
            tl_entities.append(MessageEntityStrike(offset=e.offset, length=e.length))
        elif e.type == "code":
            tl_entities.append(MessageEntityCode(offset=e.offset, length=e.length))
        elif e.type == "pre":
            tl_entities.append(
                MessageEntityPre(offset=e.offset, length=e.length, language=e.language or "")
            )
        elif e.type == "spoiler":
            tl_entities.append(MessageEntitySpoiler(offset=e.offset, length=e.length))
        elif e.type == "blockquote":
            tl_entities.append(MessageEntityBlockquote(offset=e.offset, length=e.length))
        elif e.type == "text_link":
            if not e.url:
                logger.warning("Skipping text_link entity with no url: %s", e)
                continue
            tl_entities.append(
                MessageEntityTextUrl(offset=e.offset, length=e.length, url=e.url)
            )
        else:
            # Unknown/unsupported entity type (e.g. mention, hashtag, url —
            # Telegram infers those from plain text automatically) - skip safely.
            logger.info("Skipping unsupported entity type: %s", e.type)
            continue
    return tl_entities


@app.get("/health")
async def health():
    authorized = await client.is_user_authorized()
    return {"status": "ok" if authorized else "unauthorized"}


@app.get("/list-dialogs")
async def list_dialogs(x_api_key: Optional[str] = Header(default=None)):
    """Diagnostic: shows every chat/channel/group this account currently
    sees, straight from Telegram. If this comes back empty or tiny, the
    session itself has no chat history — the account was never added to
    these channels (or the session string is for the wrong/blank account),
    and no code change can fix that. Join the channels with this account,
    or regenerate TG_SESSION_STRING with login.py, then check again."""
    _check_api_key(x_api_key)
    dialogs = await client.get_dialogs()
    me = await client.get_me()
    return {
        "logged_in_as": {
            "id": me.id,
            "first_name": me.first_name,
            "username": me.username,
            "phone": me.phone,
        },
        "dialog_count": len(dialogs),
        "dialogs": [
            {"id": d.entity.id, "title": getattr(d.entity, "title", None) or getattr(d.entity, "username", None) or getattr(d.entity, "first_name", None)}
            for d in dialogs
        ],
    }


@app.post("/refresh-dialogs")
async def refresh_dialogs(x_api_key: Optional[str] = Header(default=None)):
    """Call this after adding the bridge account to a new channel/group,
    so Telethon can resolve its numeric chat_id without a full restart."""
    _check_api_key(x_api_key)
    dialogs = await client.get_dialogs()
    return {"status": "ok", "dialog_count": len(dialogs)}


class CheckChatsRequest(BaseModel):
    chat_ids: List[str]


@app.post("/check-chats")
async def check_chats(payload: CheckChatsRequest, x_api_key: Optional[str] = Header(default=None)):
    """Diagnostic: pass every channel_id/telegram_chat_id from your config
    sheet in one call, get back which ones the bridge account can actually
    resolve/send to right now, and which ones it needs to join first.
    Avoids discovering broken channels one at a time via failed sends."""
    _check_api_key(x_api_key)

    # Refresh the cache first so this reflects current membership, not stale data.
    await client.get_dialogs()

    results = []
    for cid in payload.chat_ids:
        entry = {"chat_id": cid, "ok": False, "title": None, "error": None}
        try:
            entity = await client.get_entity(_resolve_chat_id(cid))
            entry["ok"] = True
            entry["title"] = getattr(entity, "title", None) or getattr(entity, "username", None)
        except Exception as e:
            entry["error"] = str(e)
        results.append(entry)

    return {
        "checked": len(results),
        "resolvable": sum(1 for r in results if r["ok"]),
        "unresolvable": [r for r in results if not r["ok"]],
        "results": results,
    }


@app.post("/send-message", response_model=SendMessageResponse)
async def send_message(payload: SendMessageRequest, x_api_key: Optional[str] = Header(default=None)):
    _check_api_key(x_api_key)

    tl_entities = _build_entities(payload.entities or [])

    try:
        message = await client.send_message(
            _resolve_chat_id(payload.chat_id),
            payload.text,
            formatting_entities=tl_entities or None,
        )
        return SendMessageResponse(success=True, message_id=message.id)

    except ValueError as e:
        if "Cannot find any entity" in str(e):
            logger.error("Entity resolution failed for chat_id=%s: %s", payload.chat_id, e)
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Bridge account can't resolve chat_id {payload.chat_id!r}. "
                    "The userbot account must be a member of this chat before it "
                    "can send to it by numeric ID. Join the chat with that account, "
                    "then call POST /refresh-dialogs (or restart the bridge)."
                ),
            )
        raise HTTPException(status_code=400, detail=str(e))

    except FloodWaitError as e:
        logger.warning("Flood wait triggered: %s seconds", e.seconds)
        raise HTTPException(status_code=429, detail=f"Flood wait: retry after {e.seconds}s")

    except AuthKeyUnregisteredError:
        logger.error("Session invalidated (logged out / revoked). Needs re-authentication via login.py.")
        raise HTTPException(status_code=401, detail="Session invalidated, needs re-login")

    except RPCError as e:
        logger.exception("Telegram RPC error")
        raise HTTPException(status_code=400, detail=str(e))

    except Exception as e:
        logger.exception("Unexpected failure sending message")
        raise HTTPException(status_code=500, detail=str(e))

class SendPhotoRequest(BaseModel):
    chat_id: str
    photo_url: str
    caption: str = ""
    entities: Optional[List[EmojiEntity]] = []

def _fetch_as_jpeg(url: str) -> io.BytesIO:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = r.read()
    img = Image.open(io.BytesIO(data))
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[-1])
        img = bg
    else:
        img = img.convert("RGB")
    img.thumbnail((2560, 2560))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=92)
    buf.seek(0)
    buf.name = "photo.jpg"
    return buf


@app.post("/send-photo", response_model=SendMessageResponse)
async def send_photo(payload: SendPhotoRequest, x_api_key: Optional[str] = Header(default=None)):
    _check_api_key(x_api_key)
    tl_entities = _build_entities(payload.entities or [])
    try:
        # Telethon sends .webp URLs as STICKERS (no caption allowed), so always
        # download + re-encode to JPEG to guarantee a real photo with caption.
        try:
            photo = await asyncio.to_thread(_fetch_as_jpeg, payload.photo_url)
        except Exception as e:
            logger.exception("Failed to download/convert photo_url=%s", payload.photo_url)
            raise HTTPException(status_code=400, detail=f"Could not fetch/convert photo_url: {e}")
        message = await client.send_file(
            _resolve_chat_id(payload.chat_id),
            file=photo,
            force_document=False,
            caption=payload.caption,
            formatting_entities=tl_entities or None,
        )
        return SendMessageResponse(success=True, message_id=message.id)
    except HTTPException:
        raise
    except ValueError as e:
        if "Cannot find any entity" in str(e):
            logger.error("Entity resolution failed for chat_id=%s: %s", payload.chat_id, e)
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Bridge account can't resolve chat_id {payload.chat_id!r}. "
                    "The userbot account must be a member of this chat before it "
                    "can send to it by numeric ID. Join the chat with that account, "
                    "then call POST /refresh-dialogs (or restart the bridge)."
                ),
            )
        raise HTTPException(status_code=400, detail=str(e))
    except FloodWaitError as e:
        raise HTTPException(status_code=429, detail=f"Flood wait: retry after {e.seconds}s")
    except AuthKeyUnregisteredError:
        raise HTTPException(status_code=401, detail="Session invalidated, needs re-login")
    except RPCError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))