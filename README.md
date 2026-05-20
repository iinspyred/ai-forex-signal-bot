# AI Forex Signal Bot

Production-ready FastAPI forex signal scanner that reads market candles, generates technical BUY/SELL signals, stores signals in SQLite, and sends Telegram alerts.

## Features

- FastAPI dashboard endpoints: `/`, `/health`, `/signals`, `/stats`
- Async TwelveData candle fetching for `EUR/USD`, `GBP/USD`, `USD/JPY`, `AUD/USD`
- Optional Alpha Vantage FX intraday candle provider
- Finnhub quote enrichment with graceful fallback
- RSI, EMA 20/50, MACD, ATR volatility, volume confirmation
- Duplicate signal prevention and confidence score
- ATR-based stop loss, take profit, trailing stop, and risk/reward levels
- Telegram alerts, startup notification, hourly heartbeat, and error alerts
- Telegram commands: `/start`, `/help`, `/status`, `/signals`, `/stats`
- Telegram polling by default, webhook mode when `TELEGRAM_WEBHOOK_URL` is set
- TradingView webhook endpoint: `POST /webhooks/tradingview`
- Rotating application and trade logs
- Docker, Render, Procfile, and Railway compatibility files

## Security Notice

Never commit real API keys or Telegram tokens. If credentials were pasted into a chat, rotate them before production deployment.

Secrets must be provided through environment variables only:

```bash
TWELVEDATA_API_KEY=
FINNHUB_API_KEY=
ALPHAVANTAGE_API_KEY=
MARKET_DATA_PROVIDER=twelvedata
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
RISK_ATR_STOP_MULTIPLIER=1.5
RISK_REWARD_RATIO=2.0
TRAILING_STOP_ATR_MULTIPLIER=1.0
ACCOUNT_RISK_PERCENT=1.0
```

## Local Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Edit `.env` and add your rotated keys.

Run the app:

```bash
uvicorn app.main:app --reload
```

Open:

- `http://127.0.0.1:8000/`
- `http://127.0.0.1:8000/health`
- `http://127.0.0.1:8000/signals`
- `http://127.0.0.1:8000/stats`

## Telegram Setup

1. Create a bot with BotFather.
2. Set `TELEGRAM_BOT_TOKEN`.
3. Start the app locally.
4. Send `/start` to the bot.
5. Copy the chat ID from the bot reply into `TELEGRAM_CHAT_ID`.

Polling is used by default. For webhook mode, set:

```bash
TELEGRAM_WEBHOOK_URL=https://your-domain.com/telegram/webhook
```

## Render Deployment

1. Push this project to a private GitHub repository.
2. In Render, create a new Web Service from that repo.
3. Render will detect `render.yaml` and the Dockerfile.
4. Add environment variables in the Render dashboard.
5. Deploy.

Start command:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Health check:

```text
/health
```

## Market Data Limits

The default provider is TwelveData:

```env
MARKET_DATA_PROVIDER=twelvedata
MARKET_DATA_MIN_INTERVAL_SECONDS=8
SCAN_INTERVAL_SECONDS=120
```

This spaces candle requests out so free or low-tier minute limits are less likely to be exceeded. To use Alpha Vantage instead, add an Alpha Vantage key and set:

```env
MARKET_DATA_PROVIDER=alphavantage
ALPHAVANTAGE_API_KEY=your_key_here
```

Alpha Vantage uses the official `FX_INTRADAY` endpoint for forex pairs.

## Risk Engine

Every generated signal includes an ATR-based risk plan:

```text
Entry
Stop Loss
Take Profit
Trailing Stop
Risk/Reward
Account Risk %
```

The default values are:

```env
RISK_ATR_STOP_MULTIPLIER=1.5
RISK_REWARD_RATIO=2.0
TRAILING_STOP_ATR_MULTIPLIER=1.0
ACCOUNT_RISK_PERCENT=1.0
```

## GitHub Auto Deploy

Render auto deploys when connected to the GitHub repository and `autoDeploy` is enabled in `render.yaml`.

Recommended repo creation:

```bash
gh repo create ai-forex-signal-bot --private --source . --remote origin
git add .
git commit -m "Initial production forex signal bot"
git push -u origin main
```

## TradingView Webhook

Endpoint:

```text
POST /webhooks/tradingview
```

Example payload:

```json
{
  "pair": "EUR/USD",
  "timeframe": "5m",
  "action": "BUY",
  "price": 1.0845,
  "message": "External confirmation"
}
```

## Troubleshooting

- Missing environment variables: confirm all required keys are set in `.env` or Render.
- Telegram sends no alerts: send `/start` to the bot and set the returned chat ID.
- No signals: strict filters may produce no signal in quiet markets.
- TwelveData errors: check API quota, symbol support, and interval names.
- Render restarts: inspect `/health`, Render logs, and `logs/app.log`.

## Disclaimer

This bot provides technical-analysis alerts only. It does not place trades and is not financial advice.
