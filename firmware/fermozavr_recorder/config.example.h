#pragma once

// One compiled link. Copy this file to config.h for a real Wi-Fi name
// and the address of the page. config.h is not stored in the repository.
// USB and Bluetooth do not use the Wi-Fi fields.

#define FVZ_LINK_USB 1
#define FVZ_LINK_WIFI 2
#define FVZ_LINK_BLUETOOTH 3

#define FVZ_LINK FVZ_LINK_USB

// Identity written into a real reading. Leave the experiment empty until
// FVZ-EXP-001 starts: an empty bus is not that experiment.
#define FVZ_NODE_ID "station"
#define FVZ_EXPERIMENT ""
#define FVZ_INTERVAL_MS 10000
#define FVZ_BAUD 115200
#define FVZ_BT_NAME "Fermozavr-TRH"

#define FVZ_WIFI_SSID "change-me"
#define FVZ_WIFI_PASSWORD "change-me"
// Address of the computer that runs the page. 127.0.0.1 on the board is
// the board itself, not the laptop.
#define FVZ_URL "http://192.168.1.10:8321/api/readings"

// Pins for the original ESP32 Dev Module. This is an assignment, not a
// checked module schematic. I2C is the future TCA9548A bus. DS18B20 has
// its own wire. Pt100 sits on MAX31865 over SPI, 20–30 cm from the board.
#define FVZ_PIN_SDA 21
#define FVZ_PIN_SCL 22
#define FVZ_PIN_ONEWIRE 4
#define FVZ_PIN_MAX_CS 5
#define FVZ_PIN_MAX_SCK 18
#define FVZ_PIN_MAX_MISO 19
#define FVZ_PIN_MAX_MOSI 23
