# HAM RADIO GPS
# 2022 DOUGLAS GRAHAM, AB9XA
#
# SELF CONTAINED CLOCK, GPS, COMPASS AND ALTIMETER
# DISPLAYS TIME IN UTC AND LOCAL
# DISPLAYS CURRENT MAIDENHEAD GRID SQUARE BASED ON GPS LOCATION
#
# HARDWARE:
#
# SPARKFUN THING PLUS SAMD51
# BN-880 GPS WITH MAGNETOMETER - USES U-BLOX 8 SERIES CHIPSET
# WAVESHARE 2.4" TFT DISPLAY (320X240)
# 3,600 MAH LIPO BATTERY
#
# AVERAGE RUNTIME IS 29 HOURS
#
# PINS:
#
# A0    ANALOG INPUT TO MEASURE BATTERY VOLTAGE
# SCK   SPI CLOCK FOR DISPLAY
# MOSI  SPI DATA OUT FOR DISPLAY
# D0    UART TX FOR GPS
# D1    UART RX FOR GPS
# SDA   I2C DATA FOR MAGNETOMETER
# SCL   I2C CLOCK FOR MAGNETOMETER
# D5    DIGITAL OUTPUT - DISPLAY CHIP SELECT
# D6    DIGITAL OUTPUT - DISPLAY DATA/COMMAND
# D9    DIGITAL OUTPUT - DISPLAY RESET
# D10   PWN OUTPUT - DISPLAY BRIGHTNESS
# D11   DIGITAL INPUT - BRIGHTNESS DOWN
# D12   DIGITAL INPUT - BRIGHTNESS UP

import analogio
import board
import busio
import displayio
import math
import pwmio
import rtc
import time

import adafruit_fancyled.adafruit_fancyled as fancy
import adafruit_gps
import adafruit_ili9341
import adafruit_lsm303dlh_mag

from adafruit_bitmap_font import bitmap_font
from adafruit_display_text import bitmap_label
from adafruit_progressbar.horizontalprogressbar import (HorizontalProgressBar, HorizontalFillDirection)
from digitalio import DigitalInOut, Direction, Pull

# VERSION
version = '1.3'

################################################################
# USER ADJUSTABLE VARIABLES LISTED BELOW                       #
################################################################

# DST START / END (MONTH, WEEK, DAY, HOUR) / OFFSET IN SECONDS
dst_start = (3, 2, 6, 2)
dst_end = (11, 1, 6, 2)
dst_offset = 3600

# TIMEZONE DATA
timezone_desc = ('EST', 'EDT')
timezone_offset = -5

# MAGNETOMETER DATA
offset_x_axis = 30.9091
offset_y_axis = -20.5
declination = -6

# MAGNETOMETER ORIENTATION
# BN-880 GPS HAS X AND Y AXIS FLIPPED (N/S E/W READINGS ARE BACKWARDS)
# BN-880 X AND Y AXIS ARE ROTATED 90 DEGREES
flip_x_axis = True
flip_y_axis = False
swap_axis = False

# STARTUP LOGO
startup_logo = '/images/ab9xa.bmp'

# TEXT COLOR SETUP
clock_color = 0x00FF00
compass_color = 0xFFFF00
date_color = 0x0000FF
gps_color = 0xFF0000
grid_color = 0xFFFF00
location_color = 0x00FF00
sat_color = 0xFF00FF

# PIN LAYOUT
pin_battery = board.A0
pin_sck = board.SCK
pin_mosi = board.MOSI
pin_rx = board.RX
pin_tx = board.TX
pin_sda = board.SDA
pin_scl = board.SCL
pin_cs = board.D5
pin_dc = board.D6
pin_rst = board.D9
pin_bl = board.D10
pin_bright_down = board.D11
pin_bright_up = board.D12

# STARTUP DISPLAY BRIGHTNESS
disp_level = 32767

# ARRAY FOR ADC VALUE TO BATTERY PERCENTAGE (BELOW [0] = 0%, [0] - [1] = 10%, [9]-[10] = 100%
bat_curve = (48500, 49600, 50900, 51400, 52000, 52900, 53900, 55900, 56900, 58000, 65535)

# BATTERY CUTOFF
bat_cutoff = 48300

# BATTERY BARGRAPH SIZE
bat_x = 32
bat_y = 12

# GPS HEARTBEAT CHARACTER
gps_char = chr(0x2665)

# DISPLAY SIZE
disp_x = 320
disp_y = 240

# DISPLAY FONT DATA
font = bitmap_font.load_font('fonts/consolas-16.pcf')
char_height = 20
char_start = 6
char_width = 12
line_space = 2
line_gap = 12

################################################################
# END OF USER ADJUSTABLE VARIABLES                             #
################################################################

# ARRAYS FOR DAY AND MONTH TEXT
day_text = ('MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT', 'SUN')
month_text = ('JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC')

# COMPASS DATA
comp_angle = (11.25, 33.75, 56.25, 78.75, 101.25, 123.75, 146.25, 168.75, 191.25, 213.75, 236.25, 258.75, 281.25, 303.75, 326.25, 348.75)
comp_point = ('NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW')

# ARRAYS FOR GRID SQUARE TEXT
grid_upper = 'ABCDEFGHIJKLMNOPQRSTUVWX'
grid_lower = 'abcdefghijklmnopqrstuvwx'


# CALCULATE AND FORMAT UTC TIME, UTC DATE, TIMEZONE TIME AND TIMEZONE DATE. CALCULATE DST


class comp_date_time:
    def __init__(self, base_time_secs):
        time_utc_tuple = time.localtime(base_time_secs)

        # CHECK FOR DEC 31 / JAN 1 OVERLAP AND CORRECT YEAR FOR TIMEZONE DATE
        base_year = time_utc_tuple[0]
        err_check_tuple = (base_year, 1, 1, 0, 0, 0, 0, 0, 0)
        err_check_secs = time.mktime(err_check_tuple) - timezone_offset * 3600

        if base_time_secs < err_check_secs:
            base_year -= 1

        # CALCULATE IN SECONDS THE DST START TIME AND DATE
        dst_start_tuple = (base_year, dst_start[0], dst_start[1] * 7 - 6, dst_start[3], 0, 0, 0, 0, 0)
        dst_start_secs = time.mktime(dst_start_tuple)
        dst_start_tuple = time.localtime(dst_start_secs)

        dst_start_diff = dst_start[2] - dst_start_tuple[6]

        if dst_start_diff < 0:
            dst_start_diff += 7

        dst_start_secs += dst_start_diff * 86400 - timezone_offset * 3600

        # CALCULATE IN SECONDS THE DST END TIME AND DATE
        dst_end_tuple = (base_year, dst_end[0], dst_end[1] * 7 - 6, dst_end[3], 0, 0, 0, 0, 0)
        dst_end_secs = time.mktime(dst_end_tuple) - dst_offset
        dst_end_tuple = time.localtime(dst_end_secs)

        dst_end_diff = dst_end[2] - dst_end_tuple[6]

        if dst_end_diff < 0:
            dst_end_diff += 7

        dst_end_secs += dst_end_diff * 86400 - timezone_offset * 3600 - dst_offset

        # IF THE CURRENT TIME AND DATE FALL BETWEEN THE DST START AND END TIMES, SET DST_ACTIVE
        if base_time_secs >= dst_start_secs and base_time_secs < dst_end_secs:
            dst_active = True
        else:
            dst_active = False

        # FORMAT UTC DATA
        self.utc_date = '{} {} {:02d}, {}'.format(day_text[time_utc_tuple[6]], month_text[time_utc_tuple[1] - 1], time_utc_tuple[2], time_utc_tuple[0])
        self.utc_time = '{:02d}:{:02d}:{:02d}'.format(time_utc_tuple[3], time_utc_tuple[4], time_utc_tuple[5])

        # CALCULATE TIMEZONE TIME AND DATE
        time_tz_secs = base_time_secs + timezone_offset * 3600 + dst_active * dst_offset
        time_tz_tuple = time.localtime(time_tz_secs)

        # FORMAT TIMEZONE DATA
        self.tz_date = '{} {} {:02d}, {}'.format(day_text[time_tz_tuple[6]], month_text[time_tz_tuple[1] - 1], time_tz_tuple[2], time_tz_tuple[0])
        self.tz_time = '{:02d}:{:02d}:{:02d}'.format(time_tz_tuple[3], time_tz_tuple[4], time_tz_tuple[5])

        self.tz_desc = timezone_desc[dst_active]


# SEND UBX MESSAGES TO GPS
# WAITS FOR ACK/NAK, RETRANSMITS ON FAILED RESPONSE
# RETURNS TRUE FOR ACK, FALSE FOR NAK


def ubx_send(msg_type, msg_class, msg_payload):
    msg_len = len(msg_class) + len(msg_payload)
    msg_base = msg_type + msg_len.to_bytes(2, 'little') + msg_class + msg_payload
    msg_out = ubx_header + msg_base + ubx_checksum(msg_base)

    msg_ackx = ubx_ack + len(msg_type).to_bytes(2, 'little') + msg_type
    msg_ack = ubx_header + msg_ackx + ubx_checksum(msg_ackx)

    msg_nakx = ubx_nak + len(msg_type).to_bytes(2, 'little') + msg_type
    msg_nak = ubx_header + msg_nakx + ubx_checksum(msg_nakx)

    while True:
        serial.reset_input_buffer()
        serial.write(msg_out)
        msg_res = serial.read(10)

        if msg_res == msg_ack:
            return True
        elif msg_res == msg_nak:
            return False
        elif msg_type == cfg_prt:
            return None

        time.sleep(0.1)


# CALCULATE CHECKSUMS FOR UBX MESSAGES


def ubx_checksum(msg):
    cs_a = 0x00
    cs_b = 0x00

    for i in range(len(msg)):
        cs_a += msg[i]
        cs_b += cs_a

    checksum = (cs_a & 255).to_bytes(1, 'big') + (cs_b & 255).to_bytes(1, 'big')
    return checksum


# CALCULATE MAIDENHEAD GRID SQUARE BASED ON CURRENT LAT / LON


def calc_grid(latitude, longitude):
    grid_lat_adj = latitude + 90
    grid_lat_sq = grid_upper[int(grid_lat_adj / 10)]
    grid_lat_field = str(int(grid_lat_adj % 10))
    grid_lat_rem = (grid_lat_adj - int(grid_lat_adj)) * 60
    grid_lat_subsq = grid_lower[int(grid_lat_rem / 2.5)]

    grid_lon_adj = longitude + 180
    grid_lon_sq = grid_upper[int(grid_lon_adj / 20)]
    grid_lon_field = str(int((grid_lon_adj / 2) % 10))
    grid_lon_rem = (grid_lon_adj - int(grid_lon_adj / 2) * 2) * 60
    grid_lon_subsq = grid_lower[int(grid_lon_rem / 5)]

    return grid_lon_sq + grid_lat_sq + grid_lon_field + grid_lat_field + grid_lon_subsq + grid_lat_subsq


# CALCULATE ANGLE FROM MAGNETOMETER DATA


def comp_degree(x_axis, y_axis):
    x_axis -= offset_x_axis
    y_axis -= offset_y_axis

    if flip_x_axis:
        x_axis *= -1

    if flip_y_axis:
        y_axis *= -1

    if swap_axis:
        x_axis, y_axis = y_axis, x_axis

    if (x_axis > 0) and (y_axis == 0):
        angle = declination
    elif (x_axis < 0) and (y_axis == 0):
        angle = 180 + declination
    elif y_axis > 0:
        angle = 90 - math.atan(x_axis / y_axis) * 180 / math.pi + declination
    elif y_axis < 0:
        angle = 270 - math.atan(x_axis / y_axis) * 180 / math.pi + declination

    if angle < 0:
        angle += 360

    if angle >= 360:
        angle -= 360

    return angle


# CALCULATE COMPASS DIRECTION FROM ANGLE


def comp_direction(degrees):
    if degrees == -1:
        direction = '---'
    elif (degrees < 11.25) or (degrees >= 348.75):
        direction = 'N'
    else:
        for i in range(15):
            c_angle = comp_angle[i]

            if (degrees >= c_angle) and (degrees < (c_angle + 22.5)):
                direction = comp_point[i]
                break

    return direction


# CALCULATE BATTERY PERCENTAGE


def bat_level(adc_value):
    bat_percent = 0

    for percent in range(10, 1, -1):
        if adc_value <= bat_curve[percent] and adc_value > bat_curve[percent - 1]:
            bat_percent = percent * 10
            break

    return bat_percent


# SETUP CLOCK
clock = rtc.RTC()

# SETUP TFT DISPLAY
displayio.release_displays()
spi = busio.SPI(pin_sck, MOSI=pin_mosi)
disp_bus = displayio.FourWire(spi, command=pin_dc, chip_select=pin_cs, reset=pin_rst, baudrate=60000000)
disp = adafruit_ili9341.ILI9341(disp_bus, width=disp_x, height=disp_y)

disp_backlight = pwmio.PWMOut(pin_bl, frequency=5000, duty_cycle=disp_level)

# SETUP MAGNETOMETER
i2c = busio.I2C(pin_scl, pin_sda)
comp = adafruit_lsm303dlh_mag.LSM303DLH_Mag(i2c)

# SETUP ADC FOR BATTERY MONITORING
bat = analogio.AnalogIn(pin_battery)

# SETUP INPUTS FOR DISPLAY BRIGHTNESS ADJUSTMENT
b_up = DigitalInOut(pin_bright_up)
b_up.direction = Direction.INPUT
b_up.pull = Pull.UP

b_dn = DigitalInOut(pin_bright_down)
b_dn.direction = Direction.INPUT
b_dn.pull = Pull.UP

# DISPLAY SPLASH LOGO
bitmap = displayio.OnDiskBitmap(startup_logo)
tile_grid = displayio.TileGrid(bitmap, pixel_shader=bitmap.pixel_shader)
disp_group = displayio.Group()
disp_group.append(tile_grid)
disp.show(disp_group)

# CREATE COLOR GRADIENT AND PALETTE FOR BATTERY GAUGE
bat_gradient = [(0.0, 0xFF0000), (0.25, 0xFF7F00), (0.50, 0xFFFF00), (0.75, 0x00FF00)]
bat_palette = fancy.expand_gradient(bat_gradient, 100)
bat_colors = []

for i in range(100):
    color = fancy.palette_lookup(bat_palette, i / 100)
    bat_colors.append(color.pack())

# REMOVE SPLASH LOGO
time.sleep(1.5)
disp_group.remove(tile_grid)

# DISPLAY VERSION
message_text = 'Version ' + version
message_x = int((disp_x - len(message_text) * char_width) / 2)
message_text = bitmap_label.Label(font, text=message_text, color=0xFFB000, x=message_x, y=int(disp_y / 2))
disp_group.append(message_text)
time.sleep(1.0)
disp_group.remove(message_text)

# CONFIGURE GPS
message_text = ('Configuring GPS')
message_x = int((disp_x - len(message_text) * char_width) / 2)
message_text = bitmap_label.Label(font, text=message_text, color=0x00FFFF, x=message_x, y=int(disp_y / 2))
disp_group.append(message_text)

# UBX HEADER
ubx_header = bytes([0xb5, 0x62])

# UBX ACK/NAK
ubx_ack = bytes([0x05, 0x01])
ubx_nak = bytes([0x05, 0x00])

# UBX MESSAGE TYPES
cfg_prt = bytes([0x06, 0x00])
cfg_msg = bytes([0x06, 0x01])

# UBX CLASS IDS
cls_gll = bytes([0xF0, 0x01])
cls_gsa = bytes([0xF0, 0x02])
cls_gsv = bytes([0xF0, 0x03])
cls_vtg = bytes([0xF0, 0x05])

# CONFIGURE UART AND GPS BAUD RATE
serial = busio.UART(pin_tx, pin_rx, baudrate=9600, timeout=1, receiver_buffer_size=256)

payload = bytes([0x01, 0x00, 0x00, 0x00, 0xD0, 0x08, 0x00, 0x00, 0x00, 0x96, 0x00, 0x00, 0x07, 0x00, 0x03, 0x00, 0x00, 0x00, 0x00, 0x00])
ubx_send(cfg_prt, '', payload)
time.sleep(0.1)
ubx_send(cfg_prt, '', payload)

serial.deinit()
serial = busio.UART(pin_tx, pin_rx, baudrate=38400, timeout=1, receiver_buffer_size=256)

# DISABLE NMEA GLL, GSA, GSV AND VTG MESSAGES, ONLY RMC AND GGA ARE NEEDED
# ENABLING MORE MESSAGES THAN NEEDED CAN CAUSE SERIAL BUFFER OVERRUNS AND DEVICE LOCKUPS
payload = bytes([0x00, 0x00, 0x00, 0x00, 0x00, 0x00])

while not ubx_send(cfg_msg, cls_gll, payload):
    time.sleep(.1)

while not ubx_send(cfg_msg, cls_gsa, payload):
    time.sleep(.1)

while not ubx_send(cfg_msg, cls_gsv, payload):
    time.sleep(.1)

while not ubx_send(cfg_msg, cls_vtg, payload):
    time.sleep(0.1)

disp_group.remove(message_text)

# CONFIGURE GPS
message_text = ('Waiting for GPS Fix')
message_x = int((disp_x - len(message_text) * char_width) / 2)
message_text = bitmap_label.Label(font, text=message_text, color=0x00FFFF, x=message_x, y=int(disp_y / 2))
disp_group.append(message_text)

timer_start_gps = time.monotonic()
counter_text = '00:00'
counter_x = int((disp_x - len(counter_text) * char_width) / 2)
counter_text = bitmap_label.Label(font, text=counter_text, color=0xFFFFFF, x=counter_x, y=int(disp_y / 2) + char_height + 2)
disp_group.append(counter_text)

# SETUP GPS DECODING
gps = adafruit_gps.GPS(serial, debug=False)

# WAIT FOR INITIAL GPS FIX
old_counter = -1

while not gps.has_fix:
    gps.update()
    counter_gps = time.monotonic() - timer_start_gps
    counter_min = int(counter_gps / 60)
    counter_sec = int(counter_gps % 60)

    if old_counter != counter_sec:
        old_counter = counter_sec
        counter_text.text = '{:02d}:{:02d}'.format(counter_min, counter_sec)

    time.sleep(0.5)

disp_group.remove(message_text)

message_text = ('Waiting For Time Sync')
message_x = int((disp_x - len(message_text) * char_width) / 2)
message_text = bitmap_label.Label(font, text=message_text, color=0x00FFFF, x=message_x, y=int(disp_y / 2))
disp_group.append(message_text)

serial.reset_input_buffer()

# WAIT FOR VALID TIME DATA TO SET RTC
while True:
    if gps.timestamp_utc.tm_year != 0:
        break

    gps.update()
    counter_gps = time.monotonic() - timer_start_gps
    counter_min = int(counter_gps / 60)
    counter_sec = int(counter_gps % 60)
    counter_text.text = '{:02d}:{:02d}'.format(counter_min, counter_sec)
    time.sleep(0.5)

# SET RTC TO GPS TIME (GPS REFERENCES UTC)
clock.datetime = time.struct_time((gps.timestamp_utc.tm_year, gps.timestamp_utc.tm_mon, gps.timestamp_utc.tm_mday, gps.timestamp_utc.tm_hour, gps.timestamp_utc.tm_min, gps.timestamp_utc.tm_sec, 0, -1, -1))
rtc.set_time_source(gps)
disp_group.remove(counter_text)
disp_group.remove(message_text)

# DISPLAY BATTERY GAUGE
bat_progress_bar = HorizontalProgressBar((disp_x - bat_x, 0), (bat_x, bat_y), value=0, min_value=0, max_value=100, fill_color=0x000000, outline_color=0xFFFFFF, bar_color=0x00FF00, direction=HorizontalFillDirection.LEFT_TO_RIGHT)
disp_group.append(bat_progress_bar)

# DISPLAY TIME AND DATE FIELDS
utc_clock_text = bitmap_label.Label(font, text=' ' * 8, color=clock_color, x=0, y=char_start)
disp_group.append(utc_clock_text)

utc_clock_label = bitmap_label.Label(font, text='UTC', color=clock_color, x=char_width * 9, y=char_start)
disp_group.append(utc_clock_label)

utc_date_text = bitmap_label.Label(font, text=' ' * 16, color=date_color, x=0, y=char_start + char_height + line_space)
disp_group.append(utc_date_text)

tz_clock_text = bitmap_label.Label(font, text=' ' * 8, color=clock_color, x=0, y=char_start + (char_height + line_space) * 2 + line_gap)
disp_group.append(tz_clock_text)

tz_clock_label = bitmap_label.Label(font, text='   ', color=clock_color, x=char_width * 9, y=char_start + (char_height + line_space) * 2 + line_gap)
disp_group.append(tz_clock_label)

tz_date_text = bitmap_label.Label(font, text=' ' * 16, color=date_color, x=0, y=char_start + (char_height + line_space) * 3 + line_gap)
disp_group.append(tz_date_text)

# DISPLAY LATITUDE / LONGITUDE / ALTITUDE / GRID / COMPASS FIELDS
lat_label = bitmap_label.Label(font, text='Lat:', color=location_color, x=0, y=char_start + (char_height + line_space) * 4 + line_gap * 2)
disp_group.append(lat_label)

lat_text = bitmap_label.Label(font, text=' ' * 8, color=location_color, x=char_width * 6, y=char_start + (char_height + line_space) * 4 + line_gap * 2)
disp_group.append(lat_text)

grid_text = bitmap_label.Label(font, text=' ' * 6, color=grid_color, x=char_width * 20, y=char_start + (char_height + line_space) * 4 + line_gap * 2)
disp_group.append(grid_text)

lon_label = bitmap_label.Label(font, text='Lon:', color=location_color, x=0, y=char_start + (char_height + line_space) * 5 + line_gap * 2)
disp_group.append(lon_label)

lon_text = bitmap_label.Label(font, text=' ' * 9, color=location_color, x=char_width * 5, y=char_start + (char_height + line_space) * 5 + line_gap * 2)
disp_group.append(lon_text)

gps_update_text = bitmap_label.Label(font, text=' ', color=gps_color, x=char_width * 25, y=char_start + (char_height + line_space) * 5 + line_gap * 2)
disp_group.append(gps_update_text)

# DISPLAY GPS STATISTICS
alt_label = bitmap_label.Label(font, text='Alt:', color=location_color, x=0, y=char_start + (char_height + line_space) * 6 + line_gap * 3)
disp_group.append(alt_label)

alt_ft_text = bitmap_label.Label(font, text=' ' * 5, color=location_color, x=char_width * 6, y=char_start + (char_height + line_space) * 6 + line_gap * 3)
disp_group.append(alt_ft_text)

alt_ft_label = bitmap_label.Label(font, text='FT', color=location_color, x=char_width * 12, y=char_start + (char_height + line_space) * 6 + line_gap * 3)
disp_group.append(alt_ft_label)

alt_m_text = bitmap_label.Label(font, text=' ' * 5, color=location_color, x=char_width * 19, y=char_start + (char_height + line_space) * 6 + line_gap * 3)
disp_group.append(alt_m_text)

alt_m_label = bitmap_label.Label(font, text='M', color=location_color, x=char_width * 25, y=char_start + (char_height + line_space) * 6 + line_gap * 3)
disp_group.append(alt_m_label)

speed_label = bitmap_label.Label(font, text='Spd:', color=location_color, x=0, y=char_start + (char_height + line_space) * 7 + line_gap * 3)
disp_group.append(speed_label)

speed_text = bitmap_label.Label(font, text=' ' * 5, color=location_color, x=char_width * 6, y=char_start + (char_height + line_space) * 7 + line_gap * 3)
disp_group.append(speed_text)

track_label = bitmap_label.Label(font, text='Trk:', color=location_color, x=char_width * 13, y=char_start + (char_height + line_space) * 7 + line_gap * 3)
disp_group.append(track_label)

track_text = bitmap_label.Label(font, text=' ' * 5, color=location_color, x=char_width * 19, y=char_start + (char_height + line_space) * 7 + line_gap * 3)
disp_group.append(track_text)

sat_count_label = bitmap_label.Label(font, text='Satellites:', color=sat_color, x=0, y=char_start + (char_height + line_space) * 8 + line_gap * 4)
disp_group.append(sat_count_label)

sat_count_text = bitmap_label.Label(font, text='  ', color=sat_color, x=char_width * 12, y=char_start + (char_height + line_space) * 8 + line_gap * 4)
disp_group.append(sat_count_text)

comp_text = bitmap_label.Label(font, text='   ', color=compass_color, x=char_width * 23, y=char_start + (char_height + line_space) * 8 + line_gap * 4)
disp_group.append(comp_text)


def main():
    last_alt = None
    last_comp = None
    last_grid_sq = None
    last_lat = None
    last_lon = None
    last_tz_date = None
    last_tz_desc = None
    last_tz_time = None
    last_utc_date = None
    last_utc_time = None
    last_bat_percent = -1
    last_bat_time = -60
    last_sat = -1
    last_speed = -1
    last_track = -1

    while True:
        global disp_level

        # GET GPS DATA
        if gps.update():
            gps_update_text.text = gps_char

            if gps.latitude is not None:
                curr_lat = gps.latitude

            if gps.longitude is not None:
                curr_lon = gps.longitude

            if gps.altitude_m is not None:
                curr_alt = int(gps.altitude_m)
            else:
                curr_alt = 0

            # CONVERT FROM KNOTS TO MPH
            if gps.speed_knots is not None:
                curr_speed = gps.speed_knots * 1.15078
            else:
                curr_speed = 0

            if gps.track_angle_deg is not None:
                curr_track = gps.track_angle_deg
            else:
                curr_track = 0

            if gps.satellites is not None:
                curr_sat = gps.satellites
            else:
                curr_sat = 0

            # GET CURRENT GRID SQUARE, UPDATE LAT, LON AND GRID LABELS IF DATA HAS CHANGED
            curr_grid_sq = calc_grid(curr_lat, curr_lon)

            if last_lat != curr_lat:
                last_lat = curr_lat
                pad_length = 8 - len('{0:.4f}'.format(curr_lat))
                lat_text.text = ' ' * pad_length + '{0:.4f}'.format(curr_lat)

            if last_lon != curr_lon:
                last_lon = curr_lon
                pad_length = 9 - len('{0:.4f}'.format(curr_lon))
                lon_text.text = ' ' * pad_length + '{0:.4f}'.format(curr_lon)

            if last_grid_sq != curr_grid_sq:
                last_grid_sq = curr_grid_sq
                grid_text.text = curr_grid_sq

            # UPDATE ALTITUDE LABELS IF DATA HAS CHANGED
            if last_alt != curr_alt:
                last_alt = curr_alt
                alt_feet = int(curr_alt * 3.28084)
                meter_pad_length = 5 - len(str(curr_alt))
                feet_pad_length = 5 - len(str(alt_feet))
                alt_ft_text.text = ' ' * feet_pad_length + str(alt_feet)
                alt_m_text.text = ' ' * meter_pad_length + str(curr_alt)

            # UPDATE SPEED AND TRACK ANGLE LABELS IF DATA HAS CHANGED
            if last_speed != curr_speed:
                last_speed = curr_speed
                speed = '{0:.1f}'.format(curr_speed)
                speed_pad_length = 5 - len(speed)
                speed_text.text = ' ' * speed_pad_length + speed

            if last_track != curr_track:
                last_track = curr_track
                track = '{0:.1f}'.format(curr_track)
                track_pad_length = 5 - len(track)
                track_text.text = ' ' * track_pad_length + track

            # UPDATE SATELLITE COUNT LABEL IF DATA HAS CHANGED
            if last_sat != curr_sat:
                last_sat = curr_sat
                sat_count_text.text = str(curr_sat)

            time.sleep(0.1)

        # GET CURRENT FORMATTED TIME AND DATE, UPDATE LABELS IF ANY HAVE CHANGED
        curr_datetime = comp_date_time(time.time())

        if last_utc_time != curr_datetime.utc_time:
            last_utc_time = curr_datetime.utc_time
            utc_clock_text.text = curr_datetime.utc_time

        if last_utc_date != curr_datetime.utc_date:
            last_utc_date = curr_datetime.utc_date
            utc_date_text.text = curr_datetime.utc_date

        if last_tz_time != curr_datetime.tz_time:
            last_tz_time = curr_datetime.tz_time
            tz_clock_text.text = curr_datetime.tz_time

        if last_tz_desc != curr_datetime.tz_desc:
            last_tz_desc = curr_datetime.tz_desc
            tz_clock_label.text = curr_datetime.tz_desc

        if last_tz_date != curr_datetime.tz_date:
            last_tz_date = curr_datetime.tz_date
            tz_date_text.text = curr_datetime.tz_date

        # CHECK MAGNETOMETER AND UPDATE LABEL IF DATA HAS CHANGED
        x, y, _ = comp.magnetic

        curr_angle = comp_degree(x, y)
        curr_comp = comp_direction(curr_angle)

        if last_comp != curr_comp:
            last_comp = curr_comp
            pad_length = 3 - len(curr_comp)
            comp_text.text = ' ' * pad_length + curr_comp

        # CHECK BATTERY VOLTAGE ONCE A MINUTE AND CALCULATE PERCENTAGE OF CHARGE
        curr_bat_time = time.monotonic()

        if (curr_bat_time - last_bat_time) >= 60:
            last_bat_time = curr_bat_time
            curr_bat = bat.value
            curr_bat_percent = bat_level(curr_bat)

            # UPDATE BATTERY GAUGE IF PERCENTAGE HAS CHANGED
            if last_bat_percent != curr_bat_percent:
                bat_progress_bar.bar_color = bat_colors[curr_bat_percent - 1]
                bat_progress_bar.value = curr_bat_percent

            if curr_bat <= bat_cutoff:
                disp_group.remove(utc_clock_text)
                disp_group.remove(utc_clock_label)
                disp_group.remove(utc_date_text)
                disp_group.remove(tz_clock_text)
                disp_group.remove(tz_clock_label)
                disp_group.remove(tz_date_text)
                disp_group.remove(lat_label)
                disp_group.remove(lat_text)
                disp_group.remove(grid_text)
                disp_group.remove(lon_label)
                disp_group.remove(lon_text)
                disp_group.remove(gps_update_text)
                disp_group.remove(alt_label)
                disp_group.remove(alt_ft_text)
                disp_group.remove(alt_ft_label)
                disp_group.remove(alt_m_text)
                disp_group.remove(alt_m_label)
                disp_group.remove(speed_label)
                disp_group.remove(speed_text)
                disp_group.remove(track_label)
                disp_group.remove(track_text)
                disp_group.remove(sat_count_label)
                disp_group.remove(sat_count_text)
                disp_group.remove(comp_text)

                message_text = 'LOW BATTERY'
                message_x = int((disp_x - len(message_text) * char_width) / 2)
                message_text = bitmap_label.Label(font, text=message_text, color=0xFFB000, x=message_x, y=int(disp_y / 2))
                disp_group.append(message_text)

                while True:
                    pass

        # CHECK FOR BUTTON PRESS TO ADJUST SCREEN BRIGHTNESS
        if not b_dn.value:
            disp_level -= 1024

            if disp_level < 0:
                disp_level = 0

            disp_backlight.duty_cycle = disp_level
            time.sleep(0.05)

        if not b_up.value:
            disp_level += 1024

            if disp_level > 65535:
                disp_level = 65535

            disp_backlight.duty_cycle = disp_level
            time.sleep(0.05)

        gps_update_text.text = ' '


main()
