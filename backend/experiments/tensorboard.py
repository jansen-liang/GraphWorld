from __future__ import annotations

import contextlib
import io
import time
from pathlib import Path

import matplotlib.pyplot as plt
try:
    from tensorboard.compat.proto import event_pb2, summary_pb2, tensor_pb2, tensor_shape_pb2, types_pb2
    from tensorboard.summary.writer.event_file_writer import EventFileWriter
except ModuleNotFoundError:  # TensorBoard is optional for core simulation runs.
    event_pb2 = summary_pb2 = tensor_pb2 = tensor_shape_pb2 = types_pb2 = None
    EventFileWriter = None
from tqdm import tqdm

class TensorBoardWriter:
    def __init__(self, log_dir: Path | str) -> None:
        self._log_dir = Path(log_dir)
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._writer = EventFileWriter(str(self._log_dir)) if EventFileWriter else None
        self._disabled = self._writer is None
        self._warned = False

    def _disable(self, exc: Exception) -> None:
        if self._disabled:
            return
        self._disabled = True
        if not self._warned:
            tqdm.write(f"tensorboard disabled for {self._log_dir}: {exc}")
            self._warned = True
        with contextlib.suppress(Exception):
            self._writer.close()

    def _add_event(self, event: event_pb2.Event) -> None:
        if self._disabled:
            return
        try:
            self._log_dir.mkdir(parents=True, exist_ok=True)
            self._writer.add_event(event)
        except Exception as exc:
            self._disable(exc)

    def add_scalar(self, tag: str, value: float, step: int) -> None:
        if self._disabled:
            return
        summary = summary_pb2.Summary(
            value=[summary_pb2.Summary.Value(tag=tag, simple_value=float(value))]
        )
        self._add_event(event_pb2.Event(wall_time=time.time(), step=int(step), summary=summary))

    def add_text(self, tag: str, text: str, step: int = 0) -> None:
        if self._disabled:
            return
        metadata = summary_pb2.SummaryMetadata(
            plugin_data=summary_pb2.SummaryMetadata.PluginData(plugin_name="text")
        )
        tensor = tensor_pb2.TensorProto(
            dtype=types_pb2.DT_STRING,
            string_val=[text.encode("utf-8")],
            tensor_shape=tensor_shape_pb2.TensorShapeProto(dim=[tensor_shape_pb2.TensorShapeProto.Dim(size=1)]),
        )
        summary = summary_pb2.Summary(
            value=[summary_pb2.Summary.Value(tag=tag, metadata=metadata, tensor=tensor)]
        )
        self._add_event(event_pb2.Event(wall_time=time.time(), step=int(step), summary=summary))

    def add_figure(self, tag: str, fig: plt.Figure, step: int = 0) -> None:
        if self._disabled:
            return
        buffer = io.BytesIO()
        fig.savefig(buffer, format="png", dpi=140)
        image = summary_pb2.Summary.Image(
            encoded_image_string=buffer.getvalue(),
            height=int(fig.bbox.bounds[3]),
            width=int(fig.bbox.bounds[2]),
            colorspace=4,
        )
        summary = summary_pb2.Summary(value=[summary_pb2.Summary.Value(tag=tag, image=image)])
        self._add_event(event_pb2.Event(wall_time=time.time(), step=int(step), summary=summary))

    def flush(self) -> None:
        if self._disabled:
            return
        try:
            self._writer.flush()
        except Exception as exc:
            self._disable(exc)

    def close(self) -> None:
        with contextlib.suppress(Exception):
            self._writer.close()
