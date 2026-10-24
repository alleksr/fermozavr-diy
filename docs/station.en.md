# Station

[Русский](station.md) · [Documentation](README.en.md)

## Run

Python 3 is required; no third-party libraries are needed. From the repository root, run:

```sh
python3 station/server.py
```

Open `http://127.0.0.1:8321`. By default the server listens only on this computer. Stop it with `Ctrl+C`.

Set `FVZ_PORT` to change the port or `FVZ_DB` to change the SQLite database path. By default the database is created at `station/data/station.sqlite`; keep it to preserve the reading log and dashboard layouts.

For a Wi-Fi board, the page has to listen on the network address: `FVZ_HOST=0.0.0.0`. Any device on that network can then post a row. The intake has no password. USB and Bluetooth do not need this.

## Readings

Enter a row in the page form or send JSON to `POST /api/readings`. The server accepts a single object, an array of objects, or an object containing a `readings` array. Each row requires `sensor_id`, `quantity`, `unit`, and a numeric `value`; `node_id` defaults to `station`. Optional fields are `observed_at`, `experiment`, and `note`.

Supported quantities and units:

| `quantity` | `unit` |
| --- | --- |
| `air_temperature` | `celsius` |
| `relative_humidity` | `percent_rh` |
| `reference_temperature` | `celsius` |

Other API routes serve page state, the reading log, and dashboard settings; their implementation is in `station/server.py`.

## Recording from the board

The sketch is in `firmware/fermozavr_recorder/`. One build enables one link: USB, Wi-Fi, or Bluetooth. `FVZ_LINK` in `config.example.h` selects it. A private network name and the page address belong in a `config.h` copy next to the sketch. That file is not stored in the repository.

Flash the sketch from the Arduino IDE onto an “ESP32 Dev Module”. No extra library is required: Wire, Wi-Fi, and BluetoothSerial come with the ESP32 core.

Until a sensor answers with a number, nothing is written to the log. The sketch looks at the I²C bus and the 1-Wire pin and says so when nobody answers. It does not invent a temperature from that silence.

The poll interval is ten seconds. The one-second interval after dew starts together with the sensor driver, not before.

### USB

Leave `FVZ_LINK` at `FVZ_LINK_USB`. Start the page as usual, then read the port in another window:

```sh
python3 station/line_in.py /dev/ttyUSB0
```

The port may be named `/dev/ttyACM0`. The bridge forwards only a reading row. It prints “на шине никто не ответил” locally and does not store that sentence.

### Wi-Fi

In `config.h` set `FVZ_LINK_WIFI`, the network name, and the address of the computer running the page. `127.0.0.1` from the board means the board itself, so it is the wrong address.

```sh
FVZ_HOST=0.0.0.0 python3 station/server.py
```

`FVZ_URL` in the sketch then looks like `http://192.168.1.10:8321/api/readings`.

### Bluetooth

Set `FVZ_LINK` to `FVZ_LINK_BLUETOOTH`. The board advertises itself as `Fermozavr-TRH`. This is the Classic serial profile of the original ESP32, not BLE. The Bluetooth build does not compile on ESP32-S3 or ESP32-C3: those chips have no such profile. USB and Wi-Fi remain.

The page stays on this computer. The laptop receives the same line it would receive over the cable:

```sh
bluetoothctl pair AA:BB:CC:DD:EE:FF
sudo rfcomm bind 0 AA:BB:CC:DD:EE:FF 1
python3 station/line_in.py /dev/rfcomm0
```

`AA:BB:CC:DD:EE:FF` is the board address after pairing.

### Pins

The pins below are for the original ESP32. They are an assignment, not a checked module schematic: the modules are not on the table yet.

| Signal | GPIO |
| --- | --- |
| I²C SDA, later TCA9548A | 21 |
| I²C SCL | 22 |
| DS18B20 | 4 |
| MAX31865 CS | 5 |
| MAX31865 SCK | 18 |
| MAX31865 MISO | 19 |
| MAX31865 MOSI | 23 |

The sketch does not poll Pt100 through MAX31865 yet: SPI has no separate “I am here” reply. Keep sensors 20–30 cm from the board, because the ESP32 warms itself.
