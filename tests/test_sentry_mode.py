from robot_manage.sentry_mode import _first_nonrisk_line, _risk_line_is_high, sentry_u_centers


def test_risk_line_detection() -> None:
    assert _risk_line_is_high("A person is visible.\nRISK: high")
    assert not _risk_line_is_high("A person is visible.\nRISK: low")
    assert _first_nonrisk_line("Chair and desk.\nRISK: high") == "Chair and desk."


def test_sentry_u_centers_monotonic_and_covers_span() -> None:
    us = sentry_u_centers(span_start=0.1, span_end=0.9, fov_horizontal=0.3, overlap_fraction=0.1)
    assert len(us) >= 2
    assert us[0] >= 0.1 - 1e-6
    assert us[-1] >= 0.9 - 1e-6
    for a, b in zip(us, us[1:]):
        assert b > a
