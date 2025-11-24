// function startTimer(seconds) {
//     let remaining = seconds;

//     const el = document.getElementById("timer");
//     el.innerText = remaining;

//     const interval = setInterval(() => {
//         remaining--;
//         el.innerText = remaining;

//         if (remaining <= 0) {
//             clearInterval(interval);
//         }
//     }, 1000);
// }

// timer.js

let timerInterval;
let totalSeconds = 0;

function formatTime(totalSeconds) {
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;
    return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
}

function startTimer(durationInSeconds) {
    totalSeconds = durationInSeconds;
    const timerDisplay = document.getElementById('timer');
    
    // Clear any existing interval
    if (timerInterval) {
        clearInterval(timerInterval);
    }

    timerInterval = setInterval(() => {
        if (totalSeconds <= 0) {
            clearInterval(timerInterval);
            timerDisplay.textContent = "Time's Up!";
            // Auto-trigger feedback when time runs out
            if (typeof endInterview === 'function') {
                endInterview();
            }
            return;
        }

        totalSeconds--;
        timerDisplay.textContent = formatTime(totalSeconds);
    }, 1000);
}

// Global exposure (important if not using modules)
window.startTimer = startTimer;