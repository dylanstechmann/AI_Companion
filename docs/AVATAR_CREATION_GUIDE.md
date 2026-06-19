# 3D Avatar Creation Guide for AI Companion

This guide explains how to create a 3D human avatar in Blender that can be integrated into the AI Companion platform.

## Overview

The AI Companion project needs animated 3D avatars with:
- Idle animations (breathing, blinking, subtle movements)
- Lip-sync to TTS audio
- Emotion expressions (happy, sad, thinking, neutral)
- Customizable per character

## Option 1: Using VRoid Studio (Easiest)

**Recommended for fastest results without Blender expertise**

### Steps:
1. Go to https://vroid.com/en/studio
2. Download and install VRoid Studio
3. Create a character with their tool
4. Export as VRM format
5. Place in `frontend/public/avatars/[character_name].vrm`

**Pros:**
- Fastest way to get a character model
- VRM format is optimized for web
- Includes rigging for expressions
- Free to use

**Cons:**
- Less customization than Blender
- Anime/stylized aesthetic (not photorealistic)

---

## Option 2: Creating in Blender (Advanced)

For full control over avatar design and customization.

### Requirements:
- Blender 4.0+ (free from blender.org)
- Basic 3D modeling knowledge
- 30-60 minutes per avatar

### Step-by-Step Process:

#### 1. Start with a Base Model

**Option A: Use Mixamo**
1. Go to https://www.mixamo.com/ (free Adobe account)
2. Search for "human" or download a base character model
3. Download in GLB format
4. Open in Blender: File > Import > glTF 2.0 (.glb/.gltf)

**Option B: Create from Scratch**
1. Start with Blender's default cube
2. Use modeling tools to shape a humanoid head, body, arms, legs
3. Add subdivision surface modifier for smoothness

**Option C: Use Community Models**
- Sketchfab: https://sketchfab.com (filter: downloadable, rigged)
- Blender Cloud: https://cloud.blender.org/

#### 2. Set Up Rigging (Skeleton)

For animations and blend shapes to work:

1. **Select your model** in Blender
2. **Add an Armature:**
   - Add > Armature > Human (Meta-Rig)
   - This creates a basic humanoid skeleton
3. **Parent the mesh to the armature:**
   - Select mesh, then armature
   - Ctrl+P > Armature Deform > With Automatic Weights
4. **Pose mode testing:**
   - Tab into Pose Mode (Tab key)
   - Move bones to test animations

#### 3. Create Blend Shapes for Expressions (Critical for Avatar)

Blend shapes (also called shape keys) control facial expressions:

1. **Select the head mesh**
2. **Add shape keys:**
   - Object Data Properties (green triangle icon)
   - Shape Keys section > + button
   - Select "Basis" (the default shape)
3. **Create expression shapes:**
   - Duplicate Basis: + > Duplicate Shape
   - Rename to "Viseme_aa" (mouth wide open)
   - Tab into Edit Mode
   - Deform the mouth geometry to be wide open
   - Tab back to Object Mode
   - Repeat for other visemes and emotions:

   **Visemes (for lip-sync):**
   - Viseme_aa (wide open, like "ah")
   - Viseme_E (open, like "eh")
   - Viseme_I (smile, like "ee")
   - Viseme_O (round, like "oh")
   - Viseme_U (round closed, like "oo")

   **Emotions:**
   - Joy (raise cheeks, smile, squint eyes)
   - Angry (furrow brows, open mouth)
   - Sad (lower mouth corners, droop eyes)
   - Thinking (slight frown, raised brow)
   - Neutral (baseline)

4. **Test blend shapes:**
   - Go to Shape Key properties
   - Adjust "Value" slider (0.0 to 1.0) to see the deformation

#### 4. Create/Add Animations

**Option A: Use Mixamo Animations**
1. Download animations from Mixamo (same account as your model)
2. Import into Blender as Action strips
3. NLA Editor (Nonlinear Animation) > add actions

**Option B: Create Simple Animations**
1. Create an Action in the Action Editor
2. Insert keyframes at different poses:
   - Frame 0: Neutral pose
   - Frame 30: Slight head tilt (breathing effect)
   - Frame 60: Back to neutral
   - Set to looping

#### 5. Export as VRM (Recommended)

VRM is the standard format for web avatars:

1. **Install VRM export addon:**
   - Download: https://github.com/saturday06/VRM-Addon-for-Blender
   - Blender > Edit > Preferences > Add-ons > Install
   - Enable "VRM Export"

2. **Prepare model for VRM export:**
   - Ensure all objects are applied (Modifier > Apply All)
   - Ensure proper T-pose for rigging
   - Make sure blend shapes are named correctly (VRM standard names)

3. **Export:**
   - File > Export > VRM Export (.vrm)
   - Choose location: `frontend/public/avatars/[character_name].vrm`
   - Check shape key naming

#### 6. Alternative: Export as GLB

If VRM export fails, GLB is also supported:

```bash
File > Export > glTF 2.0 (.glb/.gltf)
# Location: frontend/public/avatars/[character_name].glb
```

---

## Blender Script for Automation (Optional)

You can use Python scripting in Blender to automate creation:

```python
# blender_avatar_setup.py
# Run in Blender's Python console

import bpy

# Create basic humanoid
bpy.ops.mesh.primitive_uv_sphere_add(radius=1, location=(0, 0, 1.7))
head = bpy.context.active_object
head.name = "Head"

# Add armature
bpy.ops.object.armature_add(location=(0, 0, 1))
armature = bpy.context.active_object

# Parent mesh to armature
bpy.context.view_layer.objects.active = head
head.parent = armature

# Create blend shape key for smile
head.shape_key_add(name="Smile", from_mix=False)

print("Basic avatar structure created!")
```

---

## Integration with AI Companion

Once you have your VRM files:

### 1. Place avatar files:
```
frontend/public/avatars/
├── greg.vrm
├── tiffany.vrm
└── friendly_ai.vrm
```

### 2. Update character database:
Add `avatar_url` field to characters:
```json
{
  "id": 1,
  "name": "Greg",
  "avatar_url": "/avatars/greg.vrm"
}
```

### 3. The Avatar3D component will load and render them (see Avatar3D.jsx in the next file)

---

## Common Blender Shortcuts

| Action | Shortcut |
|--------|----------|
| Enter Edit Mode | Tab |
| Exit Edit Mode | Tab |
| Select All | A |
| Box Select | B |
| Rotate View | Middle Mouse |
| Pan View | Shift + Middle Mouse |
| Zoom | Mouse Wheel |
| Insert Keyframe | I |
| Play Animation | Spacebar |
| Frame Next | Right Arrow |

---

## Troubleshooting

**Problem: Avatar looks broken in web viewer**
- Solution: Check that all modifiers are applied, UV maps exist, and materials are set

**Problem: Blend shapes not exported to VRM**
- Solution: Ensure shape keys have proper names (use Viseme_aa, not just "aa")

**Problem: Animation looks jerky**
- Solution: Ensure smooth curves in the Graph Editor, increase keyframe density

**Problem: VRM export option missing**
- Solution: Install the VRM addon from GitHub (see Export as VRM section)

---

## Resources

- **Blender Basics:** https://www.blender.org/support/tutorials/
- **VRM Standard:** https://vrm.dev/
- **Mixamo:** https://www.mixamo.com/
- **VRoid Studio:** https://vroid.com/
- **Sketchfab Models:** https://sketchfab.com/