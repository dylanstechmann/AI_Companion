# AI Companion - Phase 2: 3D Avatar + Live Code Streaming

COST TIER: Top-tier model for avatar, Mid-tier for code streaming
COMPLEXITY: High (avatar), Medium (code streaming)
PREREQUISITES: Phase 1 + TTS working

---

## Task 1: 3D Avatar with Lip Sync and Emotion

### Goal
Render a 3D character avatar in the chat area that:
- Has idle animations (breathing, blinking, subtle movement)
- Lip-syncs to TTS audio output
- Shows emotion based on the AI's response sentiment
- Is customizable per character

### Technology Choices

**Option A: Three.js + VRM (Recommended)**
- Use @pixiv/three-vrm for VRM avatar loading
- VRM is the open standard for 3D avatars (used by VTubers)
- Free avatar creation at VRoid Studio (https://vroid.com/en/studio)
- Lip sync via Rhubarb Lip Sync or Oculus Viseme mapping

**Option B: Three.js + Ready Player Me**
- Ready Player Me provides an API for avatar creation
- Higher quality but requires API key and has usage limits
- GLB format with blend shapes for expressions

**Option C: Three.js + Custom GLB**
- Maximum control but requires 3D modeling skills
- Use Mixamo for animations

### Implementation Plan

#### New Files to Create:

**frontend/src/components/Avatar3D.jsx**
```
Purpose: React component that renders the 3D avatar
Dependencies: three, @react-three/fiber, @react-three/drei, @pixiv/three-vrm

Structure:
- Canvas wrapper with WebGL renderer
- VRM model loader
- Animation mixer for idle animations
- Lip sync controller (maps audio amplitude to mouth blend shapes)
- Emotion controller (maps sentiment to expression blend shapes)

Props:
- characterId: number (to load character-specific avatar)
- audioData: Float32Array (from TTS audio for lip sync)
- emotion: string ('neutral' | 'happy' | 'sad' | 'excited' | 'thinking')
- isStreaming: boolean (show thinking animation while AI generates)

Blend Shape Mapping (VRM standard):
- Viseme_aa, Viseme_E, Viseme_I, Viseme_O, Viseme_U (lip shapes)
- Joy, Angry, Sorrow, Fun (emotions)
- Blink, BlinkL, BlinkR (eye blinks)
```

**frontend/src/hooks/useAvatarAudio.js**
```
Purpose: Analyze TTS audio in real-time for lip sync

- Takes an AudioContext and audio source
- Uses AnalyserNode to get frequency data at 60fps
- Maps frequency bands to viseme intensities
- Returns current viseme weights as an object

Simple approach (amplitude-based):
- Low amplitude = mouth closed
- Medium amplitude = small open (Viseme_E)
- High amplitude = wide open (Viseme_aa)

Advanced approach (phoneme-based):
- Use Rhubarb Lip Sync as a backend service to pre-analyze TTS audio
- Returns timestamped phoneme sequence
- Frontend plays back phonemes in sync with audio
```

**frontend/src/hooks/useSentiment.js**
```
Purpose: Derive emotion from AI response text

Simple approach (keyword-based, runs in browser):
- Scan for emoji and keywords: "haha", "!", "?", "sorry", etc.
- Map to emotion enum
- No API cost

Advanced approach (LLM-based):
- Add a lightweight POST /api/sentiment endpoint
- Use a tiny model to classify: neutral/happy/sad/excited/thinking
- Cost: minimal (a few tokens per message)
```

#### Package Dependencies to Add:
```json
{
  "three": "^0.170.0",
  "@react-three/fiber": "^8.17.0",
  "@react-three/drei": "^9.114.0",
  "@pixiv/three-vrm": "^3.3.0"
}
```

#### Layout Changes:
- ChatArea currently fills the main content area
- Split into: Avatar panel (top or left) + Chat panel (bottom or right)
- On mobile: Avatar is a small floating circle above the chat
- On desktop: Avatar takes ~40% of the area, chat takes ~60%
- Add a toggle to show/hide the avatar

#### Avatar Assets:
- Store default VRM files in frontend/public/avatars/
- Each character can have a custom avatar_url in the database
- Provide 3 default avatars matching Greg, Tiffany, Friendly AI
- Free VRM avatars available from:
  - VRoid Hub (https://hub.vroid.com/)
  - Mixamo (for animations)

### Performance Considerations:
- Use requestAnimationFrame for the render loop (Three.js default)
- Limit to 30fps on mobile to save battery
- Use LOD (Level of Detail) for complex models
- Dispose of Three.js resources on unmount
- Consider OffscreenCanvas for worker-thread rendering

---

## Task 2: Live Code Streaming

### Goal
When the AI executes code via the sandbox, stream the output in real-time to the frontend instead of waiting for completion.

### Backend Changes:

**Modify backend/app/sandbox.py:**
```python
async def execute_streaming(self, language: str, code: str) -> AsyncGenerator[str, None]:
    """Execute code and yield stdout/stderr lines as they appear."""
    # Use asyncio.create_subprocess_exec instead of subprocess.run
    # Yield each line of output as it arrives
    # Still enforce timeout
    # Yield final {exit_code, execution_time} as last event
```

**Add new route in backend/app/main.py:**
```python
@app.post("/api/code/execute/stream", tags=["Tools"])
async def execute_code_streaming(request: CodeExecuteRequest):
    """Stream code execution output in real-time."""
    async def event_generator():
        async for line in sandbox.execute_streaming(request.language, request.code):
            yield f"data: {json.dumps({'output': line})}\n\n"
        yield "data: [DONE]\n\n"
    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

### Frontend Changes:

**Create frontend/src/components/CodePanel.jsx:**
```
Purpose: Terminal-like panel that shows live code execution output

Features:
- Dark terminal aesthetic (monospace font, green-on-black or custom theme)
- Auto-scroll as output arrives
- Show language badge (Python/JS)
- Show execution time and exit code
- Copy output button
- Expandable/collapsible within the chat

Renders inline within chat messages when the AI uses the execute_code tool.
```

**Update ChatArea.jsx:**
- When a tool_call for execute_code is detected in the stream, render a CodePanel
- The CodePanel connects to the streaming execution endpoint
- Shows a live terminal while code runs

---

## Acceptance Criteria

### Avatar:
- [ ] 3D avatar renders in the chat area
- [ ] Avatar has idle breathing/blinking animation
- [ ] Avatar lip-syncs to TTS audio
- [ ] Avatar shows at least 3 emotions (neutral, happy, thinking)
- [ ] Avatar can be toggled on/off
- [ ] Mobile: avatar renders as a small floating element
- [ ] Performance: maintains 30fps on mid-range hardware

### Code Streaming:
- [ ] Code execution output streams in real-time
- [ ] Terminal-style rendering within chat
- [ ] Shows exit code and execution time
- [ ] Timeout still enforced
- [ ] Copy output button works
