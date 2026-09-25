"""A deliberately unconfigurable, fail-closed live-order boundary."""

from typing import NoReturn


class LiveOrdersDisabledError(RuntimeError):
    """Real-money order actions are unavailable in this repository."""


class DisabledLiveOrderAdapter:
    def submit_order(self, *args: object, **kwargs: object) -> NoReturn:
        raise LiveOrdersDisabledError("Live orders are disabled; only local PAPER entries exist")

    def cancel_order(self, *args: object, **kwargs: object) -> NoReturn:
        raise LiveOrdersDisabledError("Live orders are disabled; only local PAPER entries exist")

    def replace_order(self, *args: object, **kwargs: object) -> NoReturn:
        raise LiveOrdersDisabledError("Live orders are disabled; only local PAPER entries exist")
