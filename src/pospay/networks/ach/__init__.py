from pospay.networks.ach.adapter import AchAdapter
from pospay.networks.registry import register_adapter

register_adapter(AchAdapter())
