import asyncio

from fastapi import APIRouter
from lnbits.tasks import create_permanent_unique_task
from loguru import logger

from .crud import db
from .tasks import wait_for_paid_invoices
from .views import agent_wallet_generic_router
from .views_api import agent_wallet_api_router

agent_wallet_ext: APIRouter = APIRouter(
    prefix="/agent_wallet", tags=["Agent Wallet"]
)
agent_wallet_ext.include_router(agent_wallet_generic_router)
agent_wallet_ext.include_router(agent_wallet_api_router)


agent_wallet_static_files = [
    {
        "path": "/agent_wallet/static",
        "name": "agent_wallet_static",
    }
]

scheduled_tasks: list[asyncio.Task] = []


def agent_wallet_stop():
    for task in scheduled_tasks:
        try:
            task.cancel()
        except Exception as ex:
            logger.warning(ex)


def agent_wallet_start():
    task = create_permanent_unique_task("ext_agent_wallet", wait_for_paid_invoices)
    scheduled_tasks.append(task)


__all__ = [
    "db",
    "agent_wallet_ext",
    "agent_wallet_start",
    "agent_wallet_static_files",
    "agent_wallet_stop",
]