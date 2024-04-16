import asyncio
from functools import cached_property
from threading import Thread
from typing import Dict, Any

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, ConversationHandler, MessageHandler, filters

from snitchbot.model import Config


async def hello(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(f'Hello {update.effective_user.first_name}')


class Commands:
    """Bot commands."""
    WATCH = "watch"
    STOP_WATCH = "stopwatch"
    CANCEL = "cancel"


class SiteWatcher:
    """Site watcher."""

    tasks: Dict[Any, Dict[str, asyncio.Task]]

    class States:
        GET_SITE: int = 1

    def __init__(self):
        self.tasks = {}

    def user_tasks(self, user: str) -> Dict[str, asyncio.Task]:
        if user not in self.tasks:
            self.tasks[user] = {}
        return self.tasks[user]

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Initiate watch-site conversation."""
        await update.message.reply_text(f'Пожалуйста, напиши адрес сайта, статус которого надо отслеживать?')
        return SiteWatcher.States.GET_SITE

    async def stop(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Stop watching."""
        user = update.effective_user.username
        user_tasks = self.user_tasks(user)
        if not user_tasks:
            await update.message.reply_text("В данный момент вы не отслеживаете никаких сайтов.")
            return ConversationHandler.END

        await update.message.reply_text(
            f"Пожалуйста, укажите, какой сайт перестать отслеживать?",
            reply_markup=ReplyKeyboardMarkup(
                [sorted(list(user_tasks.keys()))], one_time_keyboard=True, input_field_placeholder="Адрес сайта"
            )
        )
        return ConversationHandler.END

    async def get_site(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Get site URL."""
        url = update.message.text.strip()
        user = update.effective_user.username
        user_tasks = self.user_tasks(user)
        if url in user_tasks:
            await update.message.reply_text(f"Сайт '{url}' уже отслеживается.")
            return ConversationHandler.END

        task = asyncio.create_task(self._do_watch_site(update, update.message.text.strip()))
        user_tasks[url] = task
        task.add_done_callback(lambda *_: self.clear_task(user, url))
        await update.message.reply_text(f'Отслеживаю статус сайта "{url}" '
                                        f'и сразу напишу, как только он станет доступным...')
        return ConversationHandler.END

    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Cancels and ends the conversation."""
        await update.message.reply_text("Хорошо, проехали!")
        return ConversationHandler.END

    async def _do_watch_site(self, update: Update, site: str):
        await asyncio.sleep(15)
        await update.message.reply_text(f"{site} доступен!")

    def clear_task(self, user: str, url: str):
        """Clear task from the active list."""
        print(f"Clearing task: {user} -> {url}")
        user_tasks = self.user_tasks(user)
        user_tasks.pop(url)

    @cached_property
    def handler(self) -> ConversationHandler:
        """Get conversation handler."""
        # Conversation states:
        states = {
            # Get site URL
            SiteWatcher.States.GET_SITE: [MessageHandler(filters.TEXT, self.get_site)]
        }

        return ConversationHandler(
            entry_points=[
                CommandHandler(Commands.WATCH, self.start),
                CommandHandler(Commands.STOP_WATCH, self.stop)
            ],
            fallbacks=[CommandHandler(Commands.CANCEL, self.cancel)],
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
