import asyncio
import math
import os
import socket
import threading
from datetime import datetime

from flask import Flask, send_from_directory
from flask_socketio import SocketIO, emit
from ib_async import IB, Index, Option

app = Flask(
    __name__, static_folder="frontend/build/static", template_folder="frontend/build"
)
app.config["SECRET_KEY"] = "your-secret-key-here"
socketio = SocketIO(app, cors_allowed_origins="*")

# Configuration
PORT = 7496  # 7497 (Paper) or 7496 (Live)
CLIENT_ID = 3
UNDERLYING = "SPX"
EXCHANGE = "CBOE"

# Shared state
dashboard_data = {
    "spot_price": 0.0,
    "active_strike": 0,
    "straddles": [],
    "status": "disconnected",
    "last_update": None,
}


def get_nearest_strike(price, step=5):
    """Rounds price to the nearest strike interval (default 5 for SPX)."""
    return step * round(price / step)


async def get_next_n_spxw_expiries(ib, contract, n=6):
    """
    Fetches option chains, looks for SPXW, and returns the next N expirations.
    Returns a list of (expiry_date, trading_class).
    """
    if not contract.conId:
        await ib.qualifyContractsAsync(contract)

    print(f"Fetching Option Chains for {contract.symbol}...")
    chains = await ib.reqSecDefOptParamsAsync(
        contract.symbol, "", contract.secType, contract.conId
    )

    # Filter for SPXW (PM Settled) on SMART or CBOE
    spxw_chains = [
        c for c in chains if c.tradingClass == "SPXW" and c.exchange == "SMART"
    ]

    # Fallback if specific SPXW logic fails (rare for SPX)
    if not spxw_chains:
        print("Warning: No SPXW chains found. Falling back to standard search.")
        spxw_chains = [c for c in chains if c.exchange == "SMART"]

    all_expirations = set()
    for chain in spxw_chains:
        all_expirations.update(chain.expirations)

    sorted_exp = sorted(list(all_expirations))

    # Filter for today and future
    now_str = datetime.now().strftime("%Y%m%d")
    future_exps = [e for e in sorted_exp if e >= now_str]

    # Select top N
    selected = future_exps[:n]

    # Return list of (expiry, tradingClass)
    t_class = spxw_chains[0].tradingClass if spxw_chains else "SPX"

    return [(exp, t_class) for exp in selected]


def get_greeks(ticker):
    """
    Safely extracts Implied Vol, Gamma, and Theta from a ticker's modelGreeks.
    Returns (iv, gamma, theta) or (0, 0, 0) if not available.
    """
    if ticker.modelGreeks:
        iv = ticker.modelGreeks.impliedVol if ticker.modelGreeks.impliedVol else 0.0
        gamma = ticker.modelGreeks.gamma if ticker.modelGreeks.gamma else 0.0
        theta = ticker.modelGreeks.theta if ticker.modelGreeks.theta else 0.0
        return iv, gamma, theta
    return 0.0, 0.0, 0.0


def check_port_open(host, port):
    """Check if a port is open and accepting connections."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception:
        return False


def is_valid_price(val):
    """Check if price is a valid positive number (not NaN)."""
    return val and isinstance(val, float) and not math.isnan(val) and val > 0


async def collect_market_data():
    """Main async function to collect market data and emit to clients."""
    global dashboard_data

    ib = IB()

    print(f"Connecting to TWS/IB Gateway on port {PORT}...")
    dashboard_data["status"] = "connecting"
    socketio.emit("status_update", {"status": "connecting"})

    # Check if port is open
    if not check_port_open("127.0.0.1", PORT):
        error_msg = f"Port {PORT} is not accepting connections"
        print(f"❌ {error_msg}")
        dashboard_data["status"] = "error"
        socketio.emit("status_update", {"status": "error", "message": error_msg})
        return

    try:
        await ib.connectAsync("127.0.0.1", PORT, clientId=CLIENT_ID)
        print("✓ Connected successfully!")
        dashboard_data["status"] = "connected"
        socketio.emit("status_update", {"status": "connected"})
    except Exception as e:
        error_msg = f"Connection failed: {e}"
        print(f"❌ {error_msg}")
        dashboard_data["status"] = "error"
        socketio.emit("status_update", {"status": "error", "message": error_msg})
        return

    # Request Delayed (3) or Live (1) data
    ib.reqMarketDataType(3)

    # Get underlying price
    print(f"Fetching {UNDERLYING} price...")
    spx = Index(UNDERLYING, EXCHANGE)
    await ib.qualifyContractsAsync(spx)

    spx_ticker = ib.reqMktData(spx, "", False, False)

    print("Waiting for data stream...")
    attempts = 0
    while not (is_valid_price(spx_ticker.last) or is_valid_price(spx_ticker.close)):
        await asyncio.sleep(0.2)
        attempts += 1
        if attempts > 50:
            print("Timeout waiting for SPX data. Check subscription.")
            dashboard_data["status"] = "error"
            socketio.emit(
                "status_update",
                {"status": "error", "message": "Timeout waiting for SPX data"},
            )
            return

    # Get expiries
    expiries_info = await get_next_n_spxw_expiries(ib, spx, n=6)

    if not expiries_info:
        print("Error: Could not find expirations.")
        dashboard_data["status"] = "error"
        socketio.emit(
            "status_update",
            {"status": "error", "message": "Could not find expirations"},
        )
        return

    print(f"Found {len(expiries_info)} expirations: {[e[0] for e in expiries_info]}")
    print("Starting Live Multi-DTE Dashboard...")

    # State variables
    current_atm_strike = 0
    tickers_map = {}
    active_tickers_list = []

    # Main loop
    try:
        while ib.isConnected():
            # Refresh Underlying
            cur_spot = (
                spx_ticker.last if is_valid_price(spx_ticker.last) else spx_ticker.close
            )
            if not is_valid_price(cur_spot):
                cur_spot = 0.0

            # Dynamic strike logic
            target_strike = get_nearest_strike(cur_spot)

            # If strike moved, update contracts
            if target_strike != current_atm_strike and target_strike > 0:
                print(
                    f"Strike Update: Moving from {current_atm_strike} to {target_strike}..."
                )

                # Cleanup old data
                for t in active_tickers_list:
                    ib.cancelMktData(t.contract)
                active_tickers_list = []
                tickers_map = {}

                # Build new contracts
                contracts = []
                for i, (expiry, t_class) in enumerate(expiries_info):
                    c = Option(
                        UNDERLYING,
                        expiry,
                        target_strike,
                        "C",
                        "SMART",
                        tradingClass=t_class,
                    )
                    p = Option(
                        UNDERLYING,
                        expiry,
                        target_strike,
                        "P",
                        "SMART",
                        tradingClass=t_class,
                    )
                    contracts.extend([c, p])

                # Qualify contracts
                try:
                    contracts = await ib.qualifyContractsAsync(*contracts)
                except Exception as e:
                    print(f"Error qualifying contracts for strike {target_strike}: {e}")
                    await asyncio.sleep(5)
                    continue

                # Request new data
                for i in range(0, len(contracts), 2):
                    call_c = contracts[i]
                    put_c = contracts[i + 1]

                    c_ticker = ib.reqMktData(call_c, "100,101,104,106", False, False)
                    p_ticker = ib.reqMktData(put_c, "100,101,104,106", False, False)

                    active_tickers_list.extend([c_ticker, p_ticker])

                    expiry_date = call_c.lastTradeDateOrContractMonth
                    dte_index = i // 2
                    tickers_map[expiry_date] = {
                        "dte_label": f"{dte_index}DTE",
                        "call": c_ticker,
                        "put": p_ticker,
                    }

                current_atm_strike = target_strike
                print("Contracts updated. Waiting for quotes and greeks...")
                await asyncio.sleep(2)

            # Collect data for dashboard
            straddles = []
            for i, (expiry, _) in enumerate(expiries_info):
                if expiry not in tickers_map:
                    continue

                data = tickers_map[expiry]
                c_tick = data["call"]
                p_tick = data["put"]
                label = data["dte_label"]

                # Get prices
                def get_prices(t):
                    b = t.bid if is_valid_price(t.bid) else 0.0
                    a = t.ask if is_valid_price(t.ask) else 0.0
                    return b, a

                cb, ca = get_prices(c_tick)
                pb, pa = get_prices(p_tick)

                # Mid prices
                cm = (cb + ca) / 2 if (cb > 0 and ca > 0) else 0.0
                pm = (pb + pa) / 2 if (pb > 0 and pa > 0) else 0.0
                cost = cm + pm

                # Greeks
                c_iv, c_gamma, c_theta = get_greeks(c_tick)
                p_iv, p_gamma, p_theta = get_greeks(p_tick)

                # Straddle Greeks
                if c_iv > 0 and p_iv > 0:
                    straddle_iv = (c_iv + p_iv) / 2
                else:
                    straddle_iv = c_iv or p_iv

                straddle_gamma = c_gamma + p_gamma
                straddle_theta = c_theta + p_theta

                straddles.append(
                    {
                        "dte": label,
                        "expiry": expiry,
                        "call_bid": cb,
                        "call_ask": ca,
                        "put_bid": pb,
                        "put_ask": pa,
                        "straddle_cost": cost,
                        "iv": straddle_iv,
                        "gamma": straddle_gamma,
                        "theta": straddle_theta,
                    }
                )

            # Update shared state and emit
            dashboard_data["spot_price"] = cur_spot
            dashboard_data["active_strike"] = current_atm_strike
            dashboard_data["straddles"] = straddles
            dashboard_data["last_update"] = datetime.now().isoformat()

            socketio.emit("data_update", dashboard_data)

            await asyncio.sleep(5)  # Update every 5 seconds

    except Exception as e:
        print(f"Loop error: {e}")
        dashboard_data["status"] = "error"
        socketio.emit("status_update", {"status": "error", "message": str(e)})
    finally:
        if ib.isConnected():
            ib.disconnect()


def run_async_loop():
    """Run the async loop in a separate thread."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(collect_market_data())


@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve(path):
    if path != "" and os.path.exists(os.path.join(app.template_folder, path)):
        return send_from_directory(app.template_folder, path)
    else:
        return send_from_directory(app.template_folder, "index.html")


@socketio.on("connect")
def handle_connect():
    """Send current data when client connects."""
    emit("data_update", dashboard_data)
    emit("status_update", {"status": dashboard_data["status"]})


@socketio.on("disconnect")
def handle_disconnect():
    print("Client disconnected")


if __name__ == "__main__":
    # Start market data collection in background thread
    data_thread = threading.Thread(target=run_async_loop, daemon=True)
    data_thread.start()

    # Run Flask app
    print("\n" + "=" * 50)
    print("SPX ATM STRADDLE MONITOR - Web Dashboard")
    print("=" * 50)
    print(f"Dashboard available at: http://localhost:5000")
    print("Press Ctrl+C to stop")
    print("=" * 50 + "\n")

    socketio.run(
        app, host="0.0.0.0", port=5000, debug=False, allow_unsafe_werkzeug=True
    )
