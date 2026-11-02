import csv
import math
import queue
import re
import sys
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pyqtgraph as pg
import serial
from PySide6.QtCore import QThread, QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)
from serial.tools import list_ports


@dataclass(frozen=True)
class Sample:
    throttle: int
    rpm_raw: int
    current_raw: int
    voltage_raw: int
    consumption_mah: int
    temperature_c: int
    thrust_n: float | None

    @property
    def values(self) -> dict[str, float | None]:
        return {
            "Throttle": float(self.throttle),
            "ERPM": float(self.rpm_raw * 100),
            "Current": self.current_raw * 0.01,
            "Voltage": self.voltage_raw * 0.01,
            "Consumption": float(self.consumption_mah),
            "Temperature": float(self.temperature_c),
            "Thrust": (self.thrust_n - 263000) *0.001,
        }


def parse_data_line(line: str) -> Sample:
    fields = line.strip().split(",")
    if len(fields) != 8 or fields[0] != "DATA":
        raise ValueError("Expected DATA,throttle,rpm,current,voltage,consumption,temp,thrust")
    try:
        throttle, rpm, current, voltage, consumption, temperature = map(int, fields[1:7])
        thrust = None if fields[7].strip().upper() in {"", "NA"} else float(fields[7])
    except ValueError as exc:
        raise ValueError("Telemetry fields must be numeric (thrust may be NA)") from exc
    if not 0 <= throttle <= 100:
        raise ValueError("Throttle must be between 0 and 100")
    if any(not 0 <= value <= 65535 for value in (rpm, current, voltage, consumption)):
        raise ValueError("Raw KISS telemetry fields must be unsigned 16-bit values")
    if not -128 <= temperature <= 127:
        raise ValueError("Temperature must fit the signed 8-bit KISS field")
    if thrust is not None and (not math.isfinite(thrust) or abs(thrust) > 1_000_000):
        raise ValueError("Thrust must be a finite value in newtons")
    return Sample(throttle, rpm, current, voltage, consumption, temperature, thrust)


class SerialThread(QThread):
    sample_received = Signal(object)
    status_changed = Signal(str)
    error_occurred = Signal(str)

    def __init__(self, port: str):
        super().__init__()
        self.port = port
        self.commands: queue.Queue[bytes] = queue.Queue()
        self.stopping = False
        self.bad_line_reported = False

    def send_throttle(self, value: int) -> None:
        self.commands.put(f"THROTTLE,{value}\n".encode("ascii"))

    def stop(self) -> None:
        self.send_throttle(0)
        self.stopping = True

    def run(self) -> None:
        try:
            with serial.Serial(self.port, 115200, timeout=0.1, write_timeout=0.2) as port:
                port.reset_input_buffer()
                self.status_changed.emit(f"Connected: {self.port} · 115200 baud")
                while not self.stopping or not self.commands.empty():
                    while True:
                        try:
                            port.write(self.commands.get_nowait())
                        except queue.Empty:
                            break
                    raw = port.readline()
                    if raw:
                        try:
                            self.sample_received.emit(parse_data_line(raw.decode("ascii")))
                        except (UnicodeDecodeError, ValueError) as exc:
                            if not self.bad_line_reported:
                                self.bad_line_reported = True
                                self.error_occurred.emit(f"Skipped invalid telemetry line: {exc}")
        except serial.SerialException as exc:
            self.error_occurred.emit(f"Serial connection failed: {exc}")
        finally:
            self.status_changed.emit("Disconnected")


METRICS = (
    ("Throttle", "%", "#48b7ff"),
    ("ERPM", "rpm", "#b58cff"),
    ("Current", "A", "#ffad5c"),
    ("Voltage", "V", "#f3d45c"),
    ("Consumption", "mAh", "#55d6a5"),
    ("Temperature", "°C", "#ff6d7a"),
    ("Thrust", "N", "#65d3d9"),
)


class ThrustStand(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Thrust Stand")
        self.resize(1500, 900)
        self.serial_thread: SerialThread | None = None
        self.samples: deque[tuple[float, dict[str, float | None]]] = deque(maxlen=4000)
        self.started_at: float | None = None
        self.csv_file = None
        self.csv_writer = None
        self.values: dict[str, QLabel] = {}
        self.plots: dict[str, tuple[pg.PlotWidget, object]] = {}
        self._build_ui()
        self.refresh_ports()
        self.graph_timer = QTimer(self)
        self.graph_timer.timeout.connect(self.update_graphs)
        self.graph_timer.start(50)

    def _build_ui(self) -> None:
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("THRUST STAND")
        title.setObjectName("title")
        header.addWidget(title)
        self.port_box = QComboBox()
        self.port_box.setEditable(True)
        self.port_box.setMinimumWidth(210)
        self.port_box.setEditText("/dev/ttyACM0")
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh_ports)
        self.connect_button = QPushButton("Connect")
        self.connect_button.clicked.connect(self.toggle_connection)
        header.addWidget(QLabel("UART"))
        header.addWidget(self.port_box)
        header.addWidget(refresh)
        header.addWidget(self.connect_button)
        header.addStretch(1)
        self.status_label = QLabel("Disconnected · 115200 baud")
        self.status_label.setObjectName("status")
        header.addWidget(self.status_label)
        layout.addLayout(header)

        throttle_row = QHBoxLayout()
        throttle_label = QLabel("THROTTLE INPUT")
        throttle_label.setObjectName("section")
        throttle_row.addWidget(throttle_label)
        self.throttle_slider = QSlider(Qt.Orientation.Horizontal)
        self.throttle_slider.setRange(0, 100)
        self.throttle_slider.setValue(0)
        self.throttle_spin = QSpinBox()
        self.throttle_spin.setRange(0, 100)
        self.throttle_spin.setSuffix(" %")
        self.throttle_spin.setValue(0)
        self.throttle_slider.valueChanged.connect(self.throttle_spin.setValue)
        self.throttle_spin.valueChanged.connect(self.throttle_slider.setValue)
        self.throttle_spin.valueChanged.connect(self.send_throttle)
        throttle_row.addWidget(self.throttle_slider, 1)
        throttle_row.addWidget(self.throttle_spin)
        throttle_row.addSpacing(20)
        self.test_name = QLineEdit()
        self.test_name.setPlaceholderText("Test name")
        self.test_name.setMaximumWidth(220)
        self.record_button = QPushButton("Start recording")
        self.record_button.clicked.connect(self.toggle_recording)
        throttle_row.addWidget(self.test_name)
        throttle_row.addWidget(self.record_button)
        layout.addLayout(throttle_row)

        body = QHBoxLayout()
        body.setSpacing(14)
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(245)
        metrics = QVBoxLayout(sidebar)
        metrics.setContentsMargins(16, 16, 16, 16)
        metrics.setSpacing(14)
        readout_title = QLabel("LIVE TELEMETRY")
        readout_title.setObjectName("section")
        metrics.addWidget(readout_title)
        for name, unit, color in METRICS:
            line = QFormLayout()
            label = QLabel(name)
            label.setObjectName("metricName")
            value = QLabel("--")
            value.setObjectName("metricValue")
            value.setStyleSheet(f"color: {color}")
            self.values[name] = value
            line.addRow(label, value)
            metrics.addLayout(line)
        metrics.addStretch(1)
        self.record_status = QLabel("Not recording")
        self.record_status.setWordWrap(True)
        self.record_status.setObjectName("status")
        metrics.addWidget(self.record_status)
        body.addWidget(sidebar)

        graph_grid = QGridLayout()
        graph_grid.setSpacing(10)
        for index, (name, unit, color) in enumerate(METRICS):
            plot = pg.PlotWidget()
            plot.setBackground("#111820")
            plot.setTitle(name, color="#e5edf5", size="11pt")
            plot.setLabel("left", unit)
            plot.setLabel("bottom", "Time", units="s")
            plot.showGrid(x=True, y=True, alpha=0.22)
            plot.setXRange(0, 15, padding=0)
            plot.getAxis("left").setTextPen("#91a0ad")
            plot.getAxis("bottom").setTextPen("#91a0ad")
            curve = plot.plot(pen=pg.mkPen(color, width=2))
            self.plots[name] = (plot, curve)
            graph_grid.addWidget(plot, index // 3, index % 3)
        body.addLayout(graph_grid, 1)
        layout.addLayout(body, 1)
        self.setCentralWidget(root)
        self.setStyleSheet(
            """
            QMainWindow, QWidget { background: #0c1117; color: #e5edf5; }
            QLabel#title { font-size: 19px; font-weight: 700; letter-spacing: 2px; }
            QLabel#section { color: #8fa3b8; font-size: 11px; font-weight: 700; }
            QWidget#sidebar { background: #111820; border: 1px solid #25313d; border-radius: 8px; }
            QLabel#metricName { color: #91a0ad; font-size: 12px; }
            QLabel#metricValue { font-size: 18px; font-weight: 600; }
            QLabel#status { color: #91a0ad; font-size: 11px; }
            QLineEdit, QComboBox, QSpinBox { background: #111820; border: 1px solid #31404d;
                border-radius: 4px; padding: 7px; }
            QPushButton { background: #1d3448; border: 1px solid #31516b;
                border-radius: 4px; padding: 7px 12px; }
            QPushButton:hover { background: #25445d; }
            """
        )

    def refresh_ports(self) -> None:
        current = self.port_box.currentText() or "/dev/ttyACM0"
        ports = [port.device for port in list_ports.comports()]
        self.port_box.clear()
        self.port_box.addItems(ports)
        self.port_box.setEditText(current)

    def send_throttle(self, value: int) -> None:
        if self.serial_thread and self.serial_thread.isRunning():
            self.serial_thread.send_throttle(value)

    def toggle_connection(self) -> None:
        if self.serial_thread and self.serial_thread.isRunning():
            self.serial_thread.stop()
            if not self.serial_thread.wait(1500):
                QMessageBox.warning(self, "Disconnect pending", "The serial worker has not stopped yet.")
                return
            self.serial_thread = None
            self.connect_button.setText("Connect")
            return
        port = self.port_box.currentText().strip()
        if not port:
            QMessageBox.warning(self, "Serial port required", "Enter a serial port such as /dev/ttyACM0.")
            return
        self.serial_thread = SerialThread(port)
        self.serial_thread.sample_received.connect(self.receive_sample)
        self.serial_thread.status_changed.connect(self.status_label.setText)
        self.serial_thread.error_occurred.connect(self.show_serial_error)
        self.serial_thread.finished.connect(self.connection_finished)
        self.serial_thread.start()
        self.serial_thread.send_throttle(0)
        self.connect_button.setText("Disconnect")
        self.throttle_spin.setValue(0)

    def connection_finished(self) -> None:
        self.connect_button.setText("Connect")
        if self.csv_writer:
            self.stop_recording()
            QMessageBox.warning(self, "Recording stopped", "The serial connection ended.")

    def show_serial_error(self, message: str) -> None:
        if message.startswith("Skipped invalid"):
            self.status_label.setText(message)
        else:
            QMessageBox.critical(self, "Serial error", message)

    def receive_sample(self, sample: Sample) -> None:
        elapsed = time.monotonic()
        if self.started_at is None:
            self.started_at = elapsed
        elapsed -= self.started_at
        values = sample.values
        self.samples.append((elapsed, values))
        for name, value in values.items():
            self.values[name].setText("--" if value is None else f"{value:,.2f}")
        if self.csv_writer:
            try:
                # ponytail: stdlib CSV; use pandas only if analysis moves into the GUI.
                self.csv_writer.writerow(
                    [
                        datetime.now().isoformat(timespec="milliseconds"),
                        f"{elapsed:.3f}",
                        sample.throttle,
                        f"{sample.rpm_raw * 100:.0f}",
                        f"{sample.current_raw * 0.01:.2f}",
                        f"{sample.voltage_raw * 0.01:.2f}",
                        sample.consumption_mah,
                        sample.temperature_c,
                        "" if sample.thrust_n is None else f"{sample.thrust_n:.3f}",
                    ]
                )
                self.csv_file.flush()
            except OSError as exc:
                self.stop_recording()
                QMessageBox.critical(self, "Recording failed", str(exc))

    def update_graphs(self) -> None:
        if not self.samples:
            return
        latest = self.samples[-1][0]
        visible = [(t, values) for t, values in self.samples if t >= latest - 15]
        x = [t for t, _ in visible]
        for name, (_, curve) in self.plots.items():
            y = [values[name] for _, values in visible]
            points = [(t, value) for t, value in zip(x, y) if value is not None]
            curve.setData([p[0] for p in points], [p[1] for p in points])
            self.plots[name][0].setXRange(max(0, latest - 15), max(15, latest), padding=0)

    def toggle_recording(self) -> None:
        if self.csv_writer:
            self.stop_recording()
            return
        if not self.serial_thread or not self.serial_thread.isRunning():
            QMessageBox.warning(self, "Not connected", "Connect to telemetry before recording.")
            return
        name = self.test_name.text().strip()
        safe_name = re.sub(r"[^A-Za-z0-9_-]+", "_", name).strip("_")
        if not safe_name:
            QMessageBox.warning(self, "Test name required", "Enter a test name using letters or numbers.")
            return
        directory = Path.cwd() / "recordings"
        path = directory / f"{safe_name}_{datetime.now():%Y%m%d_%H%M%S_%f}.csv"
        try:
            directory.mkdir(parents=True, exist_ok=True)
            self.csv_file = path.open("x", newline="", encoding="utf-8")
            self.csv_writer = csv.writer(self.csv_file)
            self.csv_writer.writerow(
                [
                    "timestamp",
                    "elapsed_s",
                    "throttle_pct",
                    "rpm",
                    "current_a",
                    "voltage_v",
                    "consumption_mah",
                    "temperature_c",
                    "thrust_n",
                ]
            )
        except OSError as exc:
            self.csv_file = self.csv_writer = None
            QMessageBox.critical(self, "Could not start recording", str(exc))
            return
        self.record_button.setText("Stop recording")
        self.record_status.setText(f"Recording: {path}")

    def stop_recording(self) -> None:
        if self.csv_file:
            try:
                self.csv_file.close()
            except OSError as exc:
                QMessageBox.critical(self, "Could not close recording", str(exc))
        self.csv_file = self.csv_writer = None
        self.record_button.setText("Start recording")
        self.record_status.setText("Not recording")

    def closeEvent(self, event) -> None:
        self.stop_recording()
        if self.serial_thread and self.serial_thread.isRunning():
            self.serial_thread.stop()
            if not self.serial_thread.wait(1500):
                QMessageBox.warning(self, "Shutdown pending", "The serial worker has not stopped yet.")
                event.ignore()
                return
        event.accept()


def self_test() -> None:
    sample = parse_data_line("DATA,50,123,456,1200,78,-3,1.25")
    assert sample.values["Throttle"] == 50
    assert sample.values["ERPM"] == 12300
    assert math.isclose(sample.values["Current"] or 0, 4.56)
    assert sample.values["Voltage"] == 12
    assert sample.values["Consumption"] == 78
    assert sample.values["Temperature"] == -3
    assert sample.values["Thrust"] == 1.25
    assert parse_data_line("DATA,0,0,0,0,0,0,NA").thrust_n is None
    try:
        parse_data_line("DATA,101,0,0,0,0,0,NA")
    except ValueError:
        pass
    else:
        raise AssertionError("out-of-range throttle was accepted")


def main() -> None:
    if "--self-test" in sys.argv:
        self_test()
        print("Telemetry protocol self-test passed")
        return
    app = QApplication(sys.argv)
    window = ThrustStand()
    window.show()
    sys.exit(app.exec())
