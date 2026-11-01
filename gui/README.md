# Thrust Stand GUI

Run with `uv run main.py`. The dashboard uses `/dev/ttyACM0` by default at
115200 baud and expects newline-terminated ASCII records:

```text
DATA,throttle_pct,rpm_raw,current_raw,voltage_raw,consumption_mah,temp_c,thrust_n
```

RPM, current, and voltage fields are the raw KISS values (100 RPM, 0.01 A,
and 0.01 V units). Use `NA` for thrust until the load-cell reading is
available. The GUI sends `THROTTLE,<0-100>\n` when the control changes and
sends zero throttle when disconnecting. The MCU should also enforce a
throttle-command timeout as a hardware failsafe.

Recordings are saved as CSV files under `recordings/`. Verify the telemetry
and throttle command wiring, including a zero-throttle response, before
connecting a motor. Run `uv run main.py --self-test` for a protocol check.

The current MCU firmware still reads raw KISS frames on USART2 and sends
`Hello World`; it does not yet implement this PC protocol. Resolve the UART
routing so ESC telemetry and the laptop do not drive the same RX line, then
add the firmware-side `DATA` output and `THROTTLE` command handling. Automated
sequences and the drag-and-drop editor are not included yet.