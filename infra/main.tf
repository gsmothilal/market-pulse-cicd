provider "aws" {
  region = "us-east-1"
}

# --- 1. S3 DATA LAKE (Cold Storage) ---
resource "aws_s3_bucket" "datalake" {
  bucket_prefix = "marketpulse-lake-" # Random unique name
  force_destroy = true # Allows deleting bucket even if full
}

# --- 2. KINESIS STREAM (Ingestion) ---
resource "aws_kinesis_stream" "market_stream" {
  name             = "market-pulse-stream"
  shard_count      = 1
  retention_period = 24
}

# --- 3. DYNAMODB (Hot Storage) ---
resource "aws_dynamodb_table" "alerts" {
  name         = "MarketPulseAlerts"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "symbol"
  range_key    = "timestamp"

  attribute {
    name = "symbol"
    type = "S"
  }
  attribute {
    name = "timestamp"
    type = "S"
  }
}

# --- 4. SNS TOPIC (Notifications) ---
resource "aws_sns_topic" "alerts_topic" {
  name = "MarketPulse-Notify"
}

resource "aws_sns_topic_subscription" "email_sub" {
  topic_arn = aws_sns_topic.alerts_topic.arn
  protocol  = "email"
  endpoint  = var.my_email # Variable for your email
}

# --- 5. IAM ROLES (Security) ---

# Role for Lambda
resource "aws_iam_role" "lambda_role" {
  name = "MarketPulse_Lambda_Role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{ Action = "sts:AssumeRole", Effect = "Allow", Principal = { Service = "lambda.amazonaws.com" } }]
  })
}

# Permissions for Lambda (Kinesis, Dynamo, SNS, Bedrock, SageMaker)
resource "aws_iam_role_policy_attachment" "lambda_basic" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "lambda_permissions" {
  name = "MarketPulse_Policy"
  role = aws_iam_role.lambda_role.id
  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Effect = "Allow",
        Action = ["kinesis:Get*", "kinesis:DescribeStream"],
        Resource = aws_kinesis_stream.market_stream.arn
      },
      {
        Effect = "Allow",
        Action = ["dynamodb:PutItem"],
        Resource = aws_dynamodb_table.alerts.arn
      },
      {
        Effect = "Allow",
        Action = ["sns:Publish"],
        Resource = aws_sns_topic.alerts_topic.arn
      },
      {
        Effect = "Allow",
        Action = ["bedrock:InvokeModel"],
        Resource = "*"
      },
      {
        Effect = "Allow",
        Action = ["sagemaker:InvokeEndpoint"],
        Resource = "*"
      }
    ]
  })
}

# Role for Kinesis Firehose (To write to S3)
resource "aws_iam_role" "firehose_role" {
  name = "MarketPulse_Firehose_Role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{ Action = "sts:AssumeRole", Effect = "Allow", Principal = { Service = "firehose.amazonaws.com" } }]
  })
}

resource "aws_iam_role_policy" "firehose_s3_policy" {
  role = aws_iam_role.firehose_role.id
  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      { Effect = "Allow", Action = ["s3:PutObject", "s3:PutObjectAcl"], Resource = "${aws_s3_bucket.datalake.arn}/*" },
      { Effect = "Allow", Action = ["kinesis:Get*", "kinesis:DescribeStream"], Resource = aws_kinesis_stream.market_stream.arn }
    ]
  })
}

# --- 6. KINESIS FIREHOSE (Archival) ---
resource "aws_kinesis_firehose_delivery_stream" "s3_stream" {
  name        = "market-pulse-firehose"
  destination = "extended_s3"

  extended_s3_configuration {
    role_arn   = aws_iam_role.firehose_role.arn
    bucket_arn = aws_s3_bucket.datalake.arn
    buffering_size = 1
    buffering_interval = 60
  }
  
  kinesis_source_configuration {
    kinesis_stream_arn = aws_kinesis_stream.market_stream.arn
    role_arn           = aws_iam_role.firehose_role.arn
  }
}

# --- 7. SAGEMAKER NOTEBOOK (For Training) ---
resource "aws_iam_role" "sagemaker_role" {
  name = "MarketPulse_SageMaker_Role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{ Action = "sts:AssumeRole", Effect = "Allow", Principal = { Service = "sagemaker.amazonaws.com" } }]
  })
}

resource "aws_iam_role_policy_attachment" "sagemaker_full" {
  role       = aws_iam_role.sagemaker_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSageMakerFullAccess"
}

resource "aws_iam_role_policy_attachment" "sagemaker_s3" {
  role       = aws_iam_role.sagemaker_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonS3FullAccess"
}

resource "aws_sagemaker_notebook_instance" "ml_notebook" {
  name          = "MarketPulse-Notebook"
  role_arn      = aws_iam_role.sagemaker_role.arn
  instance_type = "ml.t2.medium"
}

# --- 8. LAMBDA FUNCTION (The Brain) ---
# Zip the Python code
data "archive_file" "lambda_zip" {
  type        = "zip"
  source_file = "lambda/lambda_function.py"
  output_path = "lambda/lambda_function.zip"
}

resource "aws_lambda_function" "processor" {
  filename      = "lambda/lambda_function.zip"
  function_name = "MarketPulse-Processor"
  role          = aws_iam_role.lambda_role.arn
  handler       = "lambda_function.lambda_handler"
  runtime       = "python3.12"
  timeout       = 30
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256

  environment {
    variables = {
      TABLE_NAME         = aws_dynamodb_table.alerts.name
      SNS_TOPIC_ARN      = aws_sns_topic.alerts_topic.arn
      SAGEMAKER_ENDPOINT = "market-pulse-predictor" # Hardcoded name for Day 1
    }
  }
}

# Trigger Lambda from Kinesis
resource "aws_lambda_event_source_mapping" "kinesis_trigger" {
  event_source_arn  = aws_kinesis_stream.market_stream.arn
  function_name     = aws_lambda_function.processor.arn
  starting_position = "LATEST"
  batch_size        = 1
}
