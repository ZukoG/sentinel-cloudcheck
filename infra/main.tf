terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.4"
    }
  }
}

provider "aws" {
  region = var.aws_region

  # Tag everything this project creates, so it is easy to find in the
  # console and easy to confirm nothing is left behind after destroy.
  default_tags {
    tags = {
      Project   = var.project_name
      ManagedBy = "terraform"
    }
  }
}

locals {
  function_name = "${var.project_name}-scanner"
}

# ---------------------------------------------------------------------------
# DynamoDB: one table, one item per scan (SRS FR-5)
# ---------------------------------------------------------------------------

# Provisioned at 1 read / 1 write unit rather than on-demand: the AWS
# always-free tier covers 25 provisioned units, while on-demand requests
# are billed per request from the first one. One write per second is far
# more than a demo needs.
resource "aws_dynamodb_table" "scans" {
  name           = "${var.project_name}-scans"
  billing_mode   = "PROVISIONED"
  read_capacity  = 1
  write_capacity = 1
  hash_key       = "scan_id"

  attribute {
    name = "scan_id"
    type = "S"
  }
}

# ---------------------------------------------------------------------------
# Lambda: the scanner itself
# ---------------------------------------------------------------------------

# Zips src/ so grader.py and handler.py sit at the root of the archive,
# which is why the code imports `from grader import ...`.
data "archive_file" "lambda_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../src"
  output_path = "${path.module}/../build/lambda.zip"
  excludes    = ["__pycache__"]
}

# Created explicitly (instead of letting Lambda create it on first run) so
# that logs get a retention limit and terraform destroy removes them too.
resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${local.function_name}"
  retention_in_days = var.log_retention_days
}

data "aws_iam_policy_document" "lambda_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda" {
  name               = "${local.function_name}-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
}

# Least privilege (SRS NFR-2): write logs to its own log group and put
# items into its own table. No read, delete, or scan permissions, and no
# access to any other resource. This replaces the AWS managed
# AWSLambdaBasicExecutionRole policy, which allows creating log groups
# on any resource.
data "aws_iam_policy_document" "lambda_permissions" {
  statement {
    sid       = "WriteOwnLogs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.lambda.arn}:*"]
  }

  statement {
    sid       = "PutScanResults"
    actions   = ["dynamodb:PutItem"]
    resources = [aws_dynamodb_table.scans.arn]
  }
}

resource "aws_iam_role_policy" "lambda" {
  name   = "${local.function_name}-policy"
  role   = aws_iam_role.lambda.id
  policy = data.aws_iam_policy_document.lambda_permissions.json
}

resource "aws_lambda_function" "scanner" {
  function_name    = local.function_name
  role             = aws_iam_role.lambda.arn
  runtime          = "python3.13"
  handler          = "handler.lambda_handler"
  filename         = data.archive_file.lambda_zip.output_path
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256

  # The target fetch has a 5 second timeout (SRS FR-3.1); 10 seconds
  # leaves room for the DynamoDB write and a cold start.
  timeout     = 10
  memory_size = 128

  environment {
    variables = {
      TABLE_NAME = aws_dynamodb_table.scans.name
    }
  }

  depends_on = [
    aws_cloudwatch_log_group.lambda,
    aws_iam_role_policy.lambda,
  ]
}

# ---------------------------------------------------------------------------
# API Gateway: public HTTPS front door (SRS FR-1)
# ---------------------------------------------------------------------------

# HTTP API rather than REST API: cheaper, simpler, and enough for one route.
resource "aws_apigatewayv2_api" "this" {
  name          = "${var.project_name}-api"
  protocol_type = "HTTP"
}

resource "aws_apigatewayv2_integration" "lambda" {
  api_id                 = aws_apigatewayv2_api.this.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.scanner.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "scan" {
  api_id    = aws_apigatewayv2_api.this.id
  route_key = "POST /scan"
  target    = "integrations/${aws_apigatewayv2_integration.lambda.id}"
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.this.id
  name        = "$default"
  auto_deploy = true

  # SRS NFR-7: the API has no auth, so cap how fast anyone can call it.
  default_route_settings {
    throttling_rate_limit  = var.throttle_rate_limit
    throttling_burst_limit = var.throttle_burst_limit
  }
}

# Allows this API, and only this API, to invoke the function.
resource "aws_lambda_permission" "api_gateway" {
  statement_id  = "AllowInvokeFromApiGateway"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.scanner.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.this.execution_arn}/*/*"
}
