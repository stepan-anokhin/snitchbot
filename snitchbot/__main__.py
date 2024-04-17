import asyncio
from functools import cached_property
from threading import Thread
from typing import Dict, Any, Awaitable, Generic, TypeVar, Iterable

import aiohttp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, ConversationHandler, MessageHandler, filters, \
    CallbackQueryHandler

from snitchbot.lib.network import is_valid_url, domain_exists
from snitchbot.model import Config


async def hello(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(f'Hello {update.effective_user.first_name}')


class Commands:
    """Bot commands."""
    WATCH = "watch"
    STOP_WATCH = "stopwatch"
    CANCEL = "cancel"


Key = TypeVar("Key")


class TaskManager(Generic[Key]):
    """Keeps tasks for each user."""

    tasks: Dict[Any, Dict[Key, asyncio.Task]]

    def __init__(self):
        self.tasks = {}

    def _user_tasks(self, user: str) -> Dict[str, asyncio.Task]:
        """Get user tasks."""
        if user not in self.tasks:
            self.tasks[user] = {}
        return self.tasks[user]

    def _clear_task(self, user: str, url: str):
        """Clear task from the active watch list."""
        print(f"Clearing task: {user} -> {url}")
        user_tasks = self._user_tasks(user)
        user_tasks.pop(url, None)

    def get_tasks(self, user: str) -> Iterable[Key]:
        """Get list of user tasks."""
        return self._user_tasks(user).keys()

    def has_tasks(self, user: str) -> bool:
        """Check if user has any tasks."""
        return len(self._user_tasks(user)) > 0

    def has_task(self, user: str, key: Key) -> bool:
        """Check if user has a task with the given key."""
        return key in self._user_tasks(user)

    def submit(self, user: str, key: Key, work: Awaitable):
        """Start watching site."""
        user_tasks = self._user_tasks(user)
        task = asyncio.create_task(work)
        user_tasks[key] = task
        task.add_done_callback(lambda *_: self._clear_task(user, key))

    def cancel(self, user: str, key: str):
        """Stop watching site."""
        user_tasks = self._user_tasks(user)
        task: asyncio.Task = user_tasks.pop(key, None)
        if task is not None:
            task.cancel()


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
        await update.message.reply_text(f'Пожалуйста, напиши адрес сайта, статус которого надо отслеживать?')
        return SiteWatcher.States.GET_SITE

    async def handle_stop(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Stop watching."""
        user = update.effective_user.username
        sites = sorted(list(self.tasks.get_tasks(user)))

        if not sites:
            await update.message.reply_text("В данный момент вы не отслеживаете никаких сайтов.")
            return ConversationHandler.END

        options = [[InlineKeyboardButton(url, callback_data=url) for url in self.tasks.get_tasks(user)]]
        reply_keyboard = InlineKeyboardMarkup(options)

        await update.message.reply_text(
            f"Какой сайт нужно перестать отслеживать?",
            reply_markup=reply_keyboard
        )

        return SiteWatcher.States.CANCEL_WATCH

    async def handle_stop_site(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Do stop watching the chosen site."""
        query = update.callback_query
        await query.answer()  # TODO: Is this necessary?

        user = query.from_user.username
        url = query.data

        self.tasks.cancel(user, url)

        await update.effective_user.send_message(f"Сайт {url} больше не отслеживается!")
        return ConversationHandler.END

    async def handle_get_site(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Get site URL."""
        url = update.message.text.strip()
        user = update.effective_user.username
        if self.tasks.has_task(user, url):
            await update.message.reply_text(f"Сайт '{url}' уже отслеживается.")
            return ConversationHandler.END

        if not is_valid_url(url):
            invalid_url = f"Кажется, '{url}' не является валидным сетевым адресом. Попробуйте еще раз!"
            await update.message.reply_text(invalid_url)
            return SiteWatcher.States.GET_SITE

        if not await domain_exists(url):
            unknown_domain = f"Не удается определить адрес сайта '{url}'. Попробуйте еще раз!"
            await update.message.reply_text(unknown_domain)
            return SiteWatcher.States.GET_SITE

        notify: Awaitable = update.message.reply_text(f"{url} теперь доступен!")
        task: Awaitable = self._do_watch_site(site=url, on_success=notify)
        self.tasks.submit(user, url, task)
        await update.message.reply_text(f'Отслеживаю статус сайта "{url}" '
                                        f'и сразу напишу, как только он станет доступным...')
        return ConversationHandler.END

    async def handle_cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Cancels and ends the conversation."""
        await update.message.reply_text("Хорошо, проехали!")
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
    app.add_handler(CommandHandler("hello", hello))

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
