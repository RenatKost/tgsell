# TgSell — Project Instructions for GitHub Copilot

## Project Overview
TgSell is a Ukrainian **Telegram-channel marketplace** where sellers list channels and buyers purchase them using USDT (TRC-20). The app uses an escrow-based deal flow with admin moderation, AI analysis, and auctions.

---

## Tech Stack

### Frontend
- **React 18** + **Vite 4** (SPA), entry: `src/main.jsx`
- **Tailwind CSS v3** with custom green-black neon design tokens (see `tailwind.config.js`)
- **React Router v6** — routes defined in `src/router.jsx`
- **Axios** — all API calls centralised in `src/services/api.js`
- **ApexCharts** (react-apexcharts) — stats charts
- **Formik + Yup** — forms
- **FontAwesome** — icons (some replaced with inline SVG)
- **Framer Motion** — animations

### Backend
- **FastAPI** (Python 3.12), entry: `backend/app/main.py`
- **SQLAlchemy 2.0 async** + **asyncpg** + **PostgreSQL**
- **Alembic** — migrations in `backend/alembic/versions/`
- **Pydantic v2** — schemas
- **Telethon** + **aiogram 3** — Telegram bots & channel stats collection
- **Groq API** (Llama 3.3 70B) — AI channel analysis
- **TronPy** — USDT escrow on TRON network
- **python-jose** — JWT auth

### Deployment
- **Railway** — single service, auto-deploy on `git push main`
- `Dockerfile.railway` builds both frontend (vite build → `backend/static/`) and backend
- `railway.toml` for Railway config

---

## Frontend Architecture

### State Management
Global state in `src/context/AppContext.jsx`:
- `user`, `isAuthenticated` — auth state, loaded on mount via `/auth/me`
- `favoriteIds` (Set) — loaded after login
- `theme` (`'dark'`/`'light'`) — persisted to localStorage, applied as `dark` class on `<html>`
- `login()`, `logout()`, `toggleFavorite()`

### Routes (`src/router.jsx`)
| Path | Component | Guard |
|------|-----------|-------|
| `/` | `HomePage` | public |
| `/catalog` | `CatalogPage` | public |
| `/auction` | `AuctionPage` | public |
| `/channel/:id` | `ChannelDetailsPage` | public |
| `/sell` | `SellPage` | auth |
| `/cabinet` | `CabinetPage` | auth |
| `/deal/:id` | `DealPage` | auth |
| `/profile` | `ProfilePage` | auth |
| `/admin` | `ModerCabinet` | role=moderator |

### API Client (`src/services/api.js`)
- Base URL from `VITE_API_URL` env var (default `http://localhost:8000/api`)
- Request interceptor: attaches `Authorization: Bearer <token>` from localStorage
- Response interceptor: on 401 auto-refreshes token via `/auth/refresh`, retries once; on failure clears tokens and redirects to `/`
- Exported modules: `authAPI`, `channelsAPI`, `dealsAPI`, `adminAPI`, `favoritesAPI`, `auctionsAPI`, `activityAPI`, `usersAPI`

---

## Design System (Tailwind Tokens)

**Current theme: Green-Black Neon (dark mode)**

```js
// tailwind.config.js
colors: {
  page:        '#080E0E',  // body background
  card:        '#0D1717',  // card background
  'card-border':'#1A3A2A', // card border
  'card-inner': '#0A1414', // inner sections / inputs
  'card-hover': '#122222', // hover states
  accent:      '#00FF88',  // neon green — CTA buttons, highlights
}
boxShadow: {
  neon:    '0 0 15px rgba(0, 255, 136, 0.08)',
  'neon-lg':'0 0 30px rgba(0, 255, 136, 0.12)',
}
```

**Key CSS classes to apply consistently:**
- Cards: `bg-white dark:bg-card rounded-xl border border-gray-100 dark:border-card-border shadow-sm dark:shadow-neon`
- CTA button: `bg-accent text-black font-bold shadow-lg shadow-accent/30 hover:brightness-110`
- Chart grid: use `'#1A3A2A'` as `borderColor` in ApexCharts options
- Inner blocks: `dark:bg-card-inner`

**Note:** CatalogPage, AuctionPage, DealPage, ProfilePage, SellPage, and Header still use the OLD `slate-800/slate-700` palette and have NOT been updated to the neon theme yet.

---

## Key Components

### Channel Details Page (`src/layouts/ChannelDetailsPage.jsx`)
Fetches channel + stats + health in parallel. Layout:
- **Row 1** (3-col): `DetailsCard` + `Subscribers` chart + `Views` chart
- **Row 2** (3-col): `ER` chart + `Coverage` (PostsPerDay) chart + `AIRiskScore` gauge
- **Row 3** (2-col): `ChannelHealth` + `AiAnalysis`
- **Row 4** (full): `PostsList`

`health` state is fetched at the parent and passed as props to both `ChannelHealth` and `AIRiskScore`.

### DetailsCard (`src/components/Cards/DetailsCard.jsx`)
Left column of channel details. Displays: avatar, name, subscriber trend, category badge, telegram link, 4 key metrics (views/ER/age/income), activity badges with tooltips, CPM/price-per-sub/payback strip, and the "Купити канал" button.

### AiAnalysis (`src/components/ChanelDetails/AiAnalysis.jsx`)
- Calls `/channels/:id/ai-analysis` on mount
- 2-column layout: left = AdvReach bars + sentiment distribution + content topics; right = monetization methods + ROI estimate + growth trend
- Header shows AI verdict badge (buy/hold/avoid)

### ChannelHealth (`src/components/ChanelDetails/ChannelHealth.jsx`)
- Receives `health` prop (pre-fetched by parent)
- Shows SVG health-score ring, view velocity, activity, ER quality, suspicious posts, flags list

### Charts (all in `src/components/ChanelDetails/`)
`Subscribers.jsx`, `Views.jsx`, `ER.jsx`, `Coverage.jsx` — all ApexCharts area/line charts. Use `dark:shadow-neon` and chart grid `borderColor: '#1A3A2A'`.

### PostsList (`src/components/ChanelDetails/PostsList.jsx`)
2-column card grid with pagination (20 per page).

### AuthModal (`src/components/Header/AuthModal.jsx`)
Login modal — Telegram Login Widget + Google OAuth + QR/bot-token flow.

---

## Backend Architecture

### Routers (`backend/app/routers/`)
| Router | Prefix | Key endpoints |
|--------|--------|---------------|
| `auth.py` | `/api/auth` | `/telegram`, `/google`, `/refresh`, `/me`, `/bot-check` |
| `channels.py` | `/api/channels` | CRUD + `/stats` + `/health` + `/posts` + `/ai-analysis` |
| `deals.py` | `/api/deals` | create, status, confirm-*, wallet, chat messages |
| `admin.py` | `/api/admin` | dashboard, moderation, escrow, auctions mgmt |
| `auctions.py` | `/api/auctions` | list, detail, bid, stats |
| `favorites.py` | `/api/favorites` | add/remove/list |
| `activity.py` | `/api/stats` | activity feed, gamification |

### Models (`backend/app/models/`)
- `Channel` — main channel model with all stats fields, `views_hidden` flag, `listing_type` (sale/auction/both)
- `ChannelStats` — daily historical stats (subs, views, ER, post_count)
- `ChannelPost` — individual posts with view snapshots (1h/12h/24h/48h for bot detection)
- `Deal` — escrow deal flow: created → payment_pending → paid → channel_transferring → awaiting_payout → completed
- `Auction` + `AuctionBid` — auction system
- `User` — telegram_id, google_id, role, usdt_wallet

### AI Analysis (`backend/app/services/ai_analysis.py`)
- Sends channel data + last 20 posts + last 14 days stats to Groq
- Returns: summary, audience_quality, growth_trend, content_analysis, content_topics[5], sentiment_positive/neutral/negative (%), monetization[5] methods with income_min/max, total_potential_income_min/max, risks, opportunities, fair_price_estimate, roi_months, verdict (buy/hold/avoid), verdict_reason, score

### Background Tasks (`backend/app/tasks/`)
| Task | Interval | Purpose |
|------|----------|---------|
| `stats_collector.py` | 3h | Collect channel stats via Telethon |
| `run_view_tracker` | 3h | Update view snapshots for recent posts |
| `health_monitor.py` | 30min | Monitor channel health |
| `payment_checker.py` | 30s | Check USDT payments on TRON |
| `auction_manager.py` | 60s | End auctions, process winners |

### Auth Flow
1. Telegram Login Widget → `/auth/telegram` — verifies HMAC signature
2. Google OAuth → `/auth/google` — verifies id_token with google-auth
3. Returns `access_token` (30min) + `refresh_token` (7 days), both JWT
4. Bot token flow: `/auth/bot-token` creates a one-time token → user sends to Telegram bot → `/auth/bot-check` polls for completion

### Deal Flow (Escrow)
1. Buyer creates deal → system generates TRON wallet
2. Buyer sends USDT to escrow wallet → payment_checker detects it
3. Both parties confirm readiness
4. Seller transfers channel admin rights
5. Admin releases USDT to seller wallet (minus 3% fee)

---

## Environment Variables

### Frontend (`.env`)
```
VITE_API_URL=http://localhost:8000/api
```

### Backend (`backend/.env`)
```
DATABASE_URL=postgresql+asyncpg://...
BOT_TOKEN_AUTH=...       # Telegram Login Widget bot
BOT_TOKEN_ALERTS=...     # aiogram notification bot
BOT_TOKEN_STATS=...      # Bot API stats bot
TELEGRAM_API_ID=...
TELEGRAM_API_HASH=...
TELETHON_SESSION_STRING=...   # Required for deep analytics
GROQ_API_KEY=...         # For AI analysis
TRON_MASTER_WALLET_ADDRESS=...
TRON_MASTER_WALLET_PRIVATE_KEY=...
JWT_SECRET_KEY=...
```

---

## Known Issues / Pending Work
- CatalogPage, AuctionPage, DealPage, ProfilePage still use old `slate-*` palette — not yet updated to neon theme
- Layout.jsx body wrapper still uses `dark:bg-slate-950` instead of `dark:bg-page`
- CatalogCard uses `dark:bg-slate-800` / `#3498db` blue — not updated to green accent

---

## Development Commands
```bash
# Frontend
npm run dev       # dev server on :5173
npm run build     # production build → dist/

# Backend
cd backend
uvicorn app.main:app --reload  # dev server on :8000
alembic upgrade head           # run migrations

# Deploy (Railway auto-deploys on push to main)
git add -A && git commit -m "..." && git push
```

## Recent Git History (significant commits)
- `80a9507` — Green-black neon theme overhaul (shadow-neon cards, SVG icons, new color tokens)
- `0ce438e` — PostsList 2-col grid, AiAnalysis sentiment bars + keyword topics
- `9b3d5d0` — ChannelDetailsPage layout restructure (AIRiskScore, 3+3+2+1 grid)
- `387d7e2` — Fix f-string quoting in ai_analysis.py
- `75f136e` — Fix IndentationError in channels.py (Railway deploy fix)

---

## Instructions for GitHub Copilot (self-maintenance)
After completing any major feature or fix, **always update this file** before the final `git commit`:
1. Add a new line to "Recent Git History" with the commit hash and description.
2. Update "Known Issues / Pending Work" — remove resolved items, add new ones.
3. Update any section that changed (new components, new routes, new env vars, design system changes).
Keep entries concise — one line per fact. Do not add prose or explanations.
