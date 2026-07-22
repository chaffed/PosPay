from pospay.networks.check.adapter import CheckAdapter
from pospay.networks.registry import register_adapter

register_adapter(CheckAdapter())
