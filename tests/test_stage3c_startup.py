from test_stage3c_ui import app, make_controller


def test_compact_starting_does_not_claim_zero_network_activity(make_controller):
    c = make_controller()
    assert "未知" in c.compact_window._active_count.text()
    assert c.compact_window._empty_frame.isHidden()
