
from adafruit_datetime import datetime
import adafruit_requests as requests
import json
import time
import board
import os
import traceback

# Application Insights SDK for CircuitPython
#
# This is a (very) rudimentry ApplicationInsights SDK for CircuitPython and allows you to log traces, metrics and exceptions to Azure
#
# Requirements
# * CircuitPython 7.0 or better
# * A board with Wifi and plenty of RAM
#
# Setup
# * Create an AppInsights resource in azure, note the instrumentation key and ingestion endpoint
# * Create a Telemetry object in your code
# * Add telemetry by calling the trace, metric or exception methods
# * Schedule a periodic task to invoke upload_telemetry to upload data to ApplicationInsights
#
# ⚠ Warning
# This was developed and tested on an UnexpectedMaker Feather S2 that has tons of RAM and Wifi built in
# Please be aware that the data to be uploaded to AI will be kept in memory until uploaded. If you collect a lot of 
# telemetry or wait too long to upload the data you're likely to run out of memory


# https://github.com/microsoft/ApplicationInsights-JS/blob/master/shared/AppInsightsCommon/src/Interfaces/Contracts/Generated/SeverityLevel.ts
class Severity:
    Verbose: int = 0
    Information: int = 1
    Warning: int = 2
    Error: int = 3
    Critical: int = 4


class Telemetry:
    def __init__(self, instrumentation_key:str, endpoint_url:str=None, debug:bool=False):
        self.instrumentationKey = instrumentation_key
        if endpoint_url is None:
            self._endpointUrl = "https://dc.services.visualstudio.com/v2/track"
        else:
            self._endpointUrl = endpoint_url + "/v2/track"
        self._debug=debug
        self._defaultTags = {
            "ai.internal.sdkVersion": "cpy:0.0.1",
            "ai.device.osVersion": "CircuitPython "+os.uname().release,
            "ai.device.model": board.board_id,
            "ai.device.type": "IoT"
        }
        self._pendingData = []

    def trace(self, message:str, severity:int = Severity.Verbose, timestamp:str = None):
        # https://github.com/microsoft/ApplicationInsights-JS/blob/master/shared/AppInsightsCommon/src/Telemetry/Trace.ts
        telemetry = {
            "time": datetime.now().isoformat() if timestamp is None else timestamp,
            "name": "Microsoft.ApplicationInsights.{}.Message".format(self.instrumentationKey.replace('-', '')),
            "iKey": self.instrumentationKey,
            "tags": self._defaultTags,
            "data": {
                "baseType": "MessageData",
                "baseData": {
                    "ver": 2,
                    "message": message,
                    "severityLevel": severity,
                    # "properties":
                    # "measurements"
                }
            }
        }
        self._pendingData.append(telemetry)
    
    def exception(self, exception:Exception, severity:int = Severity.Error, timestamp:str = None):
        telemetry = {
            "time": datetime.now().isoformat() if timestamp is None else timestamp,
            "name": "Microsoft.ApplicationInsights.{}.Exception".format(self.instrumentationKey.replace('-', '')),
            "iKey": self.instrumentationKey,
            "tags": self._defaultTags,
            "data": {
                "baseType": "ExceptionData",
                "baseData": {
                    "ver": 2,
                    "exceptions": [{
                        "message": ''.join(traceback.format_exception(type(exception), exception, None)),
                        "hasFullStack": True,
                        "typeName": type(exception).__name__,
                        "stack": ''.join(traceback.format_exception(exception, exception, exception.__traceback__))
                    }],
                    "severityLevel": severity
                    # "properties":
                    # "measurements"
                }
            }
        }
        self._pendingData.append(telemetry)

    def metric(self, name:str, value, count:int=None, min:float=None, max: float=None, stdDev: float=None, timestamp:str = None):
        telemetry = {
            "time": datetime.now().isoformat() if timestamp is None else timestamp,
            "name": "Microsoft.ApplicationInsights.{}.Metric".format(self.instrumentationKey.replace('-', '')),
            "iKey": self.instrumentationKey,
            "tags": self._defaultTags,
            "data": {
                "baseType": "MetricData",
                "baseData": {
                    "ver": 2,
                    "metrics": [{ # only one metric can be passed in
                      "name": name,
                      "value": value,
                      "count": count,
                      "max": max,
                      "min": min,
                      "stdDev": stdDev
                    }]
                    # "properties":
                    # "measurements"
                }
            }
        }
        self._pendingData.append(telemetry)

    async def upload_telemetry(self, requests: requests.Session):
        if len(self._pendingData) == 0:
            return

        # swap the queue
        pending = self._pendingData
        self._pendingData = []

        # send it off to AI
        if( self._debug ):
            print("AI Url: {}\nPayload: {}".format(self._endpointUrl, json.dumps(pending)))

        with requests.post(url=self._endpointUrl, json=pending ) as response:
            if response.status_code != 200:
                print("ApplicationInsights failed with status {}".format(response.status_code))
            if( self._debug ):
                print("Response: {}".format(response.text))

## Relevant info in the AI Javascript SDK
## https://github.com/microsoft/ApplicationInsights-JS/blob/master/shared/AppInsightsCommon/src/Interfaces/PartAExtensions.ts
## https://github.com/microsoft/ApplicationInsights-JS/blob/master/shared/AppInsightsCommon/src/Interfaces/Contracts/Generated/ContextTagKeys.ts
## https://github.com/microsoft/ApplicationInsights-JS/blob/master/channels/applicationinsights-channel-js/src/EnvelopeCreator.ts



