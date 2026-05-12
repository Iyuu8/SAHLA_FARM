#include <WiFi.h>
#include <WiFiManager.h> // <-- New Library!
#include <PubSubClient.h>
#include <DHT.h>
#include <Wire.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_TSL2591.h>

// --- MQTT Broker (Raspberry Pi) ---
const char* mqtt_server = "raspberrypi.local"; 
const int   mqtt_port   = 1883;

// --- Sensor pins ---
const int DHT_PIN  = 27;
const int SOIL_PIN = 32;

// --- Calibration ---
const int dryValue = 4095;
const int wetValue = 1950;

// --- Objects ---
DHT dht(DHT_PIN, DHT22);
Adafruit_TSL2591 tsl = Adafruit_TSL2591(2591);
WiFiClient espClient;
PubSubClient client(espClient);
bool tslFound = false;

void setup() {
  Serial.begin(115200);
  Serial.println("\n--- SENSOR MQTT MODE START ---");

  // --- WiFiManager Magic ---
  WiFiManager wifiManager;
  
  // Uncomment the line below if you ever need to wipe the saved WiFi for testing
  wifiManager.resetSettings(); 

  Serial.println("Connecting to WiFi or starting Setup Portal...");
  
  // This creates the "Farm-Sensor-Setup" Wi-Fi if it can't connect to a known network.
  // It pauses the code here until the user provides credentials via their phone.
  if (!wifiManager.autoConnect("Farm-Sensor-Setup")) {
    Serial.println("Failed to connect and hit timeout");
    delay(3000);
    ESP.restart(); // Reboot and try again
  }

  Serial.println("\nWiFi connected!");
  Serial.print("ESP32 IP: ");
  Serial.println(WiFi.localIP());

  // --- Sensors init ---
  dht.begin();
  Wire.begin(26, 25);
  if (tsl.begin()) {
    tslFound = true;
    tsl.setGain(TSL2591_GAIN_MED);
    tsl.setTiming(TSL2591_INTEGRATIONTIME_100MS);
  } else {
    Serial.println("Warning: TSL2591 Light Sensor not found");
  }
  pinMode(SOIL_PIN, INPUT);

  // --- MQTT setup ---
  client.setServer(mqtt_server, mqtt_port);
}

void loop() {
  if (!client.connected()) {
    reconnect();
  }
  client.loop();

  // --- Read sensors ---
  float    h           = dht.readHumidity();
  float    t           = dht.readTemperature();
  uint32_t lux         = tslFound ? tsl.getLuminosity(TSL2591_VISIBLE) : 0;
  int      soilRaw     = analogRead(SOIL_PIN);
  int      soilPercent = map(soilRaw, dryValue, wetValue, 0, 100);
  soilPercent = constrain(soilPercent, 0, 100);

  // --- Prepare JSON payload ---
  String payload = "{";
  payload += "\"temperature\":" + String(t) + ",";
  payload += "\"humidity\":"    + String(h) + ",";
  payload += "\"light\":"       + String(lux) + ",";
  payload += "\"soil\":"        + String(soilPercent);
  payload += "}";

  // --- Publish ---
  client.publish("farm/sensors", payload.c_str());

  // --- Debug ---
  Serial.println(payload);
  delay(2000);
}

void reconnect() {
  while (!client.connected()) {
    Serial.print("Connecting to MQTT...");
    if (client.connect("ESP32Client")) {
      Serial.println("connected");
    } else {
      Serial.print("failed, rc=");
      Serial.print(client.state());
      Serial.println(" retrying in 2 seconds");
      delay(2000);
    }
  }
}