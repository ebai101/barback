import asyncio
from textual.app import App, ComposeResult
from textual.widgets import DataTable, Header, Footer
from textual.reactive import reactive


class TaskRunner:
    def __init__(self):
        self.progress = reactive(0)

    async def run_task(self, task_id):
        for i in range(101):
            self.progress = i
            await asyncio.sleep(0.1)  # Simulate work
        return f"Task {task_id} completed"


class Barback(App):
    CSS = """
    DataTable {
        height: 1fr;
    }
    """

    def __init__(self):
        super().__init__()
        self.task_runners = [TaskRunner() for _ in range(5)]

    def compose(self) -> ComposeResult:
        yield Header()
        yield DataTable()
        yield Footer()

    def on_mount(self):
        table = self.query_one(DataTable)
        table.add_columns("Task", "Status", "Progress")
        for i in range(5):
            table.add_row(f"Task {i}", "Pending", "0%")
        asyncio.create_task(self.run_tasks())

    async def run_tasks(self):
        tasks = [self.run_task(i) for i in range(5)]
        await asyncio.gather(*tasks)

    async def run_task(self, task_id):
        table = self.query_one(DataTable)
        table.update_cell(task_id, "Status", "Running")
        runner = self.task_runners[task_id]

        def update_progress():
            table.update_cell(task_id, "Progress", f"{runner.progress}%")

        runner.progress.watch(update_progress)

        result = await runner.run_task(task_id)
        table.update_cell(task_id, "Status", "Completed")
        table.update_cell(task_id, "Progress", "100%")


if __name__ == "__main__":
    app = Barback()
    app.run()
