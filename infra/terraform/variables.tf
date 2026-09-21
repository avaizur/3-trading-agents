variable "project_name" {
  description = "Project name used for AWS resource tags and names"
  type        = string
  default     = "3-trading-agents"
}

variable "instance_type" {
  description = "EC2 instance size"
  type        = string
  default     = "t3.small"
}

variable "root_volume_size" {
  description = "Root EBS volume size in GB"
  type        = number
  default     = 12
}

variable "commerce_alert_email" {
  description = "Email address for Daily Commerce Watch SNS notifications"
  type        = string
  sensitive   = true
}
