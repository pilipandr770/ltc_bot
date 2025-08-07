# app.py - Entry point для Render Web Service
import os
from app.web_bot import app

if __name__ == '__main__':
    # Для локального запуска
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
