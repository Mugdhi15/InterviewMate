let mediaRecorder;
let audioChunks = [];
let audioContext;
let analyser;
let volumeAnimation;
let stream;

// UI elements
const startBtn = document.getElementById("startRec");
const stopBtn = document.getElementById("stopRec");
const audioInputHidden = document.getElementById("audio_input");
const volumeBars = document.getElementById("volume-bars");
const recStatus = document.getElementById("recording-status");
const submitBtn = document.getElementById("submit-btn"); // Get the submit button

// Disable stop and submit button initially
stopBtn.disabled = true;
submitBtn.disabled = true;

// Helper to enable the submit button after recording is ready
function enableSubmitButton() {
    submitBtn.disabled = false;
}

// Helper to disable the submit button (e.g., when a new recording starts)
function disableSubmitButton() {
    submitBtn.disabled = true;
}


// ------------------------------
// START RECORDING
// ------------------------------
startBtn.onclick = async () => {
    // Disable submit button if it was previously enabled
    disableSubmitButton(); 
    
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    mediaRecorder = new MediaRecorder(stream);

    audioChunks = [];

    mediaRecorder.ondataavailable = e => audioChunks.push(e.data);

    // Start visualizer
    startVolumeMeter(stream);

    mediaRecorder.start();

    recStatus.innerText = "🎙️ Listening...";
    startBtn.disabled = true;
    stopBtn.disabled = false;
};


// ------------------------------
// STOP RECORDING
// ------------------------------
stopBtn.onclick = async () => {
    mediaRecorder.stop();

    stopVolumeMeter();

    mediaRecorder.onstop = () => {
        const blob = new Blob(audioChunks, { type: "audio/webm" });

        // Convert to Base64 for Django
        const reader = new FileReader();
        reader.readAsDataURL(blob);
        reader.onloadend = () => {
            audioInputHidden.value = reader.result;
            
            // CRITICAL FIX: Enable the submit button ONLY after the audio is ready
            enableSubmitButton(); 
        };

        recStatus.innerText = "Recording stopped. Ready to submit.";
        startBtn.disabled = false;
        stopBtn.disabled = true;

        // Use WaveSurfer to show playback waveform
        loadWaveform(blob);
    };
};


// ------------------------------
// LIVE VOLUME METER LOGIC
// ------------------------------
function startVolumeMeter(stream) {
    audioContext = new AudioContext();
    const source = audioContext.createMediaStreamSource(stream);

    analyser = audioContext.createAnalyser();
    analyser.fftSize = 256;

    source.connect(analyser);

    const bufferLength = analyser.frequencyBinCount;
    const dataArray = new Uint8Array(bufferLength);

    // Generate 10 bars like ChatGPT mic
    volumeBars.innerHTML = "";
    for (let i = 0; i < 10; i++) {
        const bar = document.createElement("div");
        bar.className = "vol-bar";
        volumeBars.appendChild(bar);
    }

    const bars = volumeBars.children;

    function animate() {
        analyser.getByteFrequencyData(dataArray);
        let volume = dataArray.slice(0, 10);

        for (let i = 0; i < 10; i++) {
            let height = volume[i] / 2;
            bars[i].style.height = `${height}px`;
        }

        volumeAnimation = requestAnimationFrame(animate);
    }

    animate();
}

function stopVolumeMeter() {
    if (volumeAnimation) cancelAnimationFrame(volumeAnimation);
    if (audioContext) audioContext.close();
    volumeBars.innerHTML = "";
}