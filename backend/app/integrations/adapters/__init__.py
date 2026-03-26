"""
Concrete adapter implementations.

Importing this package triggers registration of all adapters into the
global AdapterRegistry.
"""

from app.integrations.adapters.credit_bureau import CIBILAdapterV1, CIBILAdapterV2
from app.integrations.adapters.kyc import KYCAdapterV1, KYCAdapterV2
from app.integrations.adapters.gst import GSTAdapterV1
from app.integrations.adapters.payment_gateway import PaymentGatewayAdapterV1
from app.integrations.adapters.sms_gateway import SMSGatewayAdapterV1

__all__ = [
    "CIBILAdapterV1",
    "CIBILAdapterV2",
    "KYCAdapterV1",
    "KYCAdapterV2",
    "GSTAdapterV1",
    "PaymentGatewayAdapterV1",
    "SMSGatewayAdapterV1",
]
