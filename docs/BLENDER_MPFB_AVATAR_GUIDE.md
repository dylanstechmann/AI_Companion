# Complete Avatar Creation Guide: Blender + MPFB

## Overview

Based on your project's existing architecture, the **best approach** is to use **Blender with MPFB (MakeHuman Plugin for Blender)** directly. This provides:

✅ Full open-source (no commercial restrictions)
✅ Complete control over body proportions and facial features
✅ Parametric body generation (no sculpting required)
✅ Built-in rigging and morph targets (blend shapes)
✅ Direct export to GLB with animation-ready morphs
✅ Consistent with your existing HumanAvatar3D.jsx component

**Why NOT VRoid + Blender modification?**
- VRoid is primarily anime-focused (harder to customize for realistic humans)
- Converting VRoid → Blender → custom modifications = more steps, more potential breakage
- MPFB is specifically designed for parametric human generation → direct GLB export

---

## Architecture Overview

Your app currently uses this pipeline:

```
MPFB in Blender
    ↓
Configure body type (athletic, curvy, etc.)
    ↓
Add clothing via materials/geometry
    ↓
Export as GLB with morph targets
    ↓
Frontend loads GLB (HumanAvatar3D.jsx)
    ↓
Emotion → Blend Shape Mapping
Audio Amplitude → jawOpen + visemes
```

---

## Part 1: Install MPFB in Blender

### Requirements
- Blender 3.0+ (4.0+ recommended)
- ~500MB disk space for MPFB data
- Python 3.9+ (included with Blender)

### Installation Steps

1. **Download Blender**
   - https://www.blender.org/
   - Version 4.0 or later

2. **Download MPFB**
   - https://github.com/makehumancommunity/community-plugins-makehuman/releases
   - Look for "MPFB2" releases (latest stable)
   - Download the ZIP file

3. **Install MPFB Addon**
   - Extract the ZIP to a temp folder
   - Open Blender
   - Edit → Preferences → Add-ons
   - Click "Install..." button
   - Navigate to the extracted MPFB folder and select `mpfb_2` subdirectory
   - Enable the addon (check the box)
   - Close preferences

4. **Verify Installation**
   - Right side panel (N key) should show "MPFB" tab
   - If not visible, check Blender version compatibility

---

## Part 2: Create Default Characters

### 2.1 Creating Greg (Athletic Male)

Open Blender and follow these steps:

1. **Start New Project**
   - File → New → General
   - Delete the default cube (X key)

2. **Create Human Model**
   - Hit N key to open right panel
   - Find "MPFB" tab
   - Click "Create Human"
   - Set:
     - **Gender**: Male
     - **Age**: 30-35 (adult)
     - Leave other sliders at default

3. **Adjust Body Proportions (Athletic)**
   - In the MPFB panel, find the **Modeling** section
   - Scroll down to find sliders for:
     - **Muscle**: Increase to 0.7-0.8 (athletic build)
     - **Weight**: Keep at default or slightly below (0.4-0.5)
     - **Height**: Keep at default or slightly above (0.6)
   - **Chest/Torso**: Increase slightly (0.6) for defined chest
   - **Shoulders**: Increase to 0.7 for broader shoulders

4. **Add Facial Features**
   - In MPFB → Facial section:
     - **Jaw Width**: 0.6 (strong jaw)
     - **Nose Width**: 0.5 (proportional)
     - **Eyes**: Keep default (0.5)
   - Leave most at neutral for Greg's serious personality

5. **Add Basic Clothing**
   - In MPFB → Clothes section:
     - Add "T-Shirt" with color (gray or blue)
     - Add "Jeans"
     - Add "Shoes"

6. **Export as GLB**
   - Select the human model
   - File → Export → glTF 2.0 (.glb/.gltf)
   - Save as: `frontend/public/avatars/greg_3d.glb`
   - **Critical**: Ensure "Include Morphs" is enabled in export options
   - Ensure "Include Animations" is disabled (you'll use idle animations in React)

### 2.2 Creating Tiffany (Female with Above-Average Bust)

Repeat the process but with female-specific adjustments:

1. **Create Female Model**
   - MPFB → Create Human
   - **Gender**: Female
   - **Age**: 28-32

2. **Adjust Body Proportions (Curvy Female)**
   - **Muscle**: 0.3-0.4 (lean, not athletic)
   - **Weight**: 0.6 (curvy figure)
   - **Height**: Keep default
   - **Chest**: **Important**: Increase to 0.7-0.8 (above-average bust)
   - **Hips**: Increase to 0.7 (feminine curves)
   - **Waist**: Keep at 0.4 (definition)

3. **Facial Features**
   - **Jaw Width**: 0.4 (softer jawline)
   - **Cheekbones**: Increase to 0.6
   - **Lips**: Increase to 0.6 (fuller lips)
   - **Nose Width**: 0.4 (refined)
   - **Eyes**: Increase to 0.6 (larger eyes)

4. **Add Professional Clothing**
   - Add "Business Shirt" (white or light color)
   - Add "Business Pants" or "Skirt"
   - Add "Business Shoes"

5. **Export as GLB**
   - Save as: `frontend/public/avatars/tiffany_3d.glb`
   - Same export settings (with morphs enabled)

### 2.3 Creating "Friendly AI" (Neutral, Approachable)

Create a third character that's more neutral/approachable:

1. **Create Androgynous/Neutral Model**
   - Gender: Female (but adjusted)
   - Build body that's neither too masculine nor too feminine

2. **Proportions**
   - **Muscle**: 0.4
   - **Weight**: 0.5 (neutral)
   - **Height**: 0.55 (slightly below average - approachable)
   - **Chest**: 0.5 (neutral)
   - **Hips**: 0.5 (neutral)

3. **Facial Features** (Friendly)
   - **Jaw Width**: 0.45
   - **Smile**: Neutral expression (achieved through positioning, not morph targets in Blender - morphs in React)
   - **Eyes**: 0.55 (friendly, open)
   - **Cheekbones**: 0.5 (neutral)

4. **Neutral Clothing**
   - Add "Hoodie" (any color)
   - Add "Casual Pants"
   - Add "Casual Shoes"

5. **Export as GLB**
   - Save as: `frontend/public/avatars/friendly_ai_3d.glb`

---

## Part 3: Understanding the Morph Targets (Blend Shapes)

When you export with "Include Morphs" enabled, MPFB includes **~160 predefined morph targets** in the GLB file.

### Key Morph Targets Used by HumanAvatar3D.jsx

**For Speech/Audio Sync:**
```
jawOpen          - Open/close mouth (driven by audio amplitude)
Viseme_aa        - Wide open (ah sound)
Viseme_E         - Open (eh sound)
Viseme_I         - Smile (ee sound)
Viseme_O         - Round lips (oh sound)
Viseme_U         - Rounded closed (oo sound)
```

**For Emotions (Already Defined in HumanAvatar3D.jsx):**
```
// Happy
mouthSmileLeft, mouthSmileRight
cheekSquintLeft, cheekSquintRight

// Sad
mouthFrownLeft, mouthFrownRight
browInnerUp

// Excited
mouthSmileLeft, mouthSmileRight
eyeWideLeft, eyeWideRight

// Thinking
browInnerUp
mouthShrugLower
eyeSquintLeft

// Angry
browDownLeft, browDownRight
mouthPressLeft, mouthPressRight
```

**For Idle Animation:**
```
eyeBlinkLeft, eyeBlinkRight
```

These morphs are automatically generated by MPFB based on the body mesh topology.

---

## Part 4: Custom Character Creation Flow

### How Users Create Custom Avatars (In Your App)

1. **User clicks "Create Custom Character"**
2. **Form appears with sliders:**
   - Body type: slim / athletic / curvy / muscular
   - Gender: male / female / neutral
   - Age range: 20-30 / 30-45 / etc.
   - Skin tone, hair color, clothing style

3. **Backend receives form data**
4. **Python script (avatar_generator.py) generates GLB:**
   ```python
   # This script would:
   # 1. Run Blender in headless mode with MPFB
   # 2. Configure MPFB sliders based on form inputs
   # 3. Export as GLB
   # 4. Save to frontend/public/avatars/custom_[character_id].glb
   ```

5. **Frontend loads the generated GLB**
6. **HumanAvatar3D.jsx renders it with animations**

### Difficulty Assessment: **Medium (6-8 hours)**

**Breaking it down:**
1. Set up Blender headless execution: 1-2 hours
2. Write Python script for MPFB automation: 2-3 hours
3. Integrate with backend API: 2-3 hours
4. Test and debug: 1-2 hours

---

## Part 5: Database Schema

Your characters table should include:

```sql
CREATE TABLE characters (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  persona TEXT,
  avatar_3d_url TEXT,           -- Path to GLB file (e.g., /avatars/greg_3d.glb)
  avatar_url TEXT,              -- 2D fallback image (e.g., /avatars/greg.png)
  body_type TEXT,               -- 'athletic', 'curvy', 'slim', 'muscular', 'neutral'
  clothing_style TEXT,          -- 'casual', 'business', 'athletic', 'formal'
  clothing_description TEXT,    -- JSON or text describing which clothing items
  gender TEXT,                  -- 'male', 'female', 'neutral'
  appearance_description TEXT,  -- General description for documentation
  created_at TIMESTAMP
);
```

### Example Default Characters:

```javascript
DEFAULT_CHARACTERS = [
  {
    id: 1,
    name: 'Greg',
    persona: 'Witty, uncensored, humorous Grok-like personality',
    avatar_3d_url: '/avatars/greg_3d.glb',
    avatar_url: '/avatars/greg.png',
    body_type: 'athletic',
    clothing_style: 'casual',
    clothing_description: 'Gray T-shirt, jeans, casual shoes',
    gender: 'male',
    appearance_description: 'Athletic male, strong jawline, serious demeanor'
  },
  {
    id: 2,
    name: 'Tiffany',
    persona: 'Analytical, empathetic, structured thinker',
    avatar_3d_url: '/avatars/tiffany_3d.glb',
    avatar_url: '/avatars/tiffany.png',
    body_type: 'curvy',
    clothing_style: 'business',
    clothing_description: 'White business shirt, business pants, formal shoes',
    gender: 'female',
    appearance_description: 'Female with curvy figure, refined features, professional appearance'
  },
  {
    id: 3,
    name: 'Friendly AI',
    persona: 'Flexible, adaptable, takes on any personality',
    avatar_3d_url: '/avatars/friendly_ai_3d.glb',
    avatar_url: '/avatars/friendly_ai.png',
    body_type: 'neutral',
    clothing_style: 'casual',
    clothing_description: 'Hoodie, casual pants, casual shoes',
    gender: 'female',
    appearance_description: 'Neutral, approachable appearance, friendly expression'
  }
];
```

---

## Part 6: Integrating with HumanAvatar3D Component

Your existing HumanAvatar3D.jsx already supports:
1. Loading GLB files with morph targets ✅
2. Emotion-to-morph mapping ✅
3. Audio amplitude to mouth movement ✅
4. Idle animations (breathing, blinking) ✅
5. Fallback to procedural avatar ✅

### Usage in ChatArea.jsx:

```jsx
import HumanAvatar3D from './HumanAvatar3D';

export const ChatArea = ({ character, emotion, isStreaming }) => {
  const amplitudeRef = useRef(0);

  return (
    <div className="chat-wrapper">
      <div className="avatar-panel">
        <HumanAvatar3D
          avatarUrl={character.avatar_3d_url}  // Path to GLB
          emotion={emotion}
          amplitudeRef={amplitudeRef}
          isStreaming={isStreaming}
          isPaused={false}
          characterName={character.name}
          clothingStyle={character.clothing_style}
          bodyType={character.body_type}
        />
      </div>
      <div className="chat-messages">
        {/* Chat content */}
      </div>
    </div>
  );
};
```

---

## Part 7: Advanced - Headless Avatar Generation (Optional)

For automated custom avatar creation, you can use this Python approach:

```python
# backend/app/avatar_generator.py

import subprocess
import json
from pathlib import Path

def generate_avatar(
    character_id: int,
    gender: str = 'female',
    body_type: str = 'athletic',
    age: int = 30,
    skin_tone: str = 'medium',
    hair_color: str = 'brown',
    clothing_style: str = 'casual'
):
    """
    Generate a GLB avatar using Blender + MPFB in headless mode.
    
    Args:
        character_id: Unique ID for the character
        gender: 'male', 'female'
        body_type: 'slim', 'athletic', 'curvy', 'muscular'
        age: Integer age (used to set MPFB age slider)
        skin_tone: 'light', 'medium', 'dark'
        hair_color: Color name
        clothing_style: 'casual', 'business', 'athletic'
    
    Returns:
        Path to generated GLB file
    """
    
    output_path = Path(f'frontend/public/avatars/custom_{character_id}_3d.glb')
    
    # Blender Python script content
    blender_script = f"""
import bpy
from mathutils import Vector

# Clear default scene
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

# Import MPFB
import sys
sys.path.append(bpy.utils.user_resource('SCRIPTS', 'addons'))

# Load MPFB addon
bpy.ops.preferences.addon_enable(module='mpfb_2')

# Create human using MPFB API
print("Creating human...")

# Body type mapping
body_sliders = {{
    'slim': {{'muscle': 0.2, 'weight': 0.3}},
    'athletic': {{'muscle': 0.7, 'weight': 0.5}},
    'curvy': {{'muscle': 0.3, 'weight': 0.6}},
    'muscular': {{'muscle': 0.9, 'weight': 0.5}},
}}

body_config = body_sliders.get('{body_type}', body_sliders['athletic'])

# This is a placeholder - actual MPFB API calls would go here
# The exact API depends on MPFB version

# Export as GLB
print("Exporting as GLB...")
bpy.ops.export_scene.gltf(
    filepath='{output_path}',
    use_draco_mesh_compression=False,
    export_normals=True,
    export_colors=False,
    use_animations=False,
    use_deformation_bones=True,
    include_all_bone_influences=True,
    use_mesh_quantization=False,
)

print(f"Avatar generated: {{'{output_path}'}}")
"""
    
    # Write script to temp file
    script_file = Path('/tmp/mpfb_generate.py')
    script_file.write_text(blender_script)
    
    # Run Blender in headless mode
    subprocess.run([
        'blender',
        '--background',
        '--python', str(script_file)
    ], check=True)
    
    return str(output_path)
```

This is a complex feature for Phase 2+. For now, just create the 3 default characters manually.

---

## Summary: Recommended Timeline

### Immediate (This Week)
1. Install Blender + MPFB addon
2. Create Greg character (1-2 hours)
3. Create Tiffany character (1-2 hours)
4. Create Friendly AI character (1-2 hours)
5. Place GLB files in `frontend/public/avatars/`
6. Update database with avatar URLs
7. Test with HumanAvatar3D component

**Total: 6-8 hours → Production-ready with 3 default avatars**

### Later Phases (Phase 2+)
- Implement custom character creation form
- Build headless Blender automation script
- Allow users to generate custom avatars
- Add emotion-based facial rigging refinements

---

## Troubleshooting

**Problem: Headless avatar not rendering**
- Solution: Check that morphs are exported (Blender export options)
- Check browser console for morph target errors

**Problem: MPFB addon won't load**
- Solution: Verify Blender version (4.0+), check addon compatibility

**Problem: Clothes clipping into body**
- Solution: Adjust MPFB clothing fit in Blender before export

**Problem: Morphs not animating**
- Solution: HumanAvatar3D.jsx looks for specific morph names; verify export preserves names