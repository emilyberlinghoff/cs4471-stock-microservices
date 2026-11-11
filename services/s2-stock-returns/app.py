import os
from flask import Flask, request, jsonify
from werkzeug.exceptions import HTTPException
from stock_returns import StockReturnsService, ServiceError


# Information about this microservice
SERVICE_ID = "S2"
SERVICE_TITLE = "Stock Returns"
SERVICE_DESCRIPTION = "Calculates daily stock returns using Alpha Vantage data."


def create_app(service=None):
    app = Flask(__name__)

    # Limit the size of incoming requests
    app.config["MAX_CONTENT_LENGTH"] = 8192

    if service is None:
        service = StockReturnsService()

    # Main endpoint for calculating stock returns
    @app.route("/api/v1/stock-returns", methods=["GET", "POST"])
    def stock_returns():
        try:
            # Get inputs from the URL or JSON request body
            if request.method == "GET":
                data = request.args
            else:
                data = request.get_json(silent=True)

                if not isinstance(data, dict):
                    raise ServiceError(
                        "INVALID_INPUT",
                        "Request body must be valid JSON.",
                        400
                    )

            symbol = data.get("symbol")
            start_date = data.get("start_date")
            end_date = data.get("end_date")

            # Calculate returns using stock_returns.py
            result = service.run(symbol, start_date, end_date)

            return jsonify(result), 200

        except ServiceError as error:
            return jsonify(error.as_response()), error.status

        except Exception:
            app.logger.exception("Error calculating stock returns")
            return jsonify({
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "Something went wrong."
                }
            }), 500

    # Handle invalid HTTP requests
    @app.errorhandler(HTTPException)
    def http_error(error):
        return jsonify({
            "error": {
                "code": "HTTP_ERROR",
                "message": error.description
            }
        }), error.code

    # Check if the microservice is running
    @app.route("/health", methods=["GET"])
    def health():
        return jsonify({
            "status": "ok",
            "service_id": SERVICE_ID
        }), 200

    # Information used for service registration
    @app.route("/service-info", methods=["GET"])
    def service_info():
        base_url = os.getenv(
            "SERVICE_PUBLIC_URL",
            "http://localhost:5001"
        ).rstrip("/")

        return jsonify({
            "id": SERVICE_ID,
            "title": SERVICE_TITLE,
            "description": SERVICE_DESCRIPTION,
            "url": base_url + "/api/v1/stock-returns"
        }), 200

    return app


# Create the Flask application
app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)