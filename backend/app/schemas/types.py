from decimal import Decimal
from typing import Annotated

from pydantic import PlainSerializer

# A Decimal type that serializes to a string in JSON to preserve precision
# Usage: field_name: DecimalStr
DecimalStr = Annotated[
    Decimal,
    PlainSerializer(lambda x: str(x) if x is not None else None, return_type=str),
]
