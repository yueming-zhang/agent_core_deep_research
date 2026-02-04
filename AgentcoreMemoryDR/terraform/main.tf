terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 6.0, < 7.0"
    }
    null = {
      source  = "hashicorp/null"
      version = ">= 3.2"
    }
  }
}

variable "aws_region" {
  description = "AWS region to deploy the stack"
  type        = string
  default     = "us-west-2"
}

provider "aws" {
  region = var.aws_region
}

locals {
  region        = var.aws_region
  region_suffix = replace(var.aws_region, "-", "_")
  # Agent name stays consistent across regions
  agent_name    = "dr_poc_agent"
  memory_name   = "dr_poc_memory"
  # IAM resources need region suffix since they're global
  iam_prefix    = "dr_poc_agent_${local.region_suffix}"
  # Content hash for versioning
  content_hash  = md5(join("", [
    filemd5("${path.module}/../agent.py"),
    filemd5("${path.module}/../agent_runtime.py"),
    filemd5("${path.module}/../requirements.txt"),
    filemd5("${path.module}/../multi_region_memory_saver.py"),
    filemd5("${path.module}/../Dockerfile")
  ]))
  image_tag     = "v-${substr(local.content_hash, 0, 8)}"
}

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# Memory - For Persistent Conversation Context
resource "aws_bedrockagentcore_memory" "memory" {
  name                  = local.memory_name
  description           = "Memory for ${local.agent_name} to maintain conversation context"
  event_expiry_duration = 30
}

resource "aws_ecr_repository" "agent" {
  name                 = local.agent_name
  image_tag_mutability = "MUTABLE"
  force_delete         = true
}

resource "null_resource" "docker_build_push" {
  triggers = {
    content_hash = local.content_hash
    always_run   = timestamp()
  }

  provisioner "local-exec" {
    working_dir = "${path.module}/.."
    command     = <<-EOT
      aws ecr get-login-password --region ${local.region} | docker login --username AWS --password-stdin ${data.aws_caller_identity.current.account_id}.dkr.ecr.${local.region}.amazonaws.com
      docker build -t ${aws_ecr_repository.agent.repository_url}:${local.image_tag} .
      docker push ${aws_ecr_repository.agent.repository_url}:${local.image_tag}
    EOT
  }

  depends_on = [aws_ecr_repository.agent]
}

resource "aws_iam_role" "agent_execution" {
  name = "${local.iam_prefix}_execution_role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "AssumeRolePolicy"
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "bedrock-agentcore.amazonaws.com"
      }
      Condition = {
        StringEquals = { "aws:SourceAccount" = data.aws_caller_identity.current.account_id }
        ArnLike      = { "aws:SourceArn" = "arn:aws:bedrock-agentcore:${local.region}:${data.aws_caller_identity.current.account_id}:*" }
      }
    }]
  })
}

resource "aws_iam_role_policy" "agent_execution" {
  name = "${local.iam_prefix}_execution_policy"
  role = aws_iam_role.agent_execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "BedrockPermissions"
        Effect = "Allow"
        Action = [
          "bedrock:InvokeModel",
          "bedrock:InvokeModelWithResponseStream"
        ]
        Resource = "*"
      },
      {
        Sid    = "ECRImageAccess"
        Effect = "Allow"
        Action = [
          "ecr:BatchGetImage",
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchCheckLayerAvailability"
        ]
        Resource = "arn:aws:ecr:${local.region}:${data.aws_caller_identity.current.account_id}:repository/*"
      },
      {
        Sid      = "ECRTokenAccess"
        Effect   = "Allow"
        Action   = "ecr:GetAuthorizationToken"
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = ["logs:DescribeLogStreams", "logs:CreateLogGroup"]
        Resource = "arn:aws:logs:${local.region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/bedrock-agentcore/runtimes/*"
      },
      {
        Effect   = "Allow"
        Action   = "logs:DescribeLogGroups"
        Resource = "arn:aws:logs:${local.region}:${data.aws_caller_identity.current.account_id}:log-group:*"
      },
      {
        Effect = "Allow"
        Action = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "arn:aws:logs:${local.region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/bedrock-agentcore/runtimes/*:log-stream:*"
      },
      {
        Effect = "Allow"
        Action = [
          "xray:PutTraceSegments",
          "xray:PutTelemetryRecords",
          "xray:GetSamplingRules",
          "xray:GetSamplingTargets"
        ]
        Resource = "*"
      },
      {
        Effect   = "Allow"
        Action   = "cloudwatch:PutMetricData"
        Resource = "*"
        Condition = {
          StringEquals = { "cloudwatch:namespace" = "bedrock-agentcore" }
        }
      },
      {
        Sid    = "GetAgentAccessToken"
        Effect = "Allow"
        Action = [
          "bedrock-agentcore:GetWorkloadAccessToken",
          "bedrock-agentcore:GetWorkloadAccessTokenForJWT",
          "bedrock-agentcore:GetWorkloadAccessTokenForUserId"
        ]
        Resource = [
          "arn:aws:bedrock-agentcore:${local.region}:${data.aws_caller_identity.current.account_id}:workload-identity-directory/default",
          "arn:aws:bedrock-agentcore:${local.region}:${data.aws_caller_identity.current.account_id}:workload-identity-directory/default/workload-identity/${local.agent_name}-*"
        ]
      },
      {
        Effect = "Allow"
        Action = ["bedrock-agentcore:*"]
        Resource = "*"
      }
    ]
  })
}

resource "aws_bedrockagentcore_agent_runtime" "agent" {
  agent_runtime_name = local.agent_name
  description        = "AgentCore runtime for ${local.agent_name} (${local.image_tag})"
  role_arn           = aws_iam_role.agent_execution.arn

  agent_runtime_artifact {
    container_configuration {
      container_uri = "${aws_ecr_repository.agent.repository_url}:${local.image_tag}"
    }
  }

  network_configuration {
    network_mode = "PUBLIC"
  }

  environment_variables = {
    PRIMARY_MEMORY_ID = aws_bedrockagentcore_memory.memory.id
    PRIMARY_REGION    = var.aws_region
  }

  depends_on = [null_resource.docker_build_push, aws_iam_role_policy.agent_execution]
}

# ----- deploy to us-west-2
# terraform workspace new us-west-2
# terraform apply -var="aws_region=us-west-2"


# ------ deploy to eu-west-1
# terraform workspace new eu-west-1
# terraform apply -var="aws_region=eu-west-1"


# terraform workspace list
# terraform workspace select eu-west-1
# terraform destroy -var="aws_region=eu-west-1"