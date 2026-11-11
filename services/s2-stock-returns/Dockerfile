FROM python:3.12-slim
WORKDIR /srv/s2
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py stock_returns.py ./
ENV PORT=5001
EXPOSE 5001
# Each S2 instance remains independent of every other stock service.
CMD ["gunicorn", "-w", "1", "-b", "0.0.0.0:5001", "--timeout", "20", "app:app"]
