# Kinema web app (Next.js)

The user interface for the RS Mini Project. See the [project README](../README.md) for setup and the architecture docs.

```bash
npm install
npm run dev      # http://localhost:3000  (needs the API on :8000)
npm run lint && npx tsc --noEmit && npm run build
```

Configuration: `NEXT_PUBLIC_API_URL` (defaults to `http://localhost:8000`). No secrets ever live in this app; Claude and TMDB keys are read by the backend only.

Layout: `src/components/WorkspaceProvider.tsx` owns all state (session, messages, profile, optimistic feedback);
`src/lib/api.ts` is the typed client; `src/app/evaluation/page.tsx` renders the real evaluation report.

## Note on the ambient backdrop

`src/components/Backdrop.tsx` (drifting light, cursor glow, hover wash, vignette) is **disabled**: `<body>` paints an opaque background over
it, so it was never visible but still cost GPU time. To use it, set `NEXT_PUBLIC_IMMERSIVE_BACKDROP=1` in `frontend/.env.local` and make the
`<body>` background transparent in `src/app/globals.css`. This changes how the app looks.
