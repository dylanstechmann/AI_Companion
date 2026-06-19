# Avatar Implementation Roadmap for AI Companion

Complete checklist and step-by-step guide to implement the 3D avatar system.

## Phase 1: Preparation & Asset Creation

### Step 1: Create Avatar Models (Week 1)
- [ ] Use VRoid Studio or Blender to create avatars for Greg, Tiffany, and Friendly AI
  - [ ] Download VRoid Studio from https://vroid.com/en/studio
  - [ ] Create or customize 3D character models
  - [ ] Export as VRM format
  - [ ] Save to `frontend/public/avatars/[character_name].vrm`

OR if using Blender:
- [ ] Follow the Blender Avatar Creation Guide (docs/AVATAR_CREATION_GUIDE.md)
- [ ] Create base human model with proper rigging
- [ ] Add blend shapes for expressions and visemes
- [ ] Create simple idle animations
- [ ] Export as VRM or GLB

### Step 2: Prepare Avatar Assets
- [ ] Create directory: `frontend/public/avatars/`
- [ ] Copy VRM files to the avatars directory
- [ ] Test files can be loaded (run local server and check in DevTools)

---

## Phase 2: Backend Updates

### Step 3: Database Schema Migration
- [ ] Review database schema requirements (docs/AVATAR_DATABASE_SCHEMA.md)
- [ ] Create migration file or manually update SQLite schema
- [ ] Add columns:
  - [ ] `avatar_url` (TEXT)
  - [ ] `avatar_format` (TEXT)
  - [ ] `has_lip_sync` (BOOLEAN)
  - [ ] `has_emotions` (BOOLEAN)
  - [ ] `idle_animation` (TEXT)

Run migration:
```bash
cd backend
python -m alembic upgrade head
# OR for SQLite, run the SQL directly in your DB tool
```

### Step 4: Update Backend Models
- [ ] Update `backend/app/models.py` with new Character fields
- [ ] Make sure Pydantic schema matches database schema
- [ ] Add validation for avatar_format ('vrm', 'glb', 'gltf')

### Step 5: Update Character Routes
- [ ] Verify `/api/characters` returns avatar fields
- [ ] Verify `/api/characters/{id}` returns avatar fields
- [ ] Ensure `/api/characters` POST accepts avatar fields
- [ ] Ensure `/api/characters/{id}` PUT accepts avatar fields

### Step 6: Seed Default Characters
- [ ] Update seeding scripts to include avatar URLs
- [ ] Default to `/avatars/[character_name].vrm`
- [ ] Verify characters are created with avatar URLs

Test backend:
```bash
docker compose up -d
curl http://localhost:8000/api/characters
# Should include avatar_url, avatar_format, has_lip_sync, has_emotions
```

---

## Phase 3: Frontend Components

### Step 7: Install Required Dependencies
```bash
cd frontend
npm install three
npm install @react-three/fiber
npm install @react-three/drei
```

Note: We're using raw Three.js instead of React Three Fiber for better control over avatar rendering and animation.

- [ ] Verify dependencies installed
- [ ] Check `frontend/package.json` has updated versions

### Step 8: Create Avatar Component
- [ ] Copy `Avatar3D.jsx` from this guide to `frontend/src/components/Avatar3D.jsx`
- [ ] Review the component structure
- [ ] Verify it's syntactically correct

### Step 9: Create Avatar Hooks
- [ ] Copy `useAvatarAudio.js` from this guide to `frontend/src/hooks/useAvatarAudio.js`
- [ ] This includes:
  - [ ] `useAvatarAudio` - analyzes audio
  - [ ] `useVisemeFromAudio` - maps audio to lip sync
  - [ ] `useSentiment` - determines emotion from text
  - [ ] `phonemeToViseme` - mapping table

### Step 10: Update ChatArea Component Layout
- [ ] Modify `frontend/src/components/ChatArea.jsx`:
  - [ ] Split layout into avatar panel and chat panel
  - [ ] Add conditional rendering of Avatar3D component
  - [ ] Check character.avatar_url exists before rendering

Example structure:
```jsx
<div className="chat-area-wrapper">
  {character.avatar_url && (
    <div className="avatar-container">
      <Avatar3D
        avatarUrl={character.avatar_url}
        emotion={emotion}
        isStreaming={isStreaming}
      />
    </div>
  )}
  <div className="chat-container">
    {/* Existing chat content */}
  </div>
</div>
```

### Step 11: Add CSS for Avatar Layout
- [ ] Update CSS for avatar and chat layout
- [ ] Desktop: ~40% avatar / 60% chat side-by-side
- [ ] Mobile: avatar as overlay or hidden
- [ ] Ensure responsive design

CSS example:
```css
.chat-area-wrapper {
  display: flex;
  gap: 20px;
  height: 100%;
}

.avatar-container {
  flex: 0 0 40%;
  background: #1a1a1a;
  border-radius: 12px;
  overflow: hidden;
}

.chat-container {
  flex: 1;
  overflow-y: auto;
}

@media (max-width: 768px) {
  .chat-area-wrapper {
    flex-direction: column;
  }
  
  .avatar-container {
    flex: 0 0 200px;
    position: absolute;
    top: 0;
    right: 0;
    width: 150px;
    height: 150px;
  }
}
```

### Step 12: Integrate Emotion Detection
- [ ] Import `useSentiment` hook in ChatArea
- [ ] Call hook with AI's last message
- [ ] Pass emotion state to Avatar3D component

```jsx
const [messages, setMessages] = useState([]);
const lastMessage = messages[messages.length - 1];
const emotion = useSentiment(lastMessage?.content || '');

<Avatar3D emotion={emotion} avatarUrl={character.avatar_url} />
```

### Step 13: Integrate Audio Analysis (Future)
- [ ] Import `useAvatarAudio` hook
- [ ] Connect to TTS audio playback
- [ ] Pass analyser node to Avatar3D for lip sync

This requires TTS implementation first (Phase 1.5).

---

## Phase 4: Testing & Refinement

### Step 14: Manual Testing
- [ ] Start backend: `docker compose up -d`
- [ ] Start frontend: `npm run dev`
- [ ] Navigate to http://localhost:3000
- [ ] Check that characters load with avatars
- [ ] Verify avatar renders in 3D
- [ ] Test emotion changes on different messages
- [ ] Test on mobile viewport (DevTools)

### Step 15: Performance Testing
- [ ] Profile with Chrome DevTools (Performance tab)
- [ ] Check frame rate (target: 60fps on desktop, 30fps on mobile)
- [ ] Monitor memory usage
- [ ] Test on low-end devices if possible

### Step 16: Troubleshooting
Check browser console for:
- [ ] WebGL errors
- [ ] Model loading errors
- [ ] Blend shape errors
- [ ] CORS issues

Common fixes:
- [ ] Verify file paths are correct
- [ ] Check VRM blend shapes are exported correctly
- [ ] Ensure model is in proper T-pose if using custom models
- [ ] Update Three.js version if having compatibility issues

### Step 17: Documentation & Cleanup
- [ ] Document any custom changes made
- [ ] Add comments to code
- [ ] Update README if needed
- [ ] Remove debug console.logs

---

## Phase 5: Advanced Features (Optional)

### Add Avatar Customization UI
- [ ] Create avatar upload interface
- [ ] Preview before saving
- [ ] Validate VRM/GLB files

### Add Lip Sync (Requires TTS)
- [ ] Implement TTS first (Phase 1.5)
- [ ] Connect audio playback to Avatar3D
- [ ] Use `useAvatarAudio` hook for real-time analysis

### Add Advanced Animations
- [ ] Create gesture system
- [ ] Implement hand movements
- [ ] Add full-body animations

---

## Dependencies Checklist

### Backend
- [ ] Python 3.11+
- [ ] FastAPI
- [ ] SQLite or other database
- [ ] Alembic (for migrations)

### Frontend
- [ ] React 18+
- [ ] Three.js
- [ ] Node.js 18+

### Assets
- [ ] VRM models (3 default + custom uploads)
- [ ] Normal minimum file size: 2-5 MB per avatar

---

## File Checklist

### New Files Created
- [ ] `docs/AVATAR_CREATION_GUIDE.md` - Blender guide
- [ ] `docs/AVATAR_DATABASE_SCHEMA.md` - Database updates
- [ ] `docs/AVATAR_IMPLEMENTATION_ROADMAP.md` - This file
- [ ] `frontend/src/components/Avatar3D.jsx` - Main avatar component
- [ ] `frontend/src/hooks/useAvatarAudio.js` - Avatar audio hooks
- [ ] `frontend/public/avatars/greg.vrm` - Avatar asset
- [ ] `frontend/public/avatars/tiffany.vrm` - Avatar asset
- [ ] `frontend/public/avatars/friendly_ai.vrm` - Avatar asset

### Modified Files
- [ ] `backend/app/models.py` - Add avatar fields to Character
- [ ] `backend/app/main.py` - Ensure avatar routes return new fields
- [ ] `backend/app/db/seed.py` - Add avatar URLs to default characters
- [ ] `frontend/src/components/ChatArea.jsx` - Add avatar rendering
- [ ] `frontend/src/styles/chat.css` - Layout for avatar panel
- [ ] `frontend/package.json` - Add Three.js dependency

---

## Estimated Timeline

| Phase | Task | Duration |
|-------|------|----------|
| 1 | Create avatar models (VRoid or Blender) | 2-4 hours |
| 2 | Database schema and backend updates | 1-2 hours |
| 3 | Frontend components and integration | 3-4 hours |
| 4 | Testing and troubleshooting | 1-2 hours |
| **Total** | | **7-12 hours** |

---

## Success Criteria

When complete, you should have:
- ✅ Three 3D avatars rendering in the chat interface
- ✅ Avatars respond to emotional changes
- ✅ Responsive design on mobile and desktop
- ✅ No WebGL errors in console
- ✅ Smooth 30-60 fps performance
- ✅ Proper lip sync ready for future TTS integration

---

## Next Steps After Avatar Implementation

1. **TTS Integration** - Implement Phase 1.5 text-to-speech
2. **Lip Sync** - Connect audio to lip sync animations
3. **Advanced Animations** - Add gesture system
4. **Avatar Upload** - Allow users to customize avatars
5. **Emotion Analytics** - Track and visualize emotion patterns