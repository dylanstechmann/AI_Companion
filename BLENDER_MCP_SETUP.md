# Blender MCP Addon Setup - 5 Minutes

To enable me to generate high-quality avatars using MPFB, you need to install the Blender MCP addon. Here's how:

## Quick Setup

### Step 1: Install Blender MCP Addon
1. Open **Blender** (you already have it open)
2. Go to **Edit → Preferences**
3. Click **Add-ons** (left sidebar)
4. Click **Install...**
5. Navigate to: `C:\Users\AyeBayBay\Projects\AI_Companion\blender-mcp` (or wherever it is)
6. Find `blender_mcp.py` or the addon folder
7. Click **Install Add-on**
8. **Enable it** by checking the checkbox

### Step 2: Start the MCP Server
In Blender:
1. Go to the **Scripting workspace** (top menu)
2. Open **Blender MCP Console** (if available in your addon)
3. Or run this in the Python console:
```python
import subprocess
subprocess.Popen(['npx', '-y', '@agentdeskai/browser-tools-mcp@latest'])
```

### Step 3: Verify Connection
Once the addon is running, it should listen on `localhost:7000` (default) or show the port in the console.

Then I can automatically generate the high-quality avatars!

## Alternative: Quick Manual Approach (15 min)

If the addon setup is complex, you can manually create avatars in 15 minutes:

1. **In Blender**: Install MPFB addon (Edit → Preferences → Add-ons → Search "MPFB")
2. **Create Greg**: 
   - N key → MPFB tab → Create Human → Adjust sliders → Export GLB
3. **Create Tiffany**: 
   - Repeat with female settings
4. **Create Friendly AI**: 
   - Repeat with neutral settings
5. **Done** - Drop GLBs in `frontend/public/avatars/`

Then I'll load and configure them in the app.

## Which Would You Prefer?

- **Option A**: Set up MCP addon → I generate everything automatically (complex addon setup, but fully automated)
- **Option B**: Manually create in Blender using MPFB (simple, 15 minutes your time, I handle integration)
- **Option C**: Keep current avatars as-is (they work fine for testing the feature)

Which would you like?