data "aws_iam_policy_document" "application" {
  statement {
    effect = "Allow"

    actions = [
      "sqs:SendMessage",
      "sqs:ReceiveMessage",
      "sqs:DeleteMessage",
      "sqs:GetQueueAttributes"
    ]

    resources = [
      aws_sqs_queue.order_queue.arn
    ]
  }
}

resource "aws_iam_policy" "application" {
  name = "${var.project_name}-${var.environment}-application"

  policy = data.aws_iam_policy_document.application.json
}