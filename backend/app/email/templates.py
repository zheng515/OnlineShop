"""Email texts (FR96, FR97). Plain text; each says why it was sent; links only to the shop."""

from .outbox import SHOP_URL

FOOTER = "\n\n--\nOnlineShop\n{reason}\n"


def _email(subject: str, greeting_name: str, lines: list[str], reason: str) -> tuple[str, str]:
    body = f"Hello {greeting_name},\n\n" + "\n".join(lines) + FOOTER.format(reason=reason)
    return subject, body


def verify_email(name: str, token: str) -> tuple[str, str]:
    return _email(
        "Confirm your email address",
        name,
        [
            "Thank you for registering with OnlineShop. Please confirm your email address by opening this link:",
            "",
            f"{SHOP_URL}/verify-email.html?token={token}",
            "",
            "The link works once and for 24 hours.",
        ],
        "You received this email because this address was used to register an account.",
    )


def registration_attempt(name: str) -> tuple[str, str]:
    return _email(
        "Someone tried to register with your email address",
        name,
        [
            "Someone just tried to create a new OnlineShop account with this email address, which already",
            "belongs to your account. No new account was created.",
            "",
            "If it was you, you can log in with your existing account; if you forgot your password, reset it here:",
            f"{SHOP_URL}/forgot-password.html",
            "",
            "If it was not you, you can ignore this email.",
        ],
        "You received this email because your address is registered with OnlineShop.",
    )


def reset_password(name: str, token: str) -> tuple[str, str]:
    return _email(
        "Reset your password",
        name,
        [
            "We received a request to reset the password of your OnlineShop account. Choose a new password here:",
            "",
            f"{SHOP_URL}/reset-password.html?token={token}",
            "",
            "The link works once and for 1 hour. If you did not ask for this, ignore this email;",
            "your password stays as it is.",
        ],
        "You received this email because a password reset was requested for your account.",
    )


def password_changed(name: str) -> tuple[str, str]:
    return _email(
        "Your password was changed",
        name,
        [
            "The password of your OnlineShop account has just been changed.",
            "",
            "If you did not do this, reset your password right away and check your orders:",
            f"{SHOP_URL}/forgot-password.html",
        ],
        "You received this email to keep your account secure.",
    )


def _order_link(order_id: int) -> str:
    return f"{SHOP_URL}/order.html?id={order_id}"


def order_placed(name: str, number: str, order_id: int, total: str, minutes: int) -> tuple[str, str]:
    return _email(
        f"Order {number}: please complete your payment",
        name,
        [
            f"Thank you for your order {number}. The amount payable is {total}.",
            "",
            f"Your items are held for you for {minutes} minutes. If the payment is not completed by then,",
            "the order is cancelled automatically. Pay or check your order here:",
            _order_link(order_id),
        ],
        "You received this email because you placed an order.",
    )


def payment_received(name: str, number: str, order_id: int, total: str) -> tuple[str, str]:
    return _email(
        f"Order {number}: payment received",
        name,
        [f"We have received your payment of {total} for order {number}. Thank you!", "", _order_link(order_id)],
        "You received this email because you paid for an order.",
    )


def order_shipped(name: str, number: str, order_id: int) -> tuple[str, str]:
    return _email(
        f"Order {number} has been shipped",
        name,
        [f"Good news: your order {number} is on its way.", "", _order_link(order_id)],
        "You received this email because an order of yours was shipped.",
    )


def order_cancelled(name: str, number: str, order_id: int, reason: str, refunding: bool) -> tuple[str, str]:
    lines = [f"Your order {number} has been cancelled {reason}."]
    if refunding:
        lines.append("The amount you paid is being refunded; we will email you when the refund is complete.")
    lines += ["", _order_link(order_id)]
    reason_line = "You received this email because an order of yours was cancelled."
    return _email(f"Order {number} has been cancelled", name, lines, reason_line)


def refund_completed(name: str, number: str, order_id: int, amount: str) -> tuple[str, str]:
    return _email(
        f"Order {number}: refund completed",
        name,
        [f"We have refunded {amount} for order {number}.", "", _order_link(order_id)],
        "You received this email because a refund was made for one of your orders.",
    )
