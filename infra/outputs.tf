output "s3_bucket_name" {
  value = aws_s3_bucket.datalake.id
}

output "kinesis_stream_name" {
  value = aws_kinesis_stream.market_stream.name
}

output "sagemaker_notebook_url" {
  value = "https://console.aws.amazon.com/sagemaker/home?region=us-east-1#/notebook-instances/${aws_sagemaker_notebook_instance.ml_notebook.name}"
}

# --- THIS WAS MISSING ---
output "sagemaker_role_arn" {
  value = aws_iam_role.sagemaker_role.arn
}