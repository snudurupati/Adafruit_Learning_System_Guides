"""
LED Disco Tie with Bluetooth
=========================================================
Give your suit an sound-reactive upgrade with Circuit
Playground Bluefruit & Neopixels. Set color and animation
mode using the Bluefruit LE Connect app.

Author: Collin Cunningham for Adafruit Industries, 2019
"""
# pylint: disable=global-statement

import time
import array
import math
import audiobusio
import board
import neopixel
from adafruit_ble.uart_server import UARTServer
from adafruit_bluefruit_connect.packet import Packet
from adafruit_bluefruit_connect.color_packet import ColorPacket
from adafruit_bluefruit_connect.button_packet import ButtonPacket

uart_server = UARTServer()

# User input vars
mode = 0 # 0=audio, 1=rainbow, 2=larsen_scanner, 3=solid
user_color= (127,0,0)
speed = 5.0 # for larsen scanner

# Audio meter vars
PEAK_COLOR = (100, 0, 255)
NUM_PIXELS = 10
CURVE = 2
SCALE_EXPONENT = math.pow(10, CURVE * -0.1)
NUM_SAMPLES = 160

# Restrict value to be between floor and ceiling.
def constrain(value, floor, ceiling):
    return max(floor, min(value, ceiling))

# Scale input_value between output_min and output_max, exponentially.
def log_scale(input_value, input_min, input_max, output_min, output_max):
    normalized_input_value = (input_value - input_min) / \
                             (input_max - input_min)
    return output_min + \
        math.pow(normalized_input_value, SCALE_EXPONENT) \
        * (output_max - output_min)

# Remove DC bias before computing RMS.
def normalized_rms(values):
    minbuf = int(mean(values))
    samples_sum = sum(
        float(sample - minbuf) * (sample - minbuf)
        for sample in values
    )

    return math.sqrt(samples_sum / len(values))

def mean(values):
    return sum(values) / len(values)

def volume_color(volume):
    return 200, volume * (255 // NUM_PIXELS), 0

# Set up NeoPixels and turn them all off.
pixels = neopixel.NeoPixel(board.A1, NUM_PIXELS, brightness=0.1, auto_write=False)
pixels.fill(0)
pixels.show()

mic = audiobusio.PDMIn(board.MICROPHONE_CLOCK, board.MICROPHONE_DATA,
                       sample_rate=16000, bit_depth=16)

# Record an initial sample to calibrate. Assume it's quiet when we start.
samples = array.array('H', [0] * NUM_SAMPLES)
mic.record(samples, len(samples))
# Set lowest level to expect, plus a little.
input_floor = normalized_rms(samples) + 10
# Corresponds to sensitivity: lower means more pixels light up with lower sound
input_ceiling = input_floor + 500
peak = 0

def wheel(wheel_pos):
    # Input a value 0 to 255 to get a color value.
    # The colours are a transition r - g - b - back to r.
    if wheel_pos < 0 or wheel_pos > 255:
        r = g = b = 0
    elif wheel_pos < 85:
        r = int(wheel_pos * 3)
        g = int(255 - wheel_pos*3)
        b = 0
    elif wheel_pos < 170:
        wheel_pos -= 85
        r = int(255 - wheel_pos*3)
        g = 0
        b = int(wheel_pos*3)
    else:
        wheel_pos -= 170
        r = 0
        g = int(wheel_pos*3)
        b = int(255 - wheel_pos*3)
    return (r, g, b)

def rainbow_cycle(wait):
    for j in range(255):
        for i in range(NUM_PIXELS):
            pixel_index = (i * 256 // NUM_PIXELS) + j
            pixels[i] = wheel(pixel_index & 255)
        pixels.show()
        time.sleep(wait)

def audio_meter():
    mic.record(samples, len(samples))
    magnitude = normalized_rms(samples)
    global peak

    # Compute scaled logarithmic reading in the range 0 to NUM_PIXELS
    c = log_scale(constrain(magnitude, input_floor, input_ceiling),
                  input_floor, input_ceiling, 0, NUM_PIXELS)

    # Light up pixels that are below the scaled and interpolated magnitude.
    pixels.fill(0)
    for i in range(NUM_PIXELS):
        if i < c:
            pixels[i] = volume_color(i)
        # Light up the peak pixel and animate it slowly dropping.
        if c >= peak:
            peak = min(c, NUM_PIXELS - 1)
        elif peak > 0:
            peak = peak - 1
        if peak > 0:
            pixels[int(peak)] = PEAK_COLOR
    pixels.show()

pos = 0  # position
direction = 1  # direction of "eye"

def larsen_set(index, color):
    if index < 0:
        return
    else:
        pixels[index] = color

def larsen(wait):
    global pos
    global direction

    color_dark = (int(user_color[0]/8), int(user_color[1]/8),
                  int(user_color[2]/8))
    color_med = (int(user_color[0]/2), int(user_color[1]/2),
                int(user_color[2]/2))

    larsen_set(pos - 2, color_dark)
    larsen_set(pos - 1, color_med)
    larsen_set(pos, user_color)
    larsen_set(pos + 1, color_med)

    if (pos + 2) < NUM_PIXELS:
        # Dark red, do not exceed number of pixels
        larsen_set(pos + 2, color_dark)

    pixels.write()
    time.sleep(wait)

    # Erase all and draw a new one next time
    for j in range(-2, 2):
        larsen_set(pos + j, (0, 0, 0))
        if (pos + 2) < NUM_PIXELS:
            larsen_set(pos + 2, (0, 0, 0))

    # Bounce off ends of strip
    pos += direction
    if pos < 0:
        pos = 1
        direction = -direction
    elif pos >= (NUM_PIXELS - 1):
        pos = NUM_PIXELS - 2
        direction = -direction

def solid():
    global user_color
    pixels.fill(user_color)
    pixels.show()

def map_value(value, in_min, in_max, out_min, out_max):
    out_range = out_max - out_min
    in_range = in_max - in_min
    return out_min + out_range * ((value - in_min) / in_range)

def change_speed(val):
    global speed
    new_speed = speed + val
    if new_speed > 10.0:
        new_speed = 10.0
    elif new_speed < 1.0:
        new_speed = 1.0
    speed = new_speed
    print("set speed " + str(speed))

while True:
    # While BLE is *not* connected
    if not uart_server.connected:
        # OK to call again even if already advertising
        uart_server.start_advertising()

    # While BLE is connected
    else:
        if uart_server.in_waiting:
            packet = Packet.from_stream(uart_server)

            # Received ColorPacket
            if isinstance(packet, ColorPacket):
                print("color received: " + str(packet.color))
                user_color = packet.color

            # Received ButtonPacket
            elif isinstance(packet, ButtonPacket):
                if packet.pressed:
                    if packet.button == ButtonPacket.UP:
                        change_speed(1)
                    elif packet.button == ButtonPacket.DOWN:
                        change_speed(-1)
                    elif packet.button == ButtonPacket.BUTTON_1:
                        mode = 0
                    elif packet.button == ButtonPacket.BUTTON_2:
                        mode = 1
                    elif packet.button == ButtonPacket.BUTTON_3:
                        mode = 2
                    elif packet.button == ButtonPacket.BUTTON_4:
                        mode = 3

    # Determine animation based on mode
    if mode == 0:
        audio_meter()
    elif mode == 1:
        rainbow_cycle(0.001)
    elif mode == 2:
        larsen(map_value(speed, 10.0, 0.0, 0.01, 0.3))
    elif mode == 3:
        solid()
