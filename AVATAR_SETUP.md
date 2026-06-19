# Quick Avatar Setup Guide

This guide gets you up and running with 3D avatars in 5 easy steps.

## Quick Start (5 minutes)

### 1. Get Avatar Models

**Option A: Use VRoid Studio (Recommended)**
```bash
# Download from: https://vroid.com/en/studio
# Create 3 characters and export as VRM
# Save files to: frontend/public/avatars/
#   - greg.vrm
#   - tiffany.vrm
#   - friendly_ai.vrm
```

**Option B: Use Pre-made Models**
```bash
# Download free VRM models:
# - VRoid Hub: https://hub.vroid.com/
# - Copy to frontend/public/avatars/
```

### 2. Create Avatar Directory
```bash
mkdir -p frontend/public/avatars
# Place your .vrm files here
```

### 3. Install Frontend Dependencies
```bash
cd frontend
npm install three
npm install @react-three/fiber @react-three/drei
npm install @pixiv/three-vrm  # Optional, for advanced VRM features
```

### 4. Copy Component Files
Copy these files to your project:
- `frontend/src/components/Avatar3D.jsx`
- `frontend/src/hooks/useAvatarAudio.js`

### 5. Update Database

**For SQLite:**
```sql
ALTER TABLE characters ADD COLUMN avatar_url TEXT DEFAULT NULL;
ALTER TABLE characters ADD COLUMN avatar_format TEXT DEFAULT 'vrm';
ALTER TABLE characters ADD COLUMN has_lip_sync BOOLEAN DEFAULT 1;
ALTER TABLE characters ADD COLUMN has_emotions BOOLEAN DEFAULT 1;
ALTER TABLE characters ADD COLUMN idle_animation TEXT DEFAULT 'breathing';
```

**Then update existing characters:**
```sql
UPDATE characters SET avatar_url = '/avatars/greg.vrm' WHERE name = 'Greg';
UPDATE characters SET avatar_url = '/avatars/tiffany.vrm' WHERE name = 'Tiffany';
UPDATE characters SET avatar_url = '/avatars/friendly_ai.vrm' WHERE name = 'Friendly AI';
```

---

## Using the Avatar Component

### In ChatArea.jsx:

```jsx
import Avatar3D from './Avatar3D';
import { useSentiment } from '../hooks/useAvatarAudio';

export const ChatArea = ({ character, messages }) => {
  const lastMessage = messages[messages.length - 1];
  const emotion = useSentiment(lastMessage?.content || '');

  return (
    <div className="chat-wrapper">
      {character.avatar_url && (
        <div className="avatar-container">
          <Avatar3D
            avatarUrl={character.avatar_url}
            emotion={emotion}
            isStreaming={false}
          />
        </div>
      )}
      <div className="chat-messages">
        {/* Your existing chat content */}
      </div>
    </div>
  );
};
```

### CSS for Layout:

```css
.chat-wrapper {
  display: flex;
  gap: 20px;
  height: 100%;
}

.avatar-container {
  flex: 0 0 40%;
  background: #1a1a1a;
  border-radius: 12px;
  overflow: hidden;
  border: 1px solid #333;
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
}

@media (max-width: 768px) {
  .chat-wrapper {
    flex-direction: column;
  }

  .avatar-container {
    height: 200px;
    flex: 0 0 auto;
  }
}
```

---

## Creating Custom Avatars in Blender

See detailed guide: `docs/AVATAR_CREATION_GUIDE.md`

**Quick steps:**
1. Model → Rig → Add blend shapes → Animate → Export VRM
2. Blend shapes needed:
   - Viseme_aa, Viseme_E, Viseme_I, Viseme_O, Viseme_U (for lip sync)
   - Joy, Sad, Angry, Thinking (for emotions)
   - Blink (for blinking)

---

## Troubleshooting

### Avatar not showing?
1. Check `character.avatar_url` is set in database
2. Verify file exists: `frontend/public/avatars/[filename].vrm`
3. Check browser console for errors

### Avatar looks broken?
- Make sure VRM file has proper blend shapes exported
- Check that model is rigged correctly

### Performance issues?
- Reduce avatar polygon count
- Use compression tools on VRM files
- Lower animation frame rate on mobile

---

## Files Provided

| File | Purpose |
|------|---------|
| `docs/AVATAR_CREATION_GUIDE.md` | Create avatars in Blender |
| `docs/AVATAR_DATABASE_SCHEMA.md` | Database updates |
| `docs/AVATAR_IMPLEMENTATION_ROADMAP.md` | Complete checklist |
| `frontend/src/components/Avatar3D.jsx` | React component |
| `frontend/src/hooks/useAvatarAudio.js` | Audio/emotion hooks |

---

## Next Steps

1. ✅ Set up avatars (you are here)
2. 📊 Implement TTS (Phase 1.5)
3. 🎤 Add lip-sync to avatar
4. 🎨 Create emotion expressions
5. 🖼️ Add custom avatar upload UI

---

## Need Help?

- Check documentation in `/docs` folder
- Review Avatar3D.jsx comments for API details
- Check browser DevTools console for errors
- Verify VRM files with Three.js VRM loader playground

Happy avatar creating! 🎉