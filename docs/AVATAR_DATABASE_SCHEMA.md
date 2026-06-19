# Avatar Database Schema Updates

This document describes the database schema changes needed to support avatars in the AI Companion project.

## Overview

The avatar system needs to:
1. Store avatar URLs per character
2. Track emotion and animation preferences
3. Link to avatar assets in the frontend

## Database Changes

### Update Characters Table

Add the following columns to the `characters` table:

```sql
ALTER TABLE characters ADD COLUMN avatar_url TEXT DEFAULT NULL;
ALTER TABLE characters ADD COLUMN avatar_format TEXT DEFAULT 'vrm' CHECK(avatar_format IN ('vrm', 'glb', 'gltf'));
ALTER TABLE characters ADD COLUMN has_lip_sync BOOLEAN DEFAULT TRUE;
ALTER TABLE characters ADD COLUMN has_emotions BOOLEAN DEFAULT TRUE;
ALTER TABLE characters ADD COLUMN idle_animation TEXT DEFAULT 'breathing';
```

### SQL Migration

If using Alembic or similar migration tool, create a new migration:

```python
# backend/app/db/migrations/add_avatar_support.py

from sqlalchemy import Column, String, Boolean, text
from sqlalchemy.ext.declarative import declarative_base

def upgrade():
    op.add_column(
        'characters',
        Column('avatar_url', String, nullable=True)
    )
    op.add_column(
        'characters',
        Column('avatar_format', String, nullable=False, server_default='vrm')
    )
    op.add_column(
        'characters',
        Column('has_lip_sync', Boolean, nullable=False, server_default=True)
    )
    op.add_column(
        'characters',
        Column('has_emotions', Boolean, nullable=False, server_default=True)
    )
    op.add_column(
        'characters',
        Column('idle_animation', String, nullable=False, server_default='breathing')
    )

def downgrade():
    op.drop_column('characters', 'avatar_url')
    op.drop_column('characters', 'avatar_format')
    op.drop_column('characters', 'has_lip_sync')
    op.drop_column('characters', 'has_emotions')
    op.drop_column('characters', 'idle_animation')
```

### Direct SQL (if not using migrations)

```sql
-- For SQLite
ALTER TABLE characters ADD COLUMN avatar_url TEXT DEFAULT NULL;
ALTER TABLE characters ADD COLUMN avatar_format TEXT DEFAULT 'vrm';
ALTER TABLE characters ADD COLUMN has_lip_sync BOOLEAN DEFAULT 1;
ALTER TABLE characters ADD COLUMN has_emotions BOOLEAN DEFAULT 1;
ALTER TABLE characters ADD COLUMN idle_animation TEXT DEFAULT 'breathing';
```

## Updated Character Model

Update the Pydantic model in the backend:

```python
# backend/app/models.py

from pydantic import BaseModel
from typing import Optional

class CharacterBase(BaseModel):
    name: str
    persona: str
    avatar_url: Optional[str] = None
    avatar_format: str = 'vrm'  # 'vrm', 'glb', 'gltf'
    has_lip_sync: bool = True
    has_emotions: bool = True
    idle_animation: str = 'breathing'

class Character(CharacterBase):
    id: int
    created_at: str
    
    class Config:
        from_attributes = True

class CharacterUpdate(BaseModel):
    name: Optional[str] = None
    persona: Optional[str] = None
    avatar_url: Optional[str] = None
    avatar_format: Optional[str] = None
    has_lip_sync: Optional[bool] = None
    has_emotions: Optional[bool] = None
    idle_animation: Optional[str] = None
```

## API Response Examples

### GET /api/characters

```json
{
  "characters": [
    {
      "id": 1,
      "name": "Greg",
      "persona": "Witty, uncensored, humorous Grok-like personality",
      "avatar_url": "/avatars/greg.vrm",
      "avatar_format": "vrm",
      "has_lip_sync": true,
      "has_emotions": true,
      "idle_animation": "breathing",
      "created_at": "2024-01-01T00:00:00Z"
    },
    {
      "id": 2,
      "name": "Tiffany",
      "persona": "Analytical, empathetic, structured thinker",
      "avatar_url": "/avatars/tiffany.vrm",
      "avatar_format": "vrm",
      "has_lip_sync": true,
      "has_emotions": true,
      "idle_animation": "breathing",
      "created_at": "2024-01-01T00:00:00Z"
    }
  ]
}
```

### POST /api/characters

Create a character with avatar:

```json
{
  "name": "NewCharacter",
  "persona": "Description of the character",
  "avatar_url": "/avatars/newchar.vrm",
  "avatar_format": "vrm",
  "has_lip_sync": true,
  "has_emotions": true,
  "idle_animation": "breathing"
}
```

### PUT /api/characters/{id}

Update a character's avatar:

```json
{
  "avatar_url": "/avatars/new_avatar.vrm",
  "has_lip_sync": true
}
```

## Frontend Integration

### Updated Character Fetch

The frontend will automatically receive avatar data:

```javascript
// frontend/src/hooks/useCharacters.js

const fetchCharacters = async () => {
  const resp = await fetch('/api/characters');
  const data = await resp.json();
  return data.characters;
};

// Character object now includes:
// {
//   id: 1,
//   name: "Greg",
//   avatar_url: "/avatars/greg.vrm",
//   has_lip_sync: true,
//   has_emotions: true,
//   ...
// }
```

### ChatArea Component Integration

```jsx
import Avatar3D from './Avatar3D';
import { useSentiment } from '../hooks/useAvatarAudio';

export const ChatArea = ({ character, messages }) => {
  const lastMessage = messages[messages.length - 1];
  const emotion = useSentiment(lastMessage?.content || '');

  return (
    <div className="chat-container">
      {character.avatar_url && (
        <div className="avatar-panel">
          <Avatar3D
            avatarUrl={character.avatar_url}
            emotion={emotion}
            isStreaming={isStreaming}
            audioAnalyzer={audioAnalyzer}
          />
        </div>
      )}
      <div className="chat-panel">
        {/* Chat messages */}
      </div>
    </div>
  );
};
```

## Avatar Asset Organization

Create this directory structure in the frontend:

```
frontend/public/
├── avatars/
│   ├── greg.vrm
│   ├── tiffany.vrm
│   ├── friendly_ai.vrm
│   └── custom_avatar.glb
└── (other assets)
```

## Seeding Default Characters with Avatars

Update the character seeding script:

```python
# backend/app/db/seed.py

DEFAULT_CHARACTERS = [
    {
        "name": "Greg",
        "persona": "Witty, uncensored, humorous Grok-like personality",
        "avatar_url": "/avatars/greg.vrm",
        "avatar_format": "vrm",
        "has_lip_sync": True,
        "has_emotions": True,
        "idle_animation": "breathing"
    },
    {
        "name": "Tiffany",
        "persona": "Analytical, empathetic, structured thinker",
        "avatar_url": "/avatars/tiffany.vrm",
        "avatar_format": "vrm",
        "has_lip_sync": True,
        "has_emotions": True,
        "idle_animation": "breathing"
    },
    {
        "name": "Friendly AI",
        "persona": "Flexible, adaptable, takes on any personality",
        "avatar_url": "/avatars/friendly_ai.vrm",
        "avatar_format": "vrm",
        "has_lip_sync": True,
        "has_emotions": True,
        "idle_animation": "breathing"
    }
]
```

## Configuration Options

### Avatar Formats Supported

- **VRM**: Recommended. Open standard, optimized for web, supports blendshapes
- **GLB**: Good alternative. General-purpose 3D format
- **GLTF**: Text-based version of GLB, larger file size but more debuggable

### Idle Animations

- **breathing**: Subtle up-down head movement (recommended for natural look)
- **none**: No idle animation
- **gentle_sway**: Subtle side-to-side swaying
- **looking_around**: Avatar occasionally looks left/right

### Avatar File Size Recommendations

| Format | Recommended Size | Max Size |
|--------|------------------|----------|
| VRM | < 5 MB | 10 MB |
| GLB | < 8 MB | 15 MB |
| GLTF | < 5 MB | 10 MB |

Larger files will cause slower loading times on mobile.

## Future Enhancements

1. **Avatar Customization UI**
   - Allow users to upload custom avatars
   - Avatar preview before saving
   
2. **Emotion Tracking**
   - Store emotion history per message
   - Analytics on emotion patterns
   
3. **Voice Synthesis Integration**
   - Link TTS audio playback to lip sync directly
   - Automatic emotion detection from TTS providers
   
4. **Advanced Animations**
   - Complex gesture animations
   - Synchronized hand movements
   - Full-body animations beyond head movements

## Troubleshooting

### Avatar not showing?
1. Verify `avatar_url` is set in the database
2. Check that the file exists at `frontend/public/avatars/[filename]`
3. Check browser console for CORS or loading errors

### Blend shapes not working?
1. Ensure avatar is in VRM format with proper blend shapes exported
2. Check Three.js console for morph target dictionary
3. Verify blend shape naming matches VRM standard

### Performance issues?
1. Reduce avatar geometry complexity
2. Lower animation frame rate (30fps on mobile)
3. Use LOD (Level of Detail) for distant views
4. Profile with Chrome DevTools