# Get Blender MCP Working (Correct Instructions)

The earlier instructions pointed to the wrong addon (`browser-tools-mcp`). That is NOT the Blender addon. The correct one is **`addon.py` from `ahujasid/blender-mcp`**.

Good news: the Cline side is **already configured correctly**. You can confirm this — the connected MCP server shows:
```
cmd /c C:\Users\AyeBayBay\AppData\Local\hermes\bin\uvx.exe --python 3.11 blender-mcp
```

You do **NOT** need to run any `uvx` or `npx` command in a terminal. Cline launches that automatically. You ONLY need to install the Blender-side addon and click "Connect".

---

## Step 1: Remove the Wrong Addon

1. In Blender: **Edit → Preferences → Add-ons**
2. Search for **"MCP"** or **"browser-tools"**
3. If you find the wrong one, expand it, click the dropdown arrow → **Remove**
4. Keep Preferences open for the next step

---

## Step 2: Download the Correct `addon.py`

Download this single file (right-click → Save As, or use the command below):

**Raw URL:** https://raw.githubusercontent.com/ahujasid/blender-mcp/main/addon.py

Or run this in PowerShell to save it to your Downloads folder:
```powershell
curl -L https://raw.githubusercontent.com/ahujasid/blender-mcp/main/addon.py -o "$env:USERPROFILE\Downloads\addon.py"
```

---

## Step 3: Install It in Blender

1. In Blender: **Edit → Preferences → Add-ons**
2. Click **Install...** (top right; in Blender 4.2+ it's the dropdown ▾ → **Install from Disk...**)
3. Navigate to where you saved **`addon.py`** and select it
4. Click **Install Add-on**
5. In the add-on list, find **"Interface: Blender MCP"** and **check the box** to enable it

You'll know it worked because a new **BlenderMCP** panel becomes available.

---

## Step 4: Start the Connection in Blender

1. Close Preferences
2. In the 3D Viewport, press **`N`** to open the right-hand sidebar
3. Click the **"BlenderMCP"** tab in that sidebar
4. (Optional) Leave the port at **9876** — this is the default Cline expects
5. Click **"Connect to Claude"** (also works for Cline — it just starts the socket server)

The button starts a socket server inside Blender on port **9876**. That's the bridge Cline connects to.

---

## Step 5: Tell Me It's Connected

Once you've clicked "Connect to Claude" and Blender is running, just say **"connected"** (or anything). I'll immediately test it by calling the `get_scene_info` tool. If it returns scene data, we're live and I'll start generating the high-quality MPFB avatars directly in your Blender.

---

## Troubleshooting

**"Could not connect to Blender. Make sure the Blender addon is running"**
- The addon is installed but you haven't clicked **"Connect to Claude"** in the BlenderMCP sidebar panel. Click it.
- Make sure Blender is actually open and running.

**Can't find the "BlenderMCP" tab in the sidebar**
- The addon isn't enabled. Go back to Preferences → Add-ons, search "MCP", make sure the checkbox is ticked.
- Press **`N`** in the 3D viewport to toggle the sidebar.

**Addon won't install / shows an error**
- Make sure you downloaded the **raw** `addon.py` (a real Python file ~30KB), not an HTML page. Open it in a text editor — it should start with Python code and a `bl_info` dictionary.

**Port already in use**
- Change the port in the BlenderMCP panel, but then tell me the new port so I can match it (default is 9876).

**uvx not found / package errors (Cline side)**
- This is already configured. If it ever fails, the package is `blender-mcp` run via `uvx --python 3.11 blender-mcp`. You do not normally need to touch this.

---

## What Happens After Connection

Once connected, I will use `execute_blender_code` to:
1. Enable/verify the MPFB addon (or install it if needed)
2. Generate the three characters (Greg = athletic male, Tiffany = curvy female, Friendly AI = neutral)
3. Add facial morph targets / blend shapes for emotion + lip-sync
4. Export each as a GLB into `frontend/public/avatars/`
5. Update the database so the frontend loads the new high-quality avatars

You won't have to do any of the modeling — I'll drive Blender directly.