"""The privacy and assistant notice a person accepts on first login (WP19, PDPA).

Versioned: changing what the notice says means a new version, and everyone is asked again. The
provider's name is filled in from the settings, so the notice always names the provider that
actually receives the assistant's messages (D-53).
"""

CONSENT_VERSION = "v1"
PROVIDER_NAMES = {"gemini": "Google (Gemini API)", "anthropic": "Anthropic (Claude API)"}


def consent_sections(provider: str) -> list[tuple[str, str]]:
    who = PROVIDER_NAMES.get(provider, "no model provider (guided mode only)")
    free_tier = (
        " On the free tier Google may use what is sent to improve its products."
        if provider == "gemini"
        else ""
    )
    return [
        (
            "What PaySense keeps",
            "Your username, a scrambled (hashed) form of your passphrase, the transactions you add "
            "or import, your recurring items, BNPL plans, budgets, saved risk reports, and a log "
            "of what you asked the assistant and what it did.",
        ),
        (
            "Where it lives",
            "In a database in Singapore that only the PaySense server can read. Singapore is "
            "outside Malaysia, so this is a cross-border transfer under the PDPA.",
        ),
        (
            "What the assistant sends",
            f"When you chat, your message and figures PaySense worked out (totals, forecasts, "
            f"risk results and at most 20 recent transactions) are sent to {who} to write the "
            f"reply.{free_tier} Do not type details you would not want to share. The buttons "
            "(guided mode) send nothing.",
        ),
        (
            "Not advice, not a credit decision",
            "PaySense gives estimates from your own records. It is not financial advice and not a "
            "credit decision: you decide.",
        ),
        (
            "You confirm every change",
            "The assistant can only propose a change. Nothing is saved until you press Confirm.",
        ),
        (
            "Your data, your call",
            "You can download everything PaySense holds about you, or delete it, at any time "
            "from the Account page.",
        ),
    ]
