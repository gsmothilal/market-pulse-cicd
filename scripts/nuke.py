import boto3

# CONFIGURATION
REGION = "us-east-1"
PROJECT_PREFIX = "marketpulse" 

def nuke_it():
    print("☢️  STARTING DEEP CLEANUP...")
    
    # --- 1. EMPTY S3 BUCKETS ---
    s3 = boto3.resource('s3', region_name=REGION)
    for bucket in s3.buckets.all():
        if PROJECT_PREFIX in bucket.name:
            print(f"🗑️  Emptying bucket: {bucket.name}...")
            bucket.object_versions.delete()
            bucket.objects.all().delete()

    # --- 2. DELETE SAGEMAKER ENDPOINTS ---
    sm = boto3.client('sagemaker', region_name=REGION)
    print("📉 Checking SageMaker Endpoints...")
    try:
        endpoints = sm.list_endpoints(NameContains=PROJECT_PREFIX)['Endpoints']
        for ep in endpoints:
            print(f"🛑 Deleting Endpoint: {ep['EndpointName']}")
            sm.delete_endpoint(EndpointName=ep['EndpointName'])
    except:
        pass

    # --- 3. DELETE SAGEMAKER MODELS ---
    print("📉 Checking SageMaker Models...")
    try:
        models = sm.list_models(NameContains=PROJECT_PREFIX)['Models']
        for m in models:
            print(f"🛑 Deleting Model: {m['ModelName']}")
            sm.delete_model(ModelName=m['ModelName'])
    except:
        pass

    print("✨ PYTHON CLEANUP COMPLETE. Ready for Terraform Destroy.")

if __name__ == "__main__":
    nuke_it()