import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { VitePWA } from 'vite-plugin-pwa';

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['vite.svg', 'offline.html', 'icons/*.png'],
      manifest: {
        name: 'AI Companion',
        short_name: 'AI Companion',
        description: 'Your private, self-hosted AI companion with voice interaction, 3D avatars, and persistent memory.',
        id: '/?source=pwa',
        theme_color: '#0a0a1a',
        background_color: '#0a0a1a',
        display: 'standalone',
        display_override: ['window-controls-overlay', 'standalone', 'minimal-ui'],
        orientation: 'portrait',
        start_url: '/',
        scope: '/',
        categories: ['lifestyle', 'productivity', 'utilities'],
        icons: [
          {
            src: '/icons/icon-192x192.png',
            sizes: '192x192',
            type: 'image/png',
            purpose: 'any maskable',
          },
          {
            src: '/icons/icon-512x512.png',
            sizes: '512x512',
            type: 'image/png',
            purpose: 'any maskable',
          },
        ],
        shortcuts: [
          {
            name: 'Start Voice Chat',
            short_name: 'Voice',
            description: 'Jump straight into hands-free voice chat',
            url: '/?mode=voice',
            icons: [{ src: '/icons/icon-192x192.png', sizes: '192x192' }],
          },
          {
            name: '3D Avatars',
            short_name: 'Avatars',
            description: 'Switch or customize your 3D companion avatar',
            url: '/?tab=characters',
            icons: [{ src: '/icons/icon-192x192.png', sizes: '192x192' }],
          },
        ],
      },
      workbox: {
        globPatterns: ['**/*.{js,css,html,ico,png,svg,woff2}'],
        navigateFallback: '/offline.html',
        navigateFallbackDenylist: [/^\/api\//],
      },
    }),
  ],
  server: {
    host: true,
    allowedHosts: true,
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://backend:8000',
        changeOrigin: true,
        secure: false,
      },
    },
  },
});
