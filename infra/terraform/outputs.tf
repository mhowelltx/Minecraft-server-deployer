output "server_public_ipv4" {
  description = "Public IPv4 address of the Minecraft droplet"
  value       = digitalocean_droplet.minecraft.ipv4_address
}

output "server_name" {
  description = "Name of the provisioned Minecraft droplet"
  value       = digitalocean_droplet.minecraft.name
}

output "volume_id" {
  description = "Volume id if volume is enabled"
  value       = var.enable_volume ? digitalocean_volume.minecraft[0].id : null
}
