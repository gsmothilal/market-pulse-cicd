import argparse
import boto3
import sagemaker
import pandas as pd
import yfinance as yf
import os

# --- FIXED: Use the Universal 'Estimator' instead of specific 'XGBoost' ---
# This class exists in ALL versions of SageMaker, so it cannot crash.
from sagemaker.estimator import Estimator

# --- 1. SETUP ---
parser = argparse.ArgumentParser()
parser.add_argument("--role", type=str, required=True, help="AWS IAM Role ARN")
parser.add_argument("--bucket", type=str, required=True, help="S3 Bucket")
args = parser.parse_args()

role = args.role
bucket = args.bucket
prefix = 'marketpulse-real-history'
symbols = ['AAPL', 'GOOGL', 'AMZN', 'MSFT', 'TSLA']
region = "us-east-1"

print(f"✅ Using Role: {role}")
print(f"✅ Using Bucket: {bucket}")

# --- 2. PREPARE DATA ---
print("📥 Downloading real market history...")
data_frames = []
for symbol in symbols:
    try:
        df = yf.download(symbol, period="1y", interval="1h", progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df[['Close']].reset_index()
        df.columns = ['datetime', 'price']
        df['target'] = df['price'].shift(-1)
        df = df.dropna()
        df = df[['target', 'price']]
        data_frames.append(df)
    except Exception as e:
        print(f"⚠️ Error downloading {symbol}: {e}")

if data_frames:
    full_df = pd.concat(data_frames).sample(frac=1).reset_index(drop=True)
    full_df.to_csv('train.csv', header=False, index=False)
    print("✅ Data saved to train.csv")
else:
    raise Exception("❌ No data downloaded!")

# --- 3. UPLOAD & TRAIN ---
boto_session = boto3.Session(region_name=region)
sess = sagemaker.Session(boto_session=boto_session)
s3 = boto_session.resource('s3')

print("⬆️ Uploading to S3...")
s3.Bucket(bucket).Object(os.path.join(prefix, 'train/train.csv')).upload_file('train.csv')
s3_train_path = f's3://{bucket}/{prefix}/train'

print("⏳ Training Model...")
# Use version 1.0-1 which is very stable
container = sagemaker.image_uris.retrieve("xgboost", region, "1.0-1")

# --- FIXED: Using generic Estimator ---
xgb = Estimator(
    image_uri=container,
    role=role,
    instance_count=1,
    instance_type='ml.m5.large',
    output_path=f's3://{bucket}/{prefix}/output',
    sagemaker_session=sess
)

# This works the same way as the specific class
xgb.set_hyperparameters(objective='reg:squarederror', num_round=50)

# Pass the input path directly
xgb.fit({'train': s3_train_path})

# --- 4. DEPLOY ---
print("🚀 Deploying Endpoint...")
try:
    xgb.deploy(
        initial_instance_count=1,
        instance_type='ml.t2.medium',
        endpoint_name='market-pulse-predictor'
    )
    print("✅ Endpoint Deployed!")
except Exception as e:
    print(f"⚠️ Endpoint might already exist: {e}")
