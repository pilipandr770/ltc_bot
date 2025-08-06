from flask import Flask, jsonify, render_template_string
import threading
import time
import os
from datetime import datetime

app = Flask(__name__)

# Global variables for bot status
bot_status = {
    "running": False,
    "last_update": None,
    "current_price": 0,
    "current_asset": "USDT",
    "ma7": 0,
    "ma25": 0,
    "balance_usdt": 0,
    "balance_ltc": 0
}

# HTML template for monitoring page
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>LTC Trading Bot Monitor</title>
    <meta http-equiv="refresh" content="30">
    <style>
        body { font-family: Arial, sans-serif; margin: 40px; background: #f0f0f0; }
        .container { background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        .status { padding: 20px; margin: 10px 0; border-radius: 5px; }
        .running { background: #d4edda; border: 1px solid #c3e6cb; color: #155724; }
        .stopped { background: #f8d7da; border: 1px solid #f5c6cb; color: #721c24; }
        .metric { display: inline-block; margin: 10px 20px 10px 0; padding: 10px; background: #e9ecef; border-radius: 5px; }
        .price { font-size: 24px; font-weight: bold; color: #007bff; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🤖 LTC Trading Bot Monitor</h1>
        
        <div class="status {{ 'running' if status.running else 'stopped' }}">
            <h2>Status: {{ 'Running ✅' if status.running else 'Stopped ❌' }}</h2>
            <p>Last Update: {{ status.last_update or 'Never' }}</p>
        </div>
        
        <h3>📊 Current Market Data</h3>
        <div class="metric price">Price: ${{ "%.4f"|format(status.current_price) }}</div>
        <div class="metric">Current Asset: {{ status.current_asset }}</div>
        <div class="metric">MA7: {{ "%.4f"|format(status.ma7) }}</div>
        <div class="metric">MA25: {{ "%.4f"|format(status.ma25) }}</div>
        
        <h3>💰 Balances</h3>
        <div class="metric">USDT: {{ "%.4f"|format(status.balance_usdt) }}</div>
        <div class="metric">LTC: {{ "%.6f"|format(status.balance_ltc) }}</div>
        
        <p><em>Page auto-refreshes every 30 seconds</em></p>
    </div>
</body>
</html>
"""

@app.route('/')
def monitor():
    return render_template_string(HTML_TEMPLATE, status=bot_status)

@app.route('/api/status')
def api_status():
    return jsonify(bot_status)

@app.route('/health')
def health():
    return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat()})

def update_bot_status(price=0, asset="USDT", ma7=0, ma25=0, usdt=0, ltc=0):
    """Function to update bot status from main bot"""
    global bot_status
    bot_status.update({
        "running": True,
        "last_update": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "current_price": price,
        "current_asset": asset,
        "ma7": ma7,
        "ma25": ma25,
        "balance_usdt": usdt,
        "balance_ltc": ltc
    })

if __name__ == '__main__':
    # For production use gunicorn
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port, debug=False)
