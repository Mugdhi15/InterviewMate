function loadWaveform(blob) {
    const container = document.getElementById("waveform");
    container.innerHTML = "";

    const wavesurfer = WaveSurfer.create({
        container: container,
        waveColor: "yellow",
        progressColor: "red",
        height: 80
    });

    wavesurfer.loadBlob(blob);
}
