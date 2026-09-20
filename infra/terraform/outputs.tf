output "order_queue_url" {
  description = "SQS order queue URL"
  value       = aws_sqs_queue.order_queue.url
}

output "order_dlq_url" {
  description = "SQS dead-letter queue URL"
  value       = aws_sqs_queue.order_dlq.url
}

output "ecr_repository_url" {
  description = "ECR repository URL"
  value       = aws_ecr_repository.api.repository_url
}