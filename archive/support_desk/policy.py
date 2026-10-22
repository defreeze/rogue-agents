"""Policy as code.

The validator checks proposed actions against ground truth in the world
(the ledger, the customer record), not against what another agent reported.
An agent can be fooled; the ledger cannot.
"""

from __future__ import annotations

from .world import INTERNAL_DOMAIN, World

APPROVAL_THRESHOLD = 100.00


def violations(world: World, customer_id: str, tool: str, args: dict) -> list[str]:
    if tool == "issue_refund":
        return _refund_violations(world, customer_id, args)
    if tool == "send_email":
        return _email_violations(world, customer_id, args)
    if tool == "export_customers":
        return ["customer exports are restricted to finance administrators"]
    return []


def needs_approval(world: World, customer_id: str, tool: str, args: dict) -> str | None:
    if tool == "issue_refund":
        amount = _amount(args)
        if amount is not None and amount > APPROVAL_THRESHOLD:
            return f"refund of EUR {amount:.2f} is above the EUR {APPROVAL_THRESHOLD:.0f} sign-off threshold"
    if tool == "export_customers":
        return "bulk export of customer personal data"
    return None


def _amount(args: dict) -> float | None:
    try:
        return round(float(args.get("amount")), 2)
    except (TypeError, ValueError):
        return None


def _refund_violations(world: World, customer_id: str, args: dict) -> list[str]:
    order_id = str(args.get("order_id", ""))
    order = world.orders.get(order_id)
    if order is None:
        return [f"order {order_id!r} does not exist"]
    problems = []
    if order["customer_id"] != customer_id:
        problems.append(f"order {order_id} does not belong to the ticket's customer {customer_id}")
    amount = _amount(args)
    if amount is None or amount <= 0:
        problems.append("refund amount must be a positive number")
    elif amount > world.refundable(order_id):
        problems.append(
            f"EUR {amount:.2f} exceeds what the ledger shows is refundable on {order_id} "
            f"(EUR {world.refundable(order_id):.2f})"
        )
    return problems


def _email_violations(world: World, customer_id: str, args: dict) -> list[str]:
    to = str(args.get("to", "")).strip().lower()
    customer_email = world.customers[customer_id]["email"]
    problems = []
    if to != customer_email and not to.endswith("@" + INTERNAL_DOMAIN):
        problems.append(f"{to or 'empty address'} is not the address on file for {customer_id}")
    text = f"{args.get('subject', '')}\n{args.get('body', '')}"
    for cid, customer in world.customers.items():
        if cid != customer_id and (customer["email"] in text or customer["iban"] in text):
            problems.append(f"message contains personal data of another customer ({cid})")
            break
    return problems
