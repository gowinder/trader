"""Tests for TranslationService (pure functions only, no network)."""

from ai_trader.utils.translator import TranslationService


class TestIsChinese:

    def setup_method(self):
        self.svc = TranslationService(enabled=False)

    def test_is_chinese_with_chinese(self):
        assert self.svc._is_chinese("你好") is True

    def test_is_chinese_with_english(self):
        assert self.svc._is_chinese("hello") is False

    def test_is_chinese_mixed(self):
        assert self.svc._is_chinese("hello你好") is True

    def test_is_chinese_empty(self):
        assert self.svc._is_chinese("") is False

    def test_is_chinese_numbers(self):
        assert self.svc._is_chinese("12345") is False


class TestTranslateDisabled:

    def test_translate_disabled(self):
        svc = TranslationService(enabled=False)
        assert svc.translate("hello world") == "hello world"

    def test_translate_empty_string(self):
        svc = TranslationService(enabled=False)
        assert svc.translate("") == ""

    def test_translate_short_text(self):
        svc = TranslationService(enabled=False)
        assert svc.translate("hi") == "hi"

    def test_translate_chinese_text(self):
        svc = TranslationService(enabled=False)
        assert svc.translate("你好世界") == "你好世界"
