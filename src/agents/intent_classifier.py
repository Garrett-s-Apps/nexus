"""Intent classification extracted from CEO Interpreter."""

from dataclasses import dataclass, field
from enum import Enum


class IntentType(Enum):
    """Types of intents that can be classified from CEO messages."""

    DIRECTIVE = "directive"           # New work to do
    CONVERSATION = "conversation"     # Chat/question/follow-up
    ORG_COMMAND = "org_command"       # Hire/fire/reassign agents
    STATUS_QUERY = "status_query"     # "What's happening?" / status checks
    DOCUMENT_REQUEST = "document_request"  # Generate document
    SYSTEM_COMMAND = "system_command"  # Health check, restart, etc.
    QUESTION = "question"             # Research/answer work-related questions


@dataclass
class IntentResult:
    """Result of intent classification."""

    intent: IntentType
    confidence: float = 1.0
    extracted_entities: dict = field(default_factory=dict)
    raw_text: str = ""


class IntentClassifier:
    """Classifies incoming messages into intent types.

    Independently testable — no side effects, no database access.
    Uses pattern matching and heuristics for fast pre-classification
    before expensive LLM calls.
    """

    # Pattern-based pre-classification (fast path before LLM)
    ORG_PATTERNS = [
        "hire", "fire", "reassign", "promote", "demote",
        "add agent", "remove agent", "new agent", "consolidate",
        "restructure",
    ]
    STATUS_PATTERNS = [
        "status", "what's happening", "how are things",
        "progress", "update", "report", "kpi",
    ]
    DOC_PATTERNS = [
        "generate", "create a doc", "make a presentation",
        "spreadsheet", "write a report", "prepare a deck",
        "pdf", "docx", "pptx", "presentation", "document", "slide",
    ]
    SYSTEM_PATTERNS = [
        "health check", "restart", "deploy", "security scan",
        "cost report", "shutdown", "backup",
    ]
    DIRECTIVE_PATTERNS = [
        "build", "create", "fix", "ship", "implement",
        "deploy", "refactor", "optimize", "add feature",
    ]
    CONVERSATION_PATTERNS = [
        # Greetings
        r"^(hey|hi|hello|yo|sup|whats up|what\'s up|howdy|morning|afternoon|evening)\b",
        r"^(how\'s it going|how are you|hows it going|how ya doing|how you doing)",
        r"^(how\'s your day|hows your day|how was your)",
        # Acknowledgments
        r"^(thanks|thank you|thx|ty|appreciate it|cheers)",
        # Reactions
        r"^(lol|lmao|haha|heh|nice|cool|dope|sick|wow|damn|yep|nope|yea|yeah|nah)",
        # Time-based greetings
        r"^(good morning|good night|gn|gm|good evening)",
        # Emotional states
        r"^(im tired|i\'m tired|im exhausted|i\'m exhausted|long day|rough day)",
        # Small talk
        r"^(what\'s good|whats good|what\'s new|whats new|what\'s happening)",
        r"^(just checking in|checking in|just wanted to say)",
        # Farewells
        r"^(brb|gtg|gotta go|be right back|talk later|ttyl)",
    ]

    def classify(self, message: str) -> IntentResult:
        """Classify message intent using pattern matching + heuristics.

        This is a fast pre-classification that runs before expensive LLM calls.
        Returns IntentResult with the classified intent and confidence score.
        """
        import re

        msg_lower = message.lower().strip()

        # CONVERSATION: Check casual patterns first (highest priority for efficiency)
        for pattern in self.CONVERSATION_PATTERNS:
            if re.match(pattern, msg_lower):
                return IntentResult(
                    intent=IntentType.CONVERSATION,
                    confidence=0.95,
                    raw_text=message,
                    extracted_entities={"mood": "neutral"},
                )

        # CONVERSATION: Short messages without technical terms
        word_count = len(message.split())
        technical_signals = ["build", "create", "deploy", "fix", "hire", "fire", "show",
                           "kpi", "cost", "status", "org", "report", "scan", "agent",
                           "pdf", "docx", "pptx", "presentation", "document", "slide"]
        has_technical = any(t in msg_lower for t in technical_signals)

        if word_count <= 5 and not has_technical:
            return IntentResult(
                intent=IntentType.CONVERSATION,
                confidence=0.8,
                raw_text=message,
                extracted_entities={"mood": "neutral"},
            )

        # ORG_COMMAND: Check for org structure changes (highest specificity)
        if any(p in msg_lower for p in self.ORG_PATTERNS):
            return IntentResult(
                intent=IntentType.ORG_COMMAND,
                confidence=0.9,
                raw_text=message,
            )

        # STATUS_QUERY: Check for status/progress requests
        if any(p in msg_lower for p in self.STATUS_PATTERNS):
            return IntentResult(
                intent=IntentType.STATUS_QUERY,
                confidence=0.85,
                raw_text=message,
            )

        # DOCUMENT_REQUEST: Check for document generation requests
        if any(p in msg_lower for p in self.DOC_PATTERNS):
            return IntentResult(
                intent=IntentType.DOCUMENT_REQUEST,
                confidence=0.9,
                raw_text=message,
            )

        # SYSTEM_COMMAND: Check for system-level commands
        if any(p in msg_lower for p in self.SYSTEM_PATTERNS):
            return IntentResult(
                intent=IntentType.SYSTEM_COMMAND,
                confidence=0.85,
                raw_text=message,
            )

        # DIRECTIVE: Check for directive patterns
        if any(p in msg_lower for p in self.DIRECTIVE_PATTERNS):
            return IntentResult(
                intent=IntentType.DIRECTIVE,
                confidence=0.8,
                raw_text=message,
            )

        # QUESTION: Questions usually have question marks or start with question words
        question_words = ["what", "why", "how", "when", "where", "who", "which", "should", "can", "could", "would"]
        if message.strip().endswith("?") or any(msg_lower.startswith(qw) for qw in question_words):
            return IntentResult(
                intent=IntentType.QUESTION,
                confidence=0.7,
                raw_text=message,
            )

        # Default: directive (new work) with lower confidence
        # LLM classification should be used for low-confidence results
        return IntentResult(
            intent=IntentType.DIRECTIVE,
            confidence=0.5,
            raw_text=message,
        )


intent_classifier = IntentClassifier()
