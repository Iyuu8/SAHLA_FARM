import time
import json
import subprocess
import paho.mqtt.client as mqtt
from RPLCD.i2c import CharLCD
from gpiozero import Button, LED

# --- CONFIGURATION ---
I2C_ADDRESS = 0x27
TOGGLE_BUTTON_PIN = 17
COMPOSE_FILE = "/home/raspberrypi/docker/docker-compose.yml"
MQTT_BROKER = "localhost"
MQTT_TOPIC = "farm/sensors"
DATA_TIMEOUT_SECONDS = 1600

# --- GLOBALS ---
latest_temp = "--"
latest_soil = "--"
mqtt_connected = False
last_data_time = 0
docker_led_state = "off"  # Tracks: on, off, or blink

# --- HARDWARE SETUP ---
lcd = CharLCD(i2c_expander='PCF8574', address=I2C_ADDRESS, port=1, cols=16, rows=2, backlight_enabled=True)
button = Button(TOGGLE_BUTTON_PIN, pull_up=True, bounce_time=0.5)

# New LEDs!
sys_led = LED(22)    # Pin 15
docker_led = LED(27) # Pin 13

# --- MQTT CALLBACKS ---
def on_message(client, userdata, msg):
    global latest_temp, latest_soil, last_data_time
    try:
        data = json.loads(msg.payload)
        latest_temp = data.get('temperature', '--')
        latest_soil = data.get('soil', '--')
        last_data_time = time.time()
    except: pass

def on_connect(client, userdata, flags, rc, properties=None):
    global mqtt_connected
    if rc == 0:
        mqtt_connected = True
        client.subscribe(MQTT_TOPIC)
    else: mqtt_connected = False

client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
client.on_connect = on_connect
client.on_message = on_message

# --- DOCKER LOGIC ---
def get_docker_running_count():
    containers = ["homeassistant", "n8n", "mosquitto"]
    running = 0
    for c in containers:
        check = subprocess.run(["docker", "ps", "--filter", f"name={c}", "--filter", "status=running", "-q"], capture_output=True, text=True)
        if check.stdout.strip(): running += 1
    return running

def toggle_docker():
    global docker_led_state
    # Make it blink fast while the command is processing
    docker_led.blink(on_time=0.2, off_time=0.2)
    docker_led_state = "blink"

    current_count = get_docker_running_count()
    cmd = "stop" if current_count == 3 else "start"
    subprocess.run(["docker", "compose", "-f", COMPOSE_FILE, cmd])

button.when_pressed = toggle_docker

# --- MAIN LOOP ---
try:
    lcd.clear()
    while True:
        docker_count = get_docker_running_count()
        current_time = time.time()

        # 1. Update Docker LED Status
        if docker_count == 3:
            if docker_led_state != "on":
                docker_led.on()
                docker_led_state = "on"
            docker_is_on = True
        elif docker_count == 0:
            if docker_led_state != "off":
                docker_led.off()
                docker_led_state = "off"
            docker_is_on = False
        else:
            # If count is 1 or 2, containers are currently loading up or shutting down
            if docker_led_state != "blink":
                docker_led.blink(on_time=0.5, off_time=0.5)
                docker_led_state = "blink"
            docker_is_on = False

        # 2. Update System & SYS LED Status
        if docker_is_on:
            if not mqtt_connected:
                try:
                    client.connect(MQTT_BROKER, 1883, 10)
                    client.loop_start()
                except: mqtt_connected = False

            # Check ESP32
            if (current_time - last_data_time) <= DATA_TIMEOUT_SECONDS:
                status_text = "SYS: OK "
                sys_led.on() # SYS is perfect!
                disp_temp = latest_temp
                disp_soil = latest_soil
            else:
                status_text = "SYS: nOK"
                sys_led.off() # ESP32 missing, turn off SYS OK led
                disp_temp = "--"
                disp_soil = "--"

        else:
            mqtt_connected = False
            client.loop_stop()
            last_data_time = 0
            status_text = "SYS: OFF"
            sys_led.off() # System is off, turn off SYS OK led
            disp_temp = "--"
            disp_soil = "--"

        # 3. Update Display
        try:
            lcd.cursor_pos = (0, 0)
            lcd.write_string(f"{status_text}           ")
            lcd.cursor_pos = (1, 0)
            lcd.write_string(f"T:{disp_temp}C S:{disp_soil}%   ")
        except OSError:
            pass

        time.sleep(2)

except KeyboardInterrupt:
    lcd.clear()
    lcd.backlight_enabled = False
    sys_led.off()
    docker_led.off()