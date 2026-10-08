"""Keyword-rule category guessing for CSV import previews (port of v1 `services/categorize.py`).

Reserved categories carry meaning for the forecasting flows (`app/domain/flows.py`):
  Refund    money back for a purchase; netted against spend, never counted as income
  Transfer  an explicit own-account move (e-wallet top-up, to savings); ignored in both directions
  BNPL      instalments the app logged for a plan; assigned by the app, never guessed from text
"""

import re

REFUND = "Refund"
TRANSFER = "Transfer"
BNPL = "BNPL"
DEFAULT_CATEGORY = "Other"

# Order matters: the first category with a matching keyword wins, so Refund and Transfer come
# first ("Shopee refund" is a refund, not Shopping). Transfer is deliberately limited to explicit
# own-account wording: a bare "transfer in" on a statement is usually a parent's allowance.
CATEGORY_KEYWORDS = {
    REFUND: ["refund", "reversal", "cashback", "chargeback"],
    TRANSFER: [
        "own account",
        "inter-account",
        "interaccount",
        "top up",
        "top-up",
        "topup",
        "transfer to savings",
        "transfer between",
    ],
    "Food": [
        "grab food",
        "grabfood",
        "food",
        "mcd",
        "mcdonald",
        "kfc",
        "mamak",
        "cafe",
        "restoran",
        "restaurant",
        "nasi",
        "foodpanda",
        "starbucks",
        "tealive",
        "zus",
        "bakery",
        "makan",
    ],
    "Transport": [
        "tng",
        "touch n go",
        "touchngo",
        "petrol",
        "petronas",
        "shell",
        "grab ride",
        "grabcar",
        "rapidkl",
        "mrt",
        "lrt",
        "bus",
        "toll",
        "parking",
        "myrapid",
    ],
    "Rent": ["rent", "sewa", "hostel", "deposit rumah"],
    "Salary": ["salary", "gaji", "payroll", "wage", "stipend"],
    "Allowance": ["allowance", "duit", "parents", "scholarship", "ptptn", "jpa", "mara", "yayasan"],
    "Shopping": [
        "shopee",
        "lazada",
        "zalora",
        "uniqlo",
        "mr diy",
        "mr. diy",
        "watsons",
        "guardian",
        "sephora",
        "ikea",
    ],
    "Bills": [
        "bill",
        "unifi",
        "maxis",
        "celcom",
        "digi",
        "umobile",
        "u mobile",
        "tnb",
        "electric",
        "water",
        "syabas",
        "indah water",
        "astro",
        "netflix",
        "spotify",
        "icloud",
        "yes 5g",
    ],
    "Entertainment": [
        "cinema",
        "gsc",
        "tgv",
        "movie",
        "steam",
        "game",
        "concert",
        "karaoke",
        "bowling",
    ],
    "Education": [
        "book",
        "tuition",
        "course",
        "udemy",
        "coursera",
        "exam",
        "yuran",
        "utp",
        "university",
        "print",
        "stationery",
    ],
}


def _matches(keyword: str, text: str) -> bool:
    # Prefix word-boundary: "rent" matches "rental" but not "parents"; "print" still matches
    # "printing".
    return re.search(r"\b" + re.escape(keyword), text) is not None


def guess_category(description: str | None) -> str:
    text = (description or "").lower()
    if not text:
        return DEFAULT_CATEGORY
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(_matches(keyword, text) for keyword in keywords):
            return category
    return DEFAULT_CATEGORY


def guess_type(description: str | None, amount_sign: int) -> str:
    """Sign wins when the source provides one; keywords break the tie otherwise."""
    if amount_sign > 0:
        return "income"
    if amount_sign < 0:
        return "expense"
    text = (description or "").lower()
    income_words = (
        CATEGORY_KEYWORDS["Salary"]
        + CATEGORY_KEYWORDS["Allowance"]
        + ["refund", "transfer in", "credit"]
    )
    return "income" if any(_matches(word, text) for word in income_words) else "expense"
