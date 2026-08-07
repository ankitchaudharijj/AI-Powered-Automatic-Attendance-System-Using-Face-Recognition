/**
 * static/js/webcam.js
 * ====================
 * Drives the "Capture Face" wizard (templates/admin/student_capture.html).
 *
 * Flow:
 *   1. Request webcam access.
 *   2. On "Start Capture", grab a frame every ~350ms, send it to the
 *      server (CAPTURE_FRAME_URL). The backend validates exactly one
 *      face is visible before saving it to the dataset folder.
 *   3. Stop automatically once REQUIRED_SAMPLES images are captured.
 *   4. "Generate Face Encodings" button becomes active, which calls
 *      GENERATE_ENCODINGS_URL to build the 128-d encodings and persist
 *      them to the database.
 *
 * Expects the following globals to be defined inline by the template:
 *   STUDENT_ID, REQUIRED_SAMPLES, CAPTURE_FRAME_URL, GENERATE_ENCODINGS_URL
 */

(() => {
    const video = document.getElementById("webcamVideo");
    const canvas = document.getElementById("captureCanvas");
    const startBtn = document.getElementById("startCaptureBtn");
    const stopBtn = document.getElementById("stopCaptureBtn");
    const generateBtn = document.getElementById("generateEncodingsBtn");
    const progressBar = document.getElementById("captureProgressBar");
    const progressText = document.getElementById("captureProgressText");
    const overlayMsg = document.getElementById("faceOverlayMsg");
    const statusMsg = document.getElementById("captureStatusMsg");

    let mediaStream = null;
    let captureIntervalId = null;
    let capturedCount = parseInt(progressText.textContent.split("/")[0].trim(), 10) || 0;
    let isCapturing = false;

    async function startWebcam() {
        try {
            mediaStream = await navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480 }, audio: false });
            video.srcObject = mediaStream;
        } catch (err) {
            showStatus("Could not access the webcam. Please grant camera permission and reload.", "danger");
            console.error(err);
        }
    }

    function stopWebcam() {
        if (mediaStream) {
            mediaStream.getTracks().forEach((track) => track.stop());
            mediaStream = null;
        }
    }

    function captureFrameAsBase64() {
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        const ctx = canvas.getContext("2d");
        // Un-mirror before sending, since the <video> preview is mirrored via CSS only.
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
        return canvas.toDataURL("image/jpeg", 0.85);
    }

    async function sendFrame() {
        if (!isCapturing || capturedCount >= REQUIRED_SAMPLES) return;

        const imageData = captureFrameAsBase64();
        try {
            const response = await fetch(CAPTURE_FRAME_URL, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ image: imageData }),
            });
            const result = await response.json();

            if (result.success) {
                capturedCount = result.count;
                updateProgress();
                overlayMsg.textContent = "";
                overlayMsg.classList.remove("show");
            } else {
                overlayMsg.textContent = result.message || "Adjust your position...";
                overlayMsg.classList.add("show");
            }

            if (capturedCount >= REQUIRED_SAMPLES) {
                finishCapture();
            }
        } catch (err) {
            console.error("Frame capture failed:", err);
        }
    }

    function updateProgress() {
        const percent = Math.min(100, Math.round((capturedCount / REQUIRED_SAMPLES) * 100));
        progressBar.style.width = `${percent}%`;
        progressText.textContent = `${capturedCount} / ${REQUIRED_SAMPLES}`;
    }

    function finishCapture() {
        isCapturing = false;
        clearInterval(captureIntervalId);
        startBtn.classList.add("d-none");
        stopBtn.classList.add("d-none");
        generateBtn.classList.remove("d-none");
        showStatus("All images captured! Click 'Generate Face Encodings' to finish enrollment.", "success");
    }

    function showStatus(message, type) {
        statusMsg.innerHTML = `<div class="alert alert-${type}">${message}</div>`;
    }

    startBtn.addEventListener("click", async () => {
        if (!mediaStream) await startWebcam();
        isCapturing = true;
        startBtn.classList.add("d-none");
        stopBtn.classList.remove("d-none");
        captureIntervalId = setInterval(sendFrame, 350);
    });

    stopBtn.addEventListener("click", () => {
        isCapturing = false;
        clearInterval(captureIntervalId);
        startBtn.classList.remove("d-none");
        stopBtn.classList.add("d-none");
    });

    generateBtn.addEventListener("click", async () => {
        generateBtn.disabled = true;
        generateBtn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Generating...';

        try {
            const response = await fetch(GENERATE_ENCODINGS_URL, { method: "POST" });
            const result = await response.json();

            if (result.success) {
                showStatus(result.message, "success");
                stopWebcam();
                setTimeout(() => {
                    window.location.href = "/students/";
                }, 1500);
            } else {
                showStatus(result.message, "danger");
                generateBtn.disabled = false;
                generateBtn.innerHTML = '<i class="bi bi-cpu-fill"></i> Generate Face Encodings';
            }
        } catch (err) {
            showStatus("Failed to generate encodings. Please try again.", "danger");
            generateBtn.disabled = false;
        }
    });

    // Kick things off
    startWebcam();
    updateProgress();
    window.addEventListener("beforeunload", stopWebcam);
})();
