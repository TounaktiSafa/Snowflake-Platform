variable "organization_name" { type = string }
variable "account_name" { type = string }
variable "private_key_path" { type = string }

variable "service_user_public_key" {
  type        = string
  description = "Public key (no BEGIN/END lines) for SVC_PIPELINE"
}
