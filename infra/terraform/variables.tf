variable "do_token" {
  description = "DigitalOcean API token"
  type        = string
  sensitive   = true
}

variable "server_name" {
  description = "Name of the DigitalOcean droplet"
  type        = string
  default     = "minecraft-fabric"
}

variable "server_size" {
  description = "DigitalOcean droplet size slug"
  type        = string
  default     = "s-2vcpu-4gb"
}

variable "image" {
  description = "DigitalOcean droplet image slug"
  type        = string
  default     = "ubuntu-24-04-x64"
}

variable "region" {
  description = "DigitalOcean region"
  type        = string
  default     = "nyc3"
}

variable "enable_volume" {
  description = "Whether to provision and attach a DigitalOcean volume"
  type        = bool
  default     = false
}

variable "volume_size" {
  description = "Volume size in GB when enable_volume is true"
  type        = number
  default     = 50
}

variable "ssh_key_fingerprints" {
  description = "Existing DigitalOcean SSH key fingerprints to attach to droplet"
  type        = list(string)
  default     = []
}

variable "ssh_public_keys" {
  description = "Optional map of SSH key name to SSH public key for registration"
  type        = map(string)
  default     = {}
}

variable "allowed_ssh_cidrs" {
  description = "CIDRs allowed to access SSH"
  type        = list(string)
  default     = ["0.0.0.0/0", "::/0"]
}

variable "allowed_minecraft_cidrs" {
  description = "CIDRs allowed to access Minecraft port"
  type        = list(string)
  default     = ["0.0.0.0/0", "::/0"]
}
