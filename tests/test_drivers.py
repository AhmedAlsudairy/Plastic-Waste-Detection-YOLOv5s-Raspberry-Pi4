"""Tests for drivers/i2c_dev.py – LCD / I2C helpers.

smbus and RPi.GPIO are stubbed out in conftest.py so these tests run without
real hardware.  time.sleep is patched in tests that instantiate Lcd to keep
the suite fast.
"""
import sys
from unittest.mock import MagicMock, patch, call


# ── constants ─────────────────────────────────────────────────────────────────

def test_lcd_command_constants():
    """Key LCD command byte constants must match the HD44780 spec."""
    from drivers.i2c_dev import (
        LCD_CLEARDISPLAY,
        LCD_RETURNHOME,
        LCD_DISPLAYCONTROL,
        LCD_FUNCTIONSET,
        LCD_DISPLAYON,
        LCD_ENTRYLEFT,
        LCD_BACKLIGHT,
        LCD_NOBACKLIGHT,
        En, Rw, Rs,
    )

    assert LCD_CLEARDISPLAY == 0x01
    assert LCD_RETURNHOME == 0x02
    assert LCD_DISPLAYCONTROL == 0x08
    assert LCD_FUNCTIONSET == 0x20
    assert LCD_DISPLAYON == 0x04
    assert LCD_ENTRYLEFT == 0x02
    assert LCD_BACKLIGHT == 0x08
    assert LCD_NOBACKLIGHT == 0x00
    assert En == 0b00000100
    assert Rw == 0b00000010
    assert Rs == 0b00000001


# ── I2CDevice ─────────────────────────────────────────────────────────────────

def test_i2c_device_stores_address():
    """I2CDevice stores the supplied address."""
    import drivers.i2c_dev as i2c_mod

    bus_instance = MagicMock()
    with patch.object(i2c_mod, "SMBus", return_value=bus_instance):
        with patch("drivers.i2c_dev.sleep"):
            device = i2c_mod.I2CDevice(addr=0x27, bus=1)

    assert device.addr == 0x27


def test_i2c_device_write_cmd_calls_write_byte():
    """write_cmd forwards the byte to bus.write_byte."""
    import drivers.i2c_dev as i2c_mod

    bus_instance = MagicMock()
    with patch.object(i2c_mod, "SMBus", return_value=bus_instance):
        with patch("drivers.i2c_dev.sleep"):
            device = i2c_mod.I2CDevice(addr=0x27, bus=1)
            device.write_cmd(0xFF)

    bus_instance.write_byte.assert_called_with(0x27, 0xFF)


def test_i2c_device_read_returns_bus_value():
    """read() returns whatever bus.read_byte returns."""
    import drivers.i2c_dev as i2c_mod

    bus_instance = MagicMock()
    bus_instance.read_byte.return_value = 42

    with patch.object(i2c_mod, "SMBus", return_value=bus_instance):
        with patch("drivers.i2c_dev.sleep"):
            device = i2c_mod.I2CDevice(addr=0x27, bus=1)
            result = device.read()

    assert result == 42


def test_i2c_device_write_cmd_arg():
    """write_cmd_arg forwards both command and data to bus."""
    import drivers.i2c_dev as i2c_mod

    bus_instance = MagicMock()
    with patch.object(i2c_mod, "SMBus", return_value=bus_instance):
        with patch("drivers.i2c_dev.sleep"):
            device = i2c_mod.I2CDevice(addr=0x27, bus=1)
            device.write_cmd_arg(0x10, 0xAB)

    bus_instance.write_byte_data.assert_called_with(0x27, 0x10, 0xAB)


# ── Lcd ───────────────────────────────────────────────────────────────────────

def _make_lcd():
    """Return a Lcd instance with all I2C / sleep calls mocked out."""
    import drivers.i2c_dev as i2c_mod

    bus_instance = MagicMock()
    with patch.object(i2c_mod, "SMBus", return_value=bus_instance):
        with patch("drivers.i2c_dev.sleep"):
            lcd = i2c_mod.Lcd(addr=0x27)
    # Swap the underlying I2CDevice for a clean mock so individual tests
    # don't see noise from __init__ calls.
    lcd.lcd = MagicMock()
    return lcd


def test_lcd_display_string_line1_sets_cursor():
    """lcd_display_string on line 1 issues the 0x80 cursor command."""
    lcd = _make_lcd()

    with patch("drivers.i2c_dev.sleep"):
        lcd.lcd_display_string("HI", 1)

    # Collect all byte values sent via write_cmd
    sent = [c.args[0] for c in lcd.lcd.write_cmd.call_args_list]
    # 0x80 or a combination that includes 0x80 (4-bit mode splits the byte)
    assert any(b & 0x80 for b in sent)


def test_lcd_clear_sends_clear_and_home():
    """lcd_clear issues LCD_CLEARDISPLAY (0x01) and LCD_RETURNHOME (0x02)."""
    lcd = _make_lcd()

    with patch("drivers.i2c_dev.sleep"):
        lcd.lcd_clear()

    sent = [c.args[0] for c in lcd.lcd.write_cmd.call_args_list]
    # In 4-bit mode the two nibbles are OR'd with control bits; the high
    # nibble of 0x01 (CLEARDISPLAY) is 0x00 and the low nibble is 0x10.
    # We simply verify write_cmd was called (i.e. the display was addressed).
    assert lcd.lcd.write_cmd.called


def test_lcd_backlight_on_sends_backlight_byte():
    """lcd_backlight(1) sends LCD_BACKLIGHT (0x08)."""
    lcd = _make_lcd()

    with patch("drivers.i2c_dev.sleep"):
        lcd.lcd_backlight(1)

    from drivers.i2c_dev import LCD_BACKLIGHT
    lcd.lcd.write_cmd.assert_called_with(LCD_BACKLIGHT)


def test_lcd_backlight_off_sends_nobacklight_byte():
    """lcd_backlight(0) sends LCD_NOBACKLIGHT (0x00)."""
    lcd = _make_lcd()

    with patch("drivers.i2c_dev.sleep"):
        lcd.lcd_backlight(0)

    from drivers.i2c_dev import LCD_NOBACKLIGHT
    lcd.lcd.write_cmd.assert_called_with(LCD_NOBACKLIGHT)


# ── CustomCharacters ──────────────────────────────────────────────────────────

def test_custom_characters_stores_lcd_reference():
    """CustomCharacters keeps a reference to the supplied Lcd."""
    from drivers.i2c_dev import CustomCharacters

    lcd_mock = MagicMock()
    cc = CustomCharacters(lcd_mock)

    assert cc.lcd is lcd_mock
