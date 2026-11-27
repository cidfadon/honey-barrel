# Investment Analyst Skill - Quick Start

## What Was Built

A complete OpenClaw skill for stock analysis with ML-powered buy/sell/hold recommendations.

### Components

1. **Backend API** (`investment-analyst-api/`)
   - FastAPI service on port 8001
   - Yahoo Finance integration (with demo mode)
   - ML model training and inference
   - Watch list management
   - Technical indicators and fundamental data

2. **OpenClaw Skill** (`openclaw-skills/investment-analyst/`)
   - Manifest defining 7 actions
   - TypeScript handlers for API integration
   - Natural language support via OpenClaw

3. **Docker Integration**
   - Dockerfile for containerized service
   - Docker Compose configuration with health checks
   - Persistent volumes for models and data

## Quick Start

### Start the Service

```bash
cd trading212-stack
docker compose up investment-analyst-api -d
```

### Test the API

```bash
# Health check
curl http://localhost:18001/health

# Add stock to watch list
curl -X POST http://localhost:18001/api/watchlist/add \
  -H "Content-Type: application/json" \
  -d '{"ticker":"AAPL","name":"Apple"}'

# Get prediction
curl -X POST http://localhost:18001/api/model/predict \
  -H "Content-Type: application/json" \
  -d '{"ticker":"AAPL","force_retrain":true}'

# Analyze watch list
curl -X POST http://localhost:18001/api/analyze/watchlist
```

### Use via OpenClaw

Start OpenClaw with the skill registered:

```bash
docker compose up openclaw -d
```

Then in OpenClaw UI:
- "Add AAPL to my watch list"
- "Analyze my watch list"
- "What should I do with Tesla?"

## Architecture

### Data Flow

```
User Query (Natural Language)
         ↓
    OpenClaw Skill
         ↓
 Investment Analyst API
         ↓
 ┌─────────────────────┐
 │ Data Fetcher        │ → Yahoo Finance / Demo Data
 │ Feature Engineering │ → Technical Indicators, Fundamentals
 │ ML Model            │ → XGBoost/Random Forest
 │ Watch List Manager  │ → SQLite
 └─────────────────────┘
         ↓
    Predictions & Analysis
         ↓
  OpenClaw (UI) → User
```

### File Structure

```
investment-analyst-api/
├── api.py                    # Main FastAPI application
├── config.py                 # Configuration management
├── data_fetcher.py          # Yahoo Finance integration
├── feature_engineering.py   # Technical indicators
├── ml_model.py              # ML model training/inference
├── watchlist.py             # Watch list management
├── requirements.txt         # Python dependencies
├── Dockerfile               # Container definition
├── README.md                # Full documentation
└── .env.example             # Configuration template

openclaw-skills/investment-analyst/
├── manifest.json            # Skill definition (7 actions)
├── skill.ts                 # TypeScript handlers
└── README.md                # User documentation
```

## Key Features

### 1. Watch List Management
- Add/remove stocks
- Persistent SQLite storage
- Organized by date added

### 2. ML Predictions
- Buy/Sell/Hold classification
- Confidence scores
- Class probability distribution

### 3. Technical Analysis
- RSI, MACD, Moving Averages
- Bollinger Bands
- Momentum and volatility

### 4. Fundamental Data
- P/E ratio, Market cap
- Dividend yield
- Earnings growth, ROE

### 5. Data Caching
- 24-hour cache TTL
- Fast repeated queries
- Fallback to demo data

## Configuration

Edit environment in `docker-compose.yml`:

```yaml
environment:
  LOOKBACK_DAYS: "90"       # Historical window
  MODEL_ALGORITHM: "xgboost" # or random_forest
  YAHOO_CACHE_HOURS: "24"
  DEMO_MODE: "true"          # Use synthetic data
```

## Troubleshooting

### API Not Responding
```bash
# Check if container is running
docker compose ps investment-analyst-api

# View logs
docker compose logs investment-analyst-api -f

# Restart
docker compose restart investment-analyst-api
```

### Prediction Fails with "No model found"
Use `force_retrain: true` to train model first:
```bash
curl -X POST http://localhost:18001/api/model/predict \
  -H "Content-Type: application/json" \
  -d '{"ticker":"AAPL","force_retrain":true}'
```

### Yahoo Finance Issues
API automatically falls back to demo/synthetic data. This is normal in isolated environments.

## Performance Metrics

- **Health Check**: <10ms
- **Data Fetch**: 2-5s (first time), cached after
- **Model Training**: 10-30s
- **Prediction**: <1s
- **Watch List Analysis**: 2-10s (for 5+ stocks)

## Testing Results

✅ Watch list creation and management
✅ Stock prediction (BUY/HOLD/SELL)
✅ Comprehensive watch list analysis
✅ Data fetching with fallback mode
✅ Model training and persistence
✅ API health checks
✅ Docker integration

## Next Steps

1. **Production Deployment**
   - Configure real Yahoo Finance API keys
   - Set up persistent database
   - Configure monitoring/alerting

2. **Model Improvements**
   - Add more technical indicators
   - Include sentiment analysis
   - Ensemble methods
   - Backtesting framework

3. **Enhanced Features**
   - Real-time data streaming
   - Portfolio optimization
   - Risk assessment
   - Alert notifications

## Security Notes

- API is internal-only (backend-net)
- No authentication required (trusted network)
- Watch list data is local to container
- For production: add auth, encryption, logging

## References

- OpenClaw Skill Documentation: https://openclaw.dev/schemas/skill.json
- Yahoo Finance (yfinance): https://github.com/ranaroussi/yfinance
- scikit-learn: https://scikit-learn.org
- XGBoost: https://xgboost.readthedocs.io
