variable "aws_region" {
  description = "AWS region to deploy into. eu-west-1 works without opting in, unlike af-south-1."
  type        = string
  default     = "eu-west-1"
}

variable "project_name" {
  description = "Prefix for every resource name, and the value of the Project tag."
  type        = string
  default     = "sentinel-cloudcheck"
}

variable "log_retention_days" {
  description = "How long Lambda logs are kept in CloudWatch before AWS deletes them."
  type        = number
  default     = 7
}

variable "throttle_rate_limit" {
  description = "Steady-state requests per second API Gateway allows (SRS NFR-7)."
  type        = number
  default     = 2
}

variable "throttle_burst_limit" {
  description = "Short burst of requests API Gateway allows above the steady rate (SRS NFR-7)."
  type        = number
  default     = 5
}
