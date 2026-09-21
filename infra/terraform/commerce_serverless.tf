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
