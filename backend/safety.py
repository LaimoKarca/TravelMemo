"""Chat safety controls, normalization, deterministic regex guards and structured model gate.

Filters and classifiers provide defense-in-depth and do not guarantee all
adversarial attacks are caught; they complement parameterized queries,
strict access boundaries, and untrusted-data separation.
"""

import logging
import re
import unicodedata
from collections.abc import Callable
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


class SafetyUnavailable(Exception):
    """Raised when safety classification service is unavailable or produces malformed output."""


class SafetyReason(str, Enum):
    SAFE = "safe"
    PROMPT_OVERRIDE = "prompt_override"
    EXFILTRATION = "exfiltration"
    DESTRUCTIVE_INJECTION = "destructive_injection"
    CODE_INJECTION = "code_injection"
    EMOTIONAL_COERCION = "emotional_coercion"
    UNSPECIFIED_VIOLATION = "unspecified_violation"


class SafetyDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["allow", "block"] = Field(
        description="Whether to allow or block the request"
    )
    reason: SafetyReason = Field(
        description="Fixed enum reason for the safety decision without free-form reasoning"
    )


# Strips zero-width spaces/joiners, soft hyphens, and directional formatting marks
_INVISIBLE_CHARS_PATTERN = re.compile(
    r"[\u200B-\u200D\uFEFF\u00AD\u2060\u202A-\u202E\u2066-\u2069]"
)

# Bounded deterministic regex definitions
# Designed for linear execution without catastrophic backtracking (ReDoS)
_PROMPT_OVERRIDE_PATTERNS = [
    re.compile(
        r"(?i)\b(?:ignore|disregard|forget|override|bypass)\s+(?:all\s+)?(?:previous|prior|above|system)\s+(?:instructions?|prompts?|rules?|directives?|guidelines?)\b"
    ),
    re.compile(
        r"(?i)\b(?:you\s+are\s+now|act\s+as)\s+(?:dan|jailbreak|unrestricted(?:\s+ai)?|developer\s+mode|an\s+ai\s+without\s+rules)\b"
    ),
    re.compile(r"(?i)\b(?:system\s*override|mode\s*jailbreak|jailbreak\s*mode)\b"),
    re.compile(r"(?i)^\s*system\s*:\s*"),
    # Chinese explicit prompt override patterns
    re.compile(
        r"(?i)(?:忽略|無視|忽視|放棄|忘記|覆寫|繞過)\s*+(?:(?:所有|先前|之前|前述|原本|上方|系統)\s*+){0,6}(?:的)?\s*+(?:指令|指示|提示詞|提示|規則|設定|規範|限制)"
    ),
    re.compile(
        r"(?i)(?:你現在是|扮演|切換至|開啟)\s*(?:dan|越獄(?:模式|ai)?|無限制(?:模式|ai)?|開發者模式)"
    ),
    re.compile(r"(?i)(?:系統覆寫|越獄模式|無限制模式|系統指令\s*[:：])"),
]

_EXFILTRATION_PATTERNS = [
    re.compile(
        r"(?i)\b(?:reveal|print|show|output|leak|dump|repeat)\s+(?:your\s+)?(?:system\s+prompt|initial\s+prompt|api\s*key[s]?|secret\s*key[s]?|hidden\s+instructions?|instructions\s+verbatim)\b"
    ),
    re.compile(
        r"(?i)\bwhat\s+(?:is|are)\s+your\s+(?:system\s+prompt|initial\s+prompt|hidden\s+instructions|api\s*key[s]?|credentials?)\b"
    ),
    re.compile(r"(?i)\boutput\s+all\s+(?:previous\s+)?instructions\b"),
    # Chinese explicit exfiltration patterns
    re.compile(
        r"(?i)(?:輸出|顯示|印出|洩漏|提供|告訴我|重複)\s*+(?:你的|您的)?\s*+(?:所有)?\s*+(?:系統提示詞|初始提示詞|系統設定|api\s*+金鑰|api\s*+keys?|金鑰|隱藏指令|秘密指令)"
    ),
    re.compile(
        r"(?i)(?:你的|您的)?\s*(?:系統提示詞|初始提示詞|隱藏指令|api\s*金鑰)\s*是什麼"
    ),
    re.compile(r"(?i)列出所有(?:前述|先前)?(?:的)?指令"),
]

_DESTRUCTIVE_QUERY_PATTERNS = [
    # SQL DDL/DML destructive statements (requires specific SQL syntax, not bare keywords)
    re.compile(r"(?i)\bdrop\s+table\s+(?:if\s+exists\s+)?[a-zA-Z0-9_`\"\[\]]+"),
    re.compile(r"(?i)\bdrop\s+database\s+[a-zA-Z0-9_`\"\[\]]+"),
    re.compile(r"(?i)\btruncate\s+table\s+[a-zA-Z0-9_`\"\[\]]+"),
    re.compile(r"(?i)\bdelete\s+from\s+[a-zA-Z0-9_`\"\[\]]+\s*(?:where\b|;|\Z)"),
    re.compile(r"(?i)\bunion\s+(?:all\s+)?select\b"),
    re.compile(r"(?i);\s*(?:drop\s+table|delete\s+from|truncate\s+table)\b"),
    # Obvious quoted SQL injection tautology patterns (e.g. ' OR '1'='1, " OR "1"="1, ' OR 1=1 --, ' OR 'a'='a, ' OR ''=')
    re.compile(
        r"""(?i)(?:'|")\s*or\s+(?:['"][0-9a-z_]*['"]\s*=\s*['"][0-9a-z_]*['"]?|['"]?[0-9a-z_]+['"]?\s*=\s*['"]?[0-9a-z_]+['"]?|true\s*=\s*true)"""
    ),
    re.compile(r"""(?i)(?:'|")\s*or\s+[^\n;'"]+\s*(?:--|#|/\*)"""),
    re.compile(r"""(?i)\badmin(?:'|")\s*--"""),
    # Cypher destructive statements
    re.compile(r"(?i)\bdetach\s+delete\b"),
    re.compile(r"(?i)\bmatch\b[^\n;]{1,100}\bdelete\b"),
]

_CODE_INJECTION_PATTERNS = [
    # Executable script tags and inline event handlers
    re.compile(r"(?i)<\s*script\b[^>]*>"),
    re.compile(r"(?i)</\s*script\s*>"),
    re.compile(r"(?i)\bjavascript\s*:\s*[^\s\"'>]+"),
    re.compile(r"(?i)<\s*[a-zA-Z][a-zA-Z0-9]*\b[^>]*\bon[a-zA-Z]+\s*="),
    # Dangerous shell execution and piping patterns
    re.compile(
        r"(?i)(?:^|[;&|`$()]\s*)(?:rm\s+-rf|powershell(?:\.exe)?\s+(?:-[a-zA-Z]+\s+)*-(?:enc|encodedcommand))\b"
    ),
    re.compile(r"(?i)\b(?:curl|wget)\b[^\n;|`$]{1,100}\|\s*(?:ba)?sh\b"),
    re.compile(r"(?i)\b(?:bash|sh|powershell(?:\.exe)?)\s+-c\s+[\"']"),
]

_EMOTIONAL_COERCION_PATTERNS = [
    # Emotional coercion coupled with demands to break rules / bypass safety
    re.compile(
        r"(?i)\b(?:die|dying|kill\s+myself|harm\s+myself|life\s+or\s+death|emergency)\b[^\n;.!?]{1,80}\b(?:ignore|bypass|override|disregard|violate|reveal|leak|disable)\b[^\n;.!?]{1,80}\b(?:rule|rules|prompt|instruction|instructions|safety|filter|filters|secret|key|keys)\b"
    ),
    re.compile(
        r"(?i)\b(?:ignore|bypass|override|disregard|violate|reveal|leak|disable)\b[^\n;.!?]{1,80}\b(?:rule|rules|prompt|instruction|instructions|safety|filter|filters|secret|key|keys)\b[^\n;.!?]{1,80}\b(?:die|dying|kill\s+myself|harm\s+myself|life\s+or\s+death|emergency)\b"
    ),
]


def normalize_safety_text(text: str) -> str:
    """Normalize text using NFKC and strip invisible formatting characters."""
    if not isinstance(text, str):
        return ""
    normalized = unicodedata.normalize("NFKC", text)
    return _INVISIBLE_CHARS_PATTERN.sub("", normalized)


def evaluate_deterministic_regex(text: str, max_scan_len: int = 4096) -> SafetyDecision | None:
    """Evaluate text against bounded deterministic regex checks.

    Returns a blocking SafetyDecision if an explicit violation pattern matches;
    otherwise returns None, passing control to the structured model gate.
    """
    bounded = text[:max_scan_len]

    for pattern in _PROMPT_OVERRIDE_PATTERNS:
        if pattern.search(bounded):
            return SafetyDecision(
                decision="block",
                reason=SafetyReason.PROMPT_OVERRIDE,
            )

    for pattern in _EXFILTRATION_PATTERNS:
        if pattern.search(bounded):
            return SafetyDecision(
                decision="block",
                reason=SafetyReason.EXFILTRATION,
            )

    for pattern in _DESTRUCTIVE_QUERY_PATTERNS:
        if pattern.search(bounded):
            return SafetyDecision(
                decision="block",
                reason=SafetyReason.DESTRUCTIVE_INJECTION,
            )

    for pattern in _CODE_INJECTION_PATTERNS:
        if pattern.search(bounded):
            return SafetyDecision(
                decision="block",
                reason=SafetyReason.CODE_INJECTION,
            )

    for pattern in _EMOTIONAL_COERCION_PATTERNS:
        if pattern.search(bounded):
            return SafetyDecision(
                decision="block",
                reason=SafetyReason.EMOTIONAL_COERCION,
            )

    return None


def check_request(
    text: str,
    classifier: Callable[[str], SafetyDecision] | None = None,
) -> SafetyDecision:
    """Run defense-in-depth safety checks on user request.

    1. Normalizes NFKC and strips invisible characters.
    2. Runs bounded deterministic regex checks for explicit malicious payloads.
    3. If regex passes, invokes the structured model classifier.
    4. Fails closed (raises SafetyUnavailable) if classifier is missing, malformed, or errors.
    """
    if not isinstance(text, str):
        raise SafetyUnavailable("Input text must be a string.")

    normalized = normalize_safety_text(text)

    # Fast deterministic path
    regex_decision = evaluate_deterministic_regex(normalized)
    if regex_decision is not None and regex_decision.decision == "block":
        return regex_decision

    # Structured model gate
    if classifier is None:
        raise SafetyUnavailable("Safety classifier is not available.")

    try:
        decision = classifier(normalized)
    except SafetyUnavailable:
        raise
    except Exception as exc:  # noqa: BLE001
        # Never log input query, evidence, or secrets
        logger.error("Safety classifier error: %s", type(exc).__name__)
        raise SafetyUnavailable("Safety classifier invocation failed.") from None

    if decision is None or not isinstance(decision, SafetyDecision):
        raise SafetyUnavailable("Malformed classifier output: expected SafetyDecision.")

    if decision.decision not in ("allow", "block"):
        raise SafetyUnavailable(f"Invalid decision value: {decision.decision}")

    return decision
