import asyncio
from functools import cached_property
from threading import Thread
from typing import Awaitable

import aiohttp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, ConversationHandler, MessageHandler, filters, \
    CallbackQueryHandler

from snitchbot.i18n import Messages
from snitchbot.lib.network import URL, DNS
from snitchbot.model import Config, Commands
from snitchbot.tasks import TaskManager


class SiteWatcher:
    """Site watcher."""

    class States:
        GET_SITE: int = 1
        CANCEL_WATCH: int = 2

    tasks: TaskManager[str]

    def __init__(self):
        self.tasks = TaskManager()

    async def handle_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Initiate watch-site conversation."""
        await update.message.reply_text(Messages.TYPE_ADDRESS)
        return SiteWatcher.States.GET_SITE

    async def handle_stop(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Stop watching."""
        user = update.effective_user.username
        sites = sorted(list(self.tasks.get_tasks(user)))

        if not sites:
            await update.message.reply_text(Messages.NO_SITES_ARE_WATCHED)
            return ConversationHandler.END

        options = [[InlineKeyboardButton(url, callback_data=url) for url in self.tasks.get_tasks(user)]]
        reply_keyboard = InlineKeyboardMarkup(options)

        await update.message.reply_text(Messages.WHICH_TO_STOP, reply_markup=reply_keyboard)
        return SiteWatcher.States.CANCEL_WATCH

    async def handle_stop_site(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Do stop watching the chosen site."""
        query = update.callback_query
        await query.answer()  # TODO: Is this necessary?

        user = query.from_user.username
        url = query.data

        self.tasks.cancel(user, url)

        no_more_watched = Messages.NO_MORE_WATCHED.format(url=url)
        await update.effective_user.send_message(no_more_watched)
        return ConversationHandler.END

    async def handle_get_site(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Get site URL."""
        url = update.message.text.strip().lower()
        user = update.effective_user.username
        if self.tasks.has_task(user, url):
            already_watched = Messages.ALREADY_WATCHED.format(url=url)
            await update.message.reply_text(already_watched)
            return ConversationHandler.END

        url = URL.ensure_scheme(url, default_scheme='https')

        if not URL.has_netloc(url):
            invalid_url = Messages.NO_NETLOC.format(url=url)
            await update.message.reply_text(invalid_url)
            return SiteWatcher.States.GET_SITE

        if not await DNS.exists(url):
            unknown_domain = Messages.UNKNOWN_ADDR.format(url=url)
            await update.message.reply_text(unknown_domain)
            return SiteWatcher.States.GET_SITE

        site_is_available = Messages.IS_AVAILABLE.format(url=url)
        notify: Awaitable = update.message.reply_text(site_is_available)
        task: Awaitable = self._do_watch_site(site=url, on_success=notify)
        self.tasks.submit(user, url, task)
        await update.message.reply_text(Messages.WILL_NOTIFY.format(url=url))
        return ConversationHandler.END

    async def handle_cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Cancels and ends the conversation."""
        await update.message.reply_text(Messages.CANCELLED)
        return ConversationHandler.END

    async def _do_watch_site(self, site: str, on_success: Awaitable):
        while True:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(site, verify_ssl=False) as response:
                        if response.ok:
                            await on_success
                            return
            except Exception as error:
                print(f"Exception while accessing {site}: {error}")
            await asyncio.sleep(15)

    @cached_property
    def handler(self) -> ConversationHandler:
        """Get conversation handler."""
        # Conversation states:
        states = {
            # Get site URL
            SiteWatcher.States.GET_SITE: [MessageHandler(filters.TEXT, self.handle_get_site)],
            SiteWatcher.States.CANCEL_WATCH: [CallbackQueryHandler(self.handle_stop_site)],
        }

        return ConversationHandler(
            entry_points=[
                CommandHandler(Commands.WATCH, self.handle_start),
                CommandHandler(Commands.STOP_WATCH, self.handle_stop)
            ],
            fallbacks=[CommandHandler(Commands.CANCEL, self.handle_cancel)],
            states=states,
        )


class SnitchBot:
    tasks: asyncio.Queue
    background_thread: Thread


def run(config: Config):
    app = ApplicationBuilder().token(config.token).build()

    site_watcher = SiteWatcher()
    app.add_handler(site_watcher.handler)
    app.run_polling()


def main():
    with open("data/token") as token_file:
        token = token_file.read()
    config = Config(token=token)
    run(config)


if __name__ == '__main__':
    main()
