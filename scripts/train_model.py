import argparse
import boto3
import pandas as pd
import yfinance as yf
import os
import time
import json
import sagemaker # We only import this to get the session, not for submodules

# --- CONFIGURATION ---
REGION = "us-east-1"
# Hardcoded XGBoost Image for us-east-1 (Standard & Stable)
IMAGE_URI = "683313688378.dkr.ecr.us-east-1.amazonaws.com/sagemaker-xgboost:1.0-1-cpu-py3"

# --- 1. SETUP ---
parser = argparse.ArgumentParser()
parser.add_argument("--role", type=str, required=True, help="AWS IAM Role ARN")
parser.add_argument("--bucket", type=str, required=True, help="S3 Bucket")
args = parser.parse_args()

role = args.role
bucket = args.bucket
prefix = 'marketpulse-real-history'
symbols = ['AAPL', 'GOOGL', 'AMZN', 'MSFT', 'TSLA']

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

# --- 3. UPLOAD DATA ---
s3 = boto3.client('s3', region_name=REGION)
s3.upload_file('train.csv', bucket, f"{prefix}/train/train.csv")
s3_train_path = f"s3://{bucket}/{prefix}/train/train.csv"
output_path = f"s3://{bucket}/{prefix}/output"

# --- 4. TRAIN (Using Pure Boto3) ---
sm = boto3.client('sagemaker', region_name=REGION)
job_name = f"market-pulse-xgboost-{int(time.time())}"

print(f"⏳ Starting Training Job: {job_name}")

sm.create_training_job(
    TrainingJobName=job_name,
    AlgorithmSpecification={
        'TrainingImage': IMAGE_URI,
        'TrainingInputMode': 'File'
    },
    RoleArn=role,
    InputDataConfig=[{
        'ChannelName': 'train',
        'DataSource': {
            'S3DataSource': {
                'S3DataType': 'S3Prefix',
                'S3Uri': s3_train_path,
                'S3DataDistributionType': 'FullyReplicated'
            }
        },
        'ContentType': 'csv',
        'CompressionType': 'None'
    }],
    OutputDataConfig={'S3OutputPath': output_path},
    ResourceConfig={
        'InstanceType': 'ml.m5.large',
        'InstanceCount': 1,
        'VolumeSizeInGB': 10
    },
    StoppingCondition={'MaxRuntimeInSeconds': 3600},
    HyperParameters={
        'objective': 'reg:squarederror',
        'num_round': '50'
    }
)

# Wait for training to finish
print("   Waiting for training to complete...")
waiter = sm.get_waiter('training_job_completed_or_stopped')
waiter.wait(TrainingJobName=job_name)
print("✅ Training Complete.")

# --- 5. DEPLOY (Using Pure Boto3) ---
model_name = f"market-pulse-model-{int(time.time())}"
print(f"🚀 Creating Model: {model_name}")

# Create Model Object
sm.create_model(
    ModelName=model_name,
    PrimaryContainer={
        'Image': IMAGE_URI,
        'ModelDataUrl': f"{output_path}/{job_name}/output/model.tar.gz"
    },
    ExecutionRoleArn=role
)

# Create Endpoint Config
endpoint_config_name = f"market-pulse-config-{int(time.time())}"
sm.create_endpoint_config(
    EndpointConfigName=endpoint_config_name,
    ProductionVariants=[{
        'InstanceType': 'ml.t2.medium',
        'InitialInstanceCount': 1,
        'ModelName': model_name,
        'VariantName': 'AllTraffic'
    }]
)

endpoint_name = 'market-pulse-predictor'
print(f"🚀 Deploying to Endpoint: {endpoint_name}")

try:
    # Try creating new endpoint
    sm.create_endpoint(
        EndpointName=endpoint_name,
        EndpointConfigName=endpoint_config_name
    )
    print("   Creating new endpoint... (This takes ~5-10 mins)")
    # We won't wait here to save GitHub Action minutes, it runs in background
except sm.exceptions.ResourceInUseException:
    print("   Endpoint already exists. Updating...")
    sm.update_endpoint(
        EndpointName=endpoint_name,
        EndpointConfigName=endpoint_config_name
    )
    print("   Update command sent.")

print("✅ DONE! System is live.")
