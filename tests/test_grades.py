import pytest

from client.grades import grade_for_level


@pytest.mark.parametrize("level,short", [
    (1, "F"), (24, "F"), (25, "E"), (99, "E"), (100, "D"), (199, "D"), (200, "C"), (349, "C"),
    (350, "B"), (499, "B"), (500, "A"), (999, "A"), (1000, "S"), (1999, "S"), (2000, "God"), (3000, "God")])
def test_grade_boundaries(level, short):
    assert grade_for_level(level).short == short


def test_grade_labels():
    assert grade_for_level(5).label == "F Grade"
    assert grade_for_level(2500).label == "God Tier"
