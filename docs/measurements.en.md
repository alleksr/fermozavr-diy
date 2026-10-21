# Readings and decisions

[Русский](measurements.md) · [Documentation](README.en.md)

The station stores submitted readings in SQLite with their observation time, node, sensor instance, and quantity. A row with the same node, sensor instance, quantity, and time updates the existing record. Experiment notes help preserve measurement context.

## Limits on conclusions

- The code uses an uncertainty band of ±0.3 °C for temperature and ±3 %RH for relative humidity. Values near a boundary are described as uncertain, not as a definite yes or no.
- The overnight frost band is 0 to +2 °C. Temperature trend is evaluated using readings 40 minutes apart.
- A reading older than three minutes is considered stale. Sensor readings use a separate five-minute comparison window: if readings in that window disagree by more than the uncertainty band, the station reports the disagreement instead of averaging them.
- Checking a spray band requires user-defined temperature and humidity limits. Above 95 %RH, humidity is treated as a saturation flag rather than a value for that band.

These rules describe the current interface logic; they do not replace sensor calibration or an agronomic decision. They are implemented in `station/decisions.py` and `station/server.py`; accuracy and thresholds must be checked through testing.
