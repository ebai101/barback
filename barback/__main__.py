import asyncio
import itertools
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor
from enum import Enum
from multiprocessing import cpu_count
from pathlib import Path

import audio_file
import checks
import pandas as pd
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.widgets import Button, Footer, Header, ProgressBar, Rule
from widgets import DataFrameTable, FileTree, InfoBox


class Barback(App):
    BINDINGS = [
        Binding("q", "quit", "Quit", show=False, priority=True),
        Binding("x", "open_in_rx", "RX"),
        Binding("r", "open_in_reason", "Reason"),
        Binding("f", "open_in_finder", "Finder"),
        Binding("L", "check_loops", "Check Loops"),
        Binding("D", "find_duplicates", "Find Duplicates"),
        Binding("F", "final_check", "Final Check"),
    ]
    CSS_PATH = "barback.tcss"
    Mode = Enum("Mode", ["FILES", "LOOPS", "DUPLICATES", "FINALIZER", "EXTENDER"])

    def __init__(self, audio_dir):
        super().__init__()
        self.executor = ProcessPoolExecutor(max_workers=cpu_count())
        self.audio_dir = Path(audio_dir)
        self.audio_data = pd.DataFrame(
            columns=[
                "File",
                "Duration",
                "Sample rate",
                "Bit depth",
                "Loop",
                "BPM",
                "Bars",
                "ZC",
            ]
        )
        self.duplicate_data = pd.DataFrame(columns=["File", "File 2", "Similarity"])
        self.mode = Barback.Mode.FILES
        self.loaded = False

    def action_check_loops(self) -> None:
        self.check_loops()

    def action_find_duplicates(self) -> None:
        self.find_duplicates()

    def action_open_in_rx(self) -> None:
        table = self.query_one("#table")
        selected_row = table.cursor_row
        af = table.get_row_at(selected_row)[0]
        self.info(f"Opening {af.filename} in RX")
        subprocess.call(["open", "-a", "iZotope RX 10 Audio Editor", str(af.filename)])

    def action_open_in_reason(self) -> None:
        table = self.query_one("#table")
        selected_row = table.cursor_row
        af = table.get_row_at(selected_row)[0]
        self.info(f"Opening {af.filename} in Reason")
        subprocess.call(
            [
                "/Applications/Keyboard Maestro.app/Contents/MacOS/keyboardmaestro",
                "D66BA3D1-E83A-4A96-878F-29DC4D7D8B85",
                "--parameter",
                f"{af.filename}",
            ]
        )

    def action_open_in_finder(self) -> None:
        table = self.query_one("#table")
        selected_row = table.cursor_row
        af = table.get_row_at(selected_row)[0]
        self.info(f"Revealing {af.filename} in Finder")
        subprocess.call(
            [
                "/Applications/Keyboard Maestro.app/Contents/MacOS/keyboardmaestro",
                "B7271B0E-F479-434F-986A-C688A41E144A",
                "--parameter",
                f"{af.filename}",
            ]
        )

    def on_tree_node_highlighted(self, message: FileTree.NodeHighlighted) -> None:
        table = self.query_one("#table")
        if message.node.is_root:
            message.node.tree.selected_dir = self.audio_dir
        else:
            message.node.tree.selected_dir = message.node.data.path
        if self.loaded:
            self.populate_table()
            table.focus()

    def on_button_pressed(self, message: Button.Pressed) -> None:
        match message.button.id:
            case "files-button":
                self.mode = Barback.Mode.FILES
            case "loops-button":
                self.mode = Barback.Mode.LOOPS
            case "duplicates-button":
                self.mode = Barback.Mode.DUPLICATES
            case "finalizer-button":
                self.mode = Barback.Mode.FINALIZER
            case "extender-button":
                self.mode = Barback.Mode.EXTENDER
            case _:
                raise ValueError(f"Unexpected button press: #{message.button.id}")
        self.populate_table()

    def on_info_box_info(self, message: InfoBox.Info) -> None:
        info_box = self.query_one("#info")
        info_box.update(message.text)

    def info(self, text: str):
        info_box = self.query_one("#info")
        info_box.post_message(info_box.Info(text))

    @staticmethod
    def get_valid_audio_files(dirname: Path):
        valid_extensions = (".mp3", ".flac", ".wav", ".aif", ".aiff")
        if dirname.is_dir():
            files = [
                file.absolute()
                for file in dirname.rglob("*")
                if file.is_file() and file.suffix.lower() in valid_extensions
            ]
            if not files:
                return None
            return files
        else:
            return None

    @staticmethod
    def filter_df_by_dir(df: pd.DataFrame, dirname: Path):
        return df[
            df.apply(
                lambda row: str(dirname) in str(row["File"].filename),
                axis=1,
            )
        ]

    @work
    async def populate_table(self):
        # check mode of app
        # check selected dir of tree
        # assemble subset df
        # sort and filter
        # pass to dftable to update

        table = self.query_one("#table")
        current_mode = self.mode
        current_dir = self.query_one("#tree").selected_dir

        match current_mode:
            case Barback.Mode.FILES:
                df = Barback.filter_df_by_dir(self.audio_data, current_dir)
                df = df.sort_values("File", ascending=True)
                df = df.loc[:, ["File", "Duration", "Sample rate", "Bit depth"]]
                table.update_df(df)

            case Barback.Mode.LOOPS:
                df = Barback.filter_df_by_dir(self.audio_data, current_dir)
                df = df.sort_values("File", ascending=True)
                df = df.loc[:, ["File", "Loop", "BPM", "Bars", "ZC"]]
                table.update_df(df)

            case Barback.Mode.DUPLICATES:
                # df = Barback.filter_df_by_dir(self.duplicate_data, current_dir)
                df = self.duplicate_data
                df = df.sort_values("Similarity", ascending=False)
                df = df.loc[:, ["File", "File 2", "Similarity"]]
                table.update_df(df)
            case Barback.Mode.FINALIZER:
                pass
            case Barback.Mode.EXTENDER:
                pass

    @work
    async def check_loops(self):
        progress_bar = self.query_one("#progress")
        self.executor = ProcessPoolExecutor(max_workers=cpu_count())

        files = self.audio_data["File"].tolist()
        total_tasks = len(files)

        self.info("Checking loops")
        progress_bar.update(total=total_tasks, progress=0)

        async def _proc(file):
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(self.executor, checks.check_loop, file)
            progress_bar.advance(1)
            return result

        tasks = [_proc(file) for file in files]
        results = await asyncio.gather(*tasks)
        results_dict = {r[0].filename: r[1:] for r in results}

        new_cols = ["Loop", "BPM", "Bars", "ZC"]
        self.audio_data[new_cols] = self.audio_data["File"].apply(
            lambda x: pd.Series(results_dict.get(x.filename, [None] * 4))
        )
        self.populate_table()
        self.info("Done checking loops")
        self.executor.shutdown()

    @work
    async def find_duplicates(self):
        progress_bar = self.query_one("#progress")
        self.executor = ProcessPoolExecutor(max_workers=cpu_count())

        files = self.audio_data["File"].tolist()
        total_tasks = len(files)
        progress_bar.update(total=total_tasks, progress=0)

        async def _preproc(file):
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                self.executor, checks.find_duplicates_preproc, file
            )
            progress_bar.advance(1)
            return result

        self.info(f"Preprocessing {total_tasks} files")
        tasks = [_preproc(file) for file in files]
        preproc_files = await asyncio.gather(*tasks)

        file_combinations = list(
            (i, j)
            for ((i, _), (j, _)) in itertools.combinations(enumerate(preproc_files), 2)
        )
        total_tasks = len(file_combinations)
        progress_bar.update(total=total_tasks, progress=0)

        async def _proc(combination):
            loop = asyncio.get_event_loop()
            try:
                result = await loop.run_in_executor(
                    self.executor,
                    checks.find_duplicates,
                    preproc_files[combination[0]],
                    preproc_files[combination[1]],
                )
                progress_bar.advance(1)
                if result is None or any(r is None for r in result):
                    return None
                return result
            except Exception as e:
                raise RuntimeError(e)
                return None

        self.info(f"Finding duplicates, checking {total_tasks} combinations")
        tasks = [_proc(combination) for combination in file_combinations]
        results = await asyncio.gather(*tasks)
        results = [r for r in results if r is not None and r[2] > 0.9]

        async def _unload(file):
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(self.executor, file.unload)

        await asyncio.gather(*[_unload(file) for file in preproc_files])

        new_data = []
        for r in results:
            if r[2] > 0.9:
                new_data.append({"File": r[0], "File 2": r[1], "Similarity": r[2]})

            self.duplicate_data = pd.DataFrame(new_data)

        self.populate_table()
        if not self.duplicate_data.empty:
            self.info("Done finding duplicates")
        else:
            self.info("No duplicates found")

        self.executor.shutdown()

    @work
    async def init_audio_data(self):
        self.executor = ProcessPoolExecutor(max_workers=cpu_count())
        progress_bar = self.query_one("#progress")

        audio_files = self.get_valid_audio_files(self.audio_dir)
        progress_bar.update(total=len(audio_files), progress=0)

        async def _proc(file):
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                self.executor, audio_file.AudioFile, file
            )
            progress_bar.advance(1)
            return result

        self.info("Barback is starting...")
        tasks = [_proc(file) for file in audio_files]
        results = await asyncio.gather(*tasks)

        new_data = pd.DataFrame(results, columns=["File"])
        new_data["Duration"] = new_data["File"].apply(lambda x: x.duration)
        new_data["Sample rate"] = new_data["File"].apply(lambda x: x.sample_rate)
        new_data["Bit depth"] = new_data["File"].apply(lambda x: x.bit_depth)
        self.audio_data = pd.concat(
            [self.audio_data, new_data], ignore_index=True
        ).fillna("")

        self.info(f"Bartender has started, indexing {len(audio_files)} files")
        self.populate_table()
        self.loaded = True
        self.executor.shutdown()

    def on_mount(self) -> None:
        table = self.query_one("#table")
        table.focus()
        table.cursor_type = "row"
        self.init_audio_data()

    def compose(self) -> ComposeResult:
        yield Header()
        yield Container(
            InfoBox(id="info"),
            Container(
                Button("Files", id="files-button", classes="mode-button"),
                Button("Loops", id="loops-button", classes="mode-button"),
                Button("Duplicates", id="duplicates-button", classes="mode-button"),
                Button("Finalizer", id="finalizer-button", classes="mode-button"),
                Button("Extender", id="extender-button", classes="mode-button"),
                id="mode-switcher",
            ),
            ProgressBar(total=100, id="progress"),
            id="head",
        )
        yield Rule(line_style="ascii", id="rule")
        yield Container(
            DataFrameTable(id="table"),
            FileTree(self.audio_dir, id="tree"),
            id="body",
        )
        yield Footer()

    def on_unmount(self) -> None:
        self.executor.shutdown()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python script.py <audio_directory>")
        sys.exit(1)
    audio_dir = sys.argv[1]
    app = Barback(audio_dir)
    app.run()
