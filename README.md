## InterviewMate – AI-Powered Mock Interview Partner

RAG-Enhanced, Role-Aware, Voice-Driven Interview Simulator

- InterviewMate is an advanced AI-driven mock interview system designed to replicate real hiring-style conversations across different roles, levels, and company expectations.

- It provides dynamic questions, natural interviewer follow-ups, JD-aware evaluation, and strict final feedback—powered by RAG, Whisper speech-to-text, and OpenAI reasoning models.

- The agent adapts to the user’s speaking style, detects hesitation, handles off-topic answers gracefully, and maintains a highly professional, structured interview flow.

## 🚀 Key Features

**🎙️ Voice-Based Interviewing**
- Users answer by speaking.
- Whisper (via Faster-Whisper) converts speech to highly accurate text.
- Automatically detects fillers (“uh”, “umm”, “I think…”) to adjust evaluation.

**🧠 JD-Driven, Role-Specific Questioning (RAG-Powered)**
- Uses FAISS + OpenAI embeddings to extract relevant requirements from the Job Description.
- Interview questions dynamically adjust to: 
    Role (e.g., SWE, Data Analyst, PM)
    Level (Intern or senior lead)
    Technical focus (backend, ML, system design, etc.)
    No hard-coded questions — all LLM-generated in real-time.

 **🤖 Agentic Behaviors** 
- Recognizes irrelevant answers and redirects politely.
- Adjusts tone if the user hesitates or lacks clarity.
- Asks deep follow-ups based on semantic relevance and the JD.

**📊 Structured Final Feedback**  
- Not sugar-coated — hiring-manager style.
- Includes:
    - Strengths, weaknesses  
    - Actionable improvements  
    - Communication & technical skill rating  
    - Final hire recommendation  
    - Sample improved answers

## ⚙️ Tools & Technologies Used

| Category | Tool / Library | Purpose | Why This Was Used |
|---------|----------------|---------|-------------------|
| **Backend Framework** | **FastAPI** | Handles real-time LLM interaction, audio processing pipeline, and RAG operations. | Ultra-fast, async-first, perfect for low-latency conversational agents. |
| **Frontend Framework** | **Django** | Provides the web UI, forms, views, and session handling. | Stable, secure, and excellent for structured multi-page applications. |
| **LLM Provider** | **OpenAI GPT-4.1 / GPT-4o** | Generates role-based questions, evaluates answers, and creates feedback. | High reasoning accuracy, strong natural interview behavior. |
| **Embedding Model** | **text-embedding-3-small** | Converts job descriptions + user answers into vectors for similarity search. | Fastest and most cost-efficient embedding model from OpenAI. |
| **Vector Database** | **FAISS** | Retrieves the most relevant JD chunks for RAG-based question generation. | Enables highly accurate JD-driven questioning with ultra-low latency. |
| **Speech-to-Text** | **Faster-Whisper** | Transcribes user audio with high speed and accuracy. | Lightweight, real-time, and CPU-optimized transcription engine. |
| **Text-to-Speech (TTS)** | **pyttsx3** | Reads out the interviewer’s questions. | Offline, fast, and easy to integrate. |
| **JavaScript (Frontend)** | Recorder.js, WaveSurfer.js | Records user voice, displays waveform, handles UI interactions. | Enables real-time audio capture directly in browser. |
| **Styling / UI** | Custom CSS | Creates a dark, modern, interview-themed interface. | Fully customizable, lightweight, and visually clean. |
| **Package/Environment** | Python 3.12, pip, virtualenv | Core environment for backend logic. | Ensures clean reproducibility and package isolation. |

## ⚙️ How to Run the Project

### 📌 Prerequisites
- Python 3.10+
- FFmpeg installed
- OpenAI API Key configured in `backend/config.py`

---

### **1️⃣ Start the FastAPI Backend**
```bash
cd backend
uvicorn app:app --host 127.0.0.1 --port 8001 --reload
bash```

### **2️⃣ Start the Django Frontend**
```bash
cd frontend
python manage.py runserver

###🌐 Local Server URLs

Frontend: http://127.0.0.1:8000

Backend: http://127.0.0.1:8001


INITIALIZATION                    INTERVIEW LOOP (Repeats)                           COMPLETION
━━━━━━━━━━━━━━                    ━━━━━━━━━━━━━━━━━━━━━━━━━━                           ━━━━━━━━━━━━

┌──────┐    ┌────────┐    ┌──────────┐    ┌─────────┐    ┌────────┐    ┌──────────┐    ┌─────────┐    ┌────────┐
│ User │───▶│ Django │───▶│ FastAPI  │───▶│ Browser │───▶│ Record │───▶│  Django  │───▶│ FastAPI │───▶│Browser │
│ Form │    │ /start │    │ Build RAG│    │ Show Q  │    │ Audio  │    │ /submit  │    │ Process │    │ Update │
└──────┘    └────────┘    │ Gen Q1   │    └─────────┘    └────────┘    └──────────┘    └────┬────┘    └───┬────┘
                          └──────────┘                                                        │              │
                                                                                              │              │
                                                     ┌────────────────────────────────────────┘              │
                                                     │                                                       │
                                                     ▼                                                       │
                                         ┌──────────────────────────┐                                       │
                                         │   FastAPI Processing:    │                                       │
                                         │   • Whisper (transcribe) │                                       │
                                         │   • FAISS (RAG search)   │                          ┌────────────┘
                                         │   • Detect behavior      │                          │
                                         │   • LLM evaluation       │                          │
                                         └──────────────────────────┘                          ▼
                                                                                         ┌──────────┐
                                         ┌──────────────────────────┐                   │ Max Q or │
                                         │    DECISION POINT        │                   │ User End?│
                                         │  Continue? ◀─────────────┼───────────────────┤          │
                                         │  Yes → Loop Back         │         NO        └─────┬────┘
                                         │  No → Final Feedback     │                         │ YES
                                         └──────────────────────────┘                         ▼
                                                                                         ┌──────────┐
                                                                                         │ FastAPI  │
                                                                                         │ Generate │
                                                                                         │ Report   │
                                                                                         └─────┬────┘
                                                                                               │
                                                                                               ▼
                                                                                         ┌──────────┐
                                                                                         │  Django  │
                                                                                         │/feedback │
                                                                                         └─────┬────┘
                                                                                               │
                                                                                               ▼
                                                                                         ┌──────────┐
                                                                                         │ Display  │
                                                                                         │ Results  │
                                                                                         └──────────┘

## Edge case Handling
<table>
  <thead>
    <tr>
      <th>Category</th>
      <th>Behavior</th>
      <th>Agent Response</th>
    </tr>
  </thead>

  <tbody>

    <tr>
      <td><b>Role-Based Persona</b></td>
      <td>Questions adapt to role, level, JD context via RAG.</td>
      <td>“Based on the JD, could you explain how you'd handle X?”</td>
    </tr>

    <tr>
      <td><b>Hesitant User</b></td>
      <td>Detects fillers/pauses & encourages clarity.</td>
      <td>“Take your time—walk me through your thought process.”</td>
    </tr>

    <tr>
      <td><b>Off-Topic User</b></td>
      <td>Marks evaluation with <code>[OFFTOPIC]</code> and redirects politely.</td>
      <td>“Interesting, but let’s come back to the main question—can you clarify Y?”</td>
    </tr>

    <tr>
      <td><b>Chatty / Story-Drift</b></td>
      <td>Acknowledges story, gently redirects.</td>
      <td>“Thanks for sharing—now focusing on the question, what was your key decision?”</td>
    </tr>

    <tr>
      <td><b>Confused User</b></td>
      <td>Provides minimal guidance options without leaking answers.</td>
      <td>“To narrow it down, you can talk about tools, strategy, or constraints.”</td>
    </tr>

    <tr>
      <td><b>Weak / Short Responses</b></td>
      <td>Low confidence score → asks for expansion.</td>
      <td>“Could you add a concrete example to support that?”</td>
    </tr>

    <tr>
      <td><b>Capability Boundary</b></td>
      <td>Handles requests outside interview domain.</td>
      <td>“Let’s stay focused on your interview—tell me about your last project.”</td>
    </tr>

  </tbody>
</table>
