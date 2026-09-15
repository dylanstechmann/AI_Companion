export function getInstallHelp(userAgent = '') {
  if (/Android/i.test(userAgent)) {
    return 'Open your browser menu and look for Install or Add to Home screen. If unavailable, use a bookmark.';
  }
  if (/iPhone|iPad|iPod/i.test(userAgent)) {
    return 'Use the browser Share menu and look for Add to Home Screen. Availability depends on your iOS version and browser.';
  }
  if (/Firefox\//i.test(userAgent)) {
    return /Windows/i.test(userAgent)
      ? 'Firefox for Windows: use the web apps button in the address bar (Firefox 143+, or 150+ for Microsoft Store installs). Otherwise bookmark this page.'
      : 'Firefox on macOS/Linux: use this app in a normal tab or bookmark it. Native standalone installation is not currently available.';
  }
  return 'Look for your browser’s Install app option. If it is not available, the app still works in a normal tab.';
}

export function getBrowserCapabilities(win = window, nav = navigator) {
  return {
    secure: Boolean(win.isSecureContext),
    microphone: Boolean(nav.mediaDevices?.getUserMedia && win.MediaRecorder),
    speech: 'speechSynthesis' in win,
    offlineShell: 'serviceWorker' in nav,
    installed: Boolean(win.matchMedia?.('(display-mode: standalone)').matches || nav.standalone),
  };
}
