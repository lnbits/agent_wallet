from lnbits.core.models import Payment
from lnbits.core.services import create_invoice
from loguru import logger

from .crud import (
    create_client_data,
    get_client_data_by_id,
    get_profiles_by_id,
    update_client_data,
)
from .models import (
    CreateClientData,
)




async def payment_received_for_client_data(payment: Payment) -> bool:
    logger.info("Payment receive logic generation is disabled.")
    return True


