"""命令注册模块"""

from telegram.ext import CommandHandler, CallbackQueryHandler

from .handlers.menu import start_command, help_command, menu_callback
from .handlers.overview import overview_command, overview_callback
from .handlers.positions import positions_command, positions_callback, position_detail_callback
from .handlers.decisions import decisions_command, decisions_callback, decision_detail_callback
from .handlers.llm_usage import llm_command, llm_callback, llm_records_callback, llm_detail_callback
from .handlers.strategy import (
    strategy_command, strategy_callback,
    strategy_switch_callback, strategy_confirm_callback,
)
from .handlers.advisory import (
    advisory_command, advisory_callback,
    advisory_detail_callback, advisory_action_callback,
    advisory_trigger_callback,
)
from .handlers.trading import (
    trading_command, trading_callback,
    trading_toggle_callback, trading_confirm_callback,
)


def register_commands(app):
    """注册所有命令和回调 handler"""

    # 命令 handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("menu", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("overview", overview_command))
    app.add_handler(CommandHandler("positions", positions_command))
    app.add_handler(CommandHandler("decisions", decisions_command))
    app.add_handler(CommandHandler("llm", llm_command))
    app.add_handler(CommandHandler("strategy", strategy_command))
    app.add_handler(CommandHandler("advisory", advisory_command))
    app.add_handler(CommandHandler("trading", trading_command))

    # 回调 handlers — 用 pattern 正则匹配分发
    app.add_handler(CallbackQueryHandler(menu_callback, pattern=r"^menu:"))
    app.add_handler(CallbackQueryHandler(position_detail_callback, pattern=r"^pos:detail:"))
    app.add_handler(CallbackQueryHandler(decision_detail_callback, pattern=r"^dec:detail:"))
    app.add_handler(CallbackQueryHandler(llm_records_callback, pattern=r"^llm:records$"))
    app.add_handler(CallbackQueryHandler(llm_detail_callback, pattern=r"^llm:detail:"))
    app.add_handler(CallbackQueryHandler(strategy_switch_callback, pattern=r"^str:switch:"))
    app.add_handler(CallbackQueryHandler(strategy_confirm_callback, pattern=r"^str:confirm:"))
    app.add_handler(CallbackQueryHandler(advisory_detail_callback, pattern=r"^adv:detail:"))
    app.add_handler(CallbackQueryHandler(advisory_trigger_callback, pattern=r"^adv:trigger$"))
    app.add_handler(CallbackQueryHandler(advisory_action_callback, pattern=r"^adv:(accept|reject|confirm|cancel|acceptall|confirmall|cancelall):"))
    app.add_handler(CallbackQueryHandler(trading_toggle_callback, pattern=r"^trd:toggle:"))
    app.add_handler(CallbackQueryHandler(trading_confirm_callback, pattern=r"^trd:confirm:"))

    # 在 bot_data 中注册回调函数，供菜单 handler 分发
    app.bot_data["overview_callback"] = overview_callback
    app.bot_data["positions_callback"] = positions_callback
    app.bot_data["decisions_callback"] = decisions_callback
    app.bot_data["llm_callback"] = llm_callback
    app.bot_data["strategy_callback"] = strategy_callback
    app.bot_data["advisory_callback"] = advisory_callback
    app.bot_data["trading_callback"] = trading_callback
