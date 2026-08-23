## Local Frontend Preview

The frontend-only preview can be started from `frontend` with:

```bash
npm run vite -- --host 127.0.0.1
```

Then open:

```text
http://127.0.0.1:5173/vlink-preview.html
```

The preview seeds the Zustand store from `backend/config/app.json` and does not start the Python backend. Therefore:

- The settings UI and guideline rendering can be inspected.
- Browser camera access may still work through `getUserMedia()`.
- Backend reverse events and real GPIO power control are unavailable.
- Socket connection errors are expected when no backend is running.