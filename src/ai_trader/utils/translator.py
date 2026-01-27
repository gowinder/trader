"""Translation service for log messages"""

from typing import Optional
import hashlib
from functools import lru_cache
from loguru import logger
import sys


class TranslationService:
    """Translation service with caching and fallback"""

    def __init__(self, target_lang: str = "zh-CN", enabled: bool = True):
        """Initialize translation service

        Args:
            target_lang: Target language code (zh-cn, ja, ko, etc.)
            enabled: Whether translation is enabled
        """
        self.target_lang = target_lang
        self.enabled = enabled
        self.translator = None

        if enabled:
            try:
                from deep_translator import GoogleTranslator

                self.translator = GoogleTranslator(source="auto", target=target_lang)
                logger.debug(f"Translation service initialized (target: {target_lang})")
            except ImportError:
                logger.warning(
                    "deep-translator not installed. Run: uv add deep-translator"
                )
                self.enabled = False
            except Exception as e:
                logger.warning(f"Failed to initialize translator: {e}")
                self.enabled = False

    @lru_cache(maxsize=1000)
    def translate(self, text: str) -> str:
        """Translate text with caching

        Args:
            text: Text to translate

        Returns:
            Translated text (or original if translation fails)
        """
        if not self.enabled or not text.strip():
            return text

        # Skip translation for very short messages or already translated
        if len(text) < 3 or self._is_chinese(text):
            return text

        try:
            # deep-translator's translate method
            result = self.translator.translate(text)
            return result if result else text
        except Exception as e:
            # Fallback to original text on error
            logger.debug(f"Translation failed: {e}")
            return text

    def _is_chinese(self, text: str) -> bool:
        """Check if text contains Chinese characters

        Args:
            text: Text to check

        Returns:
            True if text contains Chinese characters
        """
        for char in text:
            if "\u4e00" <= char <= "\u9fff":
                return True
        return False

    def clear_cache(self):
        """Clear translation cache"""
        self.translate.cache_clear()


# Global translation service instance
_translation_service: Optional[TranslationService] = None


def get_translation_service() -> Optional[TranslationService]:
    """Get global translation service instance"""
    return _translation_service


def setup_translation_service(target_lang: str = "zh-cn", enabled: bool = True):
    """Setup global translation service

    Args:
        target_lang: Target language code
        enabled: Whether translation is enabled
    """
    global _translation_service
    _translation_service = TranslationService(target_lang, enabled)


class TranslatedLogHandler:
    """Custom log handler that translates messages before output"""

    def __init__(self, translation_service: TranslationService):
        """Initialize handler

        Args:
            translation_service: Translation service instance
        """
        self.translation_service = translation_service

    def write(self, message: str):
        """Write translated message

        Args:
            message: Log message to translate and write
        """
        if not message.strip():
            return

        # Extract the actual message (skip timestamp, level, etc.)
        # Loguru format: "2024-01-27 10:30:00.123 | INFO     | module:function:line - message"
        try:
            parts = message.split(" - ", 1)
            if len(parts) == 2:
                prefix, msg = parts
                # Translate only the message part
                translated_msg = self.translation_service.translate(msg.strip())
                output = f"{prefix} - {translated_msg}\n"
            else:
                # Translate the whole message if format is different
                output = self.translation_service.translate(message.strip()) + "\n"

            sys.stdout.write(output)
            sys.stdout.flush()
        except Exception as e:
            # Fallback: write original message
            sys.stdout.write(message)
            sys.stdout.flush()


def setup_translated_logger(
    level: str = "INFO",
    target_lang: str = "zh-CN",
    enabled: bool = True,
    log_file: Optional[str] = None,
):
    """Setup logger with translation support

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR)
        target_lang: Target language for translation
        enabled: Whether to enable translation
        log_file: Optional log file path (will not be translated)

    Example:
        >>> from ai_trader.utils.translator import setup_translated_logger
        >>> setup_translated_logger(level="INFO", target_lang="zh-cn", enabled=True)
        >>> logger.info("Trading decision made")
        # Output: "2024-01-27 10:30:00 | INFO | 已做出交易决策"
    """
    # Remove default handler
    logger.remove()

    if enabled:
        # Setup translation service
        setup_translation_service(target_lang, enabled)
        service = get_translation_service()

        if service and service.enabled:
            # Add translated console handler
            handler = TranslatedLogHandler(service)
            logger.add(
                handler.write,
                level=level,
                format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
                colorize=True,
            )
        else:
            # Fallback to standard output if translation fails
            logger.add(
                sys.stdout,
                level=level,
                format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
                colorize=True,
            )
    else:
        # Standard logger without translation
        logger.add(
            sys.stdout,
            level=level,
            format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
            colorize=True,
        )

    # Add file handler (always without translation)
    if log_file:
        logger.add(
            log_file,
            level=level,
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
            rotation="10 MB",
            retention="7 days",
            compression="zip",
        )

    logger.info(f"Logger initialized (level={level}, translation={'enabled' if enabled else 'disabled'})")


# Convenience function for quick setup
def enable_chinese_logs(level: str = "INFO", log_file: Optional[str] = None):
    """Quick setup for Chinese log translation

    Args:
        level: Log level
        log_file: Optional log file path

    Example:
        >>> from ai_trader.utils.translator import enable_chinese_logs
        >>> enable_chinese_logs()
        >>> logger.info("System started")
        # Output: "系统已启动"
    """
    setup_translated_logger(level=level, target_lang="zh-CN", enabled=True, log_file=log_file)
