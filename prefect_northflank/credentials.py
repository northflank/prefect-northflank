from typing import Optional

from prefect.blocks.core import Block
from pydantic import Field, SecretStr


class Northflank(Block):
    """
    Northflank API credentials block for authenticating with the Northflank API.
    """

    _block_type_name = "Northflank"
    _logo_url = "https://assets.northflank.com/Group_1410119476_2_b23babb7fd.png"
    _documentation_url = "https://github.com/northflank/prefect-northflank"

    api_token: SecretStr = Field(
        default=None, description="Northflank API token for authentication"
    )
    base_url: str = Field(
        default="https://api.northflank.com",
        description="Base URL for the Northflank API",
    )
