// ESP32 UHF RFID registration reader.
// Goal: read UHF RFID tags and print EPCs to the Raspberry Pi/PC Serial port.
// UART2 wiring:
//   ESP32 GPIO4 RX2 <- RFID module TX
//   ESP32 GPIO5 TX2 -> RFID module RX

#define MCU_RX_PIN 4
#define MCU_TX_PIN 5

HardwareSerial rfidSerial(2);

const uint8_t rfidCommand[] = {
  0xBB, 0x00, 0x27, 0x00, 0x03,
  0x22, 0xFF, 0xFF,
  0x4A, 0x7E
};

uint8_t rxBuf[256];
int rxLen = 0;

unsigned long lastInventoryMillis = 0;
unsigned long lastEpcMillis = 0;
unsigned long lastSendMillis = 0;
unsigned long lastStatusMillis = 0;

const unsigned long inventoryIntervalMs = 500;
const unsigned long sameTagPrintIntervalMs = 1000;
const unsigned long tagLostMs = 3000;
const unsigned long statusIntervalMs = 3000;
const bool printInventoryCommandLog = false;

String lastEpc = "";
bool tagRecentlyDetected = false;

void setup() {
  Serial.begin(115200);
  delay(1000);

  rfidSerial.begin(115200, SERIAL_8N1, MCU_RX_PIN, MCU_TX_PIN);

  Serial.println("RFID Reader Ready (ESP32).");
  Serial.println("RFID command loop mode enabled.");

  sendInventoryCommand();
  lastInventoryMillis = millis();
}

void loop() {
  if (millis() - lastInventoryMillis >= inventoryIntervalMs) {
    sendInventoryCommand();
    lastInventoryMillis = millis();
  }

  while (rfidSerial.available()) {
    uint8_t b = rfidSerial.read();

    if (rxLen == 0 && b != 0xBB) {
      continue;
    }

    if (rxLen < sizeof(rxBuf)) {
      rxBuf[rxLen++] = b;
    } else {
      rxLen = 0;
    }

    if (b == 0x7E && rxLen >= 7) {
      parseFrame(rxBuf, rxLen);
      rxLen = 0;
    }
  }

  if (tagRecentlyDetected && millis() - lastEpcMillis >= tagLostMs) {
    Serial.print("TAG_LOST,");
    Serial.println(lastEpc);

    tagRecentlyDetected = false;
    lastEpc = "";
  }

  if (!tagRecentlyDetected && millis() - lastStatusMillis >= statusIntervalMs) {
    Serial.println("RFID_WAITING_FOR_TAG");
    lastStatusMillis = millis();
  }

  delay(10);
}

void sendInventoryCommand() {
  rfidSerial.write(rfidCommand, sizeof(rfidCommand));
  if (printInventoryCommandLog) {
    Serial.println("RFID command sent.");
  }
}

void parseFrame(uint8_t *frame, int len) {
  if (len < 7) return;
  if (frame[0] != 0xBB) return;
  if (frame[len - 1] != 0x7E) return;

  int payloadLen = ((int)frame[3] << 8) | frame[4];
  int expectedLen = 7 + payloadLen;

  if (len != expectedLen) {
    Serial.println("Invalid frame length.");
    return;
  }

  uint8_t receivedChecksum = frame[5 + payloadLen];
  uint8_t calculatedChecksum = calcChecksum(frame, 1, 4 + payloadLen);

  if (receivedChecksum != calculatedChecksum) {
    Serial.println("Checksum error.");
    return;
  }

  uint8_t *payload = &frame[5];

  if (payloadLen < 6) return;

  int rssi = payload[0];
  int epcStart = 3;
  int epcLen = payloadLen - 5;

  if (epcLen <= 0) return;
  if (epcLen > 32) return;

  String epc = bytesToHex(&payload[epcStart], epcLen);

  if (epc.length() == 0) return;

  lastEpcMillis = millis();
  tagRecentlyDetected = true;

  bool isNewTag = epc != lastEpc;
  bool intervalPassed = millis() - lastSendMillis >= sameTagPrintIntervalMs;

  if (isNewTag || intervalPassed) {
    Serial.print("TAG_DETECTED,");
    Serial.print(epc);
    Serial.print(",");
    Serial.println(rssi);

    lastEpc = epc;
    lastSendMillis = millis();
  }
}

uint8_t calcChecksum(uint8_t *data, int start, int end) {
  uint16_t sum = 0;

  for (int i = start; i <= end; i++) {
    sum += data[i];
  }

  return sum & 0xFF;
}

String bytesToHex(uint8_t *data, int len) {
  String result = "";

  for (int i = 0; i < len; i++) {
    if (data[i] < 0x10) result += "0";
    result += String(data[i], HEX);
  }

  result.toUpperCase();
  return result;
}
