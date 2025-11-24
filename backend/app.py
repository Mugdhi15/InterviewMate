# backend/app.py
import os
import tempfile
import json
import time
import threading
from typing import Optional
import uuid

from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Body
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

# OpenAI
from openai import OpenAI

# Whisper
from faster_whisper import WhisperModel

# TTS (optional)
import pyttsx3

# --- IMPORT CONFIG ---
from config import OPENAI_API_KEY, OPENAI_MODEL, OPENAI_TEMPERATURE, WHISPER_SIZE, WHISPER_DEVICE

# --- IMPORT INTERVIEW BRAIN LOGIC (RAG-enabled) ---
from interview_brain import (
    build_rag_index,
    build_rag_index_from_file,
    query_rag,
    generate_system_prompt,
    parse_llm_two_line_response,
    compute_confidence_score,
    detect_hesitation,
    choose_fallback_followup,
    build_transcript,
)

# ---------------------------------------

# Initialize OpenAI client
openai_client = OpenAI(api_key=OPENAI_API_KEY)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Whisper model once
whisper_model = WhisperModel(WHISPER_SIZE, device=WHISPER_DEVICE)

# Initialize simple TTS engine
engine = pyttsx3.init()

# ----------------------------
# SESSION MANAGEMENT (IN-MEMORY)
# ----------------------------
class InterviewSession(dict):
    """Lightweight session container.""" 
    pass

SESSIONS = {}

# ----------------------------
# Helper: call OpenAI API (simple wrapper)
# ----------------------------
def call_openai_llm(messages, temperature: float = OPENAI_TEMPERATURE, timeout: int = 120) -> str:
    """
    Call OpenAI API with the given messages.
    Returns the assistant's response content as a string.
    """
    try:
        response = openai_client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            temperature=temperature,
            timeout=timeout
        )
        # Compatibility: if shape differs, handle accordingly
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"OpenAI API error: {e}")
        raise HTTPException(status_code=500, detail=f"OpenAI API error: {str(e)}")

# ----------------------------
# Utility: compute max questions from mode string
# ----------------------------
def compute_max_questions(mode: str) -> int:
    """
    mode examples: "Quick|10", "Detailed|12", "Long|20"
    Fallback sensible defaults.
    """
    if not mode:
        return 12
    if "Quick" in mode:
        return 6
    if "Detailed" in mode:
        return 12
    if "Long" in mode:
        return 20
    # fallback: try to parse number after pipe
    try:
        parts = mode.split("|")
        if len(parts) > 1:
            return int(parts[1])
    except Exception:
        pass
    return 12

# ----------------------------
# Feedback generation helper (unchanged logic, kept strict as before)
# ----------------------------
def generate_feedback_for_session(session: InterviewSession) -> str:
    """
    Build a concise feedback summary using the full transcript.
    Returns a string feedback.
    """
    transcript = build_transcript(session.get("history", []))
    # Compose a compact prompt for final feedback
    prompt = (
        "You are a senior hiring manager who gives extremely direct, strict, no-sugarcoat feedback. "
        "Evaluate the transcript honestly and critically, based ONLY on evidence provided.\n\n"

        "Your output MUST follow this exact structure with headings in HTML bold tags:\n\n"

        "<b>Overall Score</b>\n"
        "- Give one strict line with a realistic score. Be blunt.\n\n"

        "<b>Strengths</b>\n"
        "- List 2–4 strengths that the candidate genuinely demonstrated.\n\n"

        "<b>Weaknesses</b>\n"
        "- List 4–6 specific shortcomings. No soft language. No exaggeration.\n\n"

        "<b>Actionable Recommendations</b>\n"
        "- Give 3–5 practical improvement steps.\n\n"

        "<b>Communication Skills</b>\n"
        "- Provide a strict 1–2 line assessment.\n\n"

        "<b>Technical Skills</b>\n"
        "- Provide a strict 1–2 line assessment.\n\n"

        "<b>Areas Needing Immediate Improvement (with improved sample answers)</b>\n"
        "- Rewrite the weakest points with better sample responses.\n\n"

        "<b>Final Recommendation</b>\n"
        "- Choose: Hire / No Hire / Maybe, with a short justification.\n\n"

        "STRICT RULES:\n"
        "- No fluff.\n"
        "- No praise unless strongly earned.\n"
        "- No long paragraphs. Use short, sharp statements.\n"
        "- Do NOT restate the transcript.\n"
        "- Output strictly in the structured format above.\n\n"

        f"Transcript:\n{transcript}\n\n"
        "Now generate the evaluation using the exact HTML-bold structure above."
    )

    messages = [
        {"role": "system", "content": "You summarize interview transcripts and produce concise feedback."},
        {"role": "user", "content": prompt}
    ]

    try:
        fb = call_openai_llm(messages, temperature=0.2, timeout=120)
    except Exception as e:
        print("Feedback generation failed:", e)
        fb = "Feedback generation failed. Try again later."
    return fb

# ----------------------------
# Transcription endpoint
# ----------------------------
@app.post("/transcribe_audio")
async def transcribe(audio: UploadFile = File(...)):
    """
    Accept audio bytes (wav/webm) and transcribe using faster-whisper.
    """
    content = await audio.read()
    # Write to temporary wav file
    suffix = ".wav"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        segments, info = whisper_model.transcribe(tmp_path, beam_size=5)
        text = " ".join([seg.text.strip() for seg in segments if seg.text.strip()])
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass

    return {"text": text}

# ----------------------------
# Start session
# ----------------------------
@app.post("/start_session")
async def start_session(
    role: str = Form(...),
    level: str = Form(...),
    focus: str = Form(...),
    mode: str = Form(...),
    jd_text: str = Form("")
):
    """
    Initialize a new interview session and return the first concise question.
    """
    session_id = str(uuid.uuid4())
    session = InterviewSession()
    session["session_id"] = session_id
    session["role"] = role
    session["level"] = level
    session["focus"] = focus
    session["mode"] = mode
    session["jd_text"] = jd_text
    session["history"] = []
    session["questions_asked"] = 0
    session["status"] = "in_progress"
    session["feedback"] = None

    SESSIONS[session_id] = session

    # Build RAG index for JD
    try:
        # If jd_text looks like a local path and exists, build from file, else build from text
        if jd_text and isinstance(jd_text, str) and os.path.exists(jd_text):
            build_rag_index_from_file(session_id, jd_text)
        else:
            build_rag_index(session_id, jd_text)
    except Exception as e:
        print("RAG build error:", e)
        # still continue with empty index
        build_rag_index(session_id, "")

    # Get jd chunks for initial question generation
    jd_chunks = query_rag(session_id, "initial question generation", top_k=3)

    # Build system prompt and request a single concise question
    system_prompt, _ = generate_system_prompt(role, level, focus, mode, jd_chunks, history_text="", last_user_text="")
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "START INTERVIEW. Provide ONLY a single, concise interview question (one sentence) tailored to the JD context above."}
    ]

    try:
        first_question = call_openai_llm(messages)
    except Exception as e:
        print("OpenAI start_session error:", e)
        raise HTTPException(status_code=500, detail="Failed to get first question from OpenAI API.")

    # Store first interviewer message
    session["history"].append({"speaker": "Interviewer", "text": first_question})
    session["questions_asked"] = 1
    session["current_question"] = first_question
    SESSIONS[session_id] = session

    # Non-blocking TTS for the first question
    def speak(q):
        try:
            engine.say(q)
            engine.runAndWait()
        except Exception:
            pass
    threading.Thread(target=speak, args=(first_question,), daemon=True).start()

    return JSONResponse(content={"session_id": session_id, "first_question": first_question, "status": "in_progress", "current_q_count": session["questions_asked"]})

# ----------------------------
# Submit response -> transcribe -> evaluate -> followup -> return JSON
# ----------------------------
@app.post("/submit_response")
async def submit_response(
    session_id: str = Form(...),
    audio: UploadFile = File(...)
):
    """
    Accepts a session_id and a recorded audio file, transcribes it, asks the LLM
    to evaluate and produce one follow-up question. If the session reaches the
    max question count, generate and return final feedback instead.
    """
    if session_id not in SESSIONS:
        raise HTTPException(status_code=404, detail="Session not found.")
    session = SESSIONS[session_id]

    # If interview already finished, return feedback immediately if present
    if session.get("status") == "finished":
        return JSONResponse(content={
            "feedback_ready": True,
            "feedback": session.get("feedback", "Feedback is being generated.")
        })

    # 1) Transcribe audio
    transcription_result = await transcribe(audio)
    user_text = transcription_result.get("text", "").strip()

    if not user_text:
        # Ask for repetition (no increment in question count)
        return JSONResponse(content={
            "user_text": "",
            "evaluation": "",
            "followup_question": "I didn't catch that — could you please repeat your answer?",
            "new_question": session.get("current_question", ""),
            "full_response": "",
            "current_q_count": session.get("questions_asked", 0),
            "feedback_ready": False,
            "confidence": 0.0,
            "offtopic": False,
            "hesitation_flag": True
        })

    # 2) Append user answer to history
    session["history"].append({"speaker": "User", "text": user_text})

    # 3) Retrieve JD chunks (RAG)
    jd_chunks = query_rag(session_id, user_text, top_k=4)

    # 4) Build LLM system prompt with JD chunks & history; get hesitation flag
    history_text = build_transcript(session["history"])
    system_prompt, hesitation_flag = generate_system_prompt(
        role=session["role"],
        level=session["level"],
        focus=session["focus"],
        mode=session["mode"],
        jd_chunks=jd_chunks,
        history_text=history_text,
        last_user_text=user_text
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_text}
    ]

    # 5) Call LLM to produce 2-line evaluation + follow-up
    full_response = ""
    evaluation = ""
    followup_question = None
    new_question = None
    confidence_score = 0.0
    offtopic = False

    try:
        full_response = call_openai_llm(messages)
    except Exception as e:
        print("OpenAI error during response generation:", e)
        followup_question = choose_fallback_followup()
        evaluation = "Short evaluation not available due to model error."
        full_response = f"{evaluation}\n{followup_question}"

    # 6) Parse LLM output into evaluation + followup
    if full_response:
        eval_line, follow_line = parse_llm_two_line_response(full_response)
        evaluation = eval_line or ""
        followup_question = follow_line or ""
        new_question = followup_question  # by default present the followup as next question

    # 7) Compute confidence score
    try:
        confidence_score = compute_confidence_score(user_text, session_id, jd_chunks)
    except Exception as e:
        print("Confidence computation error:", e)
        confidence_score = 0.0

    # 8) Detect off-topic by prefix token [OFFTOPIC] in evaluation
    if evaluation.strip().startswith("[OFFTOPIC]"):
        offtopic = True
        # remove marker for display
        evaluation = evaluation.replace("[OFFTOPIC]", "").strip()

    # 9) Update session state: if not off-topic, increment question count
    if not offtopic:
        session["history"].append({"speaker": "Interviewer", "text": full_response})
        session["questions_asked"] = session.get("questions_asked", 0) + 1
        session["current_question"] = new_question
        SESSIONS[session_id] = session
    else:
        # Off-topic: keep the history entry so it is traceable but do NOT increment
        session["history"].append({"speaker": "Interviewer", "text": full_response})
        # still update current question to model's follow-up (which will likely request re-answer or redirect)
        session["current_question"] = new_question
        SESSIONS[session_id] = session

    # 10) Determine max questions for this session
    max_q = compute_max_questions(session.get("mode", ""))

    # 11) If we've reached or exceeded the limit, generate final feedback and mark finished
    if session["questions_asked"] >= max_q:
        print(f"Session {session_id} reached max questions ({session['questions_asked']} >= {max_q}). Generating final feedback.")
        session["status"] = "finished"
        # Generate feedback synchronously (could be moved to background task)
        feedback_text = generate_feedback_for_session(session)
        session["feedback"] = feedback_text
        SESSIONS[session_id] = session

        return JSONResponse(content={
            "user_text": user_text,
            "evaluation": evaluation,
            "followup_question": followup_question,
            "new_question": None,
            "full_response": full_response,
            "current_q_count": session["questions_asked"],
            "feedback_ready": True,
            "feedback": feedback_text,
            "confidence": confidence_score,
            "offtopic": offtopic,
            "hesitation_flag": hesitation_flag
        })

    # 12) Speak the follow-up question (non-blocking) - speak only the question text (not evaluation)
    if new_question:
        def speak_q(q):
            try:
                engine.say(q)
                engine.runAndWait()
            except Exception:
                pass
        threading.Thread(target=speak_q, args=(new_question,), daemon=True).start()

    # 13) Normal response (still in-progress)
    resp_payload = {
        "user_text": user_text,
        "evaluation": evaluation,
        "followup_question": followup_question,
        "new_question": new_question,
        "full_response": full_response,
        "current_q_count": session.get("questions_asked", 0),
        "feedback_ready": False,
        "confidence": confidence_score,
        "offtopic": offtopic,
        "hesitation_flag": hesitation_flag
    }

    return JSONResponse(content=resp_payload)


# ----------------------------
# End interview -> generate feedback now (explicit)
# ----------------------------
@app.post("/end_interview")
async def end_interview(session_id: str = Body(..., embed=True)):
    """
    Explicitly end an interview and generate final feedback.
    Accepts: { "session_id": "<id>" } as JSON.
    """
    print("DEBUG: /end_interview CALLED for session", session_id)

    if session_id not in SESSIONS:
        raise HTTPException(status_code=404, detail="Interview session not found.")
    session = SESSIONS[session_id]

    if session.get("status") == "finished" and session.get("feedback"):
        return JSONResponse(content={"status": "finished", "message": "Feedback already generated.", "session_id": session_id})

    # Mark finished
    session["status"] = "finished"

    # Generate feedback (synchronously here; you can make this async/background)
    feedback_text = generate_feedback_for_session(session)
    session["feedback"] = feedback_text
    SESSIONS[session_id] = session

    return JSONResponse(content={"status": "finished", "message": "Feedback generated.", "session_id": session_id, "feedback": feedback_text})


# ----------------------------
# Retrieve generated feedback
# ----------------------------
@app.get("/get_feedback/{session_id}")
async def get_feedback(session_id: str):
    if session_id not in SESSIONS:
        raise HTTPException(status_code=404, detail="Not found.")
    session = SESSIONS[session_id]
    fb = session.get("feedback")
    if not fb:
        return JSONResponse(content={"feedback": "Generating... Please check back."})
    return JSONResponse(content={"feedback": fb})


# ----------------------------
# (Optional) simple health endpoint
# ----------------------------
@app.get("/health")
async def health():
    return JSONResponse(content={"status": "ok"})
