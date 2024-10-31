from textual.widgets import Static


class InfoBox(Static):
    def __init__(self, id: str = ""):
        super().__init__(id=id)
