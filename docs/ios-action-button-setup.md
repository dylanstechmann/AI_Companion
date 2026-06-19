# 📱 iOS Action Button Setup Guide

> Launch your AI Companion with a single press of the Action Button on your iPhone 15 Pro / Pro Max.

---

## Prerequisites

| Requirement | Details |
|---|---|
| **Device** | iPhone 15 Pro or iPhone 15 Pro Max (or newer with Action Button) |
| **iOS Version** | iOS 17.0 or later |
| **AI Companion Backend** | Running and accessible on your local network |
| **Network** | iPhone and server on the same Wi-Fi network |
| **Backend URL** | Know your server's IP or hostname (e.g., `192.168.1.100:3000`) |

> [!IMPORTANT]
> The PWA must be served over **HTTPS** or from `localhost` for the microphone permissions to work. If you're accessing it over your LAN via IP, you may need to set up a self-signed certificate or use a tunneling service.

---

## Step 1 — Install the PWA

The AI Companion frontend is a Progressive Web App (PWA). Installing it to your Home Screen gives it a native app-like experience with full-screen display and persistent sessions.

1. Open **Safari** on your iPhone
2. Navigate to your AI Companion frontend:
   ```
   https://your-host:3000
   ```
3. Tap the **Share** button (the square with an arrow pointing up)
4. Scroll down and tap **"Add to Home Screen"**
5. Give it a name (e.g., **"AI Companion"**) and tap **Add**

> [!TIP]
> You must use **Safari** — other browsers (Chrome, Firefox) do not support installing PWAs on iOS.

The AI Companion icon will now appear on your Home Screen.

---

## Step 2 — Create an Apple Shortcut

Apple Shortcuts lets you create an automation that opens the PWA with the `autoRecord=true` query parameter, which tells the app to immediately start listening when launched.

1. Open the **Shortcuts** app
2. Tap the **+** button in the top-right corner to create a new shortcut
3. Tap **"Add Action"**
4. Search for **"Open URLs"** and select it
5. In the URL field, enter:
   ```
   https://your-host:3000?autoRecord=true
   ```
6. Tap the shortcut name at the top and rename it to something recognizable:
   ```
   AI Companion — Voice
   ```
7. *(Optional)* Tap the icon to choose a custom glyph and color (e.g., a microphone icon in purple)
8. Tap **Done** to save

> [!NOTE]
> Replace `your-host` with your actual server IP or hostname. If you're using a custom port or path, adjust accordingly.

---

## Step 3 — Assign to the Action Button

1. Open **Settings** on your iPhone
2. Tap **"Action Button"** (or search for it)
3. Swipe through the options until you reach **"Shortcut"**
4. Tap **"Choose a Shortcut"**
5. Select your **"AI Companion — Voice"** shortcut from the list

---

## Step 4 — Test It

1. **Lock your phone**, then wake it up
2. **Press and hold** the Action Button on the left side of your iPhone
3. The AI Companion PWA should launch in full-screen mode
4. The app should **immediately begin recording** audio (you'll see the recording indicator)
5. Speak your message, and the companion should transcribe and respond

> [!TIP]
> For the best experience, ensure you've granted microphone permissions to the PWA on first launch. If prompted, tap **"Allow"** to enable the microphone.

---

## Troubleshooting

### PWA doesn't open when pressing the Action Button
- **Verify the shortcut**: Open the Shortcuts app and run the shortcut manually. If it doesn't work there, the issue is with the shortcut configuration.
- **Check the URL**: Make sure the URL in the shortcut exactly matches your server address.
- **Re-assign the Action Button**: Go to Settings → Action Button and re-select the shortcut.

### Microphone doesn't activate automatically
- **Check permissions**: Go to Settings → Safari → Microphone and ensure your site is allowed.
- **HTTPS required**: iOS requires a secure context (HTTPS) for microphone access. If you're using HTTP over LAN, the browser will block mic access.
- **PWA vs. Safari**: Make sure you're launching the installed PWA from the Home Screen, not the Safari bookmark.

### "Cannot connect to server" error
- **Same network**: Ensure your iPhone and the server are on the same Wi-Fi network.
- **Firewall**: Check that port `3000` (frontend) and `8000` (backend) are open on the server's firewall.
- **Server running**: Verify the Docker containers are up:
  ```bash
  docker compose ps
  ```

### Recording works but no transcription
- **Backend health**: Check the backend logs for STT errors:
  ```bash
  docker compose logs backend
  ```
- **GPU availability**: Ensure the NVIDIA Container Toolkit is installed and the GPU is accessible inside the container.
- **Whisper model**: The `large-v3` model requires ~6 GB of VRAM. If your GPU doesn't have enough memory, switch to `medium` or `small` in your `.env` file.

### Action Button does something else
- **iOS version**: Action Button customization requires iOS 17+. Update your iPhone if needed.
- **Conflicting assignment**: Only one action can be assigned to the Action Button at a time. Reassign it in Settings → Action Button.

---

## Quick Reference

| Action | How |
|---|---|
| Open PWA manually | Tap the AI Companion icon on your Home Screen |
| Open PWA via Action Button | Press and hold the Action Button |
| Open with auto-record | Action Button (with shortcut configured above) |
| Change Action Button assignment | Settings → Action Button |
| Edit shortcut URL | Shortcuts app → tap your shortcut → edit URL |
