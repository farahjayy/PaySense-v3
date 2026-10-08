"""Merchant-style descriptions for generated transactions (English and Malay).

Each category's descriptions are worded so the importer's keyword categoriser (first match wins,
see `app.domain.categorize`) reads them as that category; `test_discretionary` asserts it. A
documented minority are replaced by generic bank-statement text the categoriser cannot place
(`discretionary.unrecognisable_description_share`), because real exports contain such lines.
"""

import numpy as np

TEMPLATES: dict[str, tuple[str, ...]] = {
    "Food": (
        "Mamak dinner",
        "Nasi lemak breakfast",
        "Kedai makan lunch",
        "Food court lunch",
        "Makan malam",
        "KFC",
        "McDonald's",
        "Starbucks",
        "Tealive",
        "Foodpanda order",
        "GrabFood order",
        "Bakery bread",
        "Restoran nasi kandar",
    ),
    "Transport": (
        "Touch n Go toll",
        "Petronas petrol",
        "Shell petrol",
        "Grab ride to campus",
        "MRT fare",
        "RapidKL bus",
        "Parking fee",
    ),
    "Shopping": (
        "Shopee order",
        "Lazada order",
        "Mr DIY purchase",
        "Watsons",
        "Uniqlo",
        "Zalora order",
    ),
    "Entertainment": (
        "GSC cinema ticket",
        "TGV movie",
        "Steam game purchase",
        "Karaoke night",
    ),
    "Education": (
        "Printing services",
        "Bookstore",
        "Stationery",
        "Coursera course",
    ),
}
REFUND_TEMPLATES = ("Shopee refund order", "Lazada refund", "Grab refund", "Zalora refund")
TRANSFER_TEMPLATES = ("TNG eWallet top up", "ShopeePay topup", "Transfer to own account")
UNRECOGNISABLE_TEMPLATES = ("POS PURCHASE", "CARD TXN", "QR PAY", "DEBIT ADVICE")


def describe(category: str, rng: np.random.Generator, *, recognisable: bool = True) -> str:
    if not recognisable:
        reference = int(rng.integers(1000, 10000))
        label = UNRECOGNISABLE_TEMPLATES[int(rng.integers(len(UNRECOGNISABLE_TEMPLATES)))]
        return f"{label} {reference}"
    options = TEMPLATES[category]
    return options[int(rng.integers(len(options)))]


def describe_refund(rng: np.random.Generator) -> str:
    return REFUND_TEMPLATES[int(rng.integers(len(REFUND_TEMPLATES)))]


def describe_transfer(rng: np.random.Generator) -> str:
    return TRANSFER_TEMPLATES[int(rng.integers(len(TRANSFER_TEMPLATES)))]
