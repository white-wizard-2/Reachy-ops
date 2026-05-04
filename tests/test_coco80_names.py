from robot_manage.coco80_names import COCO80_CLASS_NAMES, coco80_display_label


def test_len_80() -> None:
    assert len(COCO80_CLASS_NAMES) == 80


def test_placeholder_maps_to_tv() -> None:
    assert coco80_display_label(62, "class62") == "tv"


def test_real_label_unchanged() -> None:
    assert coco80_display_label(0, "person") == "person"


def test_mismatch_id_not_remapped() -> None:
    assert coco80_display_label(1, "class0") == "class0"
