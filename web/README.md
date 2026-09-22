# Campaign Heroes UI

Vite + React + Tailwind. Flask serves `dist` at `/app`.

```bash
npm ci
npm run dev      # proxies /api to Flask :8080
npm run build    # required for Flask / Docker
```

Routes: `/app/daily` `/app/review` `/app/create` `/app/calendar` `/app/publish` `/app/results` `/app/other`

Aliases without `/app` redirect. Classic desk stays at `/`. Do not delete leftover HTML.
