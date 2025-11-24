//
// interview.js — Updated to consume backend signals (confidence, hesitation, offtopic)
//

function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== "") {
        const cookies = document.cookie.split(";");
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + "=")) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

// --- Global Session State ---
let SESSION_ID = document.getElementById('session_id_input')?.value || null;
const SESSION_MODE_STRING = document.getElementById('session_mode_input')?.value || "Detailed|30";

// Determine max questions
const MAX_TIME_MINUTES = parseInt(SESSION_MODE_STRING.split('|')[1]);
let MAX_QUESTIONS = SESSION_MODE_STRING.includes("Quick") ? 6 :
                    SESSION_MODE_STRING.includes("Detailed") ? 12 :
                    SESSION_MODE_STRING.includes("Long") ? 20 : 12;

// We'll show counts from server, but init to 1 (first question already displayed)
let CURRENT_QUESTION_COUNT = 1;

// =============================
// SPEECH SYNTHESIS MANAGEMENT
// =============================
let speechActive = false;
const speakBtn = document.getElementById('speak-btn');
let currentUtterance = null;

function resetSpeechButton() {
    try { speechSynthesis.cancel(); } catch (e) {}
    speechActive = false;
    speakBtn.textContent = "🔊 Speak Question";
}

function getQuestionText() {
    const fullText = document.getElementById('question-box').innerText.trim();
    const lines = fullText.split('\n');
    return lines[lines.length - 1].trim();
}

function speakQuestion() {
    resetSpeechButton();
    const text = getQuestionText();
    if (!text) return;
    currentUtterance = new SpeechSynthesisUtterance(text);
    currentUtterance.rate = 1.0;
    currentUtterance.onstart = () => {
        speechActive = true;
        speakBtn.textContent = "⏸ Pause Speech";
    };
    currentUtterance.onend = () => {
        speechActive = false;
        speakBtn.textContent = "🔊 Speak Question";
    };
    speechSynthesis.speak(currentUtterance);
}

function toggleSpeech() {
    if (speechSynthesis.speaking && !speechSynthesis.paused) {
        speechSynthesis.pause();
        speakBtn.textContent = "▶️ Resume Speech";
    } 
    else if (speechSynthesis.paused) {
        speechSynthesis.resume();
        speakBtn.textContent = "⏸ Pause Speech";
    } 
    else {
        speakQuestion();
    }
}

// =============================
// CONFIDENCE METER UI
// =============================
function showConfidence(confidence) {
    // confidence is 0..1
    const fill = document.getElementById("confidence-fill");
    const label = document.getElementById("confidence-label");
    if (!fill || label == null) return;
    const pct = Math.round((confidence || 0) * 100);
    fill.style.width = pct + "%";

    // color: red (<40), yellow (40-70), green (>70)
    if (pct < 40) fill.style.background = "#ff5c5c";
    else if (pct < 70) fill.style.background = "#ffd166";
    else fill.style.background = "#00ffcc";

    label.textContent = `${pct}% relevance to JD`;
}

// =============================
// PROGRESS (SYNC with server count)
// =============================
function setProgressFromServer(currentCount) {
    const bar = document.getElementById("progress-bar");
    const countDisplay = document.getElementById("questions-count");
    if (!bar || !countDisplay) return;
    CURRENT_QUESTION_COUNT = currentCount || CURRENT_QUESTION_COUNT;
    const percent = Math.min(100, Math.round((CURRENT_QUESTION_COUNT / MAX_QUESTIONS) * 100));
    bar.style.width = percent + "%";
    countDisplay.textContent = CURRENT_QUESTION_COUNT;
    // If reached max, auto trigger end flow
    if (CURRENT_QUESTION_COUNT >= MAX_QUESTIONS) {
        // Ask user and redirect to feedback (or auto end)
        alert("Maximum questions reached — generating feedback...");
        endInterview();
    }
}

// =============================
// TIMER INITIALIZATION
// =============================
function initializeTimer() {
    const duration = MAX_TIME_MINUTES * 60;
    if (typeof startTimer === "function") {
        startTimer(duration);
    }
}

// =============================
// UI Helpers for interviewer messages
// =============================
function showInterviewerNote(text) {
    const node = document.getElementById("interviewer-note");
    if (!node) return;
    if (!text) { node.style.display = "none"; node.innerHTML = ""; return; }
    node.style.display = "block";
    node.innerHTML = `<strong>Interviewer:</strong> ${escapeHtml(text)}`;
}

function showHesitationWarning(show, text) {
    const node = document.getElementById("hesitation-warning");
    if (!node) return;
    if (!show) { node.style.display = "none"; node.innerHTML = ""; return; }
    node.style.display = "block";
    node.innerHTML = `<em>Take your time — it sounded like you hesitated. Tip: structure answer with situation → action → result.</em>`;
}

function showOfftopicBox(show, text) {
    const node = document.getElementById("offtopic-box");
    if (!node) return;
    if (!show) { node.style.display = "none"; node.innerHTML = ""; return; }
    node.style.display = "block";
    node.innerHTML = `<strong>Note:</strong> ${escapeHtml(text || "That was a bit off-topic — please briefly summarize the key point and tie it back to the question.")}`;
}

function escapeHtml(unsafe) {
    return String(unsafe)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
}

// =============================
// SUBMIT ANSWER LOGIC
// =============================
async function handleFormSubmit(event) {
    event.preventDefault();

    const submitBtn = document.getElementById('submit-btn');
    const questionP = document.querySelector('#question-box p');
    const audioData = document.getElementById('audio_input').value;

    if (!audioData) { alert("Please record your answer first."); return; }

    submitBtn.disabled = true;
    submitBtn.textContent = "Processing...";
    try { speechSynthesis.cancel(); } catch (e) {}

    const fd = new FormData();
    fd.append("session_id", SESSION_ID);
    fd.append("audio_data", audioData);

    let data;
    try {
        const res = await fetch("/submit_answer/", { method: "POST", body: fd });
        data = await res.json();
    } catch (e) {
        questionP.innerHTML = `<span style="color:red">Error: ${e.message}</span>`;
        submitBtn.disabled = false;
        submitBtn.textContent = "Submit Answer & Get Follow-up";
        return;
    }

    // Error handling from server
    if (data.error) {
        showInterviewerNote(data.error);
        submitBtn.disabled = false;
        submitBtn.textContent = "Submit Answer & Get Follow-up";
        return;
    }

    // Show evaluation if present
    if (data.evaluation) {
        showInterviewerNote(data.evaluation);
    } else {
        showInterviewerNote(""); // clear
    }

    // Show hesitation hint
    if (data.hesitation_flag) {
        showHesitationWarning(true);
    } else {
        showHesitationWarning(false);
    }

    // Update confidence meter
    if (typeof data.confidence !== "undefined") {
        showConfidence(data.confidence);
    }

    // Off-topic handling
    if (data.offtopic) {
        showOfftopicBox(true, "That reply seemed off-topic. Please answer briefly focusing on the job requirement.");
        // update question box with the follow-up or redirecting prompt
        if (data.new_question) {
            questionP.innerHTML = `<span class='interview-evaluation'>${data.evaluation || ""}</span><br><br><span>${data.new_question}</span>`;
        }
        // Do not advance server-side count (server doesn't increment), but keep UI counts from server
        setProgressFromServer(data.current_q_count || CURRENT_QUESTION_COUNT);
        // Auto-speak short redirect question
        setTimeout(speakQuestion, 400);
        submitBtn.disabled = false;
        submitBtn.textContent = "Submit Answer & Get Follow-up";
        return;
    } else {
        showOfftopicBox(false);
    }

    // If final feedback ready, redirect to feedback page
    if (data.feedback_ready) {
        // maybe server returned feedback inline
        if (data.feedback) {
            // store and redirect to /feedback/<id> which Django view expects
            window.location.href = `/feedback/${SESSION_ID}`;
            return;
        } else {
            // fallback redirect
            window.location.href = `/feedback/${SESSION_ID}`;
            return;
        }
    }

    // Normal new question (in-progress)
    if (data.new_question) {
        questionP.innerHTML = `
            <span class='interview-evaluation'>${data.evaluation || ""}</span><br><br>
            <span>${data.new_question}</span>
        `;
        // Update counts using server-sent count (safer)
        setProgressFromServer(data.current_q_count || (CURRENT_QUESTION_COUNT + 1));
        resetSpeechButton();
        setTimeout(speakQuestion, 300);
    } else {
        // fallback: no new question provided
        showInterviewerNote("Interviewer did not provide a follow-up — try rephrasing or ending the interview.");
    }

    submitBtn.disabled = false;
    submitBtn.textContent = "Submit Answer";
}

// =====================================
// END INTERVIEW — Full Fixed Version
// =====================================
function endInterview() {
    const endBtn = document.getElementById("endInterviewBtn");

    // Disable button + show processing state
    endBtn.disabled = true;
    endBtn.textContent = "Processing...";

    fetch("/end_interview/", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": getCookie("csrftoken")
        },
        body: JSON.stringify({ session_id: SESSION_ID })
    })
    .then(res => res.json())
    .then(data => {
        console.log("End Interview Response:", data);

        // Case 1: Django returns redirect explicitly
        if (data.redirect) {
            window.location.href = data.redirect;
            return;
        }

        // Case 2: Django sends session_id back
        if (data.session_id) {
            window.location.href = `/feedback/${data.session_id}`;
            return;
        }

        // Fallback redirect
        window.location.href = `/feedback/${SESSION_ID}`;
    })
    .catch(err => {
        console.error("End Interview Error:", err);

        alert("Could not end interview. Try again.");

        // Restore button state on failure
        endBtn.disabled = false;
        endBtn.textContent = "End Interview & Get Feedback";
    });
}


// =============================
// INIT
// =============================
document.addEventListener("DOMContentLoaded", () => {

    console.log("Interview.js Loaded ✔");

    // hook speak button
    const sbtn = document.getElementById("speak-btn");
    if (sbtn) sbtn.addEventListener("click", toggleSpeech);

    // AUTO TIMER
    initializeTimer();

    // set initial UI counts (first question shown)
    setProgressFromServer(CURRENT_QUESTION_COUNT);

    // speak initial question
    setTimeout(speakQuestion, 500);

    // END button
    const endBtn = document.getElementById("endInterviewBtn");
    if (endBtn) {
        endBtn.addEventListener("click", function () { endInterview(); });
    } else {
        console.error("End interview button not found.");
    }

    // ensure submit button is enabled only when audio exists (recorder.js should set audio_input and enable button)
    // recorder.js must set document.getElementById('audio_input').value and enable submit button when done.
});
