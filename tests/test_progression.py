import pytest
from client.progression import (MAX_LEVEL, STAT_LIMIT, Progression, base_xp, slowdown, xp_level_modifier,
                                xp_to_next)


def test_xp_curve_values_and_monotonic():
    assert [xp_to_next(n) for n in (1, 2, 3, 4)] == [100, 130, 162, 194]
    assert all(xp_to_next(n + 1) > xp_to_next(n) for n in range(1, MAX_LEVEL - 1))
    assert xp_to_next(MAX_LEVEL) == 0


def test_no_level_up_below_threshold():
    p = Progression()
    assert p.add_xp(99) == 0
    assert (p.level, p.xp) == (1, 99)


def test_level_up_carries_over_xp_and_grants_points():
    p = Progression()
    assert p.add_xp(130) == 1
    assert (p.level, p.xp, p.stat_points, p.skill_points) == (2, 30, 3, 1)


def test_multi_level_up_in_one_award():
    p = Progression()
    assert p.add_xp(100 + 130 + 10) == 2
    assert (p.level, p.xp, p.stat_points, p.skill_points) == (3, 10, 6, 2)


def test_ignores_non_positive_xp():
    p = Progression()
    assert p.add_xp(0) == 0 and p.add_xp(-50) == 0
    assert (p.level, p.xp) == (1, 0)


def test_max_level_cap():
    p = Progression()
    p.add_xp(10**13)
    assert p.level == MAX_LEVEL and p.xp == 0
    assert p.add_xp(500) == 0


def test_deterministic():
    a, b = Progression(), Progression()
    for amt in (20, 35, 80, 300, 45):
        a.add_xp(amt)
        b.add_xp(amt)
    assert a == b


def test_spend_points_on_any_stat():
    p = Progression()
    p.add_xp(100)  # 3 free points
    assert p.spend_point("intellect") and p.spend_point("vitality") and p.spend_point("intellect")
    assert p.stat_points == 0
    assert p.allocated["intellect"] == 2 and p.allocated["vitality"] == 1
    assert p.spend_point("strength") is False  # none left


def test_spend_invalid_stat_does_not_consume_point():
    p = Progression(stat_points=2)
    assert p.spend_point("charisma") is False
    assert p.stat_points == 2


def test_max_level_is_3000_and_curve_is_finite_everywhere():
    assert MAX_LEVEL == 3000
    assert xp_to_next(MAX_LEVEL - 1) > xp_to_next(1000) > xp_to_next(100) > 0


def test_add_levels_grants_points_each_level_and_caps():
    p = Progression()
    assert p.add_levels(10) == 10
    assert (p.level, p.stat_points, p.skill_points) == (11, 30, 10)
    assert p.add_levels(10**6) == MAX_LEVEL - 11
    assert p.level == MAX_LEVEL


# ---------- extended leveling ----------
def test_xp_requirements_at_milestone_levels():
    """Exact values at levels 1, 25, 100, 500, 1000 and 3000."""
    assert xp_to_next(1) == 100
    assert xp_to_next(25) == 1108                         # early game unchanged
    assert xp_to_next(100) == 25_457
    assert xp_to_next(500) == 3_216_263
    assert xp_to_next(1000) == 29_183_641
    assert xp_to_next(3000) == 0                          # cap: no further levels
    assert xp_to_next(2999) == 1_005_389_820


def test_early_levels_keep_the_original_fast_curve():
    assert all(xp_to_next(n) == base_xp(n) for n in range(1, 26)) and slowdown(25) == 1.0


def test_progression_slows_dramatically_after_25():
    ratios = [xp_to_next(n) / base_xp(n) for n in (26, 50, 100, 500, 1000, 2000)]
    assert ratios == sorted(ratios) and ratios[0] < 1.02 and ratios[2] > 3 and ratios[3] > 20 and ratios[4] > 50
    assert all(xp_to_next(n + 1) > xp_to_next(n) for n in range(1, 2999))


def test_level_3000_is_the_configurable_cap():
    p = Progression()
    p.level = 2999
    assert p.add_xp(10 ** 12) == 1 and p.level == 3000 and p.xp == 0 and p.add_xp(10 ** 9) == 0


def test_xp_from_low_level_enemies_diminishes():
    assert xp_level_modifier(100, 100) == 1.0
    assert xp_level_modifier(100, 95) == 1.0
    assert xp_level_modifier(100, 60) < 0.8
    assert xp_level_modifier(100, 20) == 0.05 and xp_level_modifier(1000, 1) == 0.05
    assert xp_level_modifier(50, 60) > 1.0                # tougher enemy pays more
    assert xp_level_modifier(1, 1) == 1.0                 # early game unaffected


def test_cannot_farm_the_cap_from_trivial_enemies():
    """Grinding level-1 enemies at level 500 yields almost nothing."""
    from client.enemy import Enemy
    e = Enemy("grunt", 100, 1)
    gain = round(e.xp * xp_level_modifier(500, 1))
    assert gain < 5 and xp_to_next(500) / max(1, gain) > 500_000


# ---------- stat allocation: +1 / +10 / +100 / +MAX ----------
def pts(n):
    return Progression(stat_points=n, level=1 + n // 3)


def test_plus_buttons_spend_exactly_the_requested_amounts():
    p = pts(300)
    assert [p.spend_points("strength", a) for a in (1, 10, 100)] == [1, 10, 100]
    assert p.allocated["strength"] == 111 and p.stat_points == 189
    assert p.spend_points("luck", "max") == 189 and p.stat_points == 0 and p.allocated["luck"] == 189


def test_spends_only_what_is_available_never_negative():
    p = pts(7)
    assert p.spend_points("agility", 100) == 7 and p.stat_points == 0
    assert p.spend_points("agility", 10) == 0 and p.spend_points("agility", "max") == 0
    assert p.stat_points == 0 and p.allocated["agility"] == 7


def test_stat_limit_is_enforced():
    p = Progression(stat_points=STAT_LIMIT + 50)
    assert p.spend_points("defense", "max") == STAT_LIMIT
    assert p.allocated["defense"] == STAT_LIMIT and p.stat_points == 50
    assert p.spend_points("defense", 1) == 0                       # full: other stats still fine
    assert p.spend_points("vitality", "max") == 50


@pytest.mark.parametrize("amount", [0, -1, -100, 1.5, "10", None, True, "MAX", [1]])
def test_invalid_amounts_spend_nothing(amount):
    p = pts(50)
    assert p.spend_points("strength", amount) == 0 and p.stat_points == 50


def test_all_seven_stats_can_receive_points():
    from client.classes import STAT_NAMES
    assert set(STAT_NAMES) == {"strength", "vitality", "defense", "agility", "intellect", "dexterity", "luck"}
    p = pts(7)
    assert all(p.spend_points(s, 1) == 1 for s in STAT_NAMES) and p.stat_points == 0
