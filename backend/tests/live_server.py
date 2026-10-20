"""The browser-test app with the REAL served risk model and the REAL assistant provider.

Opt-in, never run by CI or the default Playwright config: `frontend/playwright.live.config.ts`
starts it for one journey with the live model. The provider and its key come from the environment
(LLM_PROVIDER and GROQ_API_KEY, GEMINI_API_KEY or ANTHROPIC_API_KEY); without a key the assistant
is in guided mode and the journey says so. Same in-memory database and accounts as `e2e_server.py`.
"""

from app.engines.risk.artefact import load_if_present
from tests.e2e_server import build_e2e_app

app = build_e2e_app()
app.state.predictor = load_if_present()
