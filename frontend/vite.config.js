import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 3000,
  },
  // Production build is served from GitHub Pages project pages at
  // https://devansh1012007.github.io/ALL-of-ML---DL/; the base path must
  // match so asset URLs resolve. Local dev keeps base '/' (the default) so
  // `npm run dev` works at http://localhost:3000 unchanged.
  base: process.env.NODE_ENV === 'production' ? '/ALL-of-ML---DL/' : '/',
  test: {
    environment: 'jsdom',
    css: false,
    include: ['tests/**/*.{test,spec}.{js,jsx}'],
  },
});
