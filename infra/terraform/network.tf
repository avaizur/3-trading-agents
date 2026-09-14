data "aws_vpc" "default" {
  default = true
}

resource "aws_security_group" "app" {
  name        = "3-trading-agents-dev-sg"
  description = "3 Trading Agents dev EC2 - no inbound access"
  vpc_id      = data.aws_vpc.default.id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name    = "3-trading-agents-dev-sg"
    Project = "3-trading-agents"
  }
}
