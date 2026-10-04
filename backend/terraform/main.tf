terraform {
  required_version = ">= 1.0.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

variable "groq_api_key" {
  description = "Groq API key supplied through TF_VAR_groq_api_key for local FakeCloud use"
  type        = string
  sensitive   = true
  default     = ""
}

variable "llm_base_url" {
  description = "OpenAI-compatible LLM API base URL"
  type        = string
  default     = "https://api.groq.com/openai/v1"
}

variable "llm_model" {
  description = "Model identifier sent to the LLM provider"
  type        = string
  default     = "openai/gpt-oss-20b"
}

# -----------------------------------------------------------------------------
# AWS Provider Configured for Fakecloud
# -----------------------------------------------------------------------------
provider "aws" {
  region                      = "ap-southeast-1"
  access_key                  = "test"
  secret_key                  = "test"
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true

  endpoints {
    ecr = "http://localhost:4566"
    ecs = "http://localhost:4566"
    iam = "http://localhost:4566"
    rds = "http://localhost:4566"
    sts = "http://localhost:4566"
  }
}

# -----------------------------------------------------------------------------
# 1. RDS Postgres Instance
# -----------------------------------------------------------------------------
resource "aws_db_instance" "pulse" {
  allocated_storage   = 20
  db_name             = "pulse"
  engine              = "postgres"
  engine_version      = "15"
  instance_class      = "db.t3.micro"
  username            = "postgres"
  password            = "testpassword"
  skip_final_snapshot = true
}

# -----------------------------------------------------------------------------
# 2. ECR Repository
# -----------------------------------------------------------------------------
resource "aws_ecr_repository" "pulse_api" {
  name                 = "pulse-chat-api"
  image_tag_mutability = "MUTABLE"
}

# -----------------------------------------------------------------------------
# 3. ECS Cluster
# -----------------------------------------------------------------------------
resource "aws_ecs_cluster" "pulse_cluster" {
  name = "pulse-ecs-cluster"
}

# -----------------------------------------------------------------------------
# 4. IAM Roles for ECS Task
# -----------------------------------------------------------------------------
resource "aws_iam_role" "ecs_execution_role" {
  name = "pulse_ecs_execution_role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ecs-tasks.amazonaws.com"
        }
      }
    ]
  })
}

# -----------------------------------------------------------------------------
# 5. ECS Task Definition
# -----------------------------------------------------------------------------
resource "aws_ecs_task_definition" "pulse_api_task" {
  family                   = "pulse-api-task"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = aws_iam_role.ecs_execution_role.arn

  container_definitions = jsonencode([
    {
      name      = "pulse-api"
      image     = "${aws_ecr_repository.pulse_api.repository_url}:latest"
      cpu       = 256
      memory    = 512
      essential = true
      portMappings = [
        {
          containerPort = 4000
          hostPort      = 4000
        },
        {
          containerPort = 8001
          hostPort      = 8001
        }
      ]
      environment = [
        {
          name  = "DATABASE_URL"
          value = "postgresql://${aws_db_instance.pulse.username}:${aws_db_instance.pulse.password}@${aws_db_instance.pulse.address}:${aws_db_instance.pulse.port}/${aws_db_instance.pulse.db_name}"
        },
        {
          name  = "GROQ_API_KEY"
          value = var.groq_api_key
        },
        {
          name  = "LLM_BASE_URL"
          value = var.llm_base_url
        },
        {
          name  = "LLM_MODEL"
          value = var.llm_model
        },
        {
          name  = "MCP_SERVER_URL"
          value = "http://127.0.0.1:8001/mcp"
        }
      ]
    }
  ])
}

# -----------------------------------------------------------------------------
# 6. ECS Service
# -----------------------------------------------------------------------------
resource "aws_ecs_service" "pulse_api_service" {
  name                 = "pulse-api-service"
  cluster              = aws_ecs_cluster.pulse_cluster.id
  task_definition      = aws_ecs_task_definition.pulse_api_task.arn
  desired_count        = 1
  launch_type          = "FARGATE"
  force_new_deployment = true
}

# -----------------------------------------------------------------------------
# Outputs
# -----------------------------------------------------------------------------
output "rds_endpoint" {
  description = "RDS Postgres Endpoint"
  value       = aws_db_instance.pulse.endpoint
}

output "ecr_repository_url" {
  description = "ECR Repository URL for Docker Image"
  value       = aws_ecr_repository.pulse_api.repository_url
}

output "ecs_cluster_name" {
  description = "ECS Cluster Name"
  value       = aws_ecs_cluster.pulse_cluster.name
}

output "ecs_service_name" {
  description = "ECS Service Name"
  value       = aws_ecs_service.pulse_api_service.name
}
