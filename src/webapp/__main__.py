"""Entry point: python -m src.webapp"""
from __future__ import annotations

import os

from .app import create_app

if __name__ == "__main__":
    app = create_app(os.getenv("ACCELERATOR_CONFIG"))
    port = int(os.getenv("PORT", "8050"))
    app.run(host="127.0.0.1", port=port, debug=False)
