import os
import re
import time
import inspect
import logging
from contextlib import asynccontextmanager
from urllib.parse import urlparse

try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import func

from backend.database import get_db
from backend.models import User, Conversation, Message
from backend.auth import router as auth_router, get_current_user

from backend.ollama_engine import OllamaEngine
from backend.gemini_engine import GeminiEngine
from backend.groq_engine import GroqEngine
from backend.hybrid_engine import HybridEngine
from backend.search_engine import TavilySearchEngine
from backend.intent_router import detect_intent, should_perform_search


# ==========================================
# LOAD ENVIRONMENT VARIABLES
# ==========================================

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("leo")


# ==========================================
# LEO CONFIGURATION
# ==========================================

engine = None
search_engine = None

provider = os.getenv("LEO_PROVIDER", "ollama").lower().strip()
model_name = None
web_search_enabled = False

MAX_HISTORY_MESSAGES = 20


# ==========================================
# MODEL LIFECYCLE
# ==========================================

@asynccontextmanager
async def lifespan(app: FastAPI):

    global engine, search_engine, provider, model_name, web_search_enabled

    logger.info("Starting LEO...")
    logger.info("Configured provider: %s", provider)

    if provider == "ollama":

        model_name = os.getenv("OLLAMA_MODEL", "llama3.2:3b").strip()
        base_url = os.getenv(
            "OLLAMA_BASE_URL",
            "http://localhost:11434"
        ).strip()

        engine = OllamaEngine(
            model=model_name,
            base_url=base_url
        )

        logger.info("Ollama initialized: %s at %s", model_name, base_url)

    elif provider == "gemini":

        model_name = os.getenv(
            "GEMINI_MODEL",
            "gemini-3.8-flash"
        ).strip()

        engine = GeminiEngine(model=model_name)

        logger.info("Gemini initialized: %s", model_name)

    elif provider == "groq":

        model_name = os.getenv(
            "GROQ_MODEL",
            "openai/gpt-oss-20b"
        ).strip()

        engine = GroqEngine(model=model_name)

        logger.info("Groq initialized: %s", model_name)

    elif provider == "hybrid":

        engine = HybridEngine()
        model_name = "Gemini primary + Groq fallback"

        logger.info("Hybrid engine initialized")

    else:

        raise RuntimeError(
            f"Unsupported LEO_PROVIDER: {provider}. "
            "Supported providers: ollama, gemini, groq, hybrid."
        )

    # Initialize web search engine
    try:

        search_engine = TavilySearchEngine()
        web_search_enabled = True

        logger.info("LEO web search engine initialized.")

    except Exception:

        search_engine = None
        web_search_enabled = False

        logger.warning(
            "Web search engine unavailable or missing API key."
        )

    # Warm up NLP router
    try:

        detect_intent("hello")

        logger.info("LEO NLP intent router initialized.")

    except Exception:

        logger.warning("NLP intent router initialization skipped.")

    yield

    # Clean up resources
    if engine is not None:

        close_method = getattr(engine, "close", None)

        if close_method is not None:

            try:

                result = close_method()

                if inspect.isawaitable(result):
                    await result

            except Exception:

                logger.exception("Error while closing AI engine.")

    engine = None
    search_engine = None
    web_search_enabled = False

    logger.info("LEO stopped.")


# ==========================================
# FASTAPI APPLICATION
# ==========================================

app = FastAPI(
    title="LEO AI API",
    description=(
        "LEO AI assistant with NLP, conversational memory, "
        "AI intelligence, secure authentication, and web research."
    ),
    version="4.0.0",
    lifespan=lifespan
)


# ==========================================
# AUTHENTICATION ROUTER & STATIC FILES
# ==========================================

app.include_router(auth_router)

os.makedirs("uploads/profile_pictures", exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")


# ==========================================
# CORS CONFIGURATION
# ==========================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5500",
        "http://localhost:5500",
        "http://127.0.0.1:8000",
        "http://localhost:8000",
        "https://neelagirichandrika.github.io"
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"]
)


# ==========================================
# REQUEST & RESPONSE MODELS
# ==========================================

class RenameConversationRequest(BaseModel):

    title: str = Field(
        min_length=1,
        max_length=200
    )


class ChatRequest(BaseModel):

    message: str = Field(
        min_length=1,
        max_length=1000
    )

    conversation_id: str | None = Field(
        default=None,
        max_length=100
    )

    max_new_tokens: int = Field(
        default=900,
        ge=1,
        le=2000
    )

    temperature: float = Field(
        default=0.4,
        gt=0,
        le=2.0
    )

    search_enabled: bool = False


class ChatResponse(BaseModel):

    assistant: str
    response: str
    sources: list[dict] = Field(default_factory=list)
    conversation_id: str
    message_id: int | None = None
    user_message_id: int | None = None


# ==========================================
# SYSTEM & HEALTH ENDPOINTS
# ==========================================

@app.get("/")
def home():

    return {
        "application": "LEO AI",
        "status": "running",
        "intelligence_engine": provider,
        "model": model_name,
        "web_search_enabled": web_search_enabled,
        "conversation_memory": True
    }


@app.get("/health")
def health():

    return {
        "status": "healthy",
        "model_loaded": engine is not None,
        "intelligence_engine": provider,
        "model": model_name,
        "web_search_loaded": search_engine is not None,
        "nlp_loaded": detect_intent("hello") is not None
    }


# ==========================================
# CONVERSATION MANAGEMENT ENDPOINTS
# ==========================================

@app.get("/conversations")
def list_conversations(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):

    conversations = (
        db.query(Conversation)
        .filter(Conversation.user_id == current_user.id)
        .order_by(Conversation.updated_at.desc())
        .all()
    )

    return [
        {
            "id": str(c.id),
            "title": c.title,
            "created_at": (
                c.created_at.isoformat()
                if c.created_at else None
            ),
            "updated_at": (
                c.updated_at.isoformat()
                if c.updated_at else None
            )
        }
        for c in conversations
    ]


@app.get("/conversations/{conversation_id}")
def get_conversation_history(
    conversation_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):

    try:
        conv_id_int = int(conversation_id)

    except (ValueError, TypeError):

        raise HTTPException(
            status_code=400,
            detail="Invalid conversation ID."
        )

    conversation = (
        db.query(Conversation)
        .filter(
            Conversation.id == conv_id_int,
            Conversation.user_id == current_user.id
        )
        .first()
    )

    if not conversation:

        raise HTTPException(
            status_code=404,
            detail="Conversation not found."
        )

    messages = (
        db.query(Message)
        .filter(Message.conversation_id == conversation.id)
        .order_by(Message.created_at.asc())
        .all()
    )

    return {
        "id": str(conversation.id),
        "title": conversation.title,
        "created_at": (
            conversation.created_at.isoformat()
            if conversation.created_at else None
        ),
        "updated_at": (
            conversation.updated_at.isoformat()
            if conversation.updated_at else None
        ),
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "created_at": (
                    m.created_at.isoformat()
                    if m.created_at else None
                )
            }
            for m in messages
        ]
    }


@app.delete("/conversations/{conversation_id}")
def delete_conversation(
    conversation_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):

    try:
        conv_id_int = int(conversation_id)

    except (ValueError, TypeError):

        raise HTTPException(
            status_code=400,
            detail="Invalid conversation ID."
        )

    conversation = (
        db.query(Conversation)
        .filter(
            Conversation.id == conv_id_int,
            Conversation.user_id == current_user.id
        )
        .first()
    )

    if not conversation:

        raise HTTPException(
            status_code=404,
            detail="Conversation not found."
        )

    db.delete(conversation)
    db.commit()

    return {
        "status": "success",
        "message": "Conversation deleted."
    }


@app.patch("/conversations/{conversation_id}")
def rename_conversation(
    conversation_id: str,
    data: RenameConversationRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):

    try:
        conv_id_int = int(conversation_id)

    except (ValueError, TypeError):

        raise HTTPException(
            status_code=400,
            detail="Invalid conversation ID."
        )

    conversation = (
        db.query(Conversation)
        .filter(
            Conversation.id == conv_id_int,
            Conversation.user_id == current_user.id
        )
        .first()
    )

    if not conversation:

        raise HTTPException(
            status_code=404,
            detail="Conversation not found."
        )

    clean_title = data.title.strip()
    if not clean_title:

        raise HTTPException(
            status_code=400,
            detail="Conversation title cannot be empty."
        )

    conversation.title = clean_title
    conversation.updated_at = func.now()
    db.commit()

    return {
        "status": "success",
        "message": "Conversation renamed.",
        "id": str(conversation.id),
        "title": conversation.title
    }


@app.delete("/conversations/{conversation_id}/messages/{message_id}")
def delete_message(
    conversation_id: str,
    message_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):

    try:
        conv_id_int = int(conversation_id)

    except (ValueError, TypeError):

        raise HTTPException(
            status_code=400,
            detail="Invalid conversation ID."
        )

    conversation = (
        db.query(Conversation)
        .filter(
            Conversation.id == conv_id_int,
            Conversation.user_id == current_user.id
        )
        .first()
    )

    if not conversation:

        raise HTTPException(
            status_code=404,
            detail="Conversation not found."
        )

    message = (
        db.query(Message)
        .filter(
            Message.id == message_id,
            Message.conversation_id == conversation.id
        )
        .first()
    )

    if not message:

        raise HTTPException(
            status_code=404,
            detail="Message not found."
        )

    db.delete(message)
    conversation.updated_at = func.now()
    db.commit()

    return {
        "status": "success",
        "message": "Message deleted."
    }


# ==========================================
# LEO QUICK RESPONSE LAYER
# ==========================================

def get_quick_response(message: str) -> str | None:

    text = message.lower().strip()
    text = re.sub(r"[^\w\s']", "", text)
    text = re.sub(r"\s+", " ", text)

    greetings = {
        "hi": "Hey there! 👋 How are you doing today?",
        "hello": "Hello! 😊 It's lovely to chat with you. How can I help?",
        "hey": "Hey! 👋 What's up?",
        "hii": "Heyyy! 😊 How's your day going?",
        "hiii": "Heyyy! 😊 How's your day going?",
        "good morning": "Good morning! ☀️ Hope you're having a wonderful day!",
        "good afternoon": "Good afternoon! 😊 How's your day going?",
        "good evening": "Good evening! 🌙 How can I help you today?",
        "good night": "Good night! 🌙 Take care and sleep well!"
    }

    if text in greetings:
        return greetings[text]

    casual_responses = {
        "how are you": "I'm doing great! 😊 Thanks for asking. How are you?",
        "how are you doing": "I'm doing well! Always happy to chat with you. How about you?",
        "whats up": "Not much! 😊 I'm here and ready to chat. What's happening with you?",
        "what's up": "Not much! 😊 I'm here and ready to chat. What's happening with you?",
        "thank you": "You're very welcome! 😊 Happy to help.",
        "thanks": "Anytime! 😊",
        "bye": "See you later! 👋 Take care!",
        "goodbye": "Goodbye! 👋 Have a wonderful day!",
        "who are you": (
            "I'm LEO, your AI assistant! 🤖 "
            "I can help with learning, research, coding, "
            "and everyday questions."
        )
    }

    if text in casual_responses:
        return casual_responses[text]

    return None


# ==========================================
# CONTEXT-AWARE WEB SEARCH QUERY BUILDER
# ==========================================

FOLLOW_UP_PATTERN = re.compile(
    r"\b("
    r"it|its|they|them|that|those|these|this|"
    r"more|resources?|examples?|advantages?|disadvantages?|"
    r"benefits?|types?|applications?|uses?|"
    r"how about|what about|continue|elaborate"
    r")\b",
    re.IGNORECASE
)


def build_contextual_search_query(
    message: str,
    history: list[dict]
) -> str:

    previous_user_messages = [
        item["content"]
        for item in history
        if item.get("role") == "user"
    ][-2:]

    if not previous_user_messages:
        return message

    is_follow_up = (
        FOLLOW_UP_PATTERN.search(message) is not None
        or re.match(
            r"^\s*(for|about)\b",
            message,
            re.IGNORECASE
        ) is not None
    )

    if not is_follow_up:
        return message

    previous_context = " | ".join(previous_user_messages)

    return (
        f"Previous conversation topics: {previous_context}. "
        f"Latest user request: {message}. "
        "Find web information specifically relevant to the latest request."
    )


def build_conversation_context(history: list[dict]) -> str:

    if not history:
        return ""

    context = []

    for item in history:

        role = item.get("role", "").upper()
        content = item.get("content", "")

        if role in ("USER", "ASSISTANT") and content:
            context.append(f"{role}: {content}")

    if not context:
        return ""

    return (
        "PREVIOUS CONVERSATION:\n"
        + "\n".join(context)
        + "\n\n"
    )


# ==========================================
# BUILD WEB RESEARCH PROMPT
# ==========================================

def build_research_prompt(
    question: str,
    search_results: list[dict],
    history: list[dict] | None = None
):

    context_parts = []
    sources = []

    for item in search_results[:3]:

        title = item.get("title", "").strip()
        url = item.get("url", "").strip()
        content = item.get("content", "").strip()

        parsed_url = urlparse(url)

        if (
            not title
            or not content
            or parsed_url.scheme not in ("http", "https")
            or not parsed_url.netloc
        ):
            continue

        source_number = len(sources) + 1

        context_parts.append(
            f"SOURCE [{source_number}]\n"
            f"Title: {title}\n"
            f"URL: {url}\n"
            f"Excerpt: {content[:450]}"
        )

        sources.append({
            "title": title,
            "url": url
        })

    conversation_context = build_conversation_context(history or [])

    if not context_parts:

        prompt = f"""You are LEO, an intelligent AI assistant.

{conversation_context}The user asked: {question}

Web search was enabled, but no usable search results were retrieved.
Answer honestly that current web information could not be retrieved, then answer using your general knowledge if possible."""

        return prompt, []

    search_context = "\n\n".join(context_parts)

    prompt = f"""You are LEO, a helpful and concise AI assistant with access to web search results.

{conversation_context}The user asked:
{question}

Answer the user's question directly, clearly, and concisely using the verified web search sources below.

GUIDELINES:
1. Provide a direct, informative answer in 1 to 3 short paragraphs or bullet points.
2. Cite sources using [1], [2] next to claims.
3. Be concise and keep your answer under 150 words. Avoid filler, repetition, or lengthy introductions.
4. Do not include full URLs in your answer text.

WEB SEARCH SOURCES:
{search_context}

Answer:
"""

    return prompt, sources


# ==========================================
# CHAT ENDPOINT
# ==========================================

@app.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):

    # 1. Resolve or create persistent MySQL conversation
    conversation = None

    if request.conversation_id:

        try:
            conv_id_int = int(request.conversation_id)

        except (ValueError, TypeError):

            raise HTTPException(
                status_code=400,
                detail="Invalid conversation ID."
            )

        conversation = (
            db.query(Conversation)
            .filter(
                Conversation.id == conv_id_int,
                Conversation.user_id == current_user.id
            )
            .first()
        )

        if not conversation:

            raise HTTPException(
                status_code=404,
                detail="Conversation not found or access denied."
            )

    else:

        title_snippet = (
            request.message.strip().replace("\n", " ")
        )

        if len(title_snippet) > 40:
            title_snippet = title_snippet[:37] + "..."

        conversation = Conversation(
            user_id=current_user.id,
            title=title_snippet or "New chat"
        )

        db.add(conversation)
        db.commit()
        db.refresh(conversation)

    # 2. Retrieve conversation history from MySQL
    db_messages = (
        db.query(Message)
        .filter(Message.conversation_id == conversation.id)
        .order_by(Message.created_at.asc())
        .all()
    )

    history = [
        {
            "role": m.role,
            "content": m.content
        }
        for m in db_messages
    ][-MAX_HISTORY_MESSAGES:]

    try:

        # 3. Detect intent
        intent = detect_intent(request.message)

        logger.info(
            "User: %s (User ID: %s, Conversation ID: %s) | "
            "Intent: %s | Prior msgs: %s",
            current_user.email,
            current_user.id,
            conversation.id,
            intent,
            len(history)
        )

        # 4. Quick response layer (handles greetings instantly in <10ms even if search is toggled)
        quick_response = get_quick_response(request.message)

        if quick_response is not None:

            logger.info(
                "Quick response activated for conversation %s",
                conversation.id
            )

            user_msg = Message(
                conversation_id=conversation.id,
                role="user",
                content=request.message
            )

            assistant_msg = Message(
                conversation_id=conversation.id,
                role="assistant",
                content=quick_response
            )

            conversation.updated_at = func.now()

            db.add(user_msg)
            db.add(assistant_msg)
            db.commit()
            db.refresh(user_msg)
            db.refresh(assistant_msg)

            return ChatResponse(
                assistant="LEO",
                response=quick_response,
                sources=[],
                conversation_id=str(conversation.id),
                message_id=assistant_msg.id,
                user_message_id=user_msg.id
            )

        # 5. Check AI engine status
        if engine is None:

            raise HTTPException(
                status_code=503,
                detail="LEO intelligence engine is not initialized."
            )

        prompt = request.message
        sources = []

        # 6. Intelligent automatic web research decision
        search_needed = should_perform_search(
            message=request.message,
            search_enabled=request.search_enabled
        )

        if search_needed:

            if search_engine is not None:

                try:
                    search_query = build_contextual_search_query(
                        request.message,
                        history
                    )

                    logger.info("Intelligent web research triggered: %s", search_query)

                    search_results = await search_engine.search(
                        search_query,
                        max_results=3
                    )

                    logger.info(
                        "Retrieved %s search results",
                        len(search_results)
                    )

                    prompt, sources = build_research_prompt(
                        request.message,
                        search_results,
                        history
                    )

                except Exception as search_error:
                    logger.warning("Web search failed gracefully: %s", search_error)
                    prompt = request.message
                    sources = []

            else:
                logger.warning(
                    "Web search was needed but search engine is unavailable. "
                    "Answering using internal knowledge."
                )
                prompt = request.message
                sources = []

        if not sources:

            if history:

                conv_context = build_conversation_context(history)

                prompt = f"""You are LEO, a helpful and intelligent AI assistant.

Answer the user's questions clearly and accurately.
Use the previous conversation when it is relevant.
Do not invent facts. If you are uncertain, say so.

{conv_context}USER:
{request.message}

LEO:
"""
            else:
                prompt = request.message

        # 7. Generate response
        generation_start = time.perf_counter()

        if provider == "ollama":

            # For web research with sources, cap tokens to 220 for fast answers (<30s)
            effective_tokens = min(request.max_new_tokens, 220) if sources else request.max_new_tokens

            response = await engine.generate_response(
                prompt=prompt,
                max_new_tokens=effective_tokens,
                temperature=request.temperature,
                history=None if sources else history
            )

        else:

            response = await engine.generate_response(
                prompt=prompt,
                max_new_tokens=request.max_new_tokens,
                temperature=request.temperature
            )

        if not isinstance(response, str) or not response.strip():

            raise RuntimeError(
                "The AI engine returned an empty response."
            )

        generation_time = time.perf_counter() - generation_start

        logger.info(
            "Response generated in %.2f seconds",
            generation_time
        )

        # 8. Persist messages to MySQL
        user_msg = Message(
            conversation_id=conversation.id,
            role="user",
            content=request.message
        )

        assistant_msg = Message(
            conversation_id=conversation.id,
            role="assistant",
            content=response
        )

        conversation.updated_at = func.now()

        db.add(user_msg)
        db.add(assistant_msg)
        db.commit()
        db.refresh(user_msg)
        db.refresh(assistant_msg)

        # 9. Return response
        return ChatResponse(
            assistant="LEO",
            response=response,
            sources=sources,
            conversation_id=str(conversation.id),
            message_id=assistant_msg.id,
            user_message_id=user_msg.id
        )

    except HTTPException:

        db.rollback()
        raise

    except ValueError as error:

        db.rollback()

        logger.warning(
            "Invalid request: %s",
            error
        )

        raise HTTPException(
            status_code=400,
            detail=str(error)
        )

    except RuntimeError as error:

        db.rollback()

        logger.error(
            "LEO runtime error: %s",
            error
        )

        raise HTTPException(
            status_code=503,
            detail=f"LEO is temporarily unavailable: {error}"
        )

    except Exception:

        db.rollback()

        logger.exception(
            "Unexpected error while processing chat."
        )

        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred in LEO."
        )