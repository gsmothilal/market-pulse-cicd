import argparse
import boto3
import sagemaker
import pandas as pd
import yfinance as yf
import os
# FIXED: Removed the import that causes the "ModuleNotFoundError"
from sagemaker.xgboost.estimator import XGBoost

# --- 1. SETUP (Adapted for GitHub Actions) ---
parser = argparse.ArgumentParser()
parser.add_argument("--role", type=str, required=True, help="AWS IAM Role ARN from Terraform")
parser.add_argument("--bucket", type=str, required=True, help="S3 Bucket from Terraform")
args = parser.parse_args()

# Use the Role and Bucket provided by GitHub
role = args.role
bucket = args.bucket
prefix = 'marketpulse-real-history'
symbols = ['AAPL', 'GOOGL', 'AMZN', 'MSFT', 'TSLA']
region = "us-east-1"

print(f"✅ Using Role: {role}")
print(f"✅ Using Bucket: {bucket}")

# --- 2. PREPARE DATA ---
print("📥 Downloading real market history from Yahoo Finance...")
data_frames = []
for symbol in symbols:
    try:
        df = yf.download(symbol, period="1y", interval="1h", progress=False)
        # Fix for multi-index columns if yfinance returns them
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

# Combine and save
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
# Upload the file
s3.Bucket(bucket).Object(os.path.join(prefix, 'train/train.csv')).upload_file('train.csv')

# FIXED: We construct the S3 Path string directly. 
# This bypasses the need for the "TrainingInput" library that was crashing.
s3_train_path = f's3://{bucket}/{prefix}/train'

print("⏳ Training Model...")
# Use version 1.0-1 which is very stable
container = sagemaker.image_uris.retrieve("xgboost", region, "1.0-1")

xgb = XGBoost(
    image_uri=container,
    role=role,
    instance_count=1,
    instance_type='ml.m5.large',
    output_path=f's3://{bucket}/{prefix}/output',
    sagemaker_session=sess
)
xgb.set_hyperparameters(objective='reg:squarederror', num_round=50)

# FIXED: Pass the dictionary with the simple string path
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
    print(f"⚠️ Endpoint might already exist. Details: {e}")