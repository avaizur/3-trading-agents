resource "aws_dynamodb_table" "commerce" {
  name         = "${var.project_name}-commerce-v1"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "PK"
  range_key    = "SK"

  attribute {
    name = "PK"
    type = "S"
  }

  attribute {
    name = "SK"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled = true
  }

  tags = {
    Name    = "${var.project_name}-commerce-v1"
    Project = var.project_name
  }
}

resource "aws_iam_role" "commerce_lambda" {
  name = "${var.project_name}-commerce-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "lambda.amazonaws.com"
      }
      Action = "sts:AssumeRole"
    }]
  })

  tags = {
    Project = var.project_name
  }
}

resource "aws_iam_role_policy_attachment" "commerce_lambda_basic" {
  role       = aws_iam_role.commerce_lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "commerce_dynamodb" {
  name = "${var.project_name}-commerce-dynamodb"
  role = aws_iam_role.commerce_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "dynamodb:GetItem",
        "dynamodb:PutItem",
        "dynamodb:UpdateItem",
        "dynamodb:Query",
        "dynamodb:Scan"
      ]
      Resource = aws_dynamodb_table.commerce.arn
    }]
  })
}

output "commerce_table_name" {
  value = aws_dynamodb_table.commerce.name
}

output "commerce_lambda_role_arn" {
  value = aws_iam_role.commerce_lambda.arn
}

resource "aws_lambda_function" "commerce_smoke" {
  function_name = "${var.project_name}-commerce-smoke"

  role    = aws_iam_role.commerce_lambda.arn
  handler = "handler.lambda_handler"
  runtime = "python3.12"

  filename         = "${path.module}/../../build/commerce-smoke.zip"
  source_code_hash = filebase64sha256("${path.module}/../../build/commerce-smoke.zip")

  timeout     = 10
  memory_size = 128

  environment {
    variables = {
      COMMERCE_TABLE_NAME = aws_dynamodb_table.commerce.name
    }
  }

  depends_on = [
    aws_iam_role_policy_attachment.commerce_lambda_basic,
    aws_iam_role_policy.commerce_dynamodb
  ]

  tags = {
    Project = var.project_name
  }
}

output "commerce_smoke_lambda_name" {
  value = aws_lambda_function.commerce_smoke.function_name
}

resource "aws_lambda_function" "commerce_watch" {
  function_name = "${var.project_name}-commerce-watch"

  role    = aws_iam_role.commerce_lambda.arn
  handler = "handler.lambda_handler"
  runtime = "python3.12"

  filename         = "${path.module}/../../build/commerce-watch.zip"
  source_code_hash = filebase64sha256("${path.module}/../../build/commerce-watch.zip")

  timeout     = 30
  memory_size = 256

  environment {
    variables = {
      COMMERCE_TABLE_NAME = aws_dynamodb_table.commerce.name
    }
  }

  depends_on = [
    aws_iam_role_policy_attachment.commerce_lambda_basic,
    aws_iam_role_policy.commerce_dynamodb
  ]

  tags = {
    Project = var.project_name
    Purpose = "daily-commerce-watch"
  }
}

output "commerce_watch_lambda_name" {
  value = aws_lambda_function.commerce_watch.function_name
}
