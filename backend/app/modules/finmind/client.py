"""FinMind API async client with rate-limit handling."""

from __future__ import annotations

from typing import Any

import httpx
import structlog

logger = structlog.get_logger()

_DEFAULT_TIMEOUT = 30.0


class FinMindAPIError(Exception):
    """Raised when the FinMind API returns a non-success response."""

    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        self.message = message
        super().__init__(f"FinMind API error {status_code}: {message}")


class FinMindRateLimitError(FinMindAPIError):
    """Raised when the FinMind API returns 402 (rate limit exceeded)."""

    def __init__(self, message: str = "Rate limit exceeded") -> None:
        super().__init__(status_code=402, message=message)


class FinMindClient:
    """Low-level async client for the FinMind REST API v4.

    Parameters
    ----------
    token : str
        FinMind API bearer token.
    base_url : str
        Base URL of the FinMind API (default v4 endpoint).
    """

    def __init__(
        self,
        token: str,
        base_url: str = "https://api.finmindtrade.com/api/v4",
    ) -> None:
        self._token = token
        self._base_url = base_url.rstrip("/")

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    async def fetch(
        self,
        dataset: str,
        data_id: str | None = None,
        start_date: str = "",
        end_date: str | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch data from the FinMind ``/data`` endpoint.

        Parameters
        ----------
        dataset : str
            FinMind dataset name (e.g. ``TaiwanStockPrice``).
        data_id : str | None
            Stock symbol such as ``"2330"``.  ``None`` for datasets that
            do not require a specific security (e.g. ``TaiwanStockInfo``).
        start_date : str
            ISO-formatted start date (``YYYY-MM-DD``).
        end_date : str | None
            Optional ISO-formatted end date.

        Returns
        -------
        list[dict]
            The ``data`` array from the FinMind response.

        Raises
        ------
        FinMindRateLimitError
            When the API returns HTTP 402.
        FinMindAPIError
            For any other non-success status or unexpected response shape.
        httpx.TimeoutException
            When the request exceeds the configured timeout.
        """
        params: dict[str, str] = {"dataset": dataset}
        if data_id is not None:
            params["data_id"] = data_id
        if start_date:
            params["start_date"] = start_date
        if end_date is not None:
            params["end_date"] = end_date

        headers = {"Authorization": f"Bearer {self._token}"}
        url = f"{self._base_url}/data"

        logger.debug(
            "finmind_request",
            dataset=dataset,
            data_id=data_id,
            start_date=start_date,
            end_date=end_date,
        )

        async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
            response = await client.get(url, params=params, headers=headers)

        # ----- error handling -----
        if response.status_code == 402:
            logger.warning("finmind_rate_limit", dataset=dataset, data_id=data_id)
            raise FinMindRateLimitError()

        if response.status_code == 404:
            logger.warning("finmind_not_found", dataset=dataset, data_id=data_id)
            raise FinMindAPIError(status_code=404, message="Resource not found")

        response.raise_for_status()

        body: dict[str, Any] = response.json()

        if body.get("msg") != "success":
            msg = body.get("msg", "unknown error")
            logger.error("finmind_api_error", msg=msg, dataset=dataset)
            raise FinMindAPIError(status_code=response.status_code, message=msg)

        data: list[dict[str, Any]] = body.get("data", [])
        logger.info(
            "finmind_response",
            dataset=dataset,
            data_id=data_id,
            record_count=len(data),
        )
        return data
