terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region                      = "ap-southeast-1"
  access_key                  = "test"
  secret_key                  = "test"
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true

  # Redirect AWS API requests to FakeCloud
  endpoints {
    rds = "http://localhost:4566"
  }
}

# Define the RDS Instance
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

# Output the endpoint after provisioning
output "rds_endpoint" {
  value = aws_db_instance.pulse.endpoint
}