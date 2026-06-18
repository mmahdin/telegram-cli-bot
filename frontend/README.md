# Frontend

React + Vite panel for private Telegram dialogs.

## Setup

```bash
cd src/frontend
npm install
npm run dev
```

Default backend URL is `http://localhost:8000`.

For a remote backend:

```bash
VITE_API_BASE_URL=http://SERVER_IP:8000 npm run dev
```

The app uses REST for dialogs/messages/actions and WebSocket for real-time updates.
