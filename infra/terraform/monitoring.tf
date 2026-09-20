resource "aws_cloudwatch_metric_alarm" "order_dlq_messages" {
  alarm_name          = "${var.project_name}-${var.environment}-order-dlq-messages"
  alarm_description   = "Order processing messages have reached the dead-letter queue."
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 300
  statistic           = "Maximum"
  threshold           = 0
  treat_missing_data  = "notBreaching"

  dimensions = {
    QueueName = aws_sqs_queue.order_dlq.name
  }

  tags = {
    Environment = var.environment
    Project     = var.project_name
  }
}


resource "aws_cloudwatch_metric_alarm" "order_queue_age" {
  alarm_name          = "${var.project_name}-${var.environment}-order-queue-age"
  alarm_description   = "Old messages indicate that order processing may be falling behind."
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "ApproximateAgeOfOldestMessage"
  namespace           = "AWS/SQS"
  period              = 300
  statistic           = "Maximum"
  threshold           = 300
  treat_missing_data  = "notBreaching"

  dimensions = {
    QueueName = aws_sqs_queue.order_events.name
  }

  tags = {
    Environment = var.environment
    Project     = var.project_name
  }
}


resource "aws_cloudwatch_metric_alarm" "rds_cpu_high" {
  alarm_name          = "${var.project_name}-${var.environment}-rds-cpu-high"
  alarm_description   = "RDS CPU utilization is persistently high."
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 3
  metric_name         = "CPUUtilization"
  namespace           = "AWS/RDS"
  period              = 300
  statistic           = "Average"
  threshold           = 80
  treat_missing_data  = "notBreaching"

  dimensions = {
    DBInstanceIdentifier = aws_db_instance.postgres.identifier
  }

  tags = {
    Environment = var.environment
    Project     = var.project_name
  }
}