import urwid
import asyncio
import time
from concurrent.futures import ThreadPoolExecutor


class SelectableRow(urwid.Columns):
    def __init__(self, contents, on_select, on_task):
        super().__init__(contents)
        self.on_select = on_select
        self.on_task = on_task

    def selectable(self):
        return True

    def keypress(self, size, key):
        match key:
            case " ":
                self.on_select(self)
            case "t":
                self.on_task(self)
            case "j":
                return super().keypress(size, "down")
            case "k":
                return super().keypress(size, "up")
        return super().keypress(size, key)


class BarbackTui:
    def __init__(self):
        self.data = [
            {
                "Column 1": "Item 1",
                "Column 2": "Description 1",
                "Column 3": "Click me 1",
            },
            {
                "Column 1": "Item 2",
                "Column 2": "Description 2",
                "Column 3": "Click me 2",
            },
            {
                "Column 1": "Item 3",
                "Column 2": "Description 3",
                "Column 3": "Click me 3",
            },
        ]
        self.headers = ["Column 1", "Column 2", "Column 3"]
        self.current_focus = 0
        self.loop = None
        self.running = True
        self.message_text = urwid.Text("")
        self.progress_text = urwid.Text("")
        self.table = None
        self.executor = ThreadPoolExecutor()

    def row_select(self, row):
        row_data = self.get_row_data(row)
        self.show_message(f"Selected {row_data['Column 1']}")

    def row_task(self, row):
        row_data = self.get_row_data(row)
        asyncio.create_task(self.background_task(row_data))

    def get_row_data(self, row):
        return {h: row.contents[i][0].text for i, h in enumerate(self.headers)}

    def show_message(self, message):
        self.message_text.set_text(message)

    def update_progress(self, message):
        self.progress_text.set_text(message)

    async def background_task(self, row_data):
        self.update_progress(f"Doing a task for {row_data['Column 1']}")
        await asyncio.sleep(1)  # Simulate some async work

        # Use ThreadPoolExecutor for CPU-bound task
        result = await self.run_in_thread(self.cpu_bound_task, row_data)

        # Update the data with the result
        index = self.data.index(row_data)
        self.data[index] = result

        # Update the table
        await self.update_table()

        self.update_progress(f"Done with task for {result['Column 1']}")

    def cpu_bound_task(self, row_data):
        # Simulate CPU-bound work
        time.sleep(2)
        return {
            "Column 1": f"Modified {row_data['Column 1']}",
            "Column 2": f"New description for {row_data['Column 1']}",
            "Column 3": "Updated",
            "New Column": "Dynamic content",
        }

    async def run_in_thread(self, func, *args):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self.executor, func, *args)

    async def update_table(self):
        # Get new data for all rows using ThreadPoolExecutor
        new_data = await asyncio.gather(
            *[self.run_in_thread(self.cpu_bound_task, row) for row in self.data]
        )
        self.data = new_data

        # Update headers based on the new data
        self.headers = list(self.data[0].keys()) if self.data else []

        # Recreate the entire table with new headers and rows
        self.table = self.create_table()

        # Update the main content while preserving the Padding
        main_content = (
            self.main_widget.original_widget
        )  # Get the content inside the Padding
        main_content.contents[0] = (self.table, main_content.options())
        self.loop.draw_screen()

    def create_table(self):
        header_widgets = [urwid.AttrMap(urwid.Text(h), "head") for h in self.headers]
        header = urwid.Columns(header_widgets)
        rows = []
        for row_data in self.data:
            row_widgets = [urwid.Text(str(row_data.get(h, ""))) for h in self.headers]
            selectable_row = SelectableRow(row_widgets, self.row_select, self.row_task)
            row_attr = urwid.AttrMap(selectable_row, None, focus_map="reversed")
            rows.append(row_attr)
        return urwid.ListBox([header] + rows)

    def handle_input(self, key):
        if key in ("q", "Q"):
            raise urwid.ExitMainLoop()

    def run(self):
        self.table = self.create_table()
        quit_text = urwid.Text("<q> quit <space> select <t> start task")
        main_content = urwid.Pile(
            [
                ("weight", 1, self.table),
                ("pack", urwid.Divider()),
                ("pack", self.message_text),
                ("pack", self.progress_text),
                ("pack", urwid.Divider()),
                ("pack", quit_text),
            ]
        )
        self.main_widget = urwid.Padding(main_content, left=2, right=2)
        palette = [
            ("body", "black", "light gray"),
            ("reversed", "standout", ""),
            ("head", "yellow", "black", "standout"),
        ]

        event_loop = urwid.AsyncioEventLoop(loop=asyncio.get_event_loop())
        self.loop = urwid.MainLoop(
            self.main_widget,
            palette,
            unhandled_input=self.handle_input,
            event_loop=event_loop,
        )
        self.loop.run()

    def __del__(self):
        if hasattr(self, "executor"):
            self.executor.shutdown()


def main():
    app = BarbackTui()
    app.run()


if __name__ == "__main__":
    main()
