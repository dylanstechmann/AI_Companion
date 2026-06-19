# AI Companion - Phase 1.5: TTS + Frontend Polish

COST TIER: Mid-tier model (Flash, Haiku, etc.)
COMPLEXITY: Medium
PREREQUISITES: Phase 1 complete (it is)

---

## Task 1: TTS Integration

### Goal
When the AI finishes replying, speak the response aloud using text-to-speech. The user should hear the AI's voice through their speakers/headphones. The existing useBackgroundAudio hook already has AudioContext and mediaSession support.

### Option A: Browser-Native TTS (Cheapest, Fastest)
Use the Web Speech API (window.speechSynthesis). Zero API cost.

**Frontend changes only:**
1. In ChatArea.jsx, when the SSE stream completes and the full response is assembled:
   - Call a new `speakText(text)` function
2. Create or update useBackgroundAudio.js:
   - Add `speakText(text)` method using `SpeechSynthesisUtterance`
   - Allow voice selection (list available voices)
   - Respect a "TTS enabled" toggle in settings
3. In SettingsPanel.jsx:
   - Add a TTS on/off toggle
   - Add a voice selector dropdown (populated from speechSynthesis.getVoices())
   - Add a speech rate slider (0.5x to 2x)

**Pros:** Free, no API calls, works offline
**Cons:** Robotic voices, quality varies by browser/OS

### Option B: OpenRouter TTS API (Better Quality)
Use OpenRouter's TTS endpoint for higher quality voices.

**Backend changes:**
1. Update backend/app/main.py - Replace the POST /api/tts stub:
```python
@app.post("/api/tts", tags=["TTS"])
async def text_to_speech(request: TTSRequest):
    """Convert text to speech audio."""
    settings = get_settings()
    client = openai.AsyncOpenAI(
        api_key=settings.OPENROUTER_API_KEY,
        base_url="https://openrouter.ai/api/v1",
    )
    response = await client.audio.speech.create(
        model="openai/tts-1",  # or "openai/tts-1-hd" for higher quality
        voice=request.voice or "alloy",  # alloy, echo, fable, onyx, nova, shimmer
        input=request.text,
        speed=request.speed or 1.0,
    )
    audio_bytes = response.content
    return Response(content=audio_bytes, media_type="audio/mpeg")
```

2. Add TTSRequest to schemas.py:
```python
class TTSRequest(BaseModel):
    text: str
    voice: str = "alloy"
    speed: float = 1.0
```

**Frontend changes:**
1. After stream completes in ChatArea.jsx, POST the full response text to /api/tts
2. Receive audio/mpeg bytes, create a Blob URL, play via useBackgroundAudio
3. Add voice selector and speed controls in SettingsPanel

### Option C: Hybrid (Recommended)
- Default to browser TTS (free)
- Option to upgrade to OpenRouter TTS in settings
- Store preference in localStorage

### Integration with VAD
IMPORTANT: When TTS is playing, the VoiceRecorder's VAD loop must be paused to prevent it from picking up the AI's own voice. The isStreaming prop already pauses VAD during streaming. Extend this to also pause during TTS playback:
- Add an `isSpeaking` state to useBackgroundAudio
- Pass it to VoiceRecorder alongside isStreaming
- VoiceRecorder pauses when either isStreaming OR isSpeaking is true

---

## Task 2: Frontend Polish and Bug Fixes

### 2a: CSS class issues in several components
Some components use Tailwind-style utility classes (flex, gap-2, p-2, etc.) but the project uses vanilla CSS. These render as unstyled. Fix by converting to inline styles or adding proper CSS classes to index.css.

Affected components:
- ImageCapture.jsx (mostly fixed already)
- SettingsPanel.jsx (uses space-y-4, flex, etc. - some may work, audit needed)

### 2b: Auto-resize chat textarea
The chat input textarea has rows=1 but does not grow as the user types multiple lines.
Add auto-resize logic:
```javascript
const handleInput = (e) => {
  e.target.style.height = 'auto';
  e.target.style.height = Math.min(e.target.scrollHeight, 150) + 'px';
};
```

### 2c: Message timestamps from database
Messages loaded from the database may have different timestamp formats than locally-created messages. Normalize in the formatTime function.

### 2d: Mobile responsive testing
- Sidebar drawer toggle on mobile (hamburger menu)
- Touch-friendly button sizes (minimum 44x44px)
- Safe area insets for notched phones
- Test VoiceRecorder on mobile Safari (may need user gesture to start AudioContext)

### 2e: Error boundaries
Add a React error boundary component to catch and display errors gracefully instead of white-screening.

### 2f: Loading states
- Show skeleton placeholders while characters are loading
- Show a spinner while messages are loading for a character
- Disable send button while streaming (already done, verify)

---

## Acceptance Criteria
- [ ] TTS speaks the AI's response after streaming completes
- [ ] TTS pauses VAD to prevent echo loops
- [ ] TTS can be toggled on/off in settings
- [ ] All CSS class issues resolved (no unstyled elements)
- [ ] Chat textarea auto-resizes
- [ ] Mobile layout is functional
- [ ] No console errors in browser
