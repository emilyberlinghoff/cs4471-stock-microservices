"""Example Flask-frontend integration: call S2 over HTTP, not by importing its internals."""
import os

import requests
from flask import Flask, jsonify, request

frontend = Flask(__name__)
S2_URL = os.getenv("S2_URL", "http://localhost:5001/api/v1/stock-returns")


@frontend.get("/stock-returns")
def stock_returns_page_data():
    params = {"symbol": request.args.get("symbol"),
              "start_date": request.args.get("start_date"),
              "end_date": request.args.get("end_date")}
    try:
        response = requests.get(S2_URL, params=params, timeout=(2, 14))
        result = response.json()
        return jsonify(result), response.status_code
    except (requests.RequestException, ValueError):
        return jsonify({"error": {"code": "S2_UNAVAILABLE",
                                  "message": "Stock Returns service is unavailable."}}), 503


if __name__ == "__main__":
    frontend.run(port=5000, debug=False)
