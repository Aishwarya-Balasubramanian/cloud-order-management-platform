resource "aws_db_subnet_group" "main" {
  name = "${var.project_name}-${var.environment}-db-subnets"

  subnet_ids = [
    aws_subnet.private_a.id,
    aws_subnet.private_b.id
  ]
}

resource "aws_db_instance" "postgres" {
  identifier = "${var.project_name}-${var.environment}-postgres"

  engine         = "postgres"
  engine_version = "17"

  instance_class        = "db.t3.micro"
  allocated_storage     = 20
  max_allocated_storage = 100

  db_name  = "order_management"
  username = "postgres"

  manage_master_user_password = true

  db_subnet_group_name = aws_db_subnet_group.main.name

  vpc_security_group_ids = [
    aws_security_group.database.id
  ]

  publicly_accessible = false
  storage_encrypted   = true
  deletion_protection = false
  skip_final_snapshot = true

  backup_retention_period = 7

  tags = {
    Environment = var.environment
    Project     = var.project_name
  }
}