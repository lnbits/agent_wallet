# Description: Add your page endpoints here.


from fastapi import APIRouter, Depends
from lnbits.core.views.generic import index
from lnbits.decorators import check_account_exists
from lnbits.helpers import template_renderer

agent_wallet_generic_router = APIRouter()


def agent_wallet_renderer():
    return template_renderer(["agent_wallet/templates"])


#######################################
##### ADD YOUR PAGE ENDPOINTS HERE ####
#######################################


# Backend admin page
agent_wallet_generic_router.add_api_route(
    "/", methods=["GET"], endpoint=index, dependencies=[Depends(check_account_exists)]
)


# Frontend shareable page


