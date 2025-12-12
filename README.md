# SPX ATM Straddle Monitor

A real-time web dashboard for monitoring SPX ATM (At-The-Money) straddles using Interactive Brokers API.

## Features

- Real-time SPX spot price monitoring
- ATM straddle pricing for multiple expiration dates (0DTE to 5DTE)
- Live Greeks display (IV, Gamma, Theta)
- Modern React-based web interface
- WebSocket-based real-time updates

## Prerequisites

- Python 3.10+
- Node.js 16+ and npm
- Interactive Brokers TWS or IB Gateway running
- API access enabled in TWS/IB Gateway

## Setup

### 1. Install Python Dependencies

```bash
pip install -r requirements.txt
```

Note: `ib_async` needs to be installed from GitHub:
```bash
pip install git+https://github.com/ib-api-reloaded/ib_async.git
```

### 2. Install React Dependencies

```bash
cd frontend
npm install
```

### 3. Build React App

For development (with hot reload):
```bash
cd frontend
npm start
```

For production:
```bash
cd frontend
npm run build
```

### 4. Configure TWS/IB Gateway

1. Open TWS or IB Gateway
2. Go to **Configure → API → Settings**
3. Enable **"Enable ActiveX and Socket Clients"**
4. Set **Socket port** to `7496` (Live) or `7497` (Paper)
5. Add `127.0.0.1` to **Trusted IPs** (or leave empty for localhost)
6. Restart TWS/IB Gateway

### 5. Update Configuration (if needed)

Edit `app.py` to change:
- `PORT`: IB API port (default: 7496 for Live, 7497 for Paper)
- `CLIENT_ID`: Unique client ID (default: 3)
- `UNDERLYING`: Underlying symbol (default: "SPX")
- `EXCHANGE`: Exchange (default: "CBOE")

## Running the Application

### Development Mode

**Terminal 1 - Start Flask backend:**
```bash
python app.py
```

**Terminal 2 - Start React dev server:**
```bash
cd frontend
npm start
```

Then open http://localhost:3000 in your browser.

### Production Mode

1. Build the React app:
```bash
cd frontend
npm run build
```

2. Start the Flask server (it will serve the React build):
```bash
python app.py
```

3. Open http://localhost:5000 in your browser.

## Dashboard Features

- **Spot Price**: Current SPX index price
- **Active Strike**: Nearest ATM strike being monitored
- **Straddle Data Table**: Shows for each expiration:
  - Days to Expiration (DTE)
  - Expiry date
  - Call bid/ask prices
  - Put bid/ask prices
  - Total straddle cost
  - Implied Volatility (IV)
  - Gamma
  - Theta

## Troubleshooting

### Connection Issues

- Ensure TWS/IB Gateway is running
- Verify API is enabled in TWS/IB Gateway settings
- Check that the port matches your configuration
- Make sure `127.0.0.1` is in Trusted IPs

### No Data Displaying

- Wait a few seconds for initial data to load
- Check browser console for errors
- Verify market data subscription in TWS
- Ensure you're connected during market hours (or have delayed data subscription)

## Project Structure

```
glantz-trading/
├── app.py                 # Flask backend with WebSocket support
├── livestr.py            # Original terminal-based monitor
├── requirements.txt      # Python dependencies
├── frontend/             # React application
│   ├── src/
│   │   ├── App.js        # Main React component
│   │   ├── App.css       # Styles
│   │   └── index.js      # Entry point
│   ├── public/
│   └── package.json      # Node dependencies
└── README.md
```

## License

MIT

