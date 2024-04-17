import asyncio
from typing import Generic, Dict, Any, Iterable, Awaitable, TypeVar

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
