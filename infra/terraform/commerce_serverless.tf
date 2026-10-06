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

  timeout     = 120
  memory_size = 256

  environment {
    variables = {
      COMMERCE_TABLE_NAME         = aws_dynamodb_table.commerce.name
      APPROVAL_BASE_URL           = "${aws_apigatewayv2_api.commerce_approval.api_endpoint}/review"
      LISTING_FACTS_FUNCTION_NAME = aws_lambda_function.commerce_listing_facts.function_name
      EBAY_SECRET_ID              = "3-trading-agents/ebay-production"
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

# ------------------------------------------------------------------
# Daily Commerce Watch orchestration
# ------------------------------------------------------------------

resource "aws_iam_role" "commerce_step_functions" {
  name = "${var.project_name}-commerce-step-functions-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "states.amazonaws.com"
      }
      Action = "sts:AssumeRole"
    }]
  })

  tags = {
    Project = var.project_name
  }
}

resource "aws_iam_role_policy" "commerce_step_functions_lambda" {
  name = "${var.project_name}-commerce-step-functions-lambda"
  role = aws_iam_role.commerce_step_functions.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "lambda:InvokeFunction"
      ]
      Resource = [
        "arn:aws:lambda:eu-west-2:${data.aws_caller_identity.commerce_current.account_id}:function:${var.project_name}-commerce-supplier-discovery",
        "arn:aws:lambda:eu-west-2:${data.aws_caller_identity.commerce_current.account_id}:function:${var.project_name}-commerce-watch",
        "arn:aws:lambda:eu-west-2:${data.aws_caller_identity.commerce_current.account_id}:function:${var.project_name}-commerce-replenishment",
        "arn:aws:lambda:eu-west-2:${data.aws_caller_identity.commerce_current.account_id}:function:${var.project_name}-commerce-daily-summary"
      ]
    }]
  })
}

resource "aws_sfn_state_machine" "commerce_daily_watch" {
  name     = "${var.project_name}-commerce-daily-watch"
  role_arn = aws_iam_role.commerce_step_functions.arn

  definition = jsonencode({
    Comment = "Daily Commerce Watch V2"
    StartAt = "DiscoverSupplierProducts"

    States = {
      DiscoverSupplierProducts = {
        Type     = "Task"
        Resource = "arn:aws:states:::lambda:invoke"

        Parameters = {
          FunctionName = "arn:aws:lambda:eu-west-2:${data.aws_caller_identity.commerce_current.account_id}:function:${var.project_name}-commerce-supplier-discovery"
          Payload = {
            "trigger" = "daily"
          }
        }

        ResultPath = "$.discovery"
        Next       = "RunCommerceWatch"
      }

      RunCommerceWatch = {
        Type     = "Task"
        Resource = "arn:aws:states:::lambda:invoke"

        Parameters = {
          FunctionName = "arn:aws:lambda:eu-west-2:${data.aws_caller_identity.commerce_current.account_id}:function:${var.project_name}-commerce-watch"
          Payload = {
            "trigger" = "daily"
          }
        }

        ResultSelector = {
          "watch.$" = "$.Payload"
        }

        ResultPath = "$.watch"
        Next       = "RunReplenishment"
      }

      RunReplenishment = {
        Type     = "Task"
        Resource = "arn:aws:states:::lambda:invoke"

        Parameters = {
          FunctionName = "arn:aws:lambda:eu-west-2:${data.aws_caller_identity.commerce_current.account_id}:function:${var.project_name}-commerce-replenishment"
          Payload = {
            "trigger" = "daily"
          }
        }

        ResultSelector = {
          "replenishment.$" = "$.Payload"
        }

        ResultPath = "$.replenishment"
        Next       = "FormatDailySummary"
      }

      FormatDailySummary = {
        Type     = "Task"
        Resource = "arn:aws:states:::lambda:invoke"

        Parameters = {
          FunctionName = "arn:aws:lambda:eu-west-2:${data.aws_caller_identity.commerce_current.account_id}:function:${var.project_name}-commerce-daily-summary"
          "Payload.$"  = "$"
        }

        ResultSelector = {
          "summary.$" = "$.Payload"
        }

        ResultPath = "$.summary"
        Next       = "SendDailySummary"
      }

      SendDailySummary = {
        Type     = "Task"
        Resource = "arn:aws:states:::sns:publish"

        Parameters = {
          TopicArn    = aws_sns_topic.commerce_daily_watch.arn
          "Subject.$" = "$.summary.summary.subject"
          "Message.$" = "$.summary.summary.message"
        }

        End = true
      }
    }
  })

  tags = {
    Project = var.project_name
    Purpose = "daily-commerce-watch"
  }

  depends_on = [
    aws_iam_role_policy.commerce_step_functions_lambda,
    aws_iam_role_policy.commerce_step_functions_sns
  ]
}

resource "aws_iam_role" "commerce_eventbridge" {
  name = "${var.project_name}-commerce-eventbridge-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Service = "events.amazonaws.com"
      }
      Action = "sts:AssumeRole"
    }]
  })

  tags = {
    Project = var.project_name
  }
}

resource "aws_iam_role_policy" "commerce_eventbridge_step_functions" {
  name = "${var.project_name}-commerce-eventbridge-step-functions"
  role = aws_iam_role.commerce_eventbridge.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "states:StartExecution"
      ]
      Resource = aws_sfn_state_machine.commerce_daily_watch.arn
    }]
  })
}

resource "aws_cloudwatch_event_rule" "commerce_daily_watch" {
  name                = "${var.project_name}-commerce-daily-watch"
  description         = "Run the 3 Trading Agents commerce watch once every 24 hours"
  schedule_expression = "rate(1 day)"

  tags = {
    Project = var.project_name
    Purpose = "daily-commerce-watch"
  }
}

resource "aws_cloudwatch_event_target" "commerce_daily_watch" {
  rule     = aws_cloudwatch_event_rule.commerce_daily_watch.name
  arn      = aws_sfn_state_machine.commerce_daily_watch.arn
  role_arn = aws_iam_role.commerce_eventbridge.arn
}

output "commerce_daily_watch_state_machine_arn" {
  value = aws_sfn_state_machine.commerce_daily_watch.arn
}

output "commerce_daily_watch_schedule" {
  value = aws_cloudwatch_event_rule.commerce_daily_watch.schedule_expression
}

# ------------------------------------------------------------------
# Daily Commerce Watch notification
# ------------------------------------------------------------------

resource "aws_sns_topic" "commerce_daily_watch" {
  name = "${var.project_name}-commerce-daily-watch"

  tags = {
    Project = var.project_name
    Purpose = "daily-commerce-watch"
  }
}

resource "aws_sns_topic_subscription" "commerce_daily_watch_email" {
  topic_arn = aws_sns_topic.commerce_daily_watch.arn
  protocol  = "email"
  endpoint  = var.commerce_alert_email
}

resource "aws_iam_role_policy" "commerce_step_functions_sns" {
  name = "${var.project_name}-commerce-step-functions-sns"
  role = aws_iam_role.commerce_step_functions.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "sns:Publish"
      ]
      Resource = aws_sns_topic.commerce_daily_watch.arn
    }]
  })
}

output "commerce_daily_watch_topic_arn" {
  value = aws_sns_topic.commerce_daily_watch.arn
}

# ------------------------------------------------------------------
# Commerce human approval API
# ------------------------------------------------------------------

resource "aws_lambda_function" "commerce_approval" {
  function_name = "${var.project_name}-commerce-approval"

  role    = aws_iam_role.commerce_lambda.arn
  handler = "handler.lambda_handler"
  runtime = "python3.12"

  filename         = "${path.module}/../../build/commerce-approval.zip"
  source_code_hash = filebase64sha256("${path.module}/../../build/commerce-approval.zip")

  timeout     = 15
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
    Purpose = "commerce-human-approval"
  }
}


resource "aws_apigatewayv2_api" "commerce_approval" {
  name          = "${var.project_name}-commerce-approval"
  protocol_type = "HTTP"

  tags = {
    Project = var.project_name
    Purpose = "commerce-human-approval"
  }
}


resource "aws_apigatewayv2_integration" "commerce_approval" {
  api_id = aws_apigatewayv2_api.commerce_approval.id

  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.commerce_approval.invoke_arn
  payload_format_version = "2.0"
}


resource "aws_apigatewayv2_route" "commerce_approval_get" {
  api_id = aws_apigatewayv2_api.commerce_approval.id

  route_key = "GET /review"
  target    = "integrations/${aws_apigatewayv2_integration.commerce_approval.id}"
}


resource "aws_apigatewayv2_route" "commerce_approval_post" {
  api_id = aws_apigatewayv2_api.commerce_approval.id

  route_key = "POST /review"
  target    = "integrations/${aws_apigatewayv2_integration.commerce_approval.id}"
}


resource "aws_apigatewayv2_stage" "commerce_approval" {
  api_id = aws_apigatewayv2_api.commerce_approval.id

  name        = "$default"
  auto_deploy = true
}


resource "aws_lambda_permission" "commerce_approval_api" {
  statement_id  = "AllowCommerceApprovalApi"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.commerce_approval.function_name
  principal     = "apigateway.amazonaws.com"

  source_arn = "${aws_apigatewayv2_api.commerce_approval.execution_arn}/*/*"
}


output "commerce_approval_url" {
  value = "${aws_apigatewayv2_api.commerce_approval.api_endpoint}/review"
}

# ------------------------------------------------------------------
# Supplier catalogue ingestion
# ------------------------------------------------------------------

data "aws_caller_identity" "commerce_current" {}

resource "aws_s3_bucket" "commerce_supplier_catalog" {
  bucket = "${var.project_name}-commerce-catalog-${data.aws_caller_identity.commerce_current.account_id}"

  tags = {
    Project = var.project_name
    Purpose = "commerce-supplier-catalog"
  }
}

resource "aws_s3_bucket_public_access_block" "commerce_supplier_catalog" {
  bucket = aws_s3_bucket.commerce_supplier_catalog.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "commerce_supplier_catalog" {
  bucket = aws_s3_bucket.commerce_supplier_catalog.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_iam_role_policy" "commerce_supplier_catalog_read" {
  name = "${var.project_name}-commerce-supplier-catalog-read"
  role = aws_iam_role.commerce_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "s3:GetObject"
      ]
      Resource = "${aws_s3_bucket.commerce_supplier_catalog.arn}/incoming/*"
    }]
  })
}

resource "aws_lambda_function" "commerce_supplier_ingest" {
  function_name = "${var.project_name}-commerce-supplier-ingest"

  role    = aws_iam_role.commerce_lambda.arn
  handler = "handler.lambda_handler"
  runtime = "python3.12"

  filename         = "${path.module}/../../build/commerce-supplier-ingest.zip"
  source_code_hash = filebase64sha256("${path.module}/../../build/commerce-supplier-ingest.zip")

  timeout     = 30
  memory_size = 256

  environment {
    variables = {
      COMMERCE_TABLE_NAME = aws_dynamodb_table.commerce.name
      SUPPLIER_NAME       = "Go Dropship"
      PRODUCT_LANE        = "EVERGREEN"
      SKU_COLUMN          = "sku"
      TITLE_COLUMN        = "title"
      COST_COLUMN         = "cost"
    }
  }

  depends_on = [
    aws_iam_role_policy_attachment.commerce_lambda_basic,
    aws_iam_role_policy.commerce_dynamodb,
    aws_iam_role_policy.commerce_supplier_catalog_read
  ]

  tags = {
    Project = var.project_name
    Purpose = "commerce-supplier-ingest"
  }
}

resource "aws_lambda_permission" "allow_supplier_catalog_s3" {
  statement_id  = "AllowSupplierCatalogS3"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.commerce_supplier_ingest.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = aws_s3_bucket.commerce_supplier_catalog.arn
}

resource "aws_s3_bucket_notification" "commerce_supplier_catalog" {
  bucket = aws_s3_bucket.commerce_supplier_catalog.id

  lambda_function {
    lambda_function_arn = aws_lambda_function.commerce_supplier_ingest.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "incoming/"
    filter_suffix       = ".csv"
  }

  depends_on = [
    aws_lambda_permission.allow_supplier_catalog_s3
  ]
}

output "commerce_supplier_catalog_bucket" {
  value = aws_s3_bucket.commerce_supplier_catalog.bucket
}

output "commerce_supplier_ingest_lambda_name" {
  value = aws_lambda_function.commerce_supplier_ingest.function_name
}

# ------------------------------------------------------------------
# Automatic Go Dropship product discovery
# ------------------------------------------------------------------

resource "aws_lambda_function" "commerce_supplier_discovery" {
  function_name = "${var.project_name}-commerce-supplier-discovery"

  role    = aws_iam_role.commerce_lambda.arn
  handler = "handler.lambda_handler"
  runtime = "python3.12"

  filename         = "${path.module}/../../build/commerce-supplier-discovery.zip"
  source_code_hash = filebase64sha256("${path.module}/../../build/commerce-supplier-discovery.zip")

  timeout     = 120
  memory_size = 256

  environment {
    variables = {
      COMMERCE_TABLE_NAME    = aws_dynamodb_table.commerce.name
      DISCOVERY_MAX_PRODUCTS = "20"
    }
  }

  depends_on = [
    aws_iam_role_policy_attachment.commerce_lambda_basic,
    aws_iam_role_policy.commerce_dynamodb
  ]

  tags = {
    Project = var.project_name
    Purpose = "automatic-supplier-discovery"
  }
}

output "commerce_supplier_discovery_lambda_name" {
  value = aws_lambda_function.commerce_supplier_discovery.function_name
}


# ------------------------------------------------------------------
# Verified eBay listing facts
# ------------------------------------------------------------------

resource "aws_lambda_function" "commerce_listing_facts" {
  function_name = "${var.project_name}-commerce-listing-facts"

  role    = aws_iam_role.commerce_lambda.arn
  handler = "handler.lambda_handler"
  runtime = "python3.12"

  filename         = "${path.module}/../../build/commerce-listing-facts.zip"
  source_code_hash = filebase64sha256("${path.module}/../../build/commerce-listing-facts.zip")

  timeout     = 120
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
    Purpose = "verified-listing-facts"
  }
}

output "commerce_listing_facts_lambda_name" {
  value = aws_lambda_function.commerce_listing_facts.function_name
}


# ------------------------------------------------------------------
# Human-readable daily commerce summary
# ------------------------------------------------------------------

resource "aws_lambda_function" "commerce_daily_summary" {
  function_name = "${var.project_name}-commerce-daily-summary"

  role    = aws_iam_role.commerce_lambda.arn
  handler = "handler.lambda_handler"
  runtime = "python3.12"

  filename         = "${path.module}/../../build/commerce-daily-summary.zip"
  source_code_hash = filebase64sha256("${path.module}/../../build/commerce-daily-summary.zip")

  timeout     = 30
  memory_size = 128

  depends_on = [
    aws_iam_role_policy_attachment.commerce_lambda_basic
  ]

  tags = {
    Project = var.project_name
    Purpose = "human-readable-daily-commerce-summary"
  }
}

output "commerce_daily_summary_lambda_name" {
  value = aws_lambda_function.commerce_daily_summary.function_name
}


# ------------------------------------------------------------------
# Live eBay replenishment
# ------------------------------------------------------------------

resource "aws_lambda_function" "commerce_replenishment" {
  function_name = "${var.project_name}-commerce-replenishment"

  role    = aws_iam_role.commerce_lambda.arn
  handler = "handler.lambda_handler"
  runtime = "python3.12"

  filename         = "${path.module}/../../build/commerce-replenishment.zip"
  source_code_hash = filebase64sha256("${path.module}/../../build/commerce-replenishment.zip")

  timeout     = 120
  memory_size = 256

  environment {
    variables = {
      COMMERCE_TABLE_NAME = aws_dynamodb_table.commerce.name
      EBAY_SECRET_ID      = "3-trading-agents/ebay-production"
    }
  }

  depends_on = [
    aws_iam_role_policy_attachment.commerce_lambda_basic,
    aws_iam_role_policy.commerce_dynamodb,
    aws_iam_role_policy.commerce_ebay_secret
  ]

  tags = {
    Project = var.project_name
    Purpose = "safe-live-replenishment"
  }
}

output "commerce_replenishment_lambda_name" {
  value = aws_lambda_function.commerce_replenishment.function_name
}


# ------------------------------------------------------------------
# Narrow Lambda permissions for eBay secret + listing-facts invocation
# ------------------------------------------------------------------

resource "aws_iam_role_policy" "commerce_ebay_secret" {
  name = "${var.project_name}-commerce-ebay-secret"
  role = aws_iam_role.commerce_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "secretsmanager:GetSecretValue"
      ]
      Resource = "arn:aws:secretsmanager:eu-west-2:${data.aws_caller_identity.commerce_current.account_id}:secret:3-trading-agents/ebay-production*"
    }]
  })
}

resource "aws_iam_role_policy" "commerce_listing_facts_invoke" {
  name = "${var.project_name}-commerce-listing-facts-invoke"
  role = aws_iam_role.commerce_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "lambda:InvokeFunction"
      ]
      Resource = aws_lambda_function.commerce_listing_facts.arn
    }]
  })
}


# ------------------------------------------------------------------
# eBay sold-order monitor
# ------------------------------------------------------------------

resource "aws_iam_role_policy" "commerce_order_monitor_actions" {
  name = "${var.project_name}-commerce-order-monitor-actions"
  role = aws_iam_role.commerce_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "sns:Publish"
        ]
        Resource = "arn:aws:sns:eu-west-2:${data.aws_caller_identity.commerce_current.account_id}:${var.project_name}-commerce-daily-watch"
      },
      {
        Effect = "Allow"
        Action = [
          "lambda:InvokeFunction"
        ]
        Resource = "arn:aws:lambda:eu-west-2:${data.aws_caller_identity.commerce_current.account_id}:function:${var.project_name}-commerce-replenishment"
      }
    ]
  })
}

resource "aws_lambda_function" "commerce_order_monitor" {
  function_name = "${var.project_name}-commerce-order-monitor"

  role    = aws_iam_role.commerce_lambda.arn
  handler = "handler.lambda_handler"
  runtime = "python3.12"

  filename         = "${path.module}/../../build/commerce-order-monitor.zip"
  source_code_hash = filebase64sha256("${path.module}/../../build/commerce-order-monitor.zip")

  timeout     = 60
  memory_size = 256

  environment {
    variables = {
      COMMERCE_TABLE_NAME         = aws_dynamodb_table.commerce.name
      EBAY_SECRET_ID              = "3-trading-agents/ebay-production"
      ORDER_ALERT_TOPIC_ARN       = "arn:aws:sns:eu-west-2:${data.aws_caller_identity.commerce_current.account_id}:${var.project_name}-commerce-daily-watch"
      REPLENISHMENT_FUNCTION_NAME = "${var.project_name}-commerce-replenishment"
    }
  }

  depends_on = [
    aws_iam_role_policy_attachment.commerce_lambda_basic,
    aws_iam_role_policy.commerce_dynamodb,
    aws_iam_role_policy.commerce_ebay_secret,
    aws_iam_role_policy.commerce_order_monitor_actions
  ]

  tags = {
    Project = var.project_name
    Purpose = "ebay-sold-order-monitor"
  }
}

resource "aws_cloudwatch_event_rule" "commerce_order_monitor" {
  name                = "${var.project_name}-commerce-order-monitor"
  description         = "Check eBay for newly sold/unfulfilled orders every 5 minutes"
  schedule_expression = "rate(5 minutes)"

  tags = {
    Project = var.project_name
    Purpose = "ebay-sold-order-monitor"
  }
}

resource "aws_cloudwatch_event_target" "commerce_order_monitor" {
  rule = aws_cloudwatch_event_rule.commerce_order_monitor.name
  arn  = aws_lambda_function.commerce_order_monitor.arn
}

resource "aws_lambda_permission" "commerce_order_monitor_eventbridge" {
  statement_id  = "AllowEventBridgeOrderMonitor"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.commerce_order_monitor.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.commerce_order_monitor.arn
}

output "commerce_order_monitor_lambda_name" {
  value = aws_lambda_function.commerce_order_monitor.function_name
}

output "commerce_order_monitor_schedule" {
  value = aws_cloudwatch_event_rule.commerce_order_monitor.schedule_expression
}
