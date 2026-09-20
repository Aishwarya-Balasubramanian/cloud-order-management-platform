resource "aws_vpc" "main" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = {
    Name        = "${var.project_name}-${var.environment}-vpc"
    Environment = var.environment
    Project     = var.project_name
  }
}

resource "aws_subnet" "private_a" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.0.1.0/24"
  availability_zone = "${var.aws_region}a"

  tags = {
    Name        = "${var.project_name}-${var.environment}-private-a"
    Environment = var.environment
    Project     = var.project_name
  }
}

resource "aws_subnet" "private_b" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.0.2.0/24"
  availability_zone = "${var.aws_region}b"

  tags = {
    Name        = "${var.project_name}-${var.environment}-private-b"
    Environment = var.environment
    Project     = var.project_name
  }
}

resource "aws_security_group" "application" {
  name        = "${var.project_name}-${var.environment}-application"
  description = "Security group for application workloads"
  vpc_id      = aws_vpc.main.id

  egress {
    description = "Application outbound traffic"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name        = "${var.project_name}-${var.environment}-application-sg"
    Environment = var.environment
    Project     = var.project_name
  }
}

resource "aws_security_group" "database" {
  name        = "${var.project_name}-${var.environment}-database"
  description = "PostgreSQL access only from application workloads"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "PostgreSQL from application workloads"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.application.id]
  }

  egress {
    description = "Database outbound traffic"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name        = "${var.project_name}-${var.environment}-database-sg"
    Environment = var.environment
    Project     = var.project_name
  }
}