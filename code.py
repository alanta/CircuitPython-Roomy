from ringbuffer import RingBuffer
import time
from adafruit_datetime import datetime, timedelta
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
# Async
import tasko
import ringbuffer

# Make sure the 2nd LDO is turned on
feathers2.enable_LDO2(True)
feathers2.led_set(True)

# Create a DotStar instance
#dotstar = adafruit_dotstar.DotStar(board.APA102_SCK, board.APA102_MOSI, 1, brightness=0.5, auto_write=True)

# Create a reference to the ambient light sensor so we can read it's value
light = analogio.AnalogIn(board.AMB)



# Clock
import adafruit_ds3231

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
        self.display = display
        self.font60 = bitmap_font.load_font("/NotoSans-Bold-60.bdf") #terminalio.FONT
        self.font24 = bitmap_font.load_font("/NotoSans-Bold-24.bdf") #terminalio.FONT
        self.splash = displayio.Group(max_size=10)
        display.show(self.splash)
        text_group = displayio.Group(max_size=10)
        self.time = label.Label(self.font60, text="            ", color=0xFFFF00)
        self.time.y = 25
        self.date = label.Label(self.font24, text="            ", color=0xFFFF00)
        self.date.y = 75

        self.weather = label.Label(terminalio.FONT, scale=2, text="                                ", color=0xFFFFFF)
        self.weather.y = 150

        text_group.append(self.time)  # Subgroup for text scaling
        text_group.append(self.date)
        self.splash.append(text_group)
        self.splash.append(self.weather)

 
  #user defined function of class
  def renderTime( self, current ):
    
    utc = datetime(current.tm_year, current.tm_mon, current.tm_mday, current.tm_hour, current.tm_min, current.tm_sec)
    now = TimeZoneAmsterdam().fromutc(utc).timetuple()

    self.time.text = '{:02}:{:02}'.format(now.tm_hour, now.tm_min)
    (_, _, width, _) = self.time.bounding_box
    self.time.x = self.display.width // 2 - width // 2
    self.date.text = '{} {}'.format(now.tm_mday, self.months[now.tm_mon-1])
    (_, _, width, _) = self.date.bounding_box
    self.date.x = self.display.width // 2 - width // 2

  def renderWeather( self, report ):
       self.weather.text = report

def setupClock():
    # configure i2c
    i2c = busio.I2C(board.IO9, board.IO8)
    ### clock
    return adafruit_ds3231.DS3231(i2c)

# connect to wifi
def connectWifi():
    while not wifi.radio.ap_info:
        try:
            wifi.radio.connect(secrets["ssid"], secrets["password"])
        except Exception as e:
            print("Could not connect to AP, retrying: ", e)
            time.sleep(0.5)
            continue
    
    print("Connected, IP {0}.".format(wifi.radio.ipv4_address))
    pool = socketpool.SocketPool(wifi.radio)

    return pool;

def syncWithNtp(pool):
    print("Sync time with NTP")
    ntp = adafruit_ntp.NTP(pool)   
    # set the time from ntp - this is UTC
    ds3231.datetime = ntp.datetime
    
    printDateTime("Now : ", ds3231.datetime)


def printDateTime( str, current ):
    "Write the current date and time"
    print('{} {}/{}/{} {:02}:{:02}:{:02}'.format(str, current.tm_mday, current.tm_mon, current.tm_year, current.tm_hour, current.tm_min, current.tm_sec))



display = setupDisplay();
display.auto_brightness = False
display.brightness = 0;

ui = NightwatchUI(display);
ds3231 = setupClock();

now = ds3231.datetime
printDateTime("Now :", now)
#alarmTime = time.localtime(time.mktime(now)+60)
#printDateTime("Setting alarm at: ", alarmTime)

#ds3231.alarm1 = (alarmTime, "daily")

pool = connectWifi()
syncWithNtp(pool)
#https = adafruit_requests.Session(pool, ssl.create_default_context())

first = True;

async def updateTime():
    global first
    while True:
        #if ds3231.alarm1_status:
        #    print( 'Alarm!' )
        #    ds3231.alarm1_status = False
        current = ds3231.datetime
        printDateTime("The current time is: ", current)
        ui.renderTime(current)
        
        if (first):
            for i in range(100):
                display.brightness = 0.01 * i
                tasko.sleep(0.02)
            first = False
        await tasko.sleep(60-ds3231.datetime.tm_sec) # sleep the rest of the minute

async def sampleAmbientLight():
    #any value of 20k => 100%
    if( light.value >= 20000 ):
        brightnessReadings.append( 1.0 )
    else:
        brightnessReadings.append(((light.value - 516) / 19484 * 0.99) +0.01)

async def adjustBrightness():
    buffer = brightnessReadings.get()
    avg = sum(buffer)/len(buffer)
    # clamp
    if( avg < 0 ):
        avg = 0.01
    if avg > 1 :
        avg = 1
    if( display.brightness != avg ):
        print('brightness: ', avg)
        display.brightness = avg


async def updateWeather():
    https = requests.Session(pool, ssl.create_default_context())
    while True:
        try:
            report = https.get(secrets['weather_api']).json()
            print('{} {}°C '.format(report['liveweer'][0]['samenv'], report['liveweer'][0]['temp']))
            ui.renderWeather( '{} {}'.format(report['liveweer'][0]['samenv'], report['liveweer'][0]['temp']))
            # sup en sunder => zon op / onder
            # d0weer d0tmin d0tmax => Vandaag {weer} {min} tot {max} graden
            
        except:
            print('Weather API failed, retrying on the next run')
            https = requests.Session(pool, ssl.create_default_context())
        
        finally:
            await tasko.sleep(300) # sleep 5 minutes


brightnessReadings = RingBuffer(20)

tasko.add_task(updateTime())
tasko.add_task(updateWeather())
#tasko.schedule(hz=3, coroutine_function=sampleAmbientLight)
#tasko.schedule(hz=0.5, coroutine_function=adjustBrightness)
feathers2.led_set(False)
tasko.run()