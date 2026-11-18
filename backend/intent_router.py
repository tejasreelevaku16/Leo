
import re

# Load spaCy and its English model.
# If unavailable, LEO uses comprehensive pattern and heuristic-based detection.
try:
    import spacy
    nlp = spacy.load("en_core_web_sm")
except (ImportError, OSError):
    nlp = None


# ==========================================
# CONVERSATION / GREETINGS PATTERNS
# ==========================================

CONVERSATION_EXACT = {
    "hi", "hello", "hey", "hii", "hiii", "heyy", "hola", "sup", "yo",
    "good morning", "good afternoon", "good evening", "good night",
    "how are you", "how are you doing", "how is it going", "hows it going",
    "whats up", "what's up", "thank you", "thanks", "thanks a lot",
    "bye", "goodbye", "see you", "cya", "who are you", "what can you do",
    "ok", "okay", "cool", "nice", "great", "awesome", "got it", "understood",
    "tell me a joke", "are you an ai", "are you there", "help"
}

CONVERSATION_PATTERNS = [
    r"^(hi|hello|hey|greetings|hola)\b",
    r"\bhow are you\b",
    r"\bhow are you doing\b",
    r"\bwhat'?s up\b",
    r"\bthank(s|\s+you)\b",
    r"\b(bye|goodbye|see you)\b",
    r"\bwho are you\b",
    r"\btell me a joke\b",
]


# ==========================================
# RESOURCE / EXTERNAL DEPENDENCY PATTERNS
# ==========================================

WEB_PATTERNS = [
    # Breaking / Latest news & current events
    r"\b(latest|breaking|recent|today'?s?)\s+(news|headlines?|events?|happenings?|updates?)\b",
    r"\bwhat('?s| is|\s+has)\s+happened\s+(today|recently|this week|lately|in the news)\b",
    r"\bnews\s+(about|on|regarding)\b",
    r"\bwhat happened today\b",

    # Real-time prices, sports, weather & status
    r"\bcurrent\s+(price|stock|rate|valuation|weather|forecast|score|standing|ranking)\b",
    r"\b(stock|crypto|bitcoin|btc|ethereum|eth|gold|silver|shares?)\s+price\b",
    r"\bprice\s+of\s+[a-z0-9]+\s*(today|now|right now)?\b",
    r"\bweather\s+(in|for)\s+[a-z\s]+(today|tomorrow|now)?\b",
    r"\b(live|match|game|sports?)\s+(score|results?|standings?|updates?)\b",
    r"\bwho won (the )?(match|game|election|cup|series|race)\b",
    r"\bis\s+[a-z0-9\.\-]+\s+(down|offline|working|up)\s+(now|today|right now)?\b",

    # Software versions & recent releases
    r"\b(latest|newest|recent|current)\s+(version|release|changelog|patch|features?)\s+(of|in|for)\b",
    r"\bwhat('?s| is)\s+new\s+in\s+[a-z0-9\.\-]+\b",
    r"\b(2025|2026)\s+(updates?|release|features?|trends?|roadmap)\b",

    # Learning resources, courses, tutorials, certifications
    r"\b(courses?|certifications?|tutorials?|learning\s+resources?|study\s+material|syllabus)\b",
    r"\b(free\s+courses?|best\s+courses?|where\s+to\s+learn|how\s+to\s+learn)\b",
    r"\b(online\s+courses?|certifications?\s+for|tutorials?\s+for|bootcamps?)\b",
    r"\b(roadmap\s+(to|for)\s+learning|recommended\s+books?\s+for)\b",

    # Documentation, specifications, research papers & websites
    r"\b(official\s+docs?|official\s+documentation|api\s+docs?|api\s+reference|developer\s+docs?)\b",
    r"\b(research\s+papers?|arxiv|whitepapers?|specifications?|spec)\s+(on|for|about)\b",
    r"\bofficial\s+website\s+(of|for)\b",
    r"\bgithub\s+repo(sitory)?\s+(of|for)\b",

    # Explicit search requests
    r"\b(search\s+(the\s+)?(web|internet|online)|look\s+up\s+online|find\s+online|google\s+this)\b",
    r"\b(search\s+for\s+[a-z0-9\s]+on\s+(the\s+)?(web|internet))\b",
    r"\b(find\s+external\s+sources|provide\s+sources|give\s+me\s+links)\b",
]

TEMPORAL_TRIGGERS = {
    "today", "yesterday", "tonight", "this week", "this month", "right now",
    "currently", "latest", "recent", "breaking", "2026", "2025"
}

TEMPORAL_DOMAINS = {
    "news", "price", "stock", "weather", "score", "election", "version",
    "release", "update", "outage", "ceo", "president", "winner", "result",
    "match", "game", "standing", "standings"
}


# ==========================================
# TEXT NORMALIZATION
# ==========================================

def normalize_text(message: str) -> str:
    text = message.lower().strip()
    text = re.sub(r"\s+", " ", text)
    return text


def clean_punct(message: str) -> str:
    text = message.lower().strip()
    text = re.sub(r"[^\w\s']", "", text)
    text = re.sub(r"\s+", " ", text)
    return text


# ==========================================
# INTENT DETECTION
# ==========================================

def detect_intent(message: str) -> str:
    """
    Intelligently detect the user's message intent.

    Returns:
        conversation: Greetings, pleasantries, small talk, casual messages.
        web_search: Questions requiring external resources, real-time data,
                    latest news, courses, certifications, docs, or research.
        knowledge: Standard knowledge questions, explanations, coding, math,
                   and queries reliably answerable using internal AI weights.
    """
    if not message or not message.strip():
        return "conversation"

    text = normalize_text(message)
    stripped = clean_punct(message)

    # 1. Check exact conversation / greeting matches first
    if stripped in CONVERSATION_EXACT:
        return "conversation"

    # 2. Check for resource / external dependency intent
    for pattern in WEB_PATTERNS:
        if re.search(pattern, text):
            return "web_search"

    # 3. Check for greeting patterns in multi-word messages if not asking for external info
    for pattern in CONVERSATION_PATTERNS:
        if re.search(pattern, text):
            # If it's a short greeting like "Hello there friend", treat as conversation
            words = text.split()
            if len(words) <= 6:
                return "conversation"

    # 4. SpaCy / NLP heuristic for temporal + domain intersections
    words_set = set(re.findall(r"\b[a-z0-9]+\b", text))
    has_temporal = bool(words_set.intersection(TEMPORAL_TRIGGERS))
    has_domain = bool(words_set.intersection(TEMPORAL_DOMAINS))

    if has_temporal and has_domain:
        return "web_search"

    if nlp:
        try:
            doc = nlp(text)
            lemmas = {
                token.lemma_.lower()
                for token in doc
                if not token.is_stop and not token.is_punct
            }
            if lemmas.intersection(TEMPORAL_TRIGGERS) and lemmas.intersection(TEMPORAL_DOMAINS):
                return "web_search"
        except Exception:
            pass

    # 5. Default to general knowledge (answered internally without web search)
    return "knowledge"


# ==========================================
# AUTOMATIC SEARCH DECISION
# ==========================================

def should_perform_search(message: str, search_enabled: bool) -> bool:
    """
    Decides whether a user's message genuinely requires external web search.

    Rules:
    - If search_enabled is False: NEVER trigger web search.
    - If message is conversation / greeting: NEVER trigger web search.
    - If message is normal knowledge / coding / explanation: DO NOT trigger web search.
    - If message genuinely requires external resources (intent == "web_search"): TRIGGER search.
    """
    if not search_enabled:
        return False

    intent = detect_intent(message)
    return intent == "web_search"
