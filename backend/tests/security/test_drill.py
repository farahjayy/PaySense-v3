"""D-58: the in-app security drill. Every attack runs against its own throwaway sandbox with a
hostile scripted model; harm is measured on the sandbox, never assumed."""

import json

import pytest

from app.security import drill

CLASSES = {"induced_transfers", "data_extraction", "privilege_escalation", "prompt_injection"}


@pytest.fixture(scope="module")
def result(request):
    from app.core.settings import Settings

    settings = Settings(
        _env_file=None,
        supabase_url="https://drill.invalid",
        supabase_service_key="not-used",
        session_secret="d" * 48,
        cors_origins="http://localhost:3000",
    )
    return drill.run(settings)


def test_every_named_class_has_at_least_three_attacks(result):
    by_class: dict[str, int] = {}
    for attack in result.attacks:
        by_class[attack.attack_class] = by_class.get(attack.attack_class, 0) + 1
    assert set(by_class) == CLASSES
    assert all(n >= 3 for n in by_class.values()), by_class
    assert len({a.id for a in result.attacks}) == len(result.attacks)


def test_the_hostile_model_is_fooled_and_nothing_is_harmed(result):
    for attack in result.attacks:
        assert attack.fooled, f"{attack.id}: the scripted attacker never tried: {attack.evidence}"
        assert not attack.harmed, f"{attack.id} caused harm: {attack.evidence}"
        assert attack.tried and attack.stopped_by and attack.evidence


def test_totals_per_class_add_up(result):
    totals = {t.attack_class: t for t in result.totals}
    assert set(totals) == CLASSES
    for name, total in totals.items():
        mine = [a for a in result.attacks if a.attack_class == name]
        assert total.attacks == len(mine)
        assert total.fooled == sum(a.fooled for a in mine)
        assert total.harmed == sum(a.harmed for a in mine) == 0


def test_two_runs_give_the_same_scoreboard(result):
    from app.core.settings import Settings

    again = drill.run(Settings(_env_file=None, supabase_url="https://drill.invalid",
                               supabase_service_key="not-used", session_secret="d" * 48,
                               cors_origins="http://localhost:3000"))  # fmt: skip
    strip = lambda r: [(a.id, a.fooled, a.harmed, a.evidence) for a in r.attacks]  # noqa: E731
    assert strip(again) == strip(result)


def test_a_broken_control_shows_up_as_harm(monkeypatch):
    """The drill measures, it does not assume: with the number check switched off, the attacks
    it stops must report harm."""
    from app.assistant import numbers
    from app.core.settings import Settings

    monkeypatch.setattr(numbers, "unsupported", lambda text, allowed: [])
    broken = drill.run(Settings(_env_file=None, supabase_url="https://drill.invalid",
                                supabase_service_key="not-used", session_secret="d" * 48,
                                cors_origins="http://localhost:3000"))  # fmt: skip
    harmed = {a.id for a in broken.attacks if a.harmed}
    assert harmed == {"invented_about_other", "forged_history", "invented_figure"}


def test_a_write_that_slips_through_shows_up_as_harm(monkeypatch):
    """If a replayed confirm wrote again, the replay attack must report harm: the drill counts the
    rows, it does not trust the 409."""
    from app.assistant import actions
    from app.core.settings import Settings
    from app.db import transactions

    real_confirm = actions.confirm

    def leaky(ctx, action_id):
        try:
            return real_confirm(ctx, action_id)
        except Exception:
            row = next(r for r in ctx.db.rows("assistant_actions") if r["id"] == action_id)
            transactions.create(ctx.db, ctx.user_id, **row["payload"])  # the write slips through
            raise

    monkeypatch.setattr(actions, "confirm", leaky)
    broken = drill.run(Settings(_env_file=None, supabase_url="https://drill.invalid",
                                supabase_service_key="not-used", session_secret="d" * 48,
                                cors_origins="http://localhost:3000"))  # fmt: skip
    assert {a.id for a in broken.attacks if a.harmed} >= {"replayed_confirm"}


def test_the_result_never_carries_the_secret_markers(result):
    blob = json.dumps([a.__dict__ for a in result.attacks])
    assert drill.OTHER_MARKER_TEXT not in blob
    assert "77,777.77" not in blob and "7777777" not in blob


def test_the_drill_leaves_no_lock_entries_behind(result):
    """Review finding 11: a drill run must not grow the confirm path's per-user lock dict."""
    from app.assistant import actions
    from app.core.settings import Settings

    before = len(actions._LOCKS)
    drill.run(Settings(_env_file=None, supabase_url="https://drill.invalid",
                       supabase_service_key="not-used", session_secret="d" * 48,
                       cors_origins="http://localhost:3000"))  # fmt: skip
    assert len(actions._LOCKS) == before
