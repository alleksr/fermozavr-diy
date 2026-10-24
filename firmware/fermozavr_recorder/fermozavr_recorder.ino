// Recorder for the Fermozavr bench. One link per build: USB, Wi-Fi, or
// Bluetooth Classic. Flash and pin notes: docs/station.md
//
// setup opens the console, the I2C pins, and the chosen link.
// loop asks who is on the bus, then sends readings. A reading exists only
// when a sensor driver put a number in it. Silence is a note, not a temperature.

#include <Wire.h>

#if __has_include("config.h")
#include "config.h"
#else
#include "config.example.h"
#endif

#if FVZ_LINK == FVZ_LINK_WIFI
#include <WiFi.h>
#include <HTTPClient.h>
#elif FVZ_LINK == FVZ_LINK_BLUETOOTH
#include <BluetoothSerial.h>
#if !defined(CONFIG_BT_ENABLED) || !defined(CONFIG_BLUEDROID_ENABLED)
#error Fermozavr Bluetooth needs Classic Bluetooth on the original ESP32. USB and Wi-Fi still build on this chip.
#endif
#if defined(CONFIG_BT_CLASSIC_ENABLED) && !CONFIG_BT_CLASSIC_ENABLED
#error This chip has Bluetooth Low Energy only. The Fermozavr Bluetooth link is Classic serial. Use USB or Wi-Fi.
#endif
BluetoothSerial SerialBT;
#elif FVZ_LINK != FVZ_LINK_USB
#error FVZ_LINK must be FVZ_LINK_USB, FVZ_LINK_WIFI, or FVZ_LINK_BLUETOOTH
#endif

const int READING_CAP = 8;

struct Reading {
    char sensor_id[64];
    char quantity[32];
    char unit[32];
    double value;
    char note[120];
};

struct Text {
    char* data;
    size_t cap;
    size_t len;
    bool full;

    void reset() {
        len = 0;
        full = false;
        if (cap > 0) {
            data[0] = '\0';
        }
    }

    void add(const char* text) {
        while (*text != '\0') {
            add_char(*text);
            text++;
        }
    }

    void add_char(char symbol) {
        if (len + 1 >= cap) {
            full = true;
            return;
        }
        data[len++] = symbol;
        data[len] = '\0';
    }

    void add_escaped(const char* text) {
        while (*text != '\0') {
            if (*text == '"' || *text == '\\') {
                add_char('\\');
            }
            add_char(*text);
            text++;
        }
    }
};

void add_reading_json(Text& out, const Reading& row) {
    char number[24];
    snprintf(number, sizeof(number), "%.4f", row.value);
    out.add("{\"node_id\":\"");
    out.add_escaped(FVZ_NODE_ID);
    out.add("\",\"sensor_id\":\"");
    out.add_escaped(row.sensor_id);
    out.add("\",\"quantity\":\"");
    out.add_escaped(row.quantity);
    out.add("\",\"unit\":\"");
    out.add_escaped(row.unit);
    out.add("\",\"value\":");
    out.add(number);
    if (FVZ_EXPERIMENT[0] != '\0') {
        out.add(",\"experiment\":\"");
        out.add_escaped(FVZ_EXPERIMENT);
        out.add_char('"');
    }
    if (row.note[0] != '\0') {
        out.add(",\"note\":\"");
        out.add_escaped(row.note);
        out.add_char('"');
    }
    out.add_char('}');
}

bool event_line(char* dest, size_t cap, const char* event, const char* note) {
    Text out = {dest, cap, 0, false};
    out.reset();
    out.add("{\"event\":\"");
    out.add_escaped(event);
    out.add("\",\"note\":\"");
    out.add_escaped(note);
    out.add("\"}");
    return !out.full;
}

bool reading_line(char* dest, size_t cap, const Reading& row) {
    Text out = {dest, cap, 0, false};
    out.reset();
    add_reading_json(out, row);
    return !out.full;
}

// A note is not a reading. The USB console always shows it. Bluetooth also
// carries it, because the bridge is reading that port. Wi-Fi never posts it.
void send_event(const char* event, const char* note) {
    char line[256];
    if (!event_line(line, sizeof(line), event, note)) {
        Serial.println("строка не собралась");
        return;
    }
#if FVZ_LINK == FVZ_LINK_BLUETOOTH
    SerialBT.println(line);
#endif
    Serial.println(line);
}

const char* link_name() {
#if FVZ_LINK == FVZ_LINK_WIFI
    return "Wi-Fi";
#elif FVZ_LINK == FVZ_LINK_BLUETOOTH
    return "Bluetooth";
#else
    return "USB";
#endif
}

#if FVZ_LINK == FVZ_LINK_WIFI
bool wifi_connected(unsigned long timeout_ms) {
    unsigned long started = millis();
    while (WiFi.status() != WL_CONNECTED && millis() - started < timeout_ms) {
        delay(200);
    }
    return WiFi.status() == WL_CONNECTED;
}

bool post_readings(const char* body) {
    if (WiFi.status() != WL_CONNECTED) {
        WiFi.reconnect();
    }
    if (!wifi_connected(8000)) {
        Serial.println("Wi-Fi не подключён, строка не отправлена");
        return false;
    }
    HTTPClient http;
    http.begin(FVZ_URL);
    http.addHeader("Content-Type", "application/json");
    int code = http.POST(body);
    http.end();
    if (code != 201) {
        Serial.print("страница ответила ");
        Serial.println(code);
        return false;
    }
    return true;
}
#endif

void write_reading_line(Print& out, const Reading& row) {
    char line[512];
    if (!reading_line(line, sizeof(line), row)) {
        Serial.println("строка не собралась");
        return;
    }
    out.println(line);
}

// USB and Bluetooth send one object per line. Wi-Fi sends one batch to the
// page. Nothing is sent when count is zero.
void send_readings(const Reading* rows, int count) {
    if (count <= 0) {
        return;
    }
#if FVZ_LINK == FVZ_LINK_WIFI
    static char body[2048];
    Text out = {body, sizeof(body), 0, false};
    out.reset();
    out.add("{\"readings\":[");
    for (int index = 0; index < count; index++) {
        if (index > 0) {
            out.add_char(',');
        }
        add_reading_json(out, rows[index]);
    }
    out.add("]}");
    if (out.full) {
        Serial.println("строка не собралась");
        return;
    }
    if (post_readings(body)) {
        Serial.println("строка ушла по Wi-Fi");
    }
#elif FVZ_LINK == FVZ_LINK_BLUETOOTH
    for (int index = 0; index < count; index++) {
        write_reading_line(SerialBT, rows[index]);
    }
    Serial.println("строка ушла по Bluetooth");
#else
    for (int index = 0; index < count; index++) {
        write_reading_line(Serial, rows[index]);
    }
#endif
}

void start_link() {
#if FVZ_LINK == FVZ_LINK_WIFI
    WiFi.mode(WIFI_STA);
    WiFi.begin(FVZ_WIFI_SSID, FVZ_WIFI_PASSWORD);
    if (wifi_connected(15000)) {
        Serial.print("Wi-Fi ");
        Serial.println(WiFi.localIP());
    } else {
        Serial.println("Wi-Fi не подключён");
    }
#elif FVZ_LINK == FVZ_LINK_BLUETOOTH
    SerialBT.begin(FVZ_BT_NAME);
    Serial.print("Bluetooth ");
    Serial.println(FVZ_BT_NAME);
#endif
}

int scan_i2c() {
    int found = 0;
    for (uint8_t address = 1; address < 127; address++) {
        Wire.beginTransmission(address);
        if (Wire.endTransmission() != 0) {
            continue;
        }
        found++;
        char note[96];
        snprintf(
            note,
            sizeof(note),
            "на шине I2C ответил адрес 0x%02X, температуру не читаем",
            address
        );
        send_event("i2c", note);
    }
    return found;
}

bool onewire_present(int pin) {
    pinMode(pin, OUTPUT);
    digitalWrite(pin, LOW);
    delayMicroseconds(480);
    pinMode(pin, INPUT_PULLUP);
    delayMicroseconds(70);
    bool present = digitalRead(pin) == LOW;
    delayMicroseconds(410);
    return present;
}

// Who answered is not a measurement. An address and a presence pulse stay notes.
void report_buses() {
    int i2c_found = scan_i2c();
    bool wire_found = onewire_present(FVZ_PIN_ONEWIRE);
    if (wire_found) {
        send_event("onewire", "на шине 1-Wire кто-то ответил, температуру не читаем");
    }
    if (i2c_found == 0 && !wire_found) {
        send_event("bus_empty", "на шине никто не ответил");
    }
}

// Drivers belong here, one per chip, and only after that chip answers on
// this board. Until then the function has no number to put in a row.
int read_sensors(Reading* rows, int capacity) {
    (void)rows;
    (void)capacity;
    return 0;
}

void setup() {
    Serial.begin(FVZ_BAUD);
    delay(200);
    Wire.begin(FVZ_PIN_SDA, FVZ_PIN_SCL);
    Serial.print("Фермозавр, запись по ");
    Serial.println(link_name());
    start_link();

    char note[160];
    snprintf(
        note,
        sizeof(note),
        "Pt100 не опрашивается, выводы MAX31865 CS=%d SCK=%d MISO=%d MOSI=%d",
        FVZ_PIN_MAX_CS,
        FVZ_PIN_MAX_SCK,
        FVZ_PIN_MAX_MISO,
        FVZ_PIN_MAX_MOSI
    );
    send_event("reference", note);
}

void loop() {
    report_buses();
    Reading rows[READING_CAP];
    int count = read_sensors(rows, READING_CAP);
    send_readings(rows, count);
    delay(FVZ_INTERVAL_MS);
}
