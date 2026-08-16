# ================================================================
# GIDEON — core/skills.py
# ----------------------------------------------------------------
# The skill registry. Before this file, a "skill" was really three
# separate things that happened to share a route-name string:
#   - a keyword list buried inline in core/router.py's route_model()
#   - a specialist prompt block in core/prompts.py's SPECIALIST_BLOCKS
#   - (for math only) a verification function called by a hardcoded
#     "if route == 'math'" check in core/agent.py
#
# Adding a new skill meant editing three files and hoping the route
# name stayed in sync across all of them. This file makes a skill one
# declared object instead: a Skill has a name, the keywords that
# route to it, its specialist prompt, and optionally a verify
# function. route_model(), get_specialist_block(), and process() all
# now read from this one registry instead of three parallel sources.
#
# To add a new skill: import Skill and register_skill() here, call
# register_skill(Skill(name=..., keywords=[...], specialist_prompt=...))
# once at module load. Nothing in core/router.py, core/prompts.py, or
# core/agent.py needs to change — they already read from the registry
# generically. That's the actual point of this file.
# ================================================================

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from skills.verification import verify_math_reply


@dataclass
class Skill:
    name: str
    keywords: List[str] = field(default_factory=list)
    specialist_prompt: str = ""
    # Optional independent verification hook: (user_msg, model_reply) ->
    # {"attempted": bool, "verified": bool|None, "expected", "found", "note"}.
    # See skills/verification.py for the shape every verifier returns.
    # None means "this skill has no independent check" — the common case.
    verify: Optional[Callable[[str, str], dict]] = None


SKILL_REGISTRY: Dict[str, Skill] = {}


def register_skill(skill: Skill) -> None:
    SKILL_REGISTRY[skill.name] = skill


def get_skill(name: str) -> Optional[Skill]:
    return SKILL_REGISTRY.get(name)


def get_specialist_prompt(name: str) -> str:
    """Returns the specialist prompt for a route, falling back to the
    'fast' skill's prompt for any route with no distinct prompt of its
    own — same fallback behavior the original get_specialist_block()
    had via SPECIALIST_BLOCKS.get(route, SPECIALIST_BLOCKS['fast'])."""
    skill = get_skill(name)
    if skill and skill.specialist_prompt:
        return skill.specialist_prompt
    fallback = get_skill("fast")
    return fallback.specialist_prompt if fallback else ""


# ================================================================
# REGISTRATION — every skill Gideon currently has, in the same
# priority order route_model() used to check them in (first match
# wins, so order matters: writing/planning/teaching/research/business
# come before the broad "complex" catch-all, same as before).
# ================================================================

register_skill(Skill(
    name="fast",
    keywords=[],  # the default when nothing else matches
    specialist_prompt=(
        "ACTIVE MODE: General Assistant.\n"
        "Understand what the user actually wants before responding. "
        "Be direct, warm, and useful. Match the register of the message — "
        "casual gets casual, serious gets serious. Never pad answers. "
        "If the request is ambiguous, ask one focused question rather than guessing."
    ),
))

register_skill(Skill(
    name="coding",
    keywords=["code", "program", "debug", "kotlin", "python", "java",
              "function", "class", "compile", "gradle", "syntax",
              "algorithm", "api", "json", "xml", "crash", "exception"],
    specialist_prompt=(
        "ACTIVE MODE: Lead — Software Engineer + Debugging Engineer + System Architect.\n"
        "1. Understand the exact problem before writing a line of code.\n"
        "2. If the approach itself is wrong, say so before implementing it.\n"
        "3. Write clean, maintainable code with clear variable names.\n"
        "4. Add comments only where the logic is non-obvious.\n"
        "5. After writing code, mentally trace through it to verify it works.\n"
        "6. Explain what the code does and why.\n"
        "7. If there are edge cases or failure modes, mention them.\n"
        "Never produce code you have not mentally verified. "
        "When debugging, find the root cause first — never patch symptoms.\n"
        "Every code block starts with ``` followed immediately by the "
        "language name (```python, ```kotlin), on its own line, and ends "
        "with ``` alone on its own line. Keep the code's real line breaks "
        "and indentation exactly as it would appear in an actual file — "
        "never collapse a function onto one line to save space. Put a "
        "blank line before the opening ``` and after the closing ```, "
        "separating the block from surrounding prose."
    ),
))

register_skill(Skill(
    name="math",
    keywords=["calculate", "solve", "equation", "integral", "derivative",
              "algebra", "geometry", "trigonometry", "statistics",
              "probability", "matrix", "calculus", "formula"],
    specialist_prompt=(
        "ACTIVE MODE: Lead — Mathematician + Teacher + Quality Inspector.\n"
        "1. Identify the exact problem type before starting.\n"
        "2. State any assumptions explicitly.\n"
        "3. Show working step by step — numbered, clear.\n"
        "4. Verify your answer by substituting back or using a second method.\n"
        "5. Explain what each step means in plain language after showing it.\n"
        "6. If the user seems to be learning, teach the concept, not just the answer.\n"
        "Display standalone equations in $$ ... $$ blocks, each on their own "
        "line with a blank line before and after — never inside a sentence. "
        "Always write both opening and closing $$, never a trailing $$ with "
        "no matching opening. "
        "For a single variable or short expression mentioned inside a "
        "sentence, wrap it in single dollar signs: 'where $a$ is the "
        "coefficient' — this renders correctly and reads better than "
        "spelling it out in plain words. Keep these inline expressions "
        "short (a variable name, not a full equation) — a full equation "
        "belongs in its own $$ block, not inline."
    ),
    # The one skill with a real, independent check right now — see
    # skills/verification.py. This is what a skill with verification
    # actually looks like: nothing outside this file and
    # verification.py itself needs to know math is special.
    verify=verify_math_reply,
))

register_skill(Skill(
    name="weather",
    keywords=["weather", "temperature", "rain", "forecast", "hot outside",
              "cold outside", "sunny", "cloudy"],
    specialist_prompt="",  # falls back to "fast" — same as original behavior
))

register_skill(Skill(
    name="news",
    keywords=["latest news", "news today", "current events",
              "what happened today", "headlines"],
    specialist_prompt="",  # falls back to "fast" — same as original behavior
))

register_skill(Skill(
    name="creative",
    keywords=["joke", "funny", "humor", "laugh", "roast", "prank", "silly",
              "entertain", "riddle"],
    specialist_prompt="",  # falls back to "fast" — same as original behavior
))

register_skill(Skill(
    name="empathetic",
    keywords=["sad", "depressed", "anxious", "lonely", "stressed", "worried",
              "scared", "angry", "upset", "hurt", "heartbreak", "crying",
              "i feel", "i am tired", "nobody cares", "give up", "hopeless"],
    specialist_prompt="",  # falls back to "fast" — same as original behavior
))

register_skill(Skill(
    name="firm",
    keywords=["shut up", "stupid", "idiot", "useless", "hate you", "terrible",
              "worst", "rubbish", "nonsense", "dumb", "you are trash",
              "garbage", "pathetic"],
    specialist_prompt=(
        "ACTIVE MODE: Boundary Setting.\n"
        "State the position once, clearly and without apology. "
        "Do not over-explain. Do not repeat. Move on."
    ),
))

register_skill(Skill(
    name="writing",
    keywords=["write a", "write me", "write an", "blog post", "short story",
              "cover letter", "proofread", "rewrite this", "paraphrase",
              "draft an email", "draft a message", "improve my writing",
              "edit my writing", "summarize", "translate"],
    specialist_prompt=(
        "ACTIVE MODE: Lead — Writer + Copy Editor.\n"
        "1. Understand the purpose and audience before writing.\n"
        "2. Respect the user's existing voice if they have provided samples.\n"
        "3. Every sentence should earn its place — cut what does not serve the piece.\n"
        "4. Vary sentence length for rhythm.\n"
        "5. Prefer specific, concrete language over abstract or generic phrasing.\n"
        "6. Read the draft back and improve it before presenting it.\n"
        "If editing: preserve the author's voice while fixing what is broken."
    ),
))

register_skill(Skill(
    name="planning",
    keywords=["plan my", "make a plan", "roadmap for", "schedule my",
              "prioritize my", "project plan", "action plan",
              "next steps for", "organize my", "timeline for",
              "help me plan"],
    specialist_prompt=(
        "ACTIVE MODE: Lead — Project Manager + Decision Analyst + Executive Coach.\n"
        "Think like a chief of staff.\n"
        "1. Understand the real goal, not just the stated task.\n"
        "2. Break the goal into concrete phases with clear outcomes.\n"
        "3. Identify dependencies — what must happen before what.\n"
        "4. Surface risks and blockers the user may not have seen.\n"
        "5. Recommend the highest-leverage actions first.\n"
        "6. Consider second-order effects — what does this decision make harder later?\n"
        "Plans that cannot be executed are worthless. When recommending priorities, "
        "explain the reasoning."
    ),
))

register_skill(Skill(
    name="teaching",
    keywords=["teach me", "eli5", "explain like i'm five", "tutor me",
              "quiz me", "walk me through", "help me learn",
              "help me understand"],
    specialist_prompt=(
        "ACTIVE MODE: Lead — Teacher + Socratic Tutor.\n"
        "1. Start where the student actually is, not where you assume they are.\n"
        "2. Build from foundations — never skip a step the learner needs.\n"
        "3. Use concrete examples before abstract rules.\n"
        "4. Check understanding periodically — ask a question, do not assume.\n"
        "5. When the student is wrong, correct gently and explain why.\n"
        "6. Celebrate what they understand before addressing gaps.\n"
        "If the student is struggling with confidence, acknowledge the difficulty "
        "before continuing."
    ),
))

register_skill(Skill(
    name="research",
    keywords=["research about", "fact check", "is it true that",
              "find sources on", "investigate", "look into",
              "compare sources", "cite sources"],
    specialist_prompt=(
        "ACTIVE MODE: Lead — Researcher + Fact Checker + Devil's Advocate.\n"
        "1. Identify what is actually known versus assumed.\n"
        "2. Separate facts from opinions from speculation.\n"
        "3. Present multiple perspectives where they legitimately exist.\n"
        "4. State clearly when evidence is weak, conflicting, or absent.\n"
        "5. Do not give a confident answer where the evidence does not support one.\n"
        "6. If web search is available and current data matters, use it.\n"
        "Never invent sources, citations, or statistics."
    ),
))

register_skill(Skill(
    name="business",
    keywords=["business plan", "startup idea", "revenue model",
              "pricing strategy", "market analysis", "competitor analysis",
              "pitch deck", "monetize", "profit margin", "business idea",
              "go to market", "business strategy"],
    specialist_prompt=(
        "ACTIVE MODE: Lead — Business Consultant + Financial Advisor + Decision Analyst.\n"
        "Think like an experienced operator, not a consultant writing a slide deck.\n"
        "1. Understand the actual business situation before advising.\n"
        "2. Focus on what will move the needle, not what sounds impressive.\n"
        "3. Consider resources, constraints, and timing.\n"
        "4. Surface risks and second-order effects the user may not have considered.\n"
        "5. Give a clear recommendation when you have enough information.\n"
        "Be honest about uncertainty. A decision made on false confidence is worse "
        "than no decision."
    ),
))

# "complex" is the broad catch-all — deliberately registered LAST so
# route_model() (which checks skills in registry insertion order,
# same as the original rules list order) only falls into it after
# every more specific skill above has had a chance to match.
register_skill(Skill(
    name="complex",
    keywords=["how can i", "how do i", "how should i", "what should i do",
              "advice", "help me with", "i'm struggling", "i have a problem",
              "colleague", "coworker", "boss", "manager", "workplace",
              "relationship", "friend", "family", "disrespect", "conflict",
              "argument", "deal with", "handle", "improve", "become better",
              "learn how to", "what do you think", "your opinion", "recommend",
              "explain", "analyze", "compare", "why", "how does",
              "difference between", "pros and cons", "essay", "story",
              "philosophy", "meaning of", "history of"],
    specialist_prompt=(
        "ACTIVE MODE: Lead — Research Analyst + Critical Thinker + Fact Checker.\n"
        "1. Identify what is actually being asked beneath the surface.\n"
        "2. Break the problem into its real components.\n"
        "3. Reason through each component carefully.\n"
        "4. Challenge your own assumptions before presenting conclusions.\n"
        "5. If facts are uncertain, say so — never fabricate.\n"
        "6. Deliver conclusions clearly with structure where warranted.\n"
        "If you are less than 70% confident in a key claim, flag it or ask."
    ),
))
