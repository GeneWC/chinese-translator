import logging

from PySide6.QtCore import QObject, QRunnable, Signal, Slot


class WorkerSignals(QObject):
    finished = Signal(object, object)
    failed = Signal(object, str)
    progress = Signal(str, int)


class Worker(QRunnable):
    def __init__(self, tag, function):
        super().__init__()
        self.tag = tag
        self.function = function
        self.signals = WorkerSignals()

    @Slot()
    def run(self):
        try:
            result = self.function(self.signals.progress.emit)
        except Exception as exc:
            logging.exception("Background task failed")
            self.signals.failed.emit(self.tag, str(exc))
        else:
            self.signals.finished.emit(self.tag, result)
