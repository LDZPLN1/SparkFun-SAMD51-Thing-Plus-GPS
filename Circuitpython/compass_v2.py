import board
import displayio
import math
import pwmio
import terminalio
import time

import adafruit_ili9341
import adafruit_lsm303dlh_mag

from adafruit_display_text import label

flip_x_axis = True
flip_y_axis = False
swap_axis = False

def comp_degree(x_axis, y_axis):
  if flip_x_axis:
    x_axis *= -1

  if flip_y_axis:
    y_axis *= -1

  if swap_axis:
    x_axis, y_axis = y_axis, x_axis

  if (x_axis > 0) and (y_axis == 0):
    angle = 0
  elif (x_axis < 0) and (y_axis == 0):
    angle = 180
  elif y_axis > 0:
    angle = 90 - math.atan(x_axis/y_axis) * 180 / math.pi
  elif y_axis < 0:
    angle = 270 - math.atan(x_axis/y_axis) * 180 / math.pi

  if angle < 0:
    angle += 360

  if angle >= 360:
    angle -= 360

  return angle

def comp_direction (degrees):
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

displayio.release_displays()
spi = board.SPI()
disp_bus = displayio.FourWire(spi, command=board.D6, chip_select=board.D5, reset=board.D9, baudrate=60000000)
disp = adafruit_ili9341.ILI9341(disp_bus, width=320, height=240)

disp_backlight = pwmio.PWMOut(board.D10, frequency=5000, duty_cycle=32768)

i2c = board.I2C()
comp = adafruit_lsm303dlh_mag.LSM303DLH_Mag(i2c)

# DISPLAY SPLASH LOGO
bitmap = displayio.OnDiskBitmap('/images/ab9xa.bmp')
tile_grid = displayio.TileGrid(bitmap, pixel_shader=bitmap.pixel_shader)
disp_group = displayio.Group()
disp_group.append(tile_grid)
disp.show(disp_group)

comp_angle = (11.25, 33.75, 56.25, 78.75, 101.25, 123.75, 146.25, 168.75, 191.25, 213.75, 236.25, 258.75, 281.25, 303.75, 326.25, 348.75)
comp_point = ('NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE', 'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW')

font = terminalio.FONT

# REMOVE SPLASH LOGO
time.sleep(1.5)
disp_group.remove(tile_grid)

disp_group = displayio.Group(scale = 2)
disp.show(disp_group)
angle_text = label.Label(font, text='      ', color=0xFFFFFF, x=0, y=3)
disp_group.append(angle_text)

direction_text = label.Label(font, text='   ', color=0xFFFFFF, x=80, y=3)
disp_group.append(direction_text)

corrected_angle_text = label.Label(font, text='      ', color=0xFFFFFF, x=0, y=15)
disp_group.append(corrected_angle_text)

corrected_direction_text = label.Label(font, text='   ', color=0xFFFFFF, x=80, y=15)
disp_group.append(corrected_direction_text)

x_raw_text = label.Label(font, text='         ', color=0xFFFFFF, x=0, y=33)
disp_group.append(x_raw_text)

y_raw_text = label.Label(font, text='         ', color=0xFFFFFF, x=0, y=45)
disp_group.append(y_raw_text)

x_cal_text = label.Label(font, text='         ', color=0xFFFFFF, x=0, y=63)
disp_group.append(x_cal_text)

y_cal_text = label.Label(font, text='         ', color=0xFFFFFF, x=0, y=75)
disp_group.append(y_cal_text)

def main():
  x_min = 0
  x_max = 0
  y_min = 0
  y_max = 0

  while True:
    x, y, _ = comp.magnetic

    if x < x_min:
      x_min = x

    if x > x_max:
      x_max = x

    if y < y_min:
      y_min = y

    if y > y_max:
      y_max = y

    x_cal = (x_min + x_max) / 2
    y_cal = (y_min + y_max) / 2

    corrected_x = x - x_cal
    corrected_y = y - y_cal

    uncorrected_angle = comp_degree(x ,y)
    uncorrected_direction = comp_direction(uncorrected_angle)
    corrected_angle = comp_degree(corrected_x, corrected_y)
    corrected_direction = comp_direction(corrected_angle)

    angle_text.text = str(uncorrected_angle)
    direction_text.text = uncorrected_direction
    corrected_angle_text.text = str(corrected_angle)
    corrected_direction_text.text = corrected_direction
    x_raw_text.text = str(x)
    y_raw_text.text = str(y)
    x_cal_text.text = str(x_cal)
    y_cal_text.text = str(y_cal)

main()
