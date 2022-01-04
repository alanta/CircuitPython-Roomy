from ringbuffer import RingBuffer
import time
from adafruit_datetime import datetime, time
import board
import busio
# Network
import wifi
import ssl
import socketpool
import adafruit_ntp
import adafruit_requests as requests
from timezone_amsterdam import TimeZoneAmsterdam
# Display
import displayio
import terminalio
from adafruit_bitmap_font import bitmap_font
from adafruit_display_text import label
from adafruit_st7789 import ST7789
# Board
import feathers2
import analogio
import adafruit_dotstar
# Sensor
import adafruit_bme680
from adafruit_io.adafruit_io import IO_HTTP, AdafruitIO_RequestError
import adafruit_apds9960.apds9960
from adafruit_apds9960 import colorutility

# Telemetry
from application_insights import Telemetry, Severity

# Async
import asynccp
from asynccp.time import Duration
import gc

import sys
import traceback

# Make sure the 2nd LDO is turned on
feathers2.enable_LDO2(True)
feathers2.led_set(True)

# Create a DotStar instance
dotstar = adafruit_dotstar.DotStar(board.APA102_SCK, board.APA102_MOSI, 1, brightness=0.5, auto_write=True)

# Clock
import adafruit_ds3231
from time import struct_time

from secrets import secrets

def setupDisplay():
    # Release any resources currently in use for the displays
    displayio.release_displays()

    spi = board.SPI()
    while not spi.try_lock():
        pass
    spi.configure(baudrate=24000000) # Configure SPI for 24MHz
    spi.unlock()

    tft_cs = board.D19
    tft_dc = board.D18

    display_bus = displayio.FourWire(
        spi, command=tft_dc, chip_select=tft_cs, reset=board.D9
    )

    return ST7789(display_bus, width=320, height=240, rotation=90, backlight_pin=board.D17)
    

class NightwatchUI:

  months = ["januari", "februari", "maart", "april", "mei", "juni", "juli", "augustus", "september", "oktober", "november", "december"]
   
  #class default constructor
  def __init__(self,display): 
        self.sunUp = True
        self.display = display
        self.font60 = bitmap_font.load_font("/NotoSans-Bold-60.bdf") #terminalio.FONT
        self.font24 = bitmap_font.load_font("/NotoSans-Bold-24.bdf") #terminalio.FONT

        self.splash = displayio.Group()
        text_group = displayio.Group()
        self.time = label.Label(self.font60, text="            ", color=0xFFFF00)
        self.time.y = 25
        self.date = label.Label(self.font24, text="            ", color=0xFFFF00)
        self.date.y = 75

        self.weather = label.Label(terminalio.FONT, scale=2, text="                                ", color=0xFFFFFF)
        self.weather.y = 150

        self.ambient = label.Label(terminalio.FONT, scale=2, text="                                ", color=0xFFFFFF)
        self.ambient.y = 170

        text_group.append(self.time)
        text_group.append(self.date)
        self.splash.append(text_group)
        self.splash.append(self.weather)
        self.splash.append(self.ambient)
        display.show(self.splash)

 
  #user defined function of class
  def renderTime( self, now ):
    
    self.time.color = 0xFFFFFF if self.sunUp else 0xFFFF00
    
    self.time.text = '{:02}:{:02}'.format(now.tm_hour, now.tm_min)
    (_, _, width, _) = self.time.bounding_box
    self.time.x = self.display.width // 2 - width // 2
    self.date.text = '{} {}'.format(now.tm_mday, self.months[now.tm_mon-1])
    (_, _, width, _) = self.date.bounding_box
    self.date.x = self.display.width // 2 - width // 2

  def renderWeather( self, report ):
       self.weather.text = report

  def renderAmbient( self, temperature, humidity ):
       self.ambient.text = '{:.1f}C {:.1f}%'.format(temperature, humidity)

def setupClock():
    # configure i2c
    i2c = busio.I2C(board.IO9, board.IO8)
    ### clock
    return adafruit_ds3231.DS3231(i2c)

STATUS_NO_CONNECTION = (100, 100, 0)
STATUS_CONNECTING = (0, 0, 100)
STATUS_FETCHING = (200, 100, 0)
STATUS_DOWNLOADING = (0, 100, 100)
STATUS_CONNECTED = (0, 100, 0)
STATUS_DATA_RECEIVED = (0, 0, 100)
STATUS_OFF = (0, 0, 0)
STATUS_FAILED = (255, 0, 0)

class Application:
    def __init__(self, ui):
        self.ui = ui
        i2c = board.I2C()
        self.rtc = adafruit_ds3231.DS3231(i2c)
        now = self.rtc.datetime
        printDateTime("RTC reports UTC is ", now)
        self.environmentalSensor = adafruit_bme680.Adafruit_BME680_I2C(i2c, refresh_rate=1)
        print('Ambient temperature: {} °C'.format(self.environmentalSensor.temperature))
        self.lightSensor = adafruit_apds9960.apds9960.APDS9960(i2c)
        self.lightSensor.enable_proximity = True
        self.lightSensor.enable_gesture = True
        self.lightSensor.enable_color = True
        # https://github.com/adafruit/Adafruit_CircuitPython_APDS9960/blob/main/examples/apds9960_proximity_simpletest.py
        # int_pin = digitalio.DigitalInOut(board.D5) # TODO connect the interrupt line and pick the port
        # self.lightSensor.proximity_interrupt_threshold = (0, 175)
        # self.lightSensor.enable_proximity_interrupt = True
        # Create a reference to the ambient light sensor so we can read it's value
        self.brightnessReadings = RingBuffer(20)
        self.light = analogio.AnalogIn(board.AMB)
        self.status = STATUS_NO_CONNECTION
        self.connected = False
        self.telemetry = Telemetry(secrets['ai_key'], secrets['ai_url'], debug=True)

    async def sampleEnvironment(self):
        self.ambientTemperature = self.environmentalSensor.temperature
        self.ambientHumidity = self.environmentalSensor.humidity
        self.ui.renderAmbient(self.ambientTemperature, self.ambientHumidity)
        #if( self.connected ):
        #    self.io.send_data("ambient-temperature", self.ambientTemperature)
        #    self.io.send_data("ambient-humidity", self.ambientTemperature)

    async def sampleAmbientLight(self):
        #any value of 20k => 100%
        #light = self.light.value
        #if( light >= 20000 ):
        #    self.brightnessReadings.append( 1.0 )
        #else:
        #    self.brightnessReadings.append(((light - 516) / 19484 * 0.99) +0.01)
        r, g, b, c =  self.lightSensor.color_data
        if( c >= 20000 ):
            self.brightnessReadings.append( 1.0 )
        else:
            self.brightnessReadings.append( max(0.01, round(c / 20000, 1)) )
        

    async def adjustBrightness(self):
        buffer = self.brightnessReadings.get()
        avg = sum(buffer)/len(buffer)
        # clamp
        if( avg <= 0 ):
            avg = 0.01
        if avg > 1 :
            avg = 1
        if( display.brightness != avg ):
            display.brightness = avg
    
    async def updateStatusLed(self):
        while True:
            # blinking
            if( self.status == STATUS_NO_CONNECTION or self.status == STATUS_CONNECTING ):
                dotstar[0] = self.status
                await asynccp.delay(seconds=0.25)
                dotstar[0] = STATUS_OFF
                await asynccp.delay(seconds=0.25)
                continue

            # blink once 250ms
            if( self.status == STATUS_CONNECTED or self.status == STATUS_FETCHING or self.status == STATUS_DATA_RECEIVED ):
                dotstar[0] = self.status
                self.status = STATUS_OFF
                await asynccp.delay(seconds=0.25)
                continue
            
            # default
            # TODO : optimize to only write changes ?
            if( dotstar[0] != self.status ):
                dotstar[0] = self.status
                await asynccp.delay(seconds=0.1)
            else:
                await asynccp.delay(seconds=0.5)

    # connect to wifi
    async def connectWifi(self):
        print("Connecting to wifi")
        self.status=STATUS_CONNECTING
        while not wifi.radio.ap_info:
            try:
                wifi.radio.connect(secrets["ssid"], secrets["password"])
            except Exception as e:
                print("Could not connect to AP, retrying: ", e)
                await asynccp.delay(seconds=0.5)
                continue
        
        print("Connected, IP {0}.".format(wifi.radio.ipv4_address))
        self.pool = socketpool.SocketPool(wifi.radio)
        self.https = requests.Session(self.pool, ssl.create_default_context())
        self.status=STATUS_CONNECTED
        self.connected=True
        #self._setupAdafruitIO()
        return self.pool

    def utcnow(self):
        return to_datetime(self.rtc.datetime)

    async def uploadTelemetry(self):
        self.telemetry.trace('Ping', Severity.Information, timestamp = self.utcnow().isoformat())

        if not self.connected:
            return
        
        await self.telemetry.upload_telemetry(self.https)

    def _setupAdafruitIO(self):
        self.io = IO_HTTP(secrets["aio_username"], secrets["aio_key"], self.https)
        try:
            ambient_t_feed = self.io.get_feed("ambient-temperature")
        except AdafruitIO_RequestError:
            ambient_t_feed = self.io.create_new_feed("ambient-temperature")

        try:
            ambient_h_feed = self.io.get_feed("ambient-humidity")
        except AdafruitIO_RequestError:
            ambient_h_feed = self.io.create_new_feed("ambient-humidity")

    async def syncWithNtp(self):
        if( not self.connected ):
            await asynccp.delay(Duration.of_minutes(15))

        try:
            print("Sync time with NTP")
            ntp = adafruit_ntp.NTP(self.pool)   
            # set the time from ntp - this is UTC
            self.rtc.datetime = ntp.datetime
        
            printDateTime("RTC set to : ", self.rtc.datetime)
            await asynccp.delay(Duration.of_hours(24))
        except Exception as ex:
            print('Weather API failed, retrying on the next run')
            self.telemetry.exception(ex, Severity.Information, timestamp = self.utcnow().isoformat())
            traceback.print_exception(ex, ex, ex.__traceback__)

    async def handleGesture(self):
        gesture = self.lightSensor.gesture()

        if gesture == 0x01:
            print("up")
        elif gesture == 0x02:
            print("down")
        elif gesture == 0x03:
            print("left")
        elif gesture == 0x04:
            print("right")

        # r, g, b, c =  self.lightSenso.color_data
        # print("red: ", r)
        # print("green: ", g)
        # print("blue: ", b)
        # print("clear: ", c)

        # print("color temp {}".format(colorutility.calculate_color_temperature(r, g, b)))
        # print("light lux {}".format(colorutility.calculate_lux(r, g, b)))

    async def updateTime(self):
        while True:
            try:
                current = toLocalDateTime( self.rtc.datetime ).timetuple()
                printDateTime("The current time is: ", current)
                ui.renderTime(current)           
            except Exception as ex:
                print('updateTime failed')
                self.telemetry.exception(ex, Severity.Information, timestamp = self.utcnow().isoformat())
                traceback.print_exception(ex, ex, ex.__traceback__)
            finally:
                await asynccp.delay(seconds=60-self.rtc.datetime.tm_sec) # sleep the rest of the minute  

    async def updateWeather(self):
        while( not self.connected ):
            print('Waiting for wifi to connect')
            await asynccp.delay(seconds=5)

        try:
            self.status = STATUS_FETCHING
            with self.https.get(secrets['weather_api']) as response:
                if response.status_code != 200:
                    print("Weather API response is {}".format(response.status_code))
                    self.status = STATUS_FAILED
                else:
                    self.status = STATUS_DATA_RECEIVED
                    report = response.json()
                    try:
                        print('{} {}°C '.format(report['liveweer'][0]['samenv'], report['liveweer'][0]['temp']))
                        ui.renderWeather( '{} {}'.format(report['liveweer'][0]['samenv'], report['liveweer'][0]['temp']))
                        # sup en sunder => zon op / onder
                        sunUp = time.fromisoformat(report['liveweer'][0]['sup'])
                        sunUnder = time.fromisoformat(report['liveweer'][0]['sunder'])
                        now = toLocalDateTime( self.rtc.datetime )
                        sunIsUp = sunUp<now.time() and sunUnder>now.time()
                        if( ui.sunUp != sunIsUp ):
                            print('Sun is ', 'up' if sunIsUp else 'under')
                            ui.sunUp = sunIsUp
                    finally:
                        # see https://learn.adafruit.com/oshwa-project-display-with-adafruit-magtag/code-the-project-display
                        report.clear()
                        report = None
                        response.close()
                        gc.collect()
                
            # d0weer d0tmin d0tmax => Vandaag {weer} {min} tot {max} graden
        except Exception as ex:
            print('Weather API failed, retrying on the next run')
            self.telemetry.exception(ex, Severity.Information, timestamp = self.utcnow().isoformat())
            traceback.print_exception(ex, ex, ex.__traceback__)
            if( not wifi.radio.ap_info ):
                print('Wifi connection was dropped')
            

def printDateTime( str, current ):
    "Write the current date and time"
    print('{} {}/{}/{} {:02}:{:02}:{:02}'.format(str, current.tm_mday, current.tm_mon, current.tm_year, current.tm_hour, current.tm_min, current.tm_sec))

def to_datetime(current:struct_time) -> datetime:
    return datetime(current.tm_year, current.tm_mon, current.tm_mday, current.tm_hour, current.tm_min, current.tm_sec)

def toLocalDateTime(current:struct_time) -> datetime:
    utc = to_datetime(current)
    now = TimeZoneAmsterdam().fromutc(utc)
    return now

display = setupDisplay()
display.auto_brightness = False
display.brightness = 1

ui = NightwatchUI(display)
app = Application(ui)

asynccp.add_task(app.updateTime())
asynccp.add_task(app.updateStatusLed())
asynccp.schedule(frequency=Duration.of_minutes(5), coroutine_function=app.updateWeather)
asynccp.run_later(0.5, app.connectWifi())
asynccp.schedule_later(hz=Duration.of_hours(24), coroutine_function=app.syncWithNtp)
asynccp.schedule(frequency=3, coroutine_function=app.sampleAmbientLight)
asynccp.schedule(frequency=0.5, coroutine_function=app.adjustBrightness)
asynccp.schedule(frequency=10, coroutine_function=app.handleGesture)
asynccp.schedule(frequency=Duration.of_seconds(30), coroutine_function=app.sampleEnvironment)
asynccp.schedule(frequency=Duration.of_minutes(5), coroutine_function=app.uploadTelemetry)
feathers2.led_set(False)
asynccp.run()