"""S5 HTTP API: GET/POST /comparison and GET /health."""

import json

from flask import Flask, jsonify, request
from werkzeug.exceptions import HTTPException, UnsupportedMediaType

from s5_stock_comparison import StockComparisonError
from s5_service import fetch_stock_comparison
from s5_validation import InputValidationError
from registry_lifecycle import RegistryLifecycle, service_metadata


ERROR_STATUSES = {
    "INVALID_INPUT": 400,
    "UNKNOWN_SYMBOL": 404,
    "UNAVAILABLE_DATA": 404,
    "INSUFFICIENT_DATA": 422,
    "RATE_LIMITED": 429,
    "INVALID_DATA": 502,
    "UPSTREAM_ERROR": 502,
    "CONFIGURATION_ERROR": 503,
    "UPSTREAM_TIMEOUT": 504,
}
HTTP_ERRORS = {
    400: ("BAD_REQUEST", "The request body must contain valid JSON."),
    404: ("NOT_FOUND", "The requested endpoint does not exist."),
    405: ("METHOD_NOT_ALLOWED", "This HTTP method is not supported by the endpoint."),
    413: ("PAYLOAD_TOO_LARGE", "The request body exceeds the 16 KiB limit."),
    415: ("UNSUPPORTED_MEDIA_TYPE", "POST requests must use application/json."),
}


def _request_inputs():
    allowed = {"symbols", "start_date", "end_date", "exchange"}
    if request.method in ("GET", "HEAD"):
        if request.get_data():
            raise InputValidationError("GET requests must use query parameters without a body.", "body")
        for field in request.args:
            if len(request.args.getlist(field)) != 1:
                raise InputValidationError("Each query parameter must occur exactly once.", field)
        data = request.args.to_dict()
        symbols = data.get("symbols")
        symbols = symbols.split(",") if symbols is not None else None
    else:
        if request.args:
            raise InputValidationError("POST inputs must be in the JSON body without query parameters.", "query")
        if not request.is_json:
            raise UnsupportedMediaType()
        data = request.get_json()
        if not isinstance(data, dict):
            raise InputValidationError("The JSON body must be an object.", "body")
        allowed.add("exchanges")
        symbols = data.get("symbols")
        if not isinstance(symbols, list):
            raise InputValidationError("symbols must be a JSON array of 2–5 stock symbols.", "symbols")
        if "exchanges" in data and not isinstance(data["exchanges"], dict):
            raise InputValidationError("exchanges must be a JSON object.", "exchanges")
    unknown = set(data) - allowed
    if unknown:
        raise InputValidationError("Unsupported request field.", sorted(unknown)[0])
    return {"symbols": symbols, "start_date": data.get("start_date"),
            "end_date": data.get("end_date"), "exchange": data.get("exchange", "NYSE"),
            "exchanges": data.get("exchanges")}


def create_app(*, stock_client=None, registry=None):
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024
    metadata = service_metadata("S5", "Stock Comparison", "Ranks 2–5 stocks by percentage price change over common dates.", "/comparison", 5005)
    lifecycle = registry if registry is not None else RegistryLifecycle.from_environment(metadata)
    app.extensions["registry_lifecycle"] = lifecycle
    if lifecycle is not None:
        lifecycle.start()

    @app.get("/service-info")
    def service_info():
        return jsonify(metadata)

    @app.get("/health")
    def health():
        return jsonify({"status": "UP", "service_id": "S5"})

    @app.route("/comparison", methods=["GET", "POST"])
    def comparison():
        inputs = _request_inputs()
        return jsonify(fetch_stock_comparison(**inputs, client=stock_client))

    @app.errorhandler(StockComparisonError)
    def service_error(error):
        status = ERROR_STATUSES.get(error.code, 500)
        if status == 500:
            return jsonify({"error": {"code": "INTERNAL_ERROR", "message": "An unexpected service error occurred."}}), 500
        return jsonify(error.to_dict()), status

    @app.errorhandler(HTTPException)
    def http_error(error):
        # Preserve status and headers, especially Allow on 405 responses.
        response = error.get_response()
        code, message = HTTP_ERRORS.get(error.code, ("HTTP_ERROR", "The HTTP request could not be completed."))
        response.set_data(json.dumps({"error": {"code": code, "message": message}}))
        response.content_type = "application/json"
        return response

    @app.errorhandler(Exception)
    def unexpected_error(error):
        # Exception strings/tracebacks may contain credential-bearing URLs.
        app.logger.error("Unexpected S5 failure (%s)", type(error).__name__)
        return jsonify({"error": {"code": "INTERNAL_ERROR", "message": "An unexpected service error occurred."}}), 500

    return app
