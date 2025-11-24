function loadScoreChart(scores) {
    const ctx = document.getElementById("scoreChart");

    new Chart(ctx, {
        type: 'radar',
        data: {
            labels: ["Communication", "Clarity", "Depth", "Relevance"],
            datasets: [{
                label: 'Your Score',
                data: scores,
                borderColor: "cyan",
                backgroundColor: "rgba(0,255,255,0.2)"
            }]
        }
    });
}
