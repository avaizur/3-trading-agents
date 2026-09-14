terraform {
  backend "s3" {
    bucket       = "avaiizur-terraform-state-20260914-27424"
    key          = "3-trading-agents/dev/terraform.tfstate"
    region       = "eu-west-2"
    encrypt      = true
  }
}
