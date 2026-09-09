import pytest

from doppelhand import inputs
from doppelhand.errors import ActionError

VK_CONTROL, VK_SHIFT, VK_RETURN, VK_DOWN = 0x11, 0x10, 0x0D, 0x28


def test_named_keys_resolve():
    assert inputs.resolve_key("Return")[0] == VK_RETURN
    assert inputs.resolve_key("Down")[0] == VK_DOWN
    assert inputs.resolve_key("F5")[0] == 0x74


def test_combination_splits_into_modifiers_and_key():
    modifiers, vk = inputs.parse_combo("ctrl+shift+s")
    assert modifiers[:2] == [VK_CONTROL, VK_SHIFT]
    assert vk == ord("S")


def test_trailing_plus_is_the_plus_key():
    modifiers, vk = inputs.parse_combo("ctrl++")
    assert modifiers == [VK_CONTROL]
    assert vk == inputs.resolve_key("plus")[0]


def test_a_shifted_character_implies_shift():
    modifiers, _ = inputs.parse_combo("!")
    assert VK_SHIFT in modifiers


def test_unknown_names_are_rejected():
    with pytest.raises(ActionError):
        inputs.parse_combo("hyper+k")
    with pytest.raises(ActionError):
        inputs.resolve_key("Wingding")


def test_arrow_keys_are_flagged_extended():
    # Applications that read scan codes see Down as the numeric keypad's 2 without it.
    assert VK_DOWN in inputs._EXTENDED


def test_astral_characters_become_surrogate_pairs():
    assert len(inputs._code_units("a")) == 1
    assert len(inputs._code_units("\U0001F600")) == 2


def test_modifier_string_parses():
    assert inputs.parse_modifiers("ctrl+alt") == [VK_CONTROL, 0x12]
    assert inputs.parse_modifiers(None) == []
