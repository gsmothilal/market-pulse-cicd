import boto3
import json
import time
import yfinance as yf
from datetime import datetime

# CONFIGURATION
STREAM_NAME = "market-pulse-stream"
REGION = "us-east-1"
STOCKS = ["AAPL", "TSLA", "GOOGL", "AMZN", "MSFT"]

# Initialize Kinesis Client
kinesis = boto3.client('kinesis', region_name=REGION)

def get_real_market_data(symbol):
    try:
        ticker = yf.Ticker(symbol)
        # Fetch latest price
        price = ticker.fast_info.last_price 
        return {
            'symbol': symbol,
            'price': round(price, 2),
            'timestamp': datetime.utcnow().isoformat()
        }
    except Exception as e:
        print(f"Error fetching {symbol}: {e}")
        return None

def produce():
    print(f"📡 Connecting to Real-Time Market Data Stream: {STREAM_NAME}...")

    while True:
        for stock in STOCKS:
            data = get_real_market_data(stock)
            if data:
                # Send to AWS Kinesis
                kinesis.put_record(
                    StreamName=STREAM_NAME,
                    Data=json.dumps(data),
                    PartitionKey=data['symbol']
                )
                print(f"✅ Sent REAL Live Tick: {data['symbol']} @ ${data['price']}")

        # Wait 2 seconds so we don't get banned by Yahoo Finance
        time.sleep(15) 

if __name__ == "__main__":
    produce()



