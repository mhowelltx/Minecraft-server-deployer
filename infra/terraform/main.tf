locals {
  user_data_path = "${path.module}/../cloud-init/minecraft-server.yaml"
}

resource "digitalocean_ssh_key" "registered" {
  for_each    = var.ssh_public_keys
  name        = each.key
  public_key  = each.value
}

resource "digitalocean_droplet" "minecraft" {
  name     = var.server_name
  size     = var.server_size
  image    = var.image
  region   = var.region
  user_data = file(local.user_data_path)

  ssh_keys = concat(
    var.ssh_key_fingerprints,
    [for key in digitalocean_ssh_key.registered : key.fingerprint]
  )

  tags = ["minecraft", "fabric"]
}

resource "digitalocean_firewall" "minecraft" {
  name = "${var.server_name}-fw"

  droplet_ids = [digitalocean_droplet.minecraft.id]

  inbound_rule {
    protocol         = "tcp"
    port_range       = "22"
    source_addresses = var.allowed_ssh_cidrs
  }

  inbound_rule {
    protocol         = "tcp"
    port_range       = "25565"
    source_addresses = var.allowed_minecraft_cidrs
  }

  inbound_rule {
    protocol         = "icmp"
    source_addresses = ["0.0.0.0/0", "::/0"]
  }

  outbound_rule {
    protocol              = "tcp"
    port_range            = "1-65535"
    destination_addresses = ["0.0.0.0/0", "::/0"]
  }

  outbound_rule {
    protocol              = "udp"
    port_range            = "1-65535"
    destination_addresses = ["0.0.0.0/0", "::/0"]
  }

  outbound_rule {
    protocol              = "icmp"
    destination_addresses = ["0.0.0.0/0", "::/0"]
  }
}

resource "digitalocean_volume" "minecraft" {
  count                  = var.enable_volume ? 1 : 0
  name                   = "${var.server_name}-data"
  region                 = var.region
  size                   = var.volume_size
  filesystem_type        = "ext4"
  initial_filesystem_label = "mcdata"
}

resource "digitalocean_volume_attachment" "minecraft" {
  count      = var.enable_volume ? 1 : 0
  droplet_id = digitalocean_droplet.minecraft.id
  volume_id  = digitalocean_volume.minecraft[0].id
}
