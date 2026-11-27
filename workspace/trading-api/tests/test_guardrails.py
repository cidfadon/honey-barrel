from fastapi import HTTPException
import pytest

from app.config import settings
from app.guardrails import check_notional


def test_check_notional_passes_under_cap():
    check_notional(qty=1.0, price_hint=10.0)   # 10 EUR < default 200 EUR cap


def test_check_notional_blocks_over_cap():
    with pytest.raises(HTTPException) as exc:
        check_notional(qty=10.0, price_hint=settings.max_notional_eur * 2)
    assert exc.value.status_code == 412
