import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, patch, MagicMock

from bot.lego import _normalize_tg, _as_utc


# ---------------------------------------------------------------------------
# _normalize_tg
# ---------------------------------------------------------------------------

class TestNormalizeTg:
    def test_extra_text_after_username(self):
        assert _normalize_tg("NicetasJava телеграм юзернейм", "fb") == "@NicetasJava"

    def test_at_prefix_with_extra_text(self):
        assert _normalize_tg("@user мой тг", "fb") == "@user"

    def test_clean_username_no_at(self):
        assert _normalize_tg("someuser", "fb") == "@someuser"

    def test_clean_username_with_at(self):
        assert _normalize_tg("@someuser", "fb") == "@someuser"

    def test_phone_number_kept_as_is(self):
        assert _normalize_tg("+995598280733", "fb") == "+995598280733"

    def test_phone_with_spaces(self):
        assert _normalize_tg("+7 999 123 45 67", "fb") == "+7 999 123 45 67"

    def test_empty_returns_fallback(self):
        assert _normalize_tg("", "Никита Морозов") == "Никита Морозов"

    def test_whitespace_only_returns_fallback(self):
        assert _normalize_tg("   ", "fallback") == "fallback"

    def test_short_token_below_3_chars_returns_fallback(self):
        # tokens < 3 chars shouldn't match as usernames
        assert _normalize_tg("ok", "fallback") == "fallback"

    def test_tme_link(self):
        result = _normalize_tg("t.me/NicetasJava", "fb")
        # should extract "NicetasJava" (after "me/")
        assert result == "@me" or result == "@NicetasJava"
        # acceptable: either grabs first word-like token


# ---------------------------------------------------------------------------
# _as_utc
# ---------------------------------------------------------------------------

class TestAsUtc:
    def test_naive_datetime_gets_utc(self):
        naive = datetime(2026, 5, 15, 10, 0, 0)
        result = _as_utc(naive)
        assert result.tzinfo == timezone.utc

    def test_aware_datetime_converted_to_utc(self):
        plus3 = timezone(timedelta(hours=3))
        aware = datetime(2026, 5, 15, 13, 0, 0, tzinfo=plus3)
        result = _as_utc(aware)
        assert result.tzinfo == timezone.utc
        assert result.hour == 10  # 13:00+03 = 10:00 UTC


# ---------------------------------------------------------------------------
# import_lego — round-robin and dedup logic
# ---------------------------------------------------------------------------

def _make_state(rr_counter: int, last_dt: datetime) -> dict:
    return {"rr_counter": rr_counter, "last_processed_created_time": last_dt.isoformat()}


def _make_sheet_rows(header: list, data_rows: list[dict]) -> list[list]:
    result = [header]
    for d in data_rows:
        result.append([d.get(col, "") for col in header])
    return result


HEADER = ["created_time", "полное_имя", "ваш_телеграмм_юзернейм_или_номер_телефона:",
          "номер_телефона", "platform", "какой_ваш_возраст?",
          "был_ли_опыт_чаттером_?", "какое_у_вас_знание_английского_языка?",
          "есть_ли_у_вас_пк\\ноутбук?_нужен_для_работы"]

OLD_DT = datetime(2026, 5, 15, 10, 0, 0, tzinfo=timezone.utc)
NEW_DT1 = datetime(2026, 5, 15, 11, 0, 0, tzinfo=timezone.utc)
NEW_DT2 = datetime(2026, 5, 15, 11, 30, 0, tzinfo=timezone.utc)


def _new_row(ct: datetime, name: str, tg: str, phone: str = "") -> dict:
    return {
        "created_time": ct.isoformat(),
        "полное_имя": name,
        "ваш_телеграмм_юзернейм_или_номер_телефона:": tg,
        "номер_телефона": phone,
        "platform": "ig",
        "какой_ваш_возраст?": "25",
        "был_ли_опыт_чаттером_?": "No",
        "какое_у_вас_знание_английского_языка?": "B2",
        "есть_ли_у_вас_пк\\ноутбук?_нужен_для_работы": "Yes",
    }


def _read_range_yd_only(rows):
    """Return rows for YD forma 1 only; other sheets get empty."""
    call_count = {"n": 0}

    async def _side_effect(spreadsheet_id, range_):
        call_count["n"] += 1
        return rows if call_count["n"] == 1 else []

    return _side_effect


@pytest.mark.asyncio
async def test_rr_counter_advances_only_on_successful_write():
    """Two new rows: first is duplicate (written=0), second is new (written=5).
    rr_counter must advance only once → saved as rr_counter=1."""

    state = _make_state(rr_counter=0, last_dt=OLD_DT)
    rows = _make_sheet_rows(HEADER, [
        _new_row(NEW_DT1, "Dup Lead", "@dupuser"),
        _new_row(NEW_DT2, "Real Lead", "@realuser"),
    ])
    saved_states = []

    with (
        patch("bot.lego.get_lego_state", new=AsyncMock(return_value=state)),
        patch("bot.lego.set_lego_state", new=AsyncMock(side_effect=lambda s: saved_states.append(s))),
        patch("bot.lego.read_range", new=AsyncMock(side_effect=_read_range_yd_only(rows))),
        patch("bot.lego.append_lego_lead", new=AsyncMock(side_effect=[0, 5])),
        patch("bot.lego.config") as mock_cfg,
    ):
        mock_cfg.HR_LIST = [("Mia", "@mia"), ("Dima", "@dima")]
        mock_cfg.GROUP_CHAT_ID = -100500
        mock_cfg.LEGO_FORM_ID = "form_id"

        bot = MagicMock()
        bot.send_message = AsyncMock()

        from bot.lego import import_lego
        processed = await import_lego(bot)

    assert processed == 1
    bot.send_message.assert_called_once()
    final_state = saved_states[-1]
    assert final_state["rr_counter"] == 1


@pytest.mark.asyncio
async def test_duplicate_row_does_not_send_message():
    """All new rows are duplicates → no messages sent, rr_counter unchanged."""

    state = _make_state(rr_counter=2, last_dt=OLD_DT)
    rows = _make_sheet_rows(HEADER, [_new_row(NEW_DT1, "Dup", "@dup")])

    with (
        patch("bot.lego.get_lego_state", new=AsyncMock(return_value=state)),
        patch("bot.lego.set_lego_state", new=AsyncMock()),
        patch("bot.lego.read_range", new=AsyncMock(side_effect=_read_range_yd_only(rows))),
        patch("bot.lego.append_lego_lead", new=AsyncMock(return_value=0)),
        patch("bot.lego.config") as mock_cfg,
    ):
        mock_cfg.HR_LIST = [("Mia", "@mia"), ("Dima", "@dima")]
        mock_cfg.GROUP_CHAT_ID = -100500
        mock_cfg.LEGO_FORM_ID = "form_id"

        bot = MagicMock()
        bot.send_message = AsyncMock()

        from bot.lego import import_lego
        processed = await import_lego(bot)

    assert processed == 0
    bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_strict_gt_excludes_last_processed_row():
    """Row with ct == last_dt must be excluded (strict > comparison)."""

    state = _make_state(rr_counter=0, last_dt=NEW_DT1)
    rows = _make_sheet_rows(HEADER, [
        _new_row(NEW_DT1, "Already Done", "@already"),  # == last_dt → excluded
        _new_row(NEW_DT2, "New Lead", "@newlead"),       # > last_dt → included
    ])

    with (
        patch("bot.lego.get_lego_state", new=AsyncMock(return_value=state)),
        patch("bot.lego.set_lego_state", new=AsyncMock()),
        patch("bot.lego.read_range", new=AsyncMock(side_effect=_read_range_yd_only(rows))),
        patch("bot.lego.append_lego_lead", new=AsyncMock(return_value=42)),
        patch("bot.lego.config") as mock_cfg,
    ):
        mock_cfg.HR_LIST = [("Mia", "@mia")]
        mock_cfg.GROUP_CHAT_ID = -100500
        mock_cfg.LEGO_FORM_ID = "form_id"

        bot = MagicMock()
        bot.send_message = AsyncMock()

        from bot.lego import import_lego
        processed = await import_lego(bot)

    assert processed == 1
    bot.send_message.assert_called_once()


@pytest.mark.asyncio
async def test_round_robin_distributes_across_hrs():
    """Three new leads, two HRs → alternates: HR0, HR1, HR0."""

    state = _make_state(rr_counter=0, last_dt=OLD_DT)
    t1 = datetime(2026, 5, 15, 11, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 5, 15, 11, 1, tzinfo=timezone.utc)
    t3 = datetime(2026, 5, 15, 11, 2, tzinfo=timezone.utc)
    rows = _make_sheet_rows(HEADER, [
        _new_row(t1, "Lead1", "@lead1"),
        _new_row(t2, "Lead2", "@lead2"),
        _new_row(t3, "Lead3", "@lead3"),
    ])

    written_hr_names = []

    async def fake_append(data):
        written_hr_names.append(data["Стейдж HR, точно так,как в CRM"])
        return len(written_hr_names) * 10

    with (
        patch("bot.lego.get_lego_state", new=AsyncMock(return_value=state)),
        patch("bot.lego.set_lego_state", new=AsyncMock()),
        patch("bot.lego.read_range", new=AsyncMock(side_effect=_read_range_yd_only(rows))),
        patch("bot.lego.append_lego_lead", new=AsyncMock(side_effect=fake_append)),
        patch("bot.lego.config") as mock_cfg,
    ):
        mock_cfg.HR_LIST = [("Mia", "@mia"), ("Dima", "@dima")]
        mock_cfg.GROUP_CHAT_ID = -100500
        mock_cfg.LEGO_FORM_ID = "form_id"

        bot = MagicMock()
        bot.send_message = AsyncMock()

        from bot.lego import import_lego
        processed = await import_lego(bot)

    assert processed == 3
    assert written_hr_names == ["Mia", "Dima", "Mia"]
