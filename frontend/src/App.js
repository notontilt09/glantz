import React, { useState, useEffect, useRef } from 'react';
import { io } from 'socket.io-client';
import './App.css';

function App() {
  const [socket, setSocket] = useState(null);
  const [data, setData] = useState({
    spot_price: 0,
    active_strike: 0,
    straddles: [],
    status: 'disconnected',
    last_update: null
  });
  const [status, setStatus] = useState('disconnected');
  const [flashKeys, setFlashKeys] = useState(new Set());
  const prevDataRef = useRef({});

  useEffect(() => {
    // Connect to Flask backend
    const newSocket = io('http://localhost:5000');
    setSocket(newSocket);

    newSocket.on('connect', () => {
      console.log('Connected to server');
      setStatus('connected');
    });

    newSocket.on('disconnect', () => {
      console.log('Disconnected from server');
      setStatus('disconnected');
    });

    newSocket.on('status_update', (statusData) => {
      setStatus(statusData.status);
    });

    newSocket.on('data_update', (newData) => {
      // Track which values changed for flash effect
      const changedKeys = new Set();
      const prev = prevDataRef.current;
      const isFirstUpdate = !prev.straddles || prev.straddles.length === 0;
      
      // Only flash if this is not the first update
      if (!isFirstUpdate) {
        // Check spot price
        if (prev.spot_price !== undefined && Math.abs((prev.spot_price || 0) - (newData.spot_price || 0)) > 0.01) {
          changedKeys.add('spot_price');
        }
        
        // Check active strike
        if (prev.active_strike !== undefined && prev.active_strike !== newData.active_strike) {
          changedKeys.add('active_strike');
        }
        
        // Check straddles
        if (prev.straddles && newData.straddles) {
          newData.straddles.forEach((straddle, index) => {
            const prevStraddle = prev.straddles[index];
            if (prevStraddle) {
              const fields = ['call_bid', 'call_ask', 'put_bid', 'put_ask', 'straddle_cost', 'iv', 'gamma', 'theta'];
              fields.forEach(field => {
                const prevVal = prevStraddle[field] || 0;
                const newVal = straddle[field] || 0;
                if (Math.abs(prevVal - newVal) > 0.001) {
                  changedKeys.add(`straddle_${index}_${field}`);
                }
              });
            }
          });
        }
        
        // Set flash keys and clear after animation
        if (changedKeys.size > 0) {
          setFlashKeys(changedKeys);
          setTimeout(() => {
            setFlashKeys(new Set());
          }, 1000);
        }
      }
      
      // Update data
      prevDataRef.current = JSON.parse(JSON.stringify(newData));
      setData(newData);
      if (newData.status) {
        setStatus(newData.status);
      }
    });

    return () => {
      newSocket.close();
    };
  }, []);

  const formatPrice = (price) => {
    if (price === 0 || price === null || price === undefined) return '--';
    return price.toFixed(2);
  };

  const formatPercent = (value) => {
    if (value === 0 || value === null || value === undefined) return '--';
    return (value * 100).toFixed(1) + '%';
  };

  const formatGreek = (value) => {
    if (value === 0 || value === null || value === undefined) return '--';
    return value.toFixed(4);
  };

  const formatTheta = (value) => {
    if (value === 0 || value === null || value === undefined) return '--';
    return value.toFixed(2);
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return '--';
    try {
      const date = new Date(dateStr);
      return date.toLocaleTimeString();
    } catch {
      return dateStr;
    }
  };

  const getStatusClass = () => {
    return `status-indicator status-${status}`;
  };

  const getStatusText = () => {
    const statusMap = {
      connected: 'Connected',
      connecting: 'Connecting...',
      error: 'Error',
      disconnected: 'Disconnected'
    };
    return statusMap[status] || status;
  };

  return (
    <div className="App">
      <div className="container">
        <div className="header">
          <div>
            <h1>SPX ATM Straddle Monitor</h1>
            <div className="subtitle">Real-time options market data dashboard</div>
          </div>
          <div className={getStatusClass()}>
            <div className="status-dot"></div>
            <span>{getStatusText()}</span>
          </div>
        </div>

        <div className="stats-grid">
          <div className="stat-card">
            <div className="stat-label">Spot Price</div>
            <div className={`stat-value ${flashKeys.has('spot_price') ? 'flash' : ''}`}>
              {formatPrice(data.spot_price)}
            </div>
          </div>
          <div className="stat-card">
            <div className="stat-label">Active Strike</div>
            <div className={`stat-value small ${flashKeys.has('active_strike') ? 'flash' : ''}`}>
              {data.active_strike || '--'}
            </div>
          </div>
          <div className="stat-card">
            <div className="stat-label">Last Update</div>
            <div className="stat-value small" style={{ fontSize: '14px' }}>
              {formatDate(data.last_update)}
            </div>
          </div>
        </div>

        <div className="dashboard-table">
          {data.straddles.length === 0 ? (
            <div className="loading">Connecting to market data...</div>
          ) : (
            <>
              <table>
                <thead>
                  <tr>
                    <th>DTE</th>
                    <th>Expiry</th>
                    <th>Call Bid</th>
                    <th>Call Ask</th>
                    <th>Put Bid</th>
                    <th>Put Ask</th>
                    <th>Straddle Cost</th>
                    <th>IV</th>
                    <th>Gamma</th>
                    <th>Theta</th>
                  </tr>
                </thead>
                <tbody>
                  {data.straddles.map((straddle, index) => (
                    <tr key={index}>
                      <td>
                        <span className={`dte-badge ${straddle.dte === '0DTE' ? 'zero' : ''}`}>
                          {straddle.dte}
                        </span>
                      </td>
                      <td>{straddle.expiry}</td>
                      <td className={`price-cell bid ${flashKeys.has(`straddle_${index}_call_bid`) ? 'flash' : ''}`}>
                        {formatPrice(straddle.call_bid)}
                      </td>
                      <td className={`price-cell ask ${flashKeys.has(`straddle_${index}_call_ask`) ? 'flash' : ''}`}>
                        {formatPrice(straddle.call_ask)}
                      </td>
                      <td className={`price-cell bid ${flashKeys.has(`straddle_${index}_put_bid`) ? 'flash' : ''}`}>
                        {formatPrice(straddle.put_bid)}
                      </td>
                      <td className={`price-cell ask ${flashKeys.has(`straddle_${index}_put_ask`) ? 'flash' : ''}`}>
                        {formatPrice(straddle.put_ask)}
                      </td>
                      <td className={`straddle-cost ${flashKeys.has(`straddle_${index}_straddle_cost`) ? 'flash' : ''}`}>
                        ${formatPrice(straddle.straddle_cost)}
                      </td>
                      <td className={`greek iv ${flashKeys.has(`straddle_${index}_iv`) ? 'flash' : ''}`}>
                        {formatPercent(straddle.iv)}
                      </td>
                      <td className={`greek gamma ${flashKeys.has(`straddle_${index}_gamma`) ? 'flash' : ''}`}>
                        {formatGreek(straddle.gamma)}
                      </td>
                      <td className={`greek theta ${flashKeys.has(`straddle_${index}_theta`) ? 'flash' : ''}`}>
                        {formatTheta(straddle.theta)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div className="last-update">
                Last updated: {formatDate(data.last_update)}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

export default App;

