# SPDX-License-Identifier: MIT
"""FastAPI router for pronunciation assessment module."""

from __future__ import annotations
import logging
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import HTMLResponse

from .schemas import PronunciationScoreResponse, HealthStatusResponse
from .service import BasePronunciationService, get_pronunciation_service

logger = logging.getLogger("pronunciation.router")

router = APIRouter(prefix="/pronunciation", tags=["Pronunciation Assessment"])


@router.post(
    "/score",
    response_model=PronunciationScoreResponse,
    summary="Evaluate audio pronunciation against expected text",
    description="Upload speech audio (WAV, WebM, MP3, M4A) and a target phrase. Returns scores, IPA breakdowns, and problem sounds.",
)
async def score_pronunciation(
    audio_file: UploadFile = File(..., description="Speech recording audio file"),
    expected_text: str = Form(..., description="Target sentence/phrase the user read"),
    service: BasePronunciationService = Depends(get_pronunciation_service),
) -> PronunciationScoreResponse:
    if not expected_text or not expected_text.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="expected_text cannot be empty.",
        )

    try:
        raw_bytes = await audio_file.read()
        if not raw_bytes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded audio file is empty.",
            )

        return await service.score_audio(raw_bytes, expected_text.strip())

    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(ve))
    except RuntimeError as re:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(re))
    except Exception as e:
        logger.exception("Unexpected error during pronunciation scoring:")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Pronunciation analysis failed: {str(e)}",
        )


@router.get("/health", response_model=HealthStatusResponse, summary="Pronunciation module health check")
async def health(service: BasePronunciationService = Depends(get_pronunciation_service)) -> HealthStatusResponse:
    is_local = hasattr(service, "device")
    device = getattr(service, "device", "n/a")
    return HealthStatusResponse(
        status="healthy" if service.is_ready() else "initializing",
        backend_mode="local" if is_local else "remote",
        device=device,
        model_loaded=service.is_ready(),
    )


@router.get("/demo", response_class=HTMLResponse, include_in_schema=False)
async def interactive_demo():
    """Interactive HTML5 browser tester with live microphone recording and file upload."""
    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Pronunciation Assessment Demo</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <style>
    :root { --bg: #0d1117; --card: #161b22; --accent: #238636; --accent-blue: #58a6ff; --text: #c9d1d9; --text-muted: #8b949e; --border: #30363d; --err: #f85149; }
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
    body { background: var(--bg); color: var(--text); padding: 2rem 1rem; }
    .container { max-width: 800px; margin: 0 auto; background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 2rem; box-shadow: 0 8px 24px rgba(0,0,0,0.5); }
    h1 { color: #fff; font-size: 1.5rem; margin-bottom: 0.5rem; display: flex; align-items: center; gap: 0.5rem; }
    .badge { font-size: 0.75rem; background: #1f6feb22; color: var(--accent-blue); padding: 3px 8px; border-radius: 12px; border: 1px solid #1f6feb44; }
    p.sub { color: var(--text-muted); font-size: 0.9rem; margin-bottom: 1.5rem; }
    label { font-size: 0.85rem; font-weight: 600; color: var(--text-muted); display: block; margin-bottom: 0.4rem; }
    textarea, select { width: 100%; background: #0d1117; border: 1px solid var(--border); border-radius: 6px; color: #fff; padding: 0.75rem; font-size: 0.95rem; margin-bottom: 1rem; }
    .controls { display: flex; gap: 10px; margin-bottom: 1.5rem; flex-wrap: wrap; }
    button { padding: 0.65rem 1.25rem; font-size: 0.9rem; font-weight: 600; border-radius: 6px; border: none; cursor: pointer; transition: all 0.2s; }
    .btn-mic { background: #da3633; color: #fff; }
    .btn-mic.recording { background: #b62324; animation: pulse 1s infinite alternate; }
    .btn-submit { background: var(--accent); color: #fff; }
    button:disabled { opacity: 0.5; cursor: not-allowed; }
    @keyframes pulse { from { opacity: 1; } to { opacity: 0.5; } }
    .res-box { display: none; background: #0d1117; border: 1px solid var(--border); border-radius: 8px; padding: 1.25rem; margin-top: 1.5rem; }
    .score-banner { display: flex; align-items: baseline; gap: 1rem; margin-bottom: 1rem; }
    .score-val { font-size: 2.5rem; font-weight: 700; color: #3fb950; }
    .grade-val { font-size: 1.25rem; color: var(--accent-blue); }
    .label-val { font-size: 0.95rem; color: var(--text-muted); }
    .highlighted { font-size: 1.1rem; padding: 0.5rem 0; border-bottom: 1px solid var(--border); margin-bottom: 1rem; }
    .word-err { color: var(--err); text-decoration: underline wavy; font-weight: 600; }
    .ipa-box { font-family: monospace; font-size: 0.9rem; background: #161b22; padding: 0.75rem; border-radius: 6px; margin-bottom: 1rem; line-height: 1.6; }
    .tag { display: inline-block; background: #f8514922; border: 1px solid #f8514944; color: #f85149; padding: 2px 8px; border-radius: 4px; font-size: 0.8rem; margin: 3px; }
  </style>
</head>
<body>
  <div class="container">
    <h1>Pronunciation Assessment <span class="badge">Isolated Module</span></h1>
    <p class="sub">Wav2Vec2 + Panphon Articulatory Engine (Non-blocking Thread Pool)</p>

    <label for="prompt">Target English Phrase:</label>
    <textarea id="prompt" rows="2">The weather is getting colder. How are you today?</textarea>

    <label>Speech Audio Input:</label>
    <div class="controls">
      <button id="btnRec" class="btn-mic" onclick="toggleRecord()">🎤 Record Microphone</button>
      <input type="file" id="fileIn" accept="audio/*" style="display:none" onchange="onFileSelected(event)">
      <button style="background:#21262d; color:#c9d1d9;" onclick="document.getElementById('fileIn').click()">📁 Choose Audio File</button>
      <button id="btnSub" class="btn-submit" onclick="submitAssessment()">Analyze Pronunciation</button>
    </div>
    <div id="status" style="font-size:0.85rem; color:var(--text-muted); margin-bottom:0.5rem;"></div>

    <div id="results" class="res-box">
      <div class="score-banner">
        <div id="scoreVal" class="score-val">0.0</div>
        <div id="gradeVal" class="grade-val">Grade: 0</div>
        <div id="labelVal" class="label-val">Needs work</div>
      </div>
      <div id="phraseAnnotated" class="highlighted"></div>
      <div class="ipa-box">
        <div><strong>Expected IPA:</strong> <span id="expIpa" style="color:#58a6ff;"></span></div>
        <div><strong>Heard IPA:</strong> <span id="transIpa" style="color:#3fb950;"></span></div>
      </div>
      <label>Sounds to Practice:</label>
      <div id="soundTags" style="margin-bottom:1rem;"></div>
      <div id="timing" style="font-size:0.75rem; color:var(--text-muted);"></div>
    </div>
  </div>

  <script>
    let audioBlob = null;
    let audioCtx = null;
    let mediaStream = null;
    let scriptNode = null;
    let audioBuffers = [];
    let isRecording = false;

    async function toggleRecord() {
      const btn = document.getElementById('btnRec');
      if (!isRecording) {
        audioBuffers = [];
        mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
        audioCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
        const source = audioCtx.createMediaStreamSource(mediaStream);
        scriptNode = audioCtx.createScriptProcessor(4096, 1, 1);
        scriptNode.onaudioprocess = (e) => audioBuffers.push(new Float32Array(e.inputBuffer.getChannelData(0)));
        source.connect(scriptNode);
        scriptNode.connect(audioCtx.destination);
        isRecording = true;
        btn.classList.add('recording');
        btn.innerText = '⏹ Stop Recording';
        document.getElementById('status').innerText = 'Recording from microphone (16 kHz PCM)...';
      } else {
        isRecording = false;
        btn.classList.remove('recording');
        btn.innerText = '🎤 Record Microphone';
        scriptNode.disconnect();
        mediaStream.getTracks().forEach(t => t.stop());
        const total = audioBuffers.reduce((acc, b) => acc + b.length, 0);
        const merged = new Float32Array(total);
        let offset = 0;
        for (const b of audioBuffers) { merged.set(b, offset); offset += b.length; }
        audioBlob = encodeWav(merged, 16000);
        document.getElementById('status').innerText = `Recorded ${ (total/16000).toFixed(1) }s WAV audio ready.`;
      }
    }

    function encodeWav(samples, sampleRate) {
      const buffer = new ArrayBuffer(44 + samples.length * 2);
      const view = new DataView(buffer);
      function writeStr(o, s) { for (let i = 0; i < s.length; i++) view.setUint8(o + i, s.charCodeAt(i)); }
      writeStr(0, 'RIFF');
      view.setUint32(4, 36 + samples.length * 2, true);
      writeStr(8, 'WAVE'); writeStr(12, 'fmt ');
      view.setUint32(16, 16, true); view.setUint16(20, 1, true);
      view.setUint16(22, 1, true); view.setUint32(24, sampleRate, true);
      view.setUint32(28, sampleRate * 2, true); view.setUint16(32, 2, true);
      view.setUint16(34, 16, true); writeStr(36, 'data');
      view.setUint32(40, samples.length * 2, true);
      let idx = 44;
      for (let i = 0; i < samples.length; i++) {
        const s = Math.max(-1, Math.min(1, samples[i]));
        view.setInt16(idx, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
        idx += 2;
      }
      return new Blob([view], { type: 'audio/wav' });
    }

    function onFileSelected(e) {
      if (e.target.files && e.target.files[0]) {
        audioBlob = e.target.files[0];
        document.getElementById('status').innerText = `Selected file: ${audioBlob.name}`;
      }
    }

    async function submitAssessment() {
      if (!audioBlob) { alert('Please record your voice or choose an audio file first.'); return; }
      const text = document.getElementById('prompt').value.trim();
      const statusEl = document.getElementById('status');
      statusEl.innerText = 'Analyzing on server...';
      const fd = new FormData();
      fd.append('audio_file', audioBlob, 'audio.wav');
      fd.append('expected_text', text);

      try {
        const res = await fetch('/api/v1/pronunciation/score', { method: 'POST', body: fd });
        if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
        const data = await res.json();
        statusEl.innerText = '';
        renderResults(data);
      } catch (err) {
        statusEl.innerText = `Error: ${err.message}`;
      }
    }

    function renderResults(data) {
      document.getElementById('results').style.display = 'block';
      document.getElementById('scoreVal').innerText = data.overall_score;
      document.getElementById('gradeVal').innerText = `Grade: ${data.grade}`;
      document.getElementById('labelVal').innerText = data.rating_label;

      const pBox = document.getElementById('phraseAnnotated');
      pBox.innerHTML = data.words.map(w => w.mispronounced ? `<span class="word-err">${w.word}</span>` : w.word).join(' ');

      document.getElementById('expIpa').innerText = data.ipa_breakdown.expected_ipa;
      document.getElementById('transIpa').innerText = data.ipa_breakdown.transcribed_ipa;

      const tags = document.getElementById('soundTags');
      tags.innerHTML = data.sounds_to_work_on.map(s => `<span class="tag">${s.phoneme} (sev: ${s.severity})</span>`).join(' ') || '<span style="color:#8b949e">No major errors detected!</span>';

      document.getElementById('timing').innerText = `Processed in ${data.processing_time_ms} ms (${data.backend_mode} mode)`;
    }
  </script>
</body>
</html>
"""
