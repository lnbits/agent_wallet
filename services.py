from lnbits.core.models import Payment
from loguru import logger


async def payment_received_for_agent_wallet(payment: Payment) -> bool:
    logger.info(f"Agent Wallet invoice paid: {payment.payment_hash}")
    return True
