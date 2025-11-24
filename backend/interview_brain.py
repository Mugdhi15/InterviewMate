# backend/interview_brain.py
"""
Interview brain (RAG-based, JD-driven) for the InterviewBot.

Features:
- FAISS in-memory RAG over Job Description text (JD-only).
- OpenAI embeddings (text-embedding-3-small).
- Dynamic system prompt generation using retrieved JD context + form inputs.
- Hesitation detection (ASR text heuristics).
- Optional semantic similarity confidence score (0..1).
- Parse LLM 2-line outputs (evaluation + exactly one follow-up).
- Minimal, stable API so existing backend flow requires few changes.

Important usage notes:
- This module keeps RAG state in-process in RAG_STORE (session-scoped).
- Call build_rag_index(session_id, jd_text) at start_session.
- On each submit_response, call query_rag(session_id, user_text, top_k)
  and pass returned jd_chunks + rest to generate_system_prompt(...).
- The LLM is expected to follow the strict 2-line output format. If it
  marks an answer as off-topic, instruct it to prefix Line 1 with [OFFTOPIC].
"""

from typing import List, Tuple, Dict, Optional
import os
import re
import math
import uuid
import numpy as np
import faiss
from openai import OpenAI
import logging
import random

try:
    from config import OPENAI_API_KEY, EMBEDDING_MODEL
except Exception:
    # Fallback defaults (user should provide OPENAI_API_KEY in config)
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", None)
    EMBEDDING_MODEL = "text-embedding-3-small"

if OPENAI_API_KEY is None:
    raise RuntimeError("Please set OPENAI_API_KEY in config.py or environment variables.")

# --- Initialize OpenAI client
client = OpenAI(api_key=OPENAI_API_KEY)

# --- In-memory RAG store (session_id -> { index, chunks, dim })
RAG_STORE: Dict[str, Dict] = {}

# ----------------------------
# Utilities: text chunking
# ----------------------------
def _chunk_text(text: str, chunk_size_words: int = 150, overlap_words: int = 30) -> List[str]:
    """
    Split text into overlapping chunks by words.
    chunk_size_words: approx words per chunk (tunable)
    """
    if not text:
        return []
    words = text.strip().split()
    if len(words) <= chunk_size_words:
        return [" ".join(words)]
    chunks = []
    i = 0
    while i < len(words):
        chunk = words[i:i + chunk_size_words]
        chunks.append(" ".join(chunk))
        i += (chunk_size_words - overlap_words)
    # filter tiny
    return [c.strip() for c in chunks if len(c.split()) > 10]

# ----------------------------
# Embeddings (OpenAI)
# ----------------------------
def _embed_texts(texts: List[str]) -> List[List[float]]:
    """
    Return embeddings list (each is list[float]) using the configured model.
    """
    if not texts:
        return []
    # Using client.embeddings.create
    resp = client.embeddings.create(model=EMBEDDING_MODEL, input=texts)
    embeddings = [item.embedding for item in resp.data]
    return embeddings

# ----------------------------
# Build FAISS index for a session JD
# ----------------------------
def build_rag_index(session_id: str, jd_text: str) -> None:
    """
    Build (or rebuild) a FAISS index for a session's JD text.
    Stores result in RAG_STORE[session_id] = {"index": index, "chunks": chunks, "dim": dim}
    """
    # sanitize
    jd_text = (jd_text or "").strip()
    if not jd_text:
        # store empty placeholder
        RAG_STORE[session_id] = {"index": None, "chunks": [], "dim": 0}
        return

    chunks = _chunk_text(jd_text, chunk_size_words=150, overlap_words=30)
    if not chunks:
        RAG_STORE[session_id] = {"index": None, "chunks": [], "dim": 0}
        return

    embeddings = _embed_texts(chunks)
    dim = len(embeddings[0])
    arr = np.array(embeddings, dtype="float32")

    index = faiss.IndexFlatL2(dim)
    index.add(arr)

    RAG_STORE[session_id] = {"index": index, "chunks": chunks, "dim": dim}

# Optional helper to build index from a plain text file path
def build_rag_index_from_file(session_id: str, file_path: str) -> None:
    if not file_path or not os.path.exists(file_path):
        build_rag_index(session_id, "")
        return
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            txt = f.read()
    except Exception:
        txt = ""
    build_rag_index(session_id, txt)

# ----------------------------
# Query RAG index
# ----------------------------
def query_rag(session_id: str, query: str, top_k: int = 3) -> List[str]:
    """
    Query the session's FAISS index and return top_k relevant JD chunks.
    If no index exists, returns [].
    """
    store = RAG_STORE.get(session_id)
    if not store or not store.get("index"):
        return []
    index = store["index"]
    chunks = store["chunks"]
    if not chunks:
        return []

    q_embs = _embed_texts([query])
    if not q_embs:
        return []
    q_vec = np.array(q_embs, dtype="float32").reshape(1, -1)
    k = min(top_k, len(chunks))
    D, I = index.search(q_vec, k)
    ids = I[0].tolist()
    out = []
    for idx in ids:
        if idx is not None and 0 <= idx < len(chunks):
            out.append(chunks[idx])
    return out

# ----------------------------
# Hesitation detection
# ----------------------------
_HESITATION_PATTERNS = [
    r"\bum\b", r"\buh\b", r"\bumm?\b", r"\bwell\b", r"\bmaybe\b",
    r"\bi think\b", r"\bnot sure\b", r"\bkind of\b", r"\bsort of\b",
    r"\bI guess\b", r"\bperhaps\b", r"\b\d+\.\.\.\b"
]
_hes_re = re.compile("|".join(_HESITATION_PATTERNS), flags=re.IGNORECASE)

def detect_hesitation(text: str) -> bool:
    """
    Heuristic check for hesitation/filler tokens in transcribed text.
    Returns True if likely hesitation detected.
    """
    if not text or len(text.strip()) == 0:
        return True  # empty -> treat as hesitation/low-confidence
    return bool(_hes_re.search(text))

# ----------------------------
# Simple semantic similarity confidence
# ----------------------------
def _mean_embedding_of_chunks(chunks: List[str]) -> Optional[np.ndarray]:
    if not chunks:
        return None
    emb = _embed_texts(chunks)
    if not emb:
        return None
    arr = np.array(emb, dtype="float32")
    return np.mean(arr, axis=0)

def _cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    if a is None or b is None:
        return 0.0
    denom = (np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)

def compute_confidence_score(user_text: str, session_id: str, jd_chunks: List[str]) -> float:
    """
    Returns confidence in [0,1] that the user's answer is JD-relevant and detailed.
    Computation:
      - semantic similarity between user_text embedding and mean JD chunks embedding (0..1)
      - penalties for hesitation / very short answer
    """
    if not user_text:
        return 0.0
    # embeddings
    try:
        user_emb = _embed_texts([user_text])[0]
    except Exception:
        # if embedding fails, fallback heuristic
        user_emb = None

    mean_jd_emb = _mean_embedding_of_chunks(jd_chunks) if jd_chunks else None
    sim = _cosine_sim(np.array(user_emb) if user_emb is not None else None, mean_jd_emb) if user_emb is not None else 0.0

    # normalize sim from [-1,1] to [0,1]
    sim_norm = max(0.0, min(1.0, (sim + 1) / 2))

    # base confidence is sim_norm
    conf = sim_norm

    # penalty for hesitation
    if detect_hesitation(user_text):
        conf *= 0.6

    # penalty for very short answer (less than 8 words)
    word_count = len(user_text.split())
    if word_count < 8:
        conf *= 0.7

    # clamp to 0..1
    conf = max(0.0, min(1.0, conf))
    return conf

# ----------------------------
# System prompt generator
# ----------------------------
CORE_PROMPT_TEMPLATE = """
You are a natural, human-like interviewer. Use the provided Job Description context EXACTLY
to generate questions and brief evaluations tailored to the role.

Job Description (relevant excerpts):
{jd_context}

Interview instructions (MUST follow exactly):
- OUTPUT MUST BE EXACTLY 2 LINES:
  Line 1: Short evaluation (1-2 sentences). If the candidate's answer is unrelated to the JD context, prefix Line 1 with the token: [OFFTOPIC]
  Line 2: EXACTLY ONE follow-up question (one sentence) that is directly tied to the candidate's last answer and the JD context.

- If HESITATION_FLAG is True: The evaluation should briefly acknowledge hesitation (one short sentence),
  and the follow-up should encourage clarity and ask for a specific detail.

- If the candidate drifted into a long side-story, acknowledge it politely and then redirect (do not cut them off).
- NEVER provide sample answers.
- Keep all responses concise, natural, and interview-like.

Interview History:
{history}

Now produce only the two-line interviewer response.
"""

def generate_system_prompt(role: str,
                           level: str,
                           focus: str,
                           mode: str,
                           jd_chunks: List[str],
                           history_text: str = "",
                           last_user_text: str = "") -> Tuple[str, bool]:
    """
    Build the strict system prompt using retrieved JD chunks.
    Returns (prompt_text, hesitation_flag)
    """
    jd_context = "\n\n".join(jd_chunks) if jd_chunks else "(no JD context available)"
    hesitation_flag = detect_hesitation(last_user_text or "")

    # minimal role/level mention in prompt, but not a hard-coded persona that overrides JD
    role_info = f"{role or 'Software Engineer'} ({level or 'Mid-level'})"

    history = history_text or "(no prior context)"
    prompt = CORE_PROMPT_TEMPLATE.format(jd_context=jd_context, history=history)

    # append contextual flags (so the LLM can see them)
    prompt += f"\nHESITATION_FLAG: {str(hesitation_flag)}\nROLE: {role_info}\nFOCUS: {focus}\nMODE: {mode}\n"

    return prompt, hesitation_flag

# ----------------------------
# Parse expected two-line output
# ----------------------------
def parse_llm_two_line_response(text: str) -> Tuple[str, str]:
    """
    Given model output, parse into (evaluation, followup_question).
    If model returns >2 lines, take first non-empty as evaluation, last line containing '?' as followup if present,
    otherwise second line.
    Returns empty strings on failure.
    """
    if not text:
        return "", ""
    # Normalize and split
    lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
    if not lines:
        return "", ""
    if len(lines) == 1:
        # Single line -> treat as follow-up question (no evaluation)
        return "", lines[0]
    # else 2+ lines: first = eval, second (or last question-like) = followup
    eval_line = lines[0]
    follow = None
    # find last line that ends with '?'
    for ln in reversed(lines[1:]):
        if ln.endswith("?") or "?" in ln:
            follow = ln
            break
    if follow is None:
        # fallback: use second line
        follow = lines[1] if len(lines) > 1 else ""
    return eval_line, follow

# ----------------------------
# Fallback follow-up
# ----------------------------
FALLBACKS = [
    "Can you provide a concrete example related to this job requirement?",
    "Can you briefly quantify the impact of your action?",
    "Could you explain one technical decision in more detail?"
]

def choose_fallback_followup() -> str:
    return random.choice(FALLBACKS)

# ----------------------------
# Transcript builder (compatible)
# ----------------------------
def build_transcript(session_history: List[Dict]) -> str:
    """
    Produce a textual transcript from session history list of dicts {'speaker','text'}.
    """
    out_lines = []
    for turn in session_history:
        sp = turn.get("speaker", "Unknown")
        txt = turn.get("text", "").strip()
        out_lines.append(f"({sp}): {txt}")
    return "\n".join(out_lines)

# ----------------------------
# Exports
# ----------------------------
__all__ = [
    "build_rag_index",
    "build_rag_index_from_file",
    "query_rag",
    "generate_system_prompt",
    "detect_hesitation",
    "compute_confidence_score",
    "parse_llm_two_line_response",
    "choose_fallback_followup",
    "build_transcript",
    "RAG_STORE"
]
