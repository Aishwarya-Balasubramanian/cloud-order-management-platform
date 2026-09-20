resource "aws_sqs_queue" "order_dlq" {
  name = "${var.project_name}-${var.environment}-dlq"

  message_retention_seconds = 1209600
}

resource "aws_sqs_queue" "order_queue" {
  name = "${var.project_name}-${var.environment}-queue"

  visibility_timeout_seconds = 30
  message_retention_seconds  = 345600
  receive_wait_time_seconds  = 20

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.order_dlq.arn
    maxReceiveCount     = 5
  })
}