output "scan_url" {
  description = "POST a JSON body like {\"url\": \"https://example.com\"} here."
  value       = "${aws_apigatewayv2_api.this.api_endpoint}/scan"
}

output "table_name" {
  description = "DynamoDB table holding scan results."
  value       = aws_dynamodb_table.scans.name
}

output "function_name" {
  description = "Lambda function name, for viewing logs in CloudWatch."
  value       = aws_lambda_function.scanner.function_name
}
