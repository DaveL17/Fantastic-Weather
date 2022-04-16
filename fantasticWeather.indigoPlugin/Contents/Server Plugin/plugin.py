# noqa pylint: disable=too-many-lines, line-too-long, invalid-name, unused-argument, redefined-builtin, broad-except, fixme

"""
Fantastically Useful Weather Utility Indigo Plugin
Author: DaveL17

Credits:
  Regression Testing by: Monstergerm

The Fantastically Useful Weather Utility plugin downloads JSON data from Dark Sky and parses it into
custom device states. Theoretically, the user can create an unlimited number of devices representing
individual observation locations. The Fantastically Useful Weather Utility plugin will update each
custom device found in the device dictionary incrementally.

The base Dark Sky developer plan allows for 1000 per day. See Dark Sky for more information on API
call limitations.

The plugin tries to leave DS data unchanged. But in order to be useful, some changes need to be
made. The plugin adjusts the raw JSON data in the following ways:
- Takes numerics and converts them to strings for Indigo compatibility where necessary.
- Strips non-numeric values from numeric values for device states where appropriate (but retains
  them for ui.Value)
- Replaces anything that is not a rational value (i.e., "--" with "0" for precipitation since
  precipitation can only be zero or a positive value) and replaces "-999.0" with a value of -99.0
  and a UI value of "--" since the actual value could be positive or negative.

Weather data copyright Dark Sky and its respective data providers. This plugin and its author are
in no way affiliated with Dark Sky. For more information about data provided see Dark Sky Terms of
Service located at: https://www.darksky.net

For information regarding the use of this plugin, see the license located in the plugin package or
located on GitHub: https://github.com/DaveL17/Fantastic-Weather/blob/master/LICENSE
"""
# =================================== TO DO ===================================

# TODO - Nothing
# FIXME - pytz module is required.

# ================================== IMPORTS ==================================

# Built-in modules
import datetime as dt
import logging
import json
import textwrap
import time
import pytz
from dateutil.parser import parse

# Third-party modules
try:
    import indigo  # noqa
#     import pydevd
    import requests
except ImportError:
    pass

# My modules
import DLFramework.DLFramework as Dave  # noqa
from constants import *  # noqa
from plugin_defaults import kDefaultPluginPrefs  # noqa

# =================================== HEADER ==================================
__author__    = Dave.__author__
__copyright__ = Dave.__copyright__
__license__   = Dave.__license__
__build__     = Dave.__build__
__title__     = "Fantastically Useful Weather Utility"
__version__   = "2022.0.1"


# =============================================================================
class Plugin(indigo.PluginBase):
    """
    Standard Indigo Plugin Class

    :param indigo.PluginBase:
    """
    def __init__(self, plugin_id, plugin_display_name, plugin_version, plugin_prefs):
        """
        Plugin initialization

        :param str plugin_id:
        :param str plugin_display_name:
        :param str plugin_version:
        :param indigo.Dict plugin_prefs:
        """
        super().__init__(plugin_id, plugin_display_name, plugin_version, plugin_prefs)

        self.inst_attr = {}  # instance attributes (globals)
        self.inst_attr['ds_online'] = True
        self.inst_attr['pluginIsShuttingDown'] = False
        self.inst_attr['comm_error'] = False
        self.inst_attr['download_interval'] = dt.timedelta(
            seconds=int(self.pluginPrefs.get('downloadInterval', '900'))
        )

        self.masterWeatherDict    = {}
        self.masterTriggerDict    = {}
        self.pluginPrefs['dailyCallLimitReached'] = False

        # ========================== API Poll Values ==========================
        last_poll = self.pluginPrefs.get('lastSuccessfulPoll', "1970-01-01 00:00:00")
        try:
            self.inst_attr['last_successful_poll'] = parse(last_poll)
        except ValueError:
            self.inst_attr['last_successful_poll'] = parse("1970-01-01 00:00:00")

        next_poll = self.pluginPrefs.get('nextPoll', "1970-01-01 00:00:00")
        try:
            self.inst_attr['next_poll'] = parse(next_poll)
        except ValueError:
            self.inst_attr['next_poll'] = parse("1970-01-01 00:00:00")

        # ========================== Initialize DLFramework ===========================
        self.Fogbert     = Dave.Fogbert(self)
        self.Formatter   = Dave.Formatter(self)
        self.inst_attr['date_format'] = self.Formatter.dateFormat()
        self.inst_attr['time_format'] = self.Formatter.timeFormat()

        # Log pluginEnvironment information when plugin is first started
        self.Fogbert.pluginEnvironment()

        # Fantastically Useful Weather Utility Attribution and disclaimer.
        indigo.server.log('*' * 130)
        powered = (
            " Powered by Dark Sky. This plugin and its author are in no way affiliated with Dark "
            "Sky. "
        )
        indigo.server.log(f"{powered:*^130}")
        warning = " !!!!! WARNING. The Dark Sky API is slated to be discontinued in 2022. !!!!! "
        indigo.server.log(f"{warning:*^130}")
        indigo.server.log("*" * 130)

        # =============================== Debug Logging ===============================
        # Set the format and level handlers for the logger
        debug_level = self.pluginPrefs.get('showDebugLevel', '30')
        log_format = '%(asctime)s.%(msecs)03d\t%(levelname)-10s\t%(name)s.%(funcName)-28s %(msg)s'
        self.plugin_file_handler.setFormatter(
            logging.Formatter(fmt=log_format, datefmt='%Y-%m-%d %H:%M:%S')
        )
        self.indigo_log_handler.setLevel(int(debug_level))

        # ============================= Remote Debugging ==============================
        # try:
        #     pydevd.settrace(
        #         'localhost',
        #         port=5678,
        #         stdoutToServer=True,
        #         stderrToServer=True,
        #         suspend=False
        #     )
        # except:
        #     pass

    # =============================================================================
    def __del__(self):
        """
        Title Placeholder

        Body placeholder
        """
        indigo.PluginBase.__del__(self)

    # =============================================================================
    # ============================== Indigo Methods ===============================
    # =============================================================================
    def closedPrefsConfigUi(self, values_dict=None, user_cancelled=False):  # noqa
        """
        Title Placeholder

        Body placeholder

        :param indigo.Dict values_dict:
        :param bool user_cancelled:
        :return:
        """
        if not user_cancelled:
            self.indigo_log_handler.setLevel(int(values_dict['showDebugLevel']))

            # ============================= Update Poll Time ==============================
            self.inst_attr['download_interval'] = dt.timedelta(
                seconds=int(self.pluginPrefs.get('downloadInterval', '900'))
            )
            last_poll = self.pluginPrefs.get('lastSuccessfulPoll', "1970-01-01 00:00:00")

            try:
                next_poll = parse(last_poll) + self.inst_attr['download_interval']

            except ValueError:
                next_poll = parse(last_poll) + self.inst_attr['download_interval']

            self.pluginPrefs['nextPoll'] = f"{next_poll}"

            # =================== Update Item List Temperature Precision ==================
            # For devices that display the temperature as their main UI state, try to set them to
            # their (potentially changed) ui format.
            for dev in indigo.devices.iter('self'):

                # For weather device types
                if dev.deviceTypeId == 'Weather':

                    current_on_off_state = dev.states.get('onOffState', True)
                    current_on_off_state_ui = dev.states.get('onOffState.ui', "")

                    # If the device is currently displaying its temperature value, update it to
                    # reflect its new format
                    if current_on_off_state_ui not in ('Disabled', 'Enabled', ''):
                        try:
                            units_dict = {'auto': '', 'ca': 'C', 'uk2': 'C', 'us': 'F', 'si': 'C'}
                            units = units_dict[self.pluginPrefs.get('units', '')]
                            temp_decimal = int(self.pluginPrefs['itemListTempDecimal'])
                            temp_units = dev.pluginProps['temperatureUnits']
                            display_value = (
                                f"{dev.states['temperature']:.{temp_decimal}f} {temp_units}{units}"
                            )

                        except KeyError:
                            display_value = ""

                        dev.updateStateOnServer(
                            'onOffState', value=current_on_off_state, uiValue=display_value
                        )

            # Ensure that self.pluginPrefs includes any recent changes.
            for k in values_dict:
                self.pluginPrefs[k] = values_dict[k]

    # =============================================================================
    def deviceStartComm(self, dev=None):  # noqa
        """
        Title Placeholder

        Body placeholder

        :param indigo.Device dev:
        """
        # Check to see if the device profile has changed.
        dev.stateListOrDisplayStateIdChanged()

        # ========================= Update Temperature Display ========================
        # For devices that display the temperature as their UI state, try to set them to a value we
        # already have.
        try:
            temp_units = dev.pluginProps['temperatureUnits']
            temp_decimal = int(self.pluginPrefs['itemListTempDecimal'])
            display_value = f"{dev.states['temperature']:.{temp_decimal}f}{temp_units}"

        except KeyError:
            display_value = "Enabled"

        # =========================== Set Device Icon to Off ==========================
        if dev.deviceTypeId == 'Weather':
            dev.updateStateImageOnServer(indigo.kStateImageSel.TemperatureSensor)
        else:
            dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)

        dev.updateStateOnServer('onOffState', value=True, uiValue=display_value)

    # =============================================================================
    @staticmethod
    def deviceStopComm(dev=None):  # noqa
        """
        Title Placeholder

        Body placeholder

        :param indigo.Device dev:
        :return:
        """
        # =========================== Set Device Icon to Off ==========================
        if dev.deviceTypeId == 'Weather':
            dev.updateStateImageOnServer(indigo.kStateImageSel.TemperatureSensor)
        else:
            dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)

        dev.updateStateOnServer('onOffState', value=False, uiValue="Disabled")

    # =============================================================================
    def getDeviceConfigUiValues(self, values_dict=None, type_id="", dev_id=0):  # noqa
        """
        Title Placeholder

        Body placeholder

        :param indigo.Dict values_dict:
        :param str type_id:
        :param int dev_id:
        :return:
        """
        if type_id == 'Daily':
            # weatherSummaryEmailTime is set by a generator. We need this bit to pre-populate the
            # control with the default value when a new device is created.
            if 'weatherSummaryEmailTime' not in values_dict:
                values_dict['weatherSummaryEmailTime'] = "01:00"

        if type_id != 'satelliteImageDownloader':
            # If new device, lat/long will be zero. so let's start with the lat/long of the Indigo
            # server.

            if values_dict.get('latitude', "0") == "0" or values_dict.get('longitude', "0") == "0":
                lat_long = indigo.server.getLatitudeAndLongitude()
                values_dict['latitude'] = str(lat_long[0])
                values_dict['longitude'] = str(lat_long[1])
                self.logger.debug("Populated lat/long.")

        return values_dict

    # =============================================================================
    def runConcurrentThread(self):  # noqa
        """
        Title Placeholder

        Body placeholder
        """
        self.logger.debug("Starting main thread.")

        self.sleep(5)

        try:
            while True:

                # Load the download interval in case it's changed
                refresh_time           = self.pluginPrefs.get('downloadInterval', '900')
                self.inst_attr['download_interval'] = dt.timedelta(seconds=int(refresh_time))

                self.inst_attr['last_successful_poll'] = (
                    parse(self.pluginPrefs['lastSuccessfulPoll'])
                )
                self.inst_attr['next_poll']            = parse(self.pluginPrefs['nextPoll'])

                # If we have reached the time for the next scheduled poll
                if dt.datetime.now() > self.inst_attr['next_poll']:

                    self.refresh_weather_data()
                    self.trigger_processing()

                # Wait 30 seconds before trying again.
                self.sleep(30)

        except self.StopThread:
            self.logger.debug("Stopping Fantastically Useful Weather Utility thread.")

    # =============================================================================
    @staticmethod
    def sendDevicePing(dev_id=0, suppress_logging=False):  # noqa
        """
        Title Placeholder

        Body placeholder

        :param int dev_id:
        :param bool suppress_logging:
        :return dict:
        """
        indigo.server.log("Fantastic Weather Plugin devices do not support the ping function.")
        return {'result': 'Failure'}

    # =============================================================================
    def shutdown(self):
        """
        Standard Indigo method called at plugin shutdown

        :return:
        """
        self.inst_attr['pluginIsShuttingDown'] = True

    # =============================================================================
    def startup(self):
        """
        Standard Indigo method called at plugin startup.

        :return:
        """
        # =========================== Audit Indigo Version ============================
        self.Fogbert.audit_server_version(min_ver=2022)

        # =========================== Audit OS Version ============================
        self.Fogbert.audit_os_version(min_ver=10.13)

    # =============================================================================
    def triggerStartProcessing(self, trigger):  # noqa
        """
        Title Placeholder

        Body placeholder

        :param indigo.Trigger trigger:
        :return:
        """
        dev_id = trigger.pluginProps['list_of_devices']
        timer  = trigger.pluginProps.get('offlineTimer', '60')

        # ============================= masterTriggerDict =============================
        # masterTriggerDict contains information on Weather Location Offline triggers.
        # {dev.id: (timer, trigger.id)}
        if trigger.configured and trigger.pluginTypeId == 'weatherSiteOffline':
            self.masterTriggerDict[dev_id] = (timer, trigger.id)

    # =============================================================================
    def triggerStopProcessing(self, trigger):  # noqa
        """
        Title Placeholder

        Body placeholder

        :param indigo.Trigger trigger:
        """
        # self.logger.debug(f"Stopping {trigger.name} trigger.")

    # =============================================================================
    def validateDeviceConfigUi(self, values_dict=None, type_id="", dev_id=0):  # noqa
        """
        Title Placeholder

        Body placeholder

        :param indigo.Dict values_dict:
        :param str type_id:
        :param int dev_id:
        :return:
        """
        self.logger.debug("validateDeviceConfigUi")
        error_msg_dict = indigo.Dict()

        # We run the same validations for multiple device types. So we use a values_dict value to
        # determine whether to run these tests.
        if values_dict['isWeatherDevice']:

            # ================================= Latitude ==================================
            try:
                if not -90 <= float(values_dict['latitude']) <= 90:
                    error_msg_dict['latitude'] = "The latitude value must be between -90 and 90."
            except ValueError:
                error_msg_dict['latitude'] = "The latitude value must be between -90 and 90."

            # ================================= Longitude =================================
            try:
                if not -180 <= float(values_dict['longitude']) <= 180:
                    error_msg_dict['longitude'] = (
                        "The longitude value must be between -180 and 180."
                    )
            except ValueError:
                error_msg_dict['longitude'] = "The longitude value must be between -180 and 180."

            if len(error_msg_dict) > 0:
                return False, values_dict, error_msg_dict

        return True, values_dict

    # =============================================================================
    def validateEventConfigUi(self, values_dict=None, type_id="", event_id=0):  # noqa
        """
        Title Placeholder

        Body placeholder

        :param indigo.Dict values_dict:
        :param str type_id:
        :param int event_id:
        :return indigo.Dict values_dict:
        """
        dev_id         = values_dict['list_of_devices']
        error_msg_dict = indigo.Dict()

        # Weather Site Offline trigger
        if type_id == 'weatherSiteOffline':

            self.masterTriggerDict = {
                trigger.pluginProps['listOfDevices']: (trigger.pluginProps['offlineTimer'],
                                                       trigger.id
                                                       )
                for trigger in indigo.triggers.iter(filter="self.weatherSiteOffline")
            }

            # ======================== Validate Trigger Unique ========================
            # Limit weather location offline triggers to one per device
            if dev_id in self.masterTriggerDict and event_id != self.masterTriggerDict[dev_id][1]:
                error_msg_dict['listOfDevices'] = (
                    "Please select a weather device without an existing offline trigger."
                )
                values_dict['listOfDevices'] = ''

            # ============================ Validate Timer =============================
            try:
                if int(values_dict['offlineTimer']) <= 0:
                    error_msg_dict['offlineTimer'] = (
                        "You must enter a valid time value in minutes (positive integer greater "
                        "than zero)."
                    )

            except ValueError:
                error_msg_dict['offlineTimer'] = (
                    "You must enter a valid time value in minutes (positive integer greater than "
                    "zero)."
                )

            if len(error_msg_dict) > 0:
                error_msg_dict['showAlertText'] = (
                    "Configuration Errors\n\nThere are one or more settings that need to be "
                    "corrected. Fields requiring attention will be highlighted."
                )
                return False, values_dict, error_msg_dict

        return True, values_dict

    # =============================================================================
    def validatePrefsConfigUi(self, values_dict=None):  # noqa
        """
        Title Placeholder

        Body placeholder

        :param indigo.Dict values_dict:
        :return bool:
        :return indigo.Dict values_dict:
        """
        api_key_config      = values_dict['apiKey']
        call_counter_config = int(values_dict['callCounter'])
        error_msg_dict      = indigo.Dict()

        # Test api_key_config setting.
        if len(api_key_config) == 0:
            error_msg_dict['apiKey'] = (
                "The plugin requires an API key to function. See help for details."
            )

        elif " " in api_key_config:
            error_msg_dict['apiKey'] = "The API key can't contain a space."

        elif not int(call_counter_config):
            error_msg_dict['callCounter'] = "The call counter can only contain integers."

        elif call_counter_config < 0:
            error_msg_dict['callCounter'] = "The call counter value must be a positive integer."

        if len(error_msg_dict) > 0:
            error_msg_dict['showAlertText'] = (
                "Configuration Errors\n\nThere are one or more settings that need to be corrected. "
                "Fields requiring attention will be highlighted."
            )
            return False, values_dict, error_msg_dict

        return True, values_dict

    # =============================================================================
    # ============================== Plugin Methods ===============================
    # =============================================================================
    def action_refresh_weather(self, values_dict=None):  # noqa
        """
        Refresh all weather as a result of an action call

        The action_refresh_weather() method calls the refresh_weather_data() method to request a
        complete refresh of all weather data (Actions.XML call.)

        :param indigo.Dict values_dict:
        """
        self.logger.debug("Refresh all weather data.")
        self.refresh_weather_data()

    # =============================================================================
    def comms_kill_all(self):
        """
        Disable all plugin devices

        comms_kill_all() sets the enabled status of all plugin devices to false.
        """
        for dev in indigo.devices.iter("self"):
            try:
                indigo.device.enable(dev, value=False)

            except Exception:  # noqa
                self.logger.error("Exception when trying to kill all comms.", exc_info=True)

    # =============================================================================
    def comms_unkill_all(self):
        """
        Enable all plugin devices

        comms_unkill_all() sets the enabled status of all plugin devices to true.
        """
        for dev in indigo.devices.iter("self"):
            try:
                indigo.device.enable(dev, value=True)

            except Exception:  # noqa
                self.logger.error("Exception when trying to unkill all comms.", exc_info=True)

    # =============================================================================
    def dark_sky_site(self, values_dict=None):
        """
        Launch a web browser to register for API

        Launch a web browser session with the values_dict parm containing the target URL.

        :param indigo.Dict values_dict:
        """
        self.browserOpen(values_dict['launchParameters'])

    # =============================================================================
    def dump_the_json(self):
        """
        Dump copy of weather JSON to file

        The dump_the_json() method reaches out to Dark Sky, grabs a copy of the configured JSON
        data and saves it out to a file placed in the Indigo Logs folder. If a weather data log
        exists for that day, it will be replaced. With a new day, a new log file will be created
        (file name contains the date.)
        """
        file_name = (
            f"{indigo.server.getLogsFolderPath()}/{dt.datetime.today().date()} FUWU Plugin.txt"
        )

        try:

            with open(file_name, 'w', encoding="utf-8") as logfile:

                logfile.write("Dark Sky JSON Data\n")
                logfile.write(f"Written at: {dt.datetime.today().strftime('%Y-%m-%d %H:%M')}\n")
                logfile.write(f"{'=' * 72}\n")

                for key in self.masterWeatherDict:
                    logfile.write(f"Location Specified: {key}\n")
                    logfile.write(f"{self.masterWeatherDict[key]}\n\n")

            indigo.server.log(f"Weather data written to: {file_name}")

        except IOError:
            self.logger.error(
                "Unable to write to Indigo Log folder. Check folder permissions", exc_info=True
            )

    # =============================================================================
    def email_forecast(self, dev):
        """
        Email forecast information

        The email_forecast() method will construct and send a summary of select weather information
        to the user based on the email address specified for plugin update notifications.

        :param indigo.Device dev:
        """
        email_body = ""

        try:
            location = (dev.pluginProps['latitude'], dev.pluginProps['longitude'])

            forecast_day   = self.masterWeatherDict[location]['daily']['data'][0]
            summary_wanted = dev.pluginProps.get('weatherSummaryEmail', '')
            summary_sent   = dev.states.get('weatherSummaryEmailSent', False)

            # If it's a new day, reset the email summary sent flag.
            try:
                timestamp     = dev.states['weatherSummaryEmailTimestamp']
                last_sent     = parse(timestamp)
                last_sent_day = last_sent.day

                if last_sent_day != dt.datetime.now().day:
                    dev.updateStateOnServer('weatherSummaryEmailSent', value=False)
                    summary_sent = False
            except ValueError:
                summary_sent = False

            # Get the desired summary email time and convert it for test.
            summary_time = dev.pluginProps.get('weatherSummaryEmailTime', '01:00')
            summary_time = parse(summary_time)

            # Legacy devices had this setting improperly established as a string rather than a bool.
            if isinstance(summary_wanted, str):
                if summary_wanted.lower() == "false":
                    summary_wanted = False
                elif summary_wanted.lower() == "true":
                    summary_wanted = True

            if isinstance(summary_sent, str):
                if summary_sent.lower() == "false":
                    summary_sent = False
                elif summary_sent.lower() == "true":
                    summary_sent = True

            # If an email summary is wanted but not yet sent, and we have
            # reached the desired time of day.
            if summary_wanted and not summary_sent and dt.datetime.now().hour >= summary_time.hour:
                cloud_cover = int(self.nested_lookup(forecast_day, keys=('cloudCover',)) * 100)
                forecast_time = self.nested_lookup(forecast_day, keys=('time',))
                forecast_day_name = time.strftime('%A', time.localtime(float(forecast_time)))
                humidity = int(self.nested_lookup(forecast_day, keys=('humidity',)) * 100)
                long_range_forecast = (
                    self.masterWeatherDict[location]['daily'].get('summary', 'Not available.')
                )
                ozone = int(round(self.nested_lookup(forecast_day, keys=('ozone',))))
                precip_intensity = self.nested_lookup(forecast_day, keys=('precipIntensity',))
                precip_probability = (
                    int(self.nested_lookup(forecast_day, keys=('precipProbability',)) * 100)
                )
                precip_total = precip_intensity * 24
                precip_type = self.nested_lookup(forecast_day, keys=('precipType',))
                pressure = int(round(self.nested_lookup(forecast_day, keys=('pressure',))))
                summary = self.nested_lookup(forecast_day, keys=('summary',))
                temperature_high = (
                    int(round(self.nested_lookup(forecast_day, keys=('temperatureHigh',))))
                )
                temperature_low = (
                    int(round(self.nested_lookup(forecast_day, keys=('temperatureLow',))))
                )
                uv_index = self.nested_lookup(forecast_day, keys=('uvIndex',))
                visibility = self.nested_lookup(forecast_day, keys=('visibility',))
                wind_bearing = self.nested_lookup(forecast_day, keys=('windBearing',))
                wind_gust = int(round(self.nested_lookup(forecast_day, keys=('windGust',))))
                wind_name = self.ui_format_wind_name(val=wind_bearing)
                wind_speed  = int(round(self.nested_lookup(forecast_day, keys=('windSpeed',))))

                # Adjust for when Dark Sky doesn't send a defined precip type.
                if precip_type.lower() == "not available":
                    precip_type = "Precipitation"

                # Heading
                email_body += f"{dev.name}\n"
                email_body += f"{'-' * 38}\n\n"

                # Day
                email_body += f"{forecast_day_name} Forecast:\n"
                email_body += "-" * 38
                email_body += f"{summary}\n\n"

                # Data
                email_body += (
                    f"High: {temperature_high}{dev.pluginProps.get('temperatureUnits', '')}\n"
                )
                email_body += (
                    f"Low: {temperature_low}{dev.pluginProps.get('temperatureUnits', '')}\n"
                )
                percent_units = dev.pluginProps.get('percentageUnits', '')
                email_body += f"Chance of {precip_type}: {precip_probability}{percent_units} \n"
                email_body += (
                    f"Total Precipitation: {precip_total:.2f}"
                    f"{dev.pluginProps.get('rainAmountUnits', '')}\n"
                )
                email_body += (
                    f"Winds out of the {wind_name} at {wind_speed}"
                    f"{dev.pluginProps.get('windUnits', '')} -- gusting to {wind_gust}"
                    f"{dev.pluginProps.get('windUnits', '')}\n"
                )
                email_body += f"Clouds: {cloud_cover}{dev.pluginProps.get('percentageUnits', '')}\n"
                email_body += f"Humidity: {humidity}{dev.pluginProps.get('percentageUnits', '')}\n"
                email_body += f"Ozone: {ozone}{dev.pluginProps.get('indexUnits', '')}\n"
                email_body += f"Pressure: {pressure}{dev.pluginProps.get('pressureUnits', '')}\n"
                email_body += f"UV: {uv_index}{dev.pluginProps.get('pressureUnits', '')}\n"

                # Round visibility to the nearest quarter unit.
                visibility = round(float(visibility) * 4) / 4
                email_body += (f"Visibility: {visibility:0.2f}"
                               f"{dev.pluginProps.get('distanceUnits', '')}\n\n")

                # Long Range Forecast
                email_body += "Long Range Forecast:\n"
                email_body += "-" * 38
                email_body += f"{long_range_forecast}\n\n"

                # Footer
                email_body += "-" * 38
                email_body += (
                    "This email sent at your request on behalf of the Fantastic Weather Plugin for "
                    "Indigo.\n\n*** Powered by Dark Sky ***"
                )

                indigo.server.sendEmailTo(
                    self.pluginPrefs['updaterEmail'],
                    subject="Daily Weather Summary",
                    body=email_body
                )
                dev.updateStateOnServer('weatherSummaryEmailSent', value=True)

                # Set email sent date
                now = dt.datetime.now()
                timestamp = f"{now:%Y-%m-%d}"
                dev.updateStateOnServer('weatherSummaryEmailTimestamp', timestamp)

        except (KeyError, IndexError):
            self.logger.debug(f"Unable to compile forecast data for {dev.name}.", exc_info=True)
            dev.updateStateOnServer('weatherSummaryEmailSent', value=True, uiValue="Err")

        except Exception:  # noqa
            self.logger.error(
                "Unable to send forecast email message. Will keep trying.", exc_info=True
            )

    # =============================================================================
    def fix_corrupted_data(self, val):  # noqa
        """
        Format corrupted and missing data

        Sometimes DS receives corrupted data from personal weather stations. Could be zero, positive
        value or "--" or "-999.0" or "-9999.0". This method tries to "fix" these values for proper
        display.

        :param str or class Float val:
        :return str' or class 'float val:
        """
        try:
            if float(val) < -55.728:  # -99 F = -55.728 C
                reply = -99.0
                reply_str = "--"

            else:
                reply = float(val)
                reply_str = str(reply)

        except (ValueError, TypeError):
            reply = -99.0
            reply_str = "--"

        return reply, reply_str

    # =============================================================================
    def generator_time(self, filter="", values_dict=None, type_id="", target_id=0):  # noqa
        """
        List of hours generator

        Creates a list of times for use in setting the desired time for weather forecast emails to
        be sent.

        :param str filter:
        :param indigo.Dict values_dict:
        :param str type_id:
        :param int target_id:
        :return list:
        """
        return [(f"{hour:02.0f}:00", f"{hour:02.0f}:00") for hour in range(0, 24)]

    # =============================================================================
    def get_satellite_image(self, dev=None):
        """
        Download satellite image and save to file

        The get_satellite_image() method will download a file from a user-specified location and
        save it to a user-specified folder on the local server. This method is used by the Satellite
        Image Downloader device type.

        :param indigo.Device dev:
        """
        destination = dev.pluginProps['imageDestinationLocation']
        source      = dev.pluginProps['imageSourceLocation']

        try:
            if destination.endswith((".gif", ".jpg", ".jpeg", ".png")):

                get_data_time = dt.datetime.now()

                # If requests doesn't work for some reason, revert to urllib.
                try:
                    r = requests.get(source, stream=True, timeout=20)
                    r.raise_for_status()

                    with open(destination, 'wb') as img:
                        for chunk in r.iter_content(2000):
                            img.write(chunk)

                except requests.exceptions.ConnectionError:
                    if not self.inst_attr['comm_error']:
                        self.logger.error("Error downloading satellite image. (No comm.)")
                        self.inst_attr['comm_error'] = True
                    dev.updateStateOnServer('onOffState', value=False, uiValue="No comm")
                    dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)
                    return

                except requests.exceptions.Timeout:
                    self.logger.warning(
                        "Error downloading satellite image (server timeout occurred)."
                    )

                dev.updateStateOnServer('onOffState', value=True, uiValue=" ")
                dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOn)

                # Report results of download timer.
                data_cycle_time = (dt.datetime.now() - get_data_time)
                data_cycle_time = (dt.datetime.min + data_cycle_time).time()
                self.logger.debug(f"Satellite image download time: {data_cycle_time}")

                self.inst_attr['comm_error'] = False
                return

            else:
                self.logger.error(
                    "The image destination must include one of these types (.gif, .jpg, .jpeg, "
                    ".png)"
                )
                dev.updateStateOnServer('onOffState', value=False, uiValue="Bad Type")
                dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)
                return False

        except (
                requests.exceptions.ConnectionError, requests.exceptions.HTTPError,
                requests.exceptions.Timeout, Exception
        ):
            self.inst_attr['comm_error'] = True
            self.logger.error(f"[{dev.name}] Error downloading satellite image.", exc_info=True)
            dev.updateStateOnServer('onOffState', value=False, uiValue="No comm")
            dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)

    # =============================================================================
    def get_weather_data(self, dev=None):
        """
        Reach out to Dark Sky and download data for this location

        Grab the JSON return for the device. A separate call must be made for each weather device
        because the data are location specific.

        :param indigo.Device dev:
        :return class Dict:
        """
        api_key   = self.pluginPrefs['apiKey']
        language  = self.pluginPrefs['language']
        latitude  = dev.pluginProps['latitude']
        longitude = dev.pluginProps['longitude']
        units     = self.pluginPrefs['units']
        location  = (latitude, longitude)
        comm_timeout = 10

        # Get the data and add it to the masterWeatherDict.
        if location not in self.masterWeatherDict:
            source_url = (
                f"https://api.darksky.net/forecast/{api_key}/{latitude},{longitude}?"
                f"exclude='minutely'&extend=''&units={units}&lang={language}"
            )

            # Start download timer.

            get_data_time = dt.datetime.now()

            while True:
                try:
                    r = requests.get(url=source_url, timeout=20)
                    r.raise_for_status()

                    if r.status_code != 200:
                        if r.status_code != 400:
                            self.logger.debug(f"Status Code: {r.status_code}")
                        else:
                            self.logger.warning(
                                "Problem communicating with Dark Sky. This problem can usually "
                                "correct itself, but reloading the plugin can often force a "
                                "repair."
                            )
                            self.logger.debug(f"Bad URL - Status Code: {r.status_code}")
                            raise requests.exceptions.ConnectionError

                    # We convert the file to a json object below, so we don't use requests'
                    # built-in decoder.
                    json_string = r.text
                    self.inst_attr['comm_error'] = False
                    break

                # No connection to Internet, no response from Dark Sky. Let's keep trying.
                except (
                        requests.exceptions.ConnectionError,
                        requests.exceptions.Timeout,
                        requests.exceptions.HTTPError
                ):

                    if comm_timeout < 900:
                        self.logger.warning(
                            f"Unable to make a successful connection to Dark Sky. Retrying in "
                            f"{comm_timeout} seconds."
                        )

                    else:
                        self.logger.warning("Unable to reach Dark Sky. Retrying in 15 minutes.")

                    time.sleep(comm_timeout)

                    # Keep adding 10 seconds to timeout until it reaches one minute.
                    # Then, jack it up to 15 minutes.
                    if comm_timeout < 60:
                        comm_timeout += 10
                    else:
                        comm_timeout = 900

                    self.inst_attr['comm_error'] = True
                    for device in indigo.devices.iter("self"):
                        device.updateStateOnServer("onOffState", value=False, uiValue="No Comm")
                        device.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)

                except Exception:  # noqa
                    self.logger.debug("Error obtaining weather data", exc_info=True)

                # Report results of download timer.
                data_cycle_time = (dt.datetime.now() - get_data_time)
                data_cycle_time = (dt.datetime.min + data_cycle_time).time()
                self.logger.threaddebug(f"Satellite image download time: {data_cycle_time}")

            # Load the JSON data from the file.
            try:
                parsed_json = json.loads(json_string)
                # parsed_json = json.loads(json_string, encoding="utf-8")

            except Exception:  # noqa
                self.logger.error("Unable to decode data.", exc_info=True)
                parsed_json = {}

            # Add location JSON to master weather dictionary.
            self.masterWeatherDict[location] = parsed_json

            # Increment the call counter
            self.pluginPrefs['dailyCallCounter'] = r.headers.get('X-Forecast-API-Calls', -1)

            # We've been successful, mark device online
            self.inst_attr['comm_error'] = False
            dev.updateStateOnServer('onOffState', value=True)

        # We could have come here from several places. Return to whence we came
        # to further process the weather data.
        self.inst_attr['ds_online'] = True
        return self.masterWeatherDict

    # =============================================================================
    def list_of_devices(self, filter="", values_dict=None, target_id="", trigger_id=0):  # noqa
        """
        Generate list of devices for offline trigger

        list_of_devices returns a list of plugin devices limited to weather devices only (not
        forecast devices, etc.) when the Weather Location Offline trigger is fired.

        :param str filter:
        :param indigo.Dict values_dict:
        :param str target_id:
        :param int trigger_id:
        :return list:
        """
        return self.Fogbert.deviceList(dev_filter='self')

    # =============================================================================
    def list_of_weather_devices(
            self, filter="", values_dict=None, target_id="", trigger_id=0  # noqa
    ):
        """
        Generate list of devices for severe weather alert trigger

        list_of_weather_devices returns a list of plugin devices limited to weather devices only
        (not forecast devices, etc.) when severe weather alert trigger is fired.

        :param str filter:
        :param indigo.Dict values_dict:
        :param str target_id:
        :param int trigger_id:
        :return list:
        """
        return self.Fogbert.deviceList(dev_filter='self.Weather')

    # =============================================================================
    def nested_lookup(self, obj=None, keys=None, default="Not available"):  # noqa
        """
        Do a nested lookup of the DS JSON

        The nested_lookup() method is used to extract the relevant data from the JSON return. The
        JSON is known to be inconsistent in the form of sometimes missing keys. This method allows
        for a default value to be used in instances where a key is missing. The method call can
        rely on the default return, or send an optional 'default=some_value' parameter. Dark Sky
        says that there are times when they won't send a key (for example, if they don't have data)
        so this is to be expected.

        Credit: Jared Goguen at StackOverflow for initial implementation.

        :param class dict obj:
        :param class list keys:
        :param str default:
        :return dict:
        """
        current = obj

        for key in keys:
            current = current if isinstance(current, list) else [current]

            try:
                current = next(sub[key] for sub in current if key in sub)

            except StopIteration:
                return default

        return current

    # =============================================================================
    def parse_alerts_data(self, dev=None):
        """
        Parse alerts data to devices

        The parse_alerts_data() method takes weather alert data and parses it to device states. This
        segment iterates through all available alert information. It retains only the first five
        alerts. We set all alerts to an empty string each time, and then repopulate (this clears out
        alerts that may have expired.) If there are no alerts, set alert status to false.

        :param indigo.Device dev:
        """
        alerts_states_list = []  # Alerts_states_list needs to be a list.

        try:
            alert_array = []
            # Whether to log alerts
            alerts_logging    = self.pluginPrefs.get('alertLogging', True)
            # Suppress alert messages for dev
            alerts_suppressed = dev.pluginProps.get('suppressWeatherAlerts', False)
            # Suppress 'No Alert' messages
            no_alerts_logging  = self.pluginPrefs.get('noAlertLogging', False)

            location     = (dev.pluginProps['latitude'], dev.pluginProps['longitude'])
            weather_data = self.masterWeatherDict[location]
            alerts_data  = self.nested_lookup(obj=weather_data, keys=('alerts',))
            preferred_time = dev.pluginProps.get('time_zone', 'time_here')
            timezone = pytz.timezone(weather_data['timezone'])

            # ============================= Delete Old Alerts =============================
            for alert_counter in range(1, 6):
                for state in ('alertDescription', 'alertExpires', 'alertRegions', 'alertSeverity',
                              'alertTime', 'alertTime', 'alertTitle', 'alertUri'
                              ):
                    alerts_states_list.append(
                        {'key': f"{state}{alert_counter}", 'value': " ", 'uiValue': " "}
                    )

            # ================================= No Alerts =================================
            if alerts_data == "Not available":
                alerts_states_list.append(
                    {'key': 'alertStatus', 'value': False, 'uiValue': "False"}
                )

                if alerts_logging and not no_alerts_logging and not alerts_suppressed:
                    self.logger.info(f"{dev.name} There are no severe weather alerts.")

            # ============================ At Least One Alert =============================
            else:
                alerts_states_list.append({'key': 'alertStatus', 'value': True, 'uiValue': "True"})

                for alert in alerts_data:

                    alert_tuple = (
                        alert.get('description', "Not provided.").strip(),
                        alert.get('expires', "Not provided."),
                        alert.get('regions', "Not provided."),
                        alert.get('severity', "Not provided."),
                        alert.get('time', "Not provided."),
                        alert.get('title', "Not provided.").strip(),
                        alert.get('uri', "Not provided."),
                    )

                    alert_array.append(alert_tuple)

                if len(alert_array) == 1:
                    # If user has enabled alert logging, write alert message to the Indigo log.
                    if alerts_logging and not alerts_suppressed:
                        self.logger.info(f"{dev.name}: There is 1 severe weather alert.")
                else:
                    # If user has enabled alert logging, write alert message to the Indigo log.
                    if alerts_logging and not alerts_suppressed and 0 < len(alert_array) <= 5:
                        self.logger.info(
                            f"{dev.name}: There are {len(alert_array)} severe weather alerts."
                        )

                    # If user has enabled alert logging, write alert message to the Indigo log.
                    if alerts_logging and not alerts_suppressed and len(alert_array) > 5:
                        self.logger.info(
                            f"{dev.name}: The plugin only retains information for the first 5 "
                            f"alerts."
                        )

                alert_counter = 1
                for alert in range(len(alert_array)):
                    if alert_counter <= 5:

                        # Convert epoch times to human friendly values

                        # ========================== Effective / Expires ===========================
                        # Local Time (server timezone)
                        if preferred_time == "time_here":

                            alert_effective_time = time.localtime(int(alert_array[alert][4]))
                            alert_time    = time.strftime('%Y-%m-%d %H:%M', alert_effective_time)
                            alerts_states_list.append(
                                {'key': f"alertTime{alert_counter}", 'value': f"{alert_time}"}
                            )

                            alert_expires_time = time.localtime(int(alert_array[alert][1]))
                            alert_expires = time.strftime('%Y-%m-%d %H:%M', alert_expires_time)
                            alerts_states_list.append(
                                {'key': f"alertExpires{alert_counter}", 'value': f"{alert_expires}"}
                            )

                        # Location Time (location timezone)
                        elif preferred_time == "time_there":

                            alert_effective_time = dt.datetime.fromtimestamp(
                                int(alert_array[alert][4]), tz=pytz.utc
                            )
                            alert_effective_time = timezone.normalize(alert_effective_time)
                            alert_time = time.strftime(
                                f"{self.inst_attr['date_format']} {self.inst_attr['time_format']}",
                                alert_effective_time.timetuple()
                            )
                            alerts_states_list.append(
                                {'key': f"alertTime{alert_counter}", 'value': f"{alert_time}"}
                            )

                            alert_expires_time = dt.datetime.fromtimestamp(
                                int(alert_array[alert][1]), tz=pytz.utc
                            )
                            alert_expires_time = timezone.normalize(alert_expires_time)
                            alert_expires = time.strftime(
                                f"{self.inst_attr['date_format']} {self.inst_attr['time_format']}",
                                alert_expires_time.timetuple()
                            )
                            alerts_states_list.append(
                                {'key': f"alertExpires{alert_counter}", 'value': f"{alert_expires}"}
                            )

                        # ============================== Alert Info ================================

                        alerts_states_list.append(
                            {'key': f"alertDescription{alert_counter}",
                             'value': f"{alert_array[alert][0]}"
                             }
                        )
                        alerts_states_list.append(
                            {'key': f"alertRegions{alert_counter}",
                             'value': f"{alert_array[alert][2]}"
                             }
                        )
                        alerts_states_list.append(
                            {'key': f"alertSeverity{alert_counter}",
                             'value': f"{alert_array[alert][3]}"
                             }
                        )
                        alerts_states_list.append(
                            {'key': f"alertTitle{alert_counter}",
                             'value': f"{alert_array[alert][5]}"
                             }
                        )
                        alerts_states_list.append(
                            {'key': f"alertUri{alert_counter}",
                             'value': f"{alert_array[alert][6]}"
                             }
                        )
                        alert_counter += 1

                    # Write alert to the log?
                    if alerts_logging and not alerts_suppressed:
                        alert_text = textwrap.wrap(alert_array[alert][0], 120)
                        alert_text_wrapped = ""
                        for _ in alert_text:
                            alert_text_wrapped += f"{_}\n"

                        self.logger.info(f"\n{alert_text_wrapped}")

            alerts_states_list.append({'key': 'alertCount', 'value': len(alert_array)})
            dev.updateStatesOnServer(alerts_states_list)

        except Exception:  # noqa
            self.logger.error("Problem parsing weather alert data.", exc_info=True)
            alerts_states_list.append({'key': 'onOffState', 'value': False, 'uiValue': " "})
            dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)

    # =============================================================================
    def parse_astronomy_data(self, dev=None):
        """
        Parse astronomy data to devices

        The parse_astronomy_data() method takes astronomy data and parses it to device states. See
        Dark Sky API for value meaning.

        :param indigo.Device dev:
        """
        astronomy_states_list = []

        try:
            location       = (dev.pluginProps['latitude'], dev.pluginProps['longitude'])
            weather_data   = self.masterWeatherDict[location]
            astronomy_data = weather_data['daily']['data']
            preferred_time = dev.pluginProps.get('time_zone', 'time_here')
            timezone = pytz.timezone(zone=weather_data['timezone'])

            epoch      = self.nested_lookup(obj=weather_data, keys=('currently', 'time'))
            sun_rise   = self.nested_lookup(obj=astronomy_data, keys=('sunriseTime',))
            sun_set    = self.nested_lookup(obj=astronomy_data, keys=('sunsetTime',))
            moon_phase = float(self.nested_lookup(obj=astronomy_data, keys=('moonPhase',)))

            # ============================= Observation Epoch =============================
            current_observation_epoch = int(epoch)
            astronomy_states_list.append(
                {'key': 'currentObservationEpoch', 'value': current_observation_epoch}
            )

            # ============================= Observation Time ==============================
            last_upd = time.strftime(
                '%b %d, %H:%M %p %z', time.localtime(current_observation_epoch)
            )
            current_observation_time = f"Last updated on {last_upd}"
            astronomy_states_list.append(
                {'key': 'currentObservation', 'value': current_observation_time}
            )

            # ============================= Observation 24hr ==============================
            curr_obs = time.localtime(current_observation_epoch)
            current_observation_24hr = time.strftime(
                f"{self.inst_attr['date_format']} {self.inst_attr['time_format']}", curr_obs
            )
            astronomy_states_list.append(
                {'key': 'currentObservation24hr', 'value': current_observation_24hr}
            )

            # ============================= Sunrise / Sunset ==============================
            # Local Time (server timezone)
            if preferred_time == "time_here":

                sunrise_local = time.localtime(int(sun_rise))
                sunrise_local = time.strftime(
                    f"{self.inst_attr['date_format']} "
                    f"{self.inst_attr['time_format']}",
                    sunrise_local
                )
                astronomy_states_list.append({'key': 'sunriseTime', 'value': sunrise_local})
                astronomy_states_list.append(
                    {'key': 'sunriseTimeShort', 'value': sunrise_local[11:16]}
                )

                sunset_local  = time.localtime(int(sun_set))
                sunset_local = time.strftime(
                    f"{self.inst_attr['date_format']} "
                    f"{self.inst_attr['time_format']}",
                    sunset_local
                )
                astronomy_states_list.append({'key': 'sunsetTime', 'value': sunset_local})
                astronomy_states_list.append(
                    {'key': 'sunsetTimeShort', 'value': sunset_local[11:16]}
                )

            # Location Time (location timezone)
            elif preferred_time == "time_there":
                sunrise_aware = dt.datetime.fromtimestamp(int(sun_rise), tz=pytz.utc)
                sunset_aware  = dt.datetime.fromtimestamp(int(sun_set), tz=pytz.utc)

                sunrise_normal = timezone.normalize(dt=sunrise_aware)
                sunset_normal  = timezone.normalize(dt=sunset_aware)

                sunrise_local = time.strftime(
                    f"{self.inst_attr['date_format']} "
                    f"{self.inst_attr['time_format']}",
                    sunrise_normal.timetuple()
                )
                astronomy_states_list.append({'key': 'sunriseTime', 'value': sunrise_local})
                astronomy_states_list.append(
                    {'key': 'sunriseTimeShort', 'value': sunrise_local[11:16]}
                )

                sunset_local = time.strftime(
                    f"{self.inst_attr['date_format']} "
                    f"{self.inst_attr['time_format']}",
                    sunset_normal.timetuple()
                )
                astronomy_states_list.append({'key': 'sunsetTime', 'value': sunset_local})
                astronomy_states_list.append(
                    {'key': 'sunsetTimeShort', 'value': sunset_local[11:16]}
                )

            # ================================ Moon Phase =================================
            # Float
            moon_phase_new, moon_phase_ui = self.fix_corrupted_data(val=moon_phase * 100)
            moon_phase_ui = self.ui_format_percentage(dev=dev, val=moon_phase_ui)
            astronomy_states_list.append(
                {'key': 'moonPhase', 'value': moon_phase_new, 'uiValue': moon_phase_ui}
            )

            # ============================== Moon Phase Icon ==============================
            # Integer
            moon_phase_icon, moon_phase_icon_ui = self.fix_corrupted_data(val=int(moon_phase_new))
            moon_phase_icon_ui = self.ui_format_percentage(dev=dev, val=moon_phase_icon_ui)
            astronomy_states_list.append(
                {'key': 'moonPhaseIcon', 'value': moon_phase_icon, 'uiValue': moon_phase_icon_ui}
            )

            # ============================== Moon Phase Name ==============================
            # String
            #
            # moonPhase optional, only on daily
            # The fractional part of the lunation number during the given day: a value of 0
            # corresponds to a new moon, 0.25 to a first quarter moon, 0.5 to a full moon, and 0.75
            # to a last quarter moon. (The ranges in between these represent waxing crescent, waxing
            # gibbous, waning gibbous, and waning crescent moons, respectively.)
            # Sources: https://darksky.net/dev/docs and
            # https://en.wikipedia.org/wiki/Lunar_phase#Phases_of_the_Moon

            criteria = {
                'New': moon_phase == 0,
                'Waxing Crescent': 0 < moon_phase < .25,
                'First Quarter': moon_phase == .25,
                'Waxing Gibbous': .25 < moon_phase < .50,
                'Full': moon_phase == .50,
                'Waning Gibbous': .50 < moon_phase < .75,
                'Last Quarter': moon_phase == .75,
                'Waning Crescent': .75 < moon_phase,
            }

            for k, v in criteria.items():
                if v:
                    astronomy_states_list.append({'key': 'moonPhaseName', 'value': k})
                    break
                else:
                    astronomy_states_list.append({'key': 'moonPhaseName', 'value': "Unknown"})

            new_props = dev.pluginProps
            _lat = float(dev.pluginProps.get('latitude', 'lat'))
            _long = float(dev.pluginProps.get('longitude', 'long'))
            new_props['address'] = f"{_lat:.5f}, {_long:.5f}"
            dev.replacePluginPropsOnServer(new_props)

            astronomy_states_list.append({'key': 'onOffState', 'value': True, 'uiValue': " "})

            dev.updateStatesOnServer(astronomy_states_list)
            dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOn)

        except Exception:  # noqa
            self.logger.error("Problem parsing astronomy data.", exc_info=True)
            dev.updateStateOnServer('onOffState', value=False, uiValue=" ")
            dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)

    # =============================================================================
    def parse_hourly_forecast_data(self, dev=None):
        """
        Parse hourly forecast data to devices

        The parse_hourly_forecast_data() method takes hourly weather forecast data and parses it to
        device states. See Dark Sky API for value meaning.

        :param indigo.Device dev:
        """
        hourly_forecast_states_list = []

        try:
            hour_temp      = 0
            location       = (dev.pluginProps['latitude'], dev.pluginProps['longitude'])
            weather_data   = self.masterWeatherDict[location]
            forecast_data  = weather_data['hourly']['data']
            preferred_time = dev.pluginProps.get('time_zone', 'time_here')
            timezone       = pytz.timezone(zone=weather_data['timezone'])

            # ============================== Hourly Summary ===============================
            hourly_forecast_states_list.append(
                {'key': 'hourly_summary',
                 'value': self.masterWeatherDict[location]['hourly']['summary']
                 }
            )

            # ============================= Observation Epoch =============================
            current_observation_epoch = (
                int(self.nested_lookup(weather_data, keys=('currently', 'time')))
            )
            hourly_forecast_states_list.append(
                {'key': 'currentObservationEpoch', 'value': current_observation_epoch}
            )

            # ============================= Observation Time ==============================
            obs_time = time.strftime(
                '%b %d, %H:%M %p %z', time.localtime(current_observation_epoch)
            )
            hourly_forecast_states_list.append(
                {'key': 'currentObservation', 'value': f"Last updated on {obs_time}"}
            )

            # ============================= Observation 24hr ==============================
            epoch_24hr = time.localtime(current_observation_epoch)
            current_observation_24hr = time.strftime(
                f"{self.inst_attr['date_format']} {self.inst_attr['time_format']}", epoch_24hr
            )
            hourly_forecast_states_list.append(
                {'key': 'currentObservation24hr', 'value': current_observation_24hr}
            )

            forecast_counter = 1
            for observation in forecast_data:

                if forecast_counter <= 24:

                    cloud_cover        = self.nested_lookup(observation, keys=('cloudCover',))
                    forecast_time      = self.nested_lookup(observation, keys=('time',))
                    humidity           = self.nested_lookup(observation, keys=('humidity',))
                    icon               = self.nested_lookup(observation, keys=('icon',))
                    ozone              = self.nested_lookup(observation, keys=('ozone',))
                    precip_intensity   = self.nested_lookup(observation, keys=('precipIntensity',))
                    precip_probability = (
                        self.nested_lookup(observation, keys=('precipProbability',))
                    )
                    precip_type  = self.nested_lookup(observation, keys=('precipType',))
                    pressure     = self.nested_lookup(observation, keys=('pressure',))
                    summary      = self.nested_lookup(observation, keys=('summary',))
                    temperature  = self.nested_lookup(observation, keys=('temperature',))
                    uv_index     = self.nested_lookup(observation, keys=('uvIndex',))
                    visibility   = self.nested_lookup(observation, keys=('visibility',))
                    wind_bearing = self.nested_lookup(observation, keys=('windBearing',))
                    wind_gust    = self.nested_lookup(observation, keys=('windGust',))
                    wind_speed   = self.nested_lookup(observation, keys=('windSpeed',))

                    # Add leading zero to counter value for device state names 1-9.
                    if forecast_counter < 10:
                        fore_counter_text = f"0{forecast_counter}"
                    else:
                        fore_counter_text = forecast_counter

                    # ========================= Forecast Day, Epoch, Hour =========================
                    # Local Time (server timezone)
                    if preferred_time == "time_here":
                        local_time       = time.localtime(float(forecast_time))

                        forecast_day_long  = time.strftime('%A', local_time)
                        forecast_day_short = time.strftime('%a', local_time)
                        forecast_hour      = time.strftime('%H:%M', local_time)
                        forecast_hour_ui   = (
                            time.strftime(self.inst_attr['time_format'], local_time)
                        )

                        hourly_forecast_states_list.append(
                            {'key': f"h{fore_counter_text}_day",
                             'value': forecast_day_long,
                             'uiValue': forecast_day_long
                             }
                        )
                        hourly_forecast_states_list.append(
                            {'key': f"h{fore_counter_text}_day_short",
                             'value': forecast_day_short,
                             'uiValue': forecast_day_short
                             }
                        )
                        hourly_forecast_states_list.append(
                            {'key': f"h{fore_counter_text}_epoch",
                             'value': forecast_time
                             }
                        )
                        hourly_forecast_states_list.append(
                            {'key': f"h{fore_counter_text}_hour",
                             'value': forecast_hour,
                             'uiValue': forecast_hour_ui
                             }
                        )

                    # Location Time (location timezone)
                    elif preferred_time == "time_there":
                        aware_time = dt.datetime.fromtimestamp(int(forecast_time), tz=pytz.utc)

                        forecast_day_long  = timezone.normalize(aware_time).strftime("%A")
                        forecast_day_short = timezone.normalize(aware_time).strftime("%a")
                        forecast_hour      = timezone.normalize(aware_time).strftime("%H:%M")
                        forecast_hour_ui   = time.strftime(
                            self.inst_attr['time_format'],
                            timezone.normalize(aware_time).timetuple()
                        )

                        zone = dt.datetime.fromtimestamp(forecast_time, timezone)
                        zone_tuple = zone.timetuple()              # tuple
                        zone_posix = int(time.mktime(zone_tuple))  # timezone timestamp

                        hourly_forecast_states_list.append(
                            {'key': f"h{fore_counter_text}_day",
                             'value': forecast_day_long,
                             'uiValue': forecast_day_long
                             }
                        )
                        hourly_forecast_states_list.append(
                            {'key': f"h{fore_counter_text}_day_short",
                             'value': forecast_day_short,
                             'uiValue': forecast_day_short
                             }
                        )
                        hourly_forecast_states_list.append(
                            {'key': f"h{fore_counter_text}_epoch",
                             'value': zone_posix
                             }
                        )
                        hourly_forecast_states_list.append(
                            {'key': f"h{fore_counter_text}_hour",
                             'value': forecast_hour,
                             'uiValue': forecast_hour_ui
                             }
                        )

                    # ================================ Cloud Cover ================================
                    cloud_cover, cloud_cover_ui = self.fix_corrupted_data(val=cloud_cover * 100)
                    cloud_cover_ui = self.ui_format_percentage(dev=dev, val=cloud_cover_ui)
                    hourly_forecast_states_list.append(
                        {'key': f"h{fore_counter_text}_cloudCover",
                         'value': cloud_cover,
                         'uiValue': cloud_cover_ui
                         }
                    )

                    # ================================= Humidity ==================================
                    humidity, humidity_ui = self.fix_corrupted_data(val=humidity * 100)
                    humidity_ui = self.ui_format_percentage(dev=dev, val=humidity_ui)
                    hourly_forecast_states_list.append(
                        {'key': f"h{fore_counter_text}_humidity",
                         'value': humidity,
                         'uiValue': humidity_ui
                         }
                    )

                    # ============================= Precip Intensity ==============================
                    precip_intensity, precip_intensity_ui = (
                        self.fix_corrupted_data(val=precip_intensity)
                    )
                    precip_intensity_ui = self.ui_format_rain(dev=dev, val=precip_intensity_ui)
                    hourly_forecast_states_list.append(
                        {'key': f"h{fore_counter_text}_precipIntensity",
                         'value': precip_intensity,
                         'uiValue': precip_intensity_ui
                         }
                    )

                    # ============================ Precip Probability =============================
                    precip_probability, precip_probability_ui = (
                        self.fix_corrupted_data(val=precip_probability * 100)
                    )
                    precip_probability_ui = (
                        self.ui_format_percentage(dev=dev, val=precip_probability_ui)
                    )
                    hourly_forecast_states_list.append(
                        {'key': f"h{fore_counter_text}_precipChance",
                         'value': precip_probability,
                         'uiValue': precip_probability_ui
                         }
                    )

                    # =================================== Icon ====================================
                    hourly_forecast_states_list.append(
                        {'key': f"h{fore_counter_text}_icon", 'value': f"{icon.replace('-', '_')}"}
                    )

                    # =================================== Ozone ===================================
                    ozone, ozone_ui = self.fix_corrupted_data(val=ozone)
                    ozone_ui = self.ui_format_index(dev, val=ozone_ui)
                    hourly_forecast_states_list.append(
                        {'key': f"h{fore_counter_text}_ozone", 'value': ozone, 'uiValue': ozone_ui}
                    )

                    # ================================ Precip Type ================================
                    hourly_forecast_states_list.append(
                        {'key': f"h{fore_counter_text}_precipType", 'value': precip_type}
                    )

                    # ================================= Pressure ==================================
                    pressure, pressure_ui = self.fix_corrupted_data(val=pressure)
                    pressure_ui = self.ui_format_pressure(dev=dev, val=pressure_ui)
                    hourly_forecast_states_list.append(
                        {'key': f"h{fore_counter_text}_pressure",
                         'value': pressure,
                         'uiValue': pressure_ui
                         }
                    )

                    # ================================== Summary ==================================
                    hourly_forecast_states_list.append(
                        {'key': f"h{fore_counter_text}_summary", 'value': summary}
                    )

                    # ================================ Temperature ================================
                    temperature, temperature_ui = self.fix_corrupted_data(val=temperature)
                    temperature_ui = self.ui_format_temperature(dev=dev, val=temperature_ui)
                    hourly_forecast_states_list.append(
                        {'key': f"h{fore_counter_text}_temperature",
                         'value': temperature,
                         'uiValue': temperature_ui
                         }
                    )

                    if forecast_counter == int(dev.pluginProps.get('ui_display', '1')):
                        hour_temp = round(temperature)

                    # ================================= UV Index ==================================
                    uv_index, uv_index_ui = self.fix_corrupted_data(val=uv_index)
                    uv_index_ui = self.ui_format_index(dev, val=uv_index_ui)
                    hourly_forecast_states_list.append(
                        {'key': f"h{fore_counter_text}_uvIndex",
                         'value': uv_index,
                         'uiValue': uv_index_ui
                         }
                    )

                    # =============================== Wind Bearing ================================
                    wind_bearing, wind_bearing_ui = self.fix_corrupted_data(val=wind_bearing)
                    # We don't need fractional wind speed values for the UI, so we try to fix that
                    # here.  However, sometimes it comes through as "--" so we need to account for
                    # that, too.
                    try:
                        int(float(wind_bearing_ui))
                    except ValueError:
                        pass
                    hourly_forecast_states_list.append(
                        {'key': f"h{fore_counter_text}_windBearing",
                         'value': wind_bearing,
                         'uiValue': wind_bearing_ui
                         }
                    )

                    # ============================= Wind Bearing Name =============================
                    hourly_forecast_states_list.append(
                        {'key': f"h{fore_counter_text}_windBearingName",
                         'value': self.ui_format_wind_name(val=wind_bearing)
                         }
                    )

                    # ================================= Wind Gust =================================
                    wind_gust, wind_gust_ui = self.fix_corrupted_data(val=wind_gust)
                    wind_gust_ui = self.ui_format_wind(dev=dev, val=wind_gust_ui)
                    hourly_forecast_states_list.append(
                        {'key': f"h{fore_counter_text}_windGust",
                         'value': wind_gust,
                         'uiValue': wind_gust_ui
                         }
                    )

                    # ================================ Wind Speed =================================
                    wind_speed, wind_speed_ui = self.fix_corrupted_data(val=wind_speed)
                    wind_speed_ui = self.ui_format_wind(dev=dev, val=wind_speed_ui)
                    hourly_forecast_states_list.append(
                        {'key': f"h{fore_counter_text}_windSpeed",
                         'value': wind_speed,
                         'uiValue': wind_speed_ui
                         }
                    )

                    # ================================ Visibility =================================
                    visibility, visibility_ui = self.fix_corrupted_data(val=visibility)
                    visibility_ui = self.ui_format_distance(dev, val=visibility_ui)
                    hourly_forecast_states_list.append(
                        {'key': f"h{fore_counter_text}_visibility",
                         'value': visibility,
                         'uiValue': visibility_ui
                         }
                    )

                    forecast_counter += 1

            new_props = dev.pluginProps
            _lat = float(dev.pluginProps.get('latitude', 'lat'))
            _long = float(dev.pluginProps.get('longitude', 'long'))
            new_props['address'] = f"{_lat:.5f}, {_long:.5f}"
            dev.replacePluginPropsOnServer(new_props)

            display_value = f"{int(hour_temp)}{dev.pluginProps['temperatureUnits']}"
            hourly_forecast_states_list.append(
                {'key': 'onOffState',
                 'value': True,
                 'uiValue': display_value
                 }
            )

            dev.updateStatesOnServer(hourly_forecast_states_list)
            dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOn)

        except Exception:  # noqa
            self.logger.error("Problem parsing hourly forecast data.", exc_info=True)
            hourly_forecast_states_list.append(
                {'key': 'onOffState', 'value': False, 'uiValue': " "}
            )
            dev.updateStatesOnServer(hourly_forecast_states_list)
            dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)

    # =============================================================================
    def parse_daily_forecast_data(self, dev=None):
        """
        Parse 10-day forecast data to devices

        The parse_daily_forecast_data() method takes 10-day forecast data and parses it to device
        states. See Dark Sky API for value meaning.

        :param indigo.Device dev:
        """
        daily_forecast_states_list = []

        try:
            location      = (dev.pluginProps['latitude'], dev.pluginProps['longitude'])
            weather_data  = self.masterWeatherDict[location]
            forecast_date = self.masterWeatherDict[location]['daily']['data']
            timezone      = pytz.timezone(zone=weather_data['timezone'])
            today_high    = 0
            today_low     = 0

            # =============================== Daily Summary ===============================
            current_summary = self.nested_lookup(weather_data, keys=('daily', 'summary'))
            daily_forecast_states_list.append({'key': 'daily_summary', 'value': current_summary})

            # ============================= Observation Epoch =============================
            current_observation_epoch = self.nested_lookup(weather_data, keys=('currently', 'time'))
            daily_forecast_states_list.append(
                {'key': 'currentObservationEpoch',
                 'value': current_observation_epoch,
                 'uiValue': current_observation_epoch
                 }
            )

            # ============================= Observation Time ==============================
            curr_obs = time.strftime(
                '%b %d, %H:%M %p %z', time.localtime(current_observation_epoch)
            )
            current_observation_time = f"Last updated on {curr_obs}"
            daily_forecast_states_list.append(
                {'key': 'currentObservation',
                 'value': current_observation_time,
                 'uiValue': current_observation_time
                 }
            )

            # ============================= Observation 24hr ==============================
            curr_obs_24 = time.localtime(float(current_observation_epoch))
            current_observation_24hr = time.strftime(
                f"{self.inst_attr['date_format']} "
                f"{self.inst_attr['time_format']}",
                curr_obs_24
            )
            daily_forecast_states_list.append(
                {'key': 'currentObservation24hr', 'value': current_observation_24hr}
            )

            forecast_counter = 1
            for observation in forecast_date:
                cloud_cover        = self.nested_lookup(obj=observation, keys=('cloudCover',))
                forecast_time      = self.nested_lookup(obj=observation, keys=('time',))
                humidity           = self.nested_lookup(obj=observation, keys=('humidity',))
                icon               = self.nested_lookup(obj=observation, keys=('icon',))
                ozone              = self.nested_lookup(obj=observation, keys=('ozone',))
                precip_probability = (
                    self.nested_lookup(obj=observation, keys=('precipProbability',))
                )
                precip_intensity   = self.nested_lookup(obj=observation, keys=('precipIntensity',))
                precip_type        = self.nested_lookup(obj=observation, keys=('precipType',))
                pressure           = self.nested_lookup(obj=observation, keys=('pressure',))
                summary            = self.nested_lookup(obj=observation, keys=('summary',))
                temperature_high   = self.nested_lookup(obj=observation, keys=('temperatureHigh',))
                temperature_low    = self.nested_lookup(obj=observation, keys=('temperatureLow',))
                uv_index           = self.nested_lookup(obj=observation, keys=('uvIndex',))
                visibility         = self.nested_lookup(obj=observation, keys=('visibility',))
                wind_bearing       = self.nested_lookup(obj=observation, keys=('windBearing',))
                wind_gust          = self.nested_lookup(obj=observation, keys=('windGust',))
                wind_speed         = self.nested_lookup(obj=observation, keys=('windSpeed',))

                if forecast_counter <= 8:

                    # Add leading zero to counter value for device state names 1-9. Although Dark
                    # Sky only provides 8 days of data at this time, if it should decide to
                    # increase that, this will provide for proper sorting of states.
                    if forecast_counter < 10:
                        fore_counter_text = f"0{forecast_counter}"
                    else:
                        fore_counter_text = forecast_counter

                    # ================================ Cloud Cover ================================
                    cloud_cover, cloud_cover_ui = self.fix_corrupted_data(val=cloud_cover * 100)
                    cloud_cover_ui = self.ui_format_percentage(dev=dev, val=cloud_cover_ui)
                    daily_forecast_states_list.append(
                        {'key': f"d{fore_counter_text}_cloudCover",
                         'value': cloud_cover,
                         'uiValue': cloud_cover_ui
                         }
                    )

                    # =========================== Forecast Date and Day ===========================
                    # We set the daily stuff to the location timezone regardless, because the
                    # timestamp from DS is always 00:00 localized. If we set it using the server
                    # timezone, it may display the wrong day if the location is ahead of where we
                    # are.
                    aware_time         = dt.datetime.fromtimestamp(int(forecast_time), tz=pytz.utc)
                    forecast_date      = timezone.normalize(aware_time).strftime('%Y-%m-%d')
                    forecast_day_long  = timezone.normalize(aware_time).strftime("%A")
                    forecast_day_short = timezone.normalize(aware_time).strftime("%a")

                    daily_forecast_states_list.append(
                        {'key': f"d{fore_counter_text}_date",
                         'value': forecast_date,
                         'uiValue': forecast_date
                         }
                    )
                    daily_forecast_states_list.append(
                        {'key': f"d{fore_counter_text}_day",
                         'value': forecast_day_long,
                         'uiValue': forecast_day_long
                         }
                    )
                    daily_forecast_states_list.append(
                        {'key': f"d{fore_counter_text}_day_short",
                         'value': forecast_day_short,
                         'uiValue': forecast_day_short
                         }
                    )

                    # ================================= Humidity ==================================
                    humidity, humidity_ui = self.fix_corrupted_data(val=humidity * 100)
                    humidity_ui = self.ui_format_percentage(dev=dev, val=humidity_ui)
                    daily_forecast_states_list.append(
                        {'key': f"d{fore_counter_text}_humidity",
                         'value': humidity,
                         'uiValue': humidity_ui
                         }
                    )

                    # =================================== Icon ====================================
                    daily_forecast_states_list.append(
                        {'key': f"d{fore_counter_text}_icon", 'value': f"{icon.replace('-', '_')}"}
                    )

                    # =================================== Ozone ===================================
                    ozone, ozone_ui = self.fix_corrupted_data(val=ozone)
                    ozone_ui = self.ui_format_index(dev, val=ozone_ui)
                    daily_forecast_states_list.append(
                        {'key': f"d{fore_counter_text}_ozone",
                         'value': ozone,
                         'uiValue': ozone_ui
                         }
                    )

                    # ============================= Precip Intensity ==============================
                    precip_intensity, precip_intensity_ui = (
                        self.fix_corrupted_data(val=precip_intensity)
                    )
                    precip_intensity_ui = self.ui_format_rain(dev=dev, val=precip_intensity_ui)
                    daily_forecast_states_list.append(
                        {'key': f"d{fore_counter_text}_precipIntensity",
                         'value': precip_intensity,
                         'uiValue': precip_intensity_ui
                         }
                    )

                    # ============================ Precip Probability =============================
                    precip_probability, precip_probability_ui = (
                        self.fix_corrupted_data(val=precip_probability * 100)
                    )
                    precip_probability_ui = self.ui_format_percentage(
                        dev=dev, val=precip_probability_ui
                    )
                    daily_forecast_states_list.append(
                        {'key': f"d{fore_counter_text}_precipChance",
                         'value': precip_probability,
                         'uiValue': precip_probability_ui
                         }
                    )

                    # ================================ Precip Total ===============================
                    precip_total = precip_intensity * 24
                    precip_total_ui = self.ui_format_rain(dev, val=precip_total)
                    daily_forecast_states_list.append(
                        {'key': f"d{fore_counter_text}_precipTotal",
                         'value': precip_total,
                         'uiValue': precip_total_ui
                         }
                    )

                    # ================================ Precip Type ================================
                    daily_forecast_states_list.append(
                        {'key': f"d{fore_counter_text}_precipType", 'value': precip_type}
                    )

                    # ================================= Pressure ==================================
                    pressure, pressure_ui = self.fix_corrupted_data(val=pressure)
                    pressure_ui = self.ui_format_pressure(dev, val=pressure_ui)
                    daily_forecast_states_list.append(
                        {'key': f"d{fore_counter_text}_pressure",
                         'value': pressure,
                         'uiValue': pressure_ui
                         }
                    )

                    # ================================== Summary ==================================
                    daily_forecast_states_list.append(
                        {'key': f"d{fore_counter_text}_summary", 'value': summary}
                    )

                    # ============================= Temperature High ==============================
                    temperature_high, temperature_high_ui = (
                        self.fix_corrupted_data(val=temperature_high)
                    )
                    temperature_high_ui = self.ui_format_temperature(dev, val=temperature_high_ui)
                    daily_forecast_states_list.append(
                        {'key': f"d{fore_counter_text}_temperatureHigh",
                         'value': temperature_high,
                         'uiValue': temperature_high_ui
                         }
                    )

                    if forecast_counter == 1:
                        today_high = round(temperature_high)

                    # ============================== Temperature Low ==============================
                    temperature_low, temperature_low_ui = (
                        self.fix_corrupted_data(val=temperature_low)
                    )
                    temperature_low_ui = self.ui_format_temperature(dev, val=temperature_low_ui)
                    daily_forecast_states_list.append(
                        {'key': f"d{fore_counter_text}_temperatureLow",
                         'value': temperature_low,
                         'uiValue': temperature_low_ui
                         }
                    )

                    if forecast_counter == 1:
                        today_low = round(temperature_low)

                    # ================================= UV Index ==================================
                    uv_index, uv_index_ui = self.fix_corrupted_data(val=uv_index)
                    uv_index_ui = self.ui_format_index(dev, val=uv_index_ui)
                    daily_forecast_states_list.append(
                        {'key': f"d{fore_counter_text}_uvIndex",
                         'value': uv_index,
                         'uiValue': uv_index_ui
                         }
                    )

                    # ================================ Visibility =================================
                    visibility, visibility_ui = self.fix_corrupted_data(val=visibility)
                    visibility_ui = self.ui_format_distance(dev, val=visibility_ui)
                    daily_forecast_states_list.append(
                        {'key': f"d{fore_counter_text}_visibility",
                         'value': visibility,
                         'uiValue': visibility_ui
                         }
                    )

                    # =============================== Wind Bearing ================================
                    wind_bearing, wind_bearing_ui = self.fix_corrupted_data(val=wind_bearing)
                    daily_forecast_states_list.append(
                        {'key': f"d{fore_counter_text}_windBearing",
                         'value': wind_bearing,
                         'uiValue': int(float(wind_bearing_ui))
                         }
                    )

                    # ============================= Wind Bearing Name =============================
                    wind_bearing_name = self.ui_format_wind_name(val=wind_bearing)
                    daily_forecast_states_list.append(
                        {'key': f"d{fore_counter_text}_windBearingName",
                         'value': wind_bearing_name
                         }
                    )

                    # ================================= Wind Gust =================================
                    wind_gust, wind_gust_ui = self.fix_corrupted_data(val=wind_gust)
                    wind_gust_ui = self.ui_format_wind(dev, val=wind_gust_ui)
                    daily_forecast_states_list.append(
                        {'key': f"d{fore_counter_text}_windGust",
                         'value': wind_gust,
                         'uiValue': wind_gust_ui
                         }
                    )

                    # ================================ Wind Speed =================================
                    wind_speed, wind_speed_ui = self.fix_corrupted_data(val=wind_speed)
                    wind_speed_ui = self.ui_format_wind(dev, val=wind_speed_ui)
                    daily_forecast_states_list.append(
                        {'key': f"d{fore_counter_text}_windSpeed",
                         'value': wind_speed,
                         'uiValue': wind_speed_ui
                         }
                    )

                    forecast_counter += 1

            new_props = dev.pluginProps
            _lat = float(dev.pluginProps.get('latitude', 'lat'))
            _long = float(dev.pluginProps.get('longitude', 'long'))
            new_props['address'] = f"{_lat:0.5f}, {_long:0.5f}"
            dev.replacePluginPropsOnServer(new_props)

            temp_units = dev.pluginProps['temperatureUnits']
            display_value = f"{int(today_high)}{temp_units}/{int(today_low)}{temp_units}"
            daily_forecast_states_list.append(
                {'key': 'onOffState',
                 'value': True,
                 'uiValue': display_value
                 }
            )

            dev.updateStatesOnServer(daily_forecast_states_list)
            dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOn)

        except Exception:  # noqa
            self.logger.error("Problem parsing 10-day forecast data.", exc_info=True)
            daily_forecast_states_list.append(
                {'key': 'onOffState', 'value': False, 'uiValue': " "}
            )

            dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)
            dev.updateStatesOnServer(daily_forecast_states_list)

    # =============================================================================
    def parse_current_weather_data(self, dev=None):
        """
        Parse weather data to devices

        The parse_current_weather_data() method takes weather data and parses it to Weather Device
        states. See Dark Sky API for value meaning.

        :param indigo.Device dev:
        """

        # Reload the date and time preferences in case they've changed.

        weather_states_list = []

        try:

            location     = (dev.pluginProps['latitude'], dev.pluginProps['longitude'])
            weather_data = self.masterWeatherDict[location]

            apparent_temperature = self.nested_lookup(
                obj=weather_data, keys=('currently', 'apparentTemperature',)
            )
            cloud_cover = self.nested_lookup(
                obj=weather_data, keys=('currently', 'cloudCover',)
            )
            dew_point = self.nested_lookup(
                obj=weather_data, keys=('currently', 'dewPoint',)
            )
            humidity = self.nested_lookup(
                obj=weather_data, keys=('currently', 'humidity',)
            )
            icon = self.nested_lookup(
                obj=weather_data, keys=('currently', 'icon',)
            )
            storm_bearing = self.nested_lookup(
                obj=weather_data, keys=('currently', 'nearestStormBearing',)
            )
            storm_distance = self.nested_lookup(
                obj=weather_data, keys=('currently', 'nearestStormDistance',)
            )
            ozone = self.nested_lookup(
                obj=weather_data, keys=('currently', 'ozone',)
            )
            pressure = self.nested_lookup(
                obj=weather_data, keys=('currently', 'pressure',)
            )
            precip_intensity = self.nested_lookup(
                obj=weather_data, keys=('currently', 'precipIntensity',)
            )
            precip_probability = self.nested_lookup(
                obj=weather_data, keys=('currently', 'precipProbability',)
            )
            summary = self.nested_lookup(
                obj=weather_data, keys=('currently', 'summary',)
            )
            temperature = self.nested_lookup(
                obj=weather_data, keys=('currently', 'temperature',)
            )
            epoch = self.nested_lookup(
                obj=weather_data, keys=('currently', 'time')
            )
            uv = self.nested_lookup(
                obj=weather_data, keys=('currently', 'uvIndex',)
            )
            visibility = self.nested_lookup(
                obj=weather_data, keys=('currently', 'visibility',)
            )
            wind_bearing = self.nested_lookup(
                obj=weather_data, keys=('currently', 'windBearing',)
            )
            wind_gust = self.nested_lookup(
                obj=weather_data, keys=('currently', 'windGust',)
            )
            wind_speed = self.nested_lookup(
                obj=weather_data, keys=('currently', 'windSpeed',)
            )

            # ================================ Time Epoch =================================
            # (Int) Epoch time of the data.
            weather_states_list.append({'key': 'currentObservationEpoch', 'value': int(epoch)})

            # =================================== Time ====================================
            # (string: "Last Updated on MONTH DD, HH:MM AM/PM TZ")
            time_long = (f"Last updated on "
                         f"{time.strftime('%b %d, %H:%M %p %z', time.localtime(epoch))}")
            weather_states_list.append({'key': 'currentObservation', 'value': time_long})

            # ================================ Time 24 Hour ===============================
            time_24 = time.strftime(
                f"{self.inst_attr['date_format']} "
                f"{self.inst_attr['time_format']}",
                time.localtime(epoch)
            )
            weather_states_list.append({'key': 'currentObservation24hr', 'value': time_24})

            # ============================= Apparent Temperature ==========================
            apparent_temperature, apparent_temperature_ui = (
                self.fix_corrupted_data(val=apparent_temperature)
            )
            apparent_temperature_ui = self.ui_format_temperature(dev, val=apparent_temperature_ui)
            weather_states_list.append(
                {'key': 'apparentTemperature',
                 'value': apparent_temperature,
                 'uiValue': apparent_temperature_ui
                 }
            )
            weather_states_list.append(
                {'key': 'apparentTemperatureIcon', 'value': round(apparent_temperature)}
            )

            # ================================ Cloud Cover ================================
            cloud_cover, cloud_cover_ui = self.fix_corrupted_data(val=float(cloud_cover) * 100)
            cloud_cover_ui = self.ui_format_percentage(dev=dev, val=cloud_cover_ui)
            weather_states_list.append(
                {'key': 'cloudCover',
                 'value': cloud_cover,
                 'uiValue': cloud_cover_ui
                 }
            )
            weather_states_list.append(
                {'key': 'cloudCoverIcon', 'value': round(cloud_cover)}
            )

            # ================================= Dew Point =================================
            dew_point, dew_point_ui = self.fix_corrupted_data(val=dew_point)
            dew_point_ui = self.ui_format_temperature(dev, val=dew_point_ui)
            weather_states_list.append(
                {'key': 'dewpoint',
                 'value': dew_point,
                 'uiValue': dew_point_ui
                 }
            )
            weather_states_list.append({'key': 'dewpointIcon', 'value': round(dew_point)})

            # ================================= Humidity ==================================
            humidity, humidity_ui = self.fix_corrupted_data(val=float(humidity) * 100)
            humidity_ui = self.ui_format_percentage(dev=dev, val=humidity_ui)
            weather_states_list.append(
                {'key': 'humidity',
                 'value': humidity,
                 'uiValue': humidity_ui
                 }
            )
            weather_states_list.append(
                {'key': 'humidityIcon', 'value': round(humidity)}
            )

            # =================================== Icon ====================================
            weather_states_list.append(
                {'key': 'icon', 'value': icon.replace('-', '_')}
            )

            # =========================== Nearest Storm Bearing ===========================
            storm_bearing, storm_bearing_ui = self.fix_corrupted_data(val=storm_bearing)
            storm_bearing_ui = self.ui_format_index(dev, val=storm_bearing_ui)
            weather_states_list.append(
                {'key': 'nearestStormBearing',
                 'value': storm_bearing,
                 'uiValue': storm_bearing_ui
                 }
            )
            weather_states_list.append(
                {'key': 'nearestStormBearingIcon', 'value': storm_bearing}
            )

            # ========================== Nearest Storm Distance ===========================
            storm_distance, storm_distance_ui = self.fix_corrupted_data(val=storm_distance)
            storm_distance_ui = self.ui_format_distance(dev, val=storm_distance_ui)
            weather_states_list.append(
                {'key': 'nearestStormDistance',
                 'value': storm_distance,
                 'uiValue': storm_distance_ui}
            )
            weather_states_list.append(
                {'key': 'nearestStormDistanceIcon', 'value': round(storm_distance)}
            )

            # =================================== Ozone ===================================
            ozone, ozone_ui = self.fix_corrupted_data(val=ozone)
            ozone_ui = self.ui_format_index(dev, val=ozone_ui)
            weather_states_list.append(
                {'key': 'ozone',
                 'value': ozone,
                 'uiValue': ozone_ui
                 }
            )
            weather_states_list.append(
                {'key': 'ozoneIcon', 'value': round(ozone)}
            )

            # ============================ Barometric Pressure ============================
            pressure, pressure_ui = self.fix_corrupted_data(val=pressure)
            pressure_ui = self.ui_format_pressure(dev, val=pressure_ui)
            weather_states_list.append(
                {'key': 'pressure',
                 'value': pressure,
                 'uiValue': pressure_ui
                 }
            )
            weather_states_list.append(
                {'key': 'pressureIcon', 'value': round(pressure)}
            )

            # ============================= Precip Intensity ==============================
            precip_intensity, precip_intensity_ui = self.fix_corrupted_data(val=precip_intensity)
            precip_intensity_ui = self.ui_format_rain(dev=dev, val=precip_intensity_ui)
            weather_states_list.append(
                {'key': 'precipIntensity',
                 'value': precip_intensity,
                 'uiValue': precip_intensity_ui
                 }
            )
            weather_states_list.append(
                {'key': 'precipIntensityIcon', 'value': round(precip_intensity)}
            )

            # ============================ Precip Probability =============================
            precip_probability, precip_probability_ui = (
                self.fix_corrupted_data(val=float(precip_probability) * 100)
            )
            precip_probability_ui = self.ui_format_percentage(dev=dev, val=precip_probability_ui)
            weather_states_list.append(
                {'key': 'precipProbability',
                 'value': precip_probability,
                 'uiValue': precip_probability_ui
                 }
            )
            weather_states_list.append(
                {'key': 'precipProbabilityIcon', 'value': round(precip_probability)}
            )

            # ================================== Summary ==================================
            weather_states_list.append(
                {'key': 'summary', 'value': summary}
            )

            # ================================ Temperature ================================
            temperature, temperature_ui = self.fix_corrupted_data(val=temperature)
            temperature_ui = self.ui_format_temperature(dev=dev, val=temperature_ui)
            weather_states_list.append(
                {'key': 'temperature',
                 'value': temperature,
                 'uiValue': temperature_ui
                 }
            )
            weather_states_list.append(
                {'key': 'temperatureIcon', 'value': round(temperature)}
            )

            # ==================================== UV =====================================
            uv, uv_ui = self.fix_corrupted_data(val=uv)
            uv_ui = self.ui_format_index(dev, val=uv_ui)
            weather_states_list.append(
                {'key': 'uv', 'value': uv, 'uiValue': uv_ui}
            )
            weather_states_list.append(
                {'key': 'uvIcon', 'value': round(uv)}
            )

            # ================================ Visibility =================================
            visibility, visibility_ui = self.fix_corrupted_data(val=visibility)
            visibility_ui = self.ui_format_distance(dev, val=visibility_ui)
            weather_states_list.append(
                {'key': 'visibility',
                 'value': visibility,
                 'uiValue': visibility_ui
                 }
            )
            weather_states_list.append(
                {'key': 'visibilityIcon', 'value': round(visibility)}
            )

            # =============================== Wind Bearing ================================
            current_wind_bearing, current_wind_bearing_ui = (
                self.fix_corrupted_data(val=wind_bearing)
            )
            weather_states_list.append(
                {'key': 'windBearing',
                 'value': current_wind_bearing,
                 'uiValue': int(float(current_wind_bearing_ui))
                 }
            )
            weather_states_list.append(
                {'key': 'windBearingIcon', 'value': round(current_wind_bearing)}
            )

            # ============================= Wind Bearing Name =============================
            wind_bearing_name = self.ui_format_wind_name(val=current_wind_bearing)
            weather_states_list.append(
                {'key': 'windBearingName', 'value': wind_bearing_name}
            )

            # ================================= Wind Gust =================================
            current_wind_gust, current_wind_gust_ui = self.fix_corrupted_data(val=wind_gust)
            current_wind_gust_ui = self.ui_format_wind(dev=dev, val=current_wind_gust_ui)
            weather_states_list.append(
                {'key': 'windGust',
                 'value': current_wind_gust,
                 'uiValue': current_wind_gust_ui
                 }
            )
            weather_states_list.append(
                {'key': 'windGustIcon', 'value': round(current_wind_gust)}
            )

            # ================================ Wind Speed =================================
            current_wind_speed, current_wind_speed_ui = self.fix_corrupted_data(val=wind_speed)
            current_wind_speed_ui = self.ui_format_wind(dev=dev, val=current_wind_speed_ui)
            weather_states_list.append(
                {'key': 'windSpeed',
                 'value': current_wind_speed,
                 'uiValue': current_wind_speed_ui
                 }
            )
            weather_states_list.append(
                {'key': 'windSpeedIcon', 'value': round(current_wind_speed)}
            )

            # ================================ Wind String ================================
            weather_states_list.append(
                {'key': 'windString',
                 'value': (f"{wind_bearing_name} at "
                           f"{round(current_wind_speed):.0f}{dev.pluginProps['windUnits']}")
                 }
            )

            new_props = dev.pluginProps
            _lat = float(dev.pluginProps.get('latitude', 'lat'))
            _long = float(dev.pluginProps.get('longitude', 'long'))
            new_props['address'] = f"{_lat:.5f}, {_long:.5f}"
            dev.replacePluginPropsOnServer(new_props)

            dev.updateStatesOnServer(weather_states_list)
            dev.updateStateImageOnServer(indigo.kStateImageSel.TemperatureSensorOn)
            display_value = self.ui_format_item_list_temperature(val=temperature)
            dev.updateStateOnServer(
                'onOffState',
                value=True,
                uiValue=f"{display_value}{dev.pluginProps['temperatureUnits']}"
            )

        except Exception:  # noqa
            self.logger.error("Problem parsing weather device data.", exc_info=True)
            dev.updateStateOnServer('onOffState', value=False, uiValue=" ")
            dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)

    # =============================================================================
    def refresh_weather_data(self):
        """
        Refresh data for plugin devices

        This method refreshes weather data for all devices based on a general cycle, Action Item or
        Plugin Menu call.
        """
        self.inst_attr['download_interval'] = dt.timedelta(
            seconds=int(self.pluginPrefs.get('downloadInterval', '900'))
        )
        self.inst_attr['ds_online'] = True

        self.inst_attr['date_format'] = self.Formatter.dateFormat()
        self.inst_attr['time_format'] = self.Formatter.timeFormat()

        # Check to see if the daily call limit has been reached.
        self.masterWeatherDict = {}

        for dev in indigo.devices.iter("self"):
            # for dev in indigo.devices.items("self"):

            try:

                if not self.inst_attr['ds_online']:
                    break

                if not dev:
                    # There are no FUWU devices, so go to sleep.
                    self.logger.warning("There aren't any devices to poll yet. Sleeping.")

                elif not dev.configured:
                    # A device has been created, but hasn't been fully configured yet.
                    self.logger.warning(
                        "A device has been created, but is not fully configured. Sleeping for a "
                        "minute while you finish."
                    )

                elif not dev.enabled:
                    dev.updateStateOnServer('onOffState', value=False, uiValue="Disabled")
                    dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)

                elif dev.enabled:
                    dev.updateStateOnServer('onOffState', value=True, uiValue=" ")

                    if dev.pluginProps['isWeatherDevice']:

                        location = (dev.pluginProps['latitude'], dev.pluginProps['longitude'])

                        self.get_weather_data(dev)

                        try:
                            # New devices may not have an epoch value yet.
                            device_epoch = dev.states['currentObservationEpoch']
                            try:
                                device_epoch = int(device_epoch)

                            except ValueError:
                                device_epoch = 0

                            # If we don't know the age of the data, we don't update.
                            try:
                                weather_data_epoch = int(
                                    self.masterWeatherDict[location]['currently']['time']
                                )

                            except ValueError:
                                weather_data_epoch = 0

                            good_time = device_epoch <= weather_data_epoch
                            if not good_time:
                                self.logger.warning(
                                    f"Latest data are older than data we already have. Skipping "
                                    f"{dev.name} update."
                                )

                        except KeyError:
                            if not self.inst_attr['comm_error']:
                                self.logger.warning(
                                    f"{dev.name} cannot determine age of data. Skipping until next "
                                    f"scheduled  poll."
                                )
                            good_time = False

                        # If the weather dict is not empty, the data are newer than the data we
                        # already have lets update the devices.
                        if self.masterWeatherDict and good_time:

                            # Astronomy devices.
                            if dev.deviceTypeId == 'Astronomy':
                                self.parse_astronomy_data(dev=dev)

                            # Hourly devices.
                            elif dev.deviceTypeId == 'Hourly':
                                self.parse_hourly_forecast_data(dev=dev)

                            # Daily devices.
                            elif dev.deviceTypeId == 'Daily':
                                self.parse_daily_forecast_data(dev=dev)

                                if self.pluginPrefs.get('updaterEmailsEnabled', False):
                                    self.email_forecast(dev=dev)

                            # Weather devices.
                            elif dev.deviceTypeId == 'Weather':
                                self.parse_current_weather_data(dev=dev)
                                self.parse_alerts_data(dev=dev)

                    # Image Downloader devices.
                    elif dev.deviceTypeId == 'satelliteImageDownloader':
                        self.get_satellite_image(dev=dev)

                # Update last successful poll time
                now = dt.datetime.now()
                self.inst_attr['last_successful_poll'] = now
                self.pluginPrefs['lastSuccessfulPoll'] = f"{now:%Y-%m-%d}"

                # Update next poll time
                next_poll_time = now + self.inst_attr['download_interval']
                self.inst_attr['next_poll'] = next_poll_time
                self.pluginPrefs['nextPoll'] = f"{next_poll_time:%Y-%m-%d %H:%M:%S}"

            except Exception:  # noqa
                self.logger.error(f"Problem parsing Weather data. Dev: {dev.name}", exc_info=True)

        self.logger.info("Weather data cycle complete.")

    # =============================================================================
    def trigger_processing(self):
        """
        Fire various triggers for plugin devices

        Weather Location Offline:
        The trigger_processing method will examine the time of the last weather location update and,
        if the update exceeds the time delta specified in a Fantastically Useful Weather Utility
        Plugin Weather Location Offline trigger, the trigger will be fired. The plugin examines the
        value of the latest "currentObservationEpoch" and *not* the Indigo Last Update value.

        An additional event that will cause a trigger to be fired is if the weather location
        temperature is less than -55 which indicates that a data value is invalid.

        Severe Weather Alerts:
        This trigger will fire if a weather location has at least one severe weather alert.

        Note that trigger processing will only occur during routine weather update cycles and will
        not be triggered when a data refresh is called from the Indigo Plugins menu.
        """
        # Reconstruct the masterTriggerDict in case it has changed.
        self.masterTriggerDict = {
            trigger.pluginProps['listOfDevices']: (
                trigger.pluginProps['offlineTimer'], trigger.id
            )
            for trigger in indigo.triggers.iter(filter="self.weatherSiteOffline")
        }

        try:

            # Iterate through all the plugin devices to see if a related trigger should be fired
            for dev in indigo.devices.iter(filter='self'):

                # ========================== Weather Location Offline ==========================
                # If the device is in the masterTriggerDict, it has an offline trigger
                if str(dev.id) in self.masterTriggerDict:

                    # Process the trigger only if the device is enabled
                    if dev.enabled:

                        trigger_id = self.masterTriggerDict[str(dev.id)][1]  # Indigo trigger ID

                        if indigo.triggers[trigger_id].pluginTypeId == 'weatherSiteOffline':

                            offline_delta = dt.timedelta(
                                minutes=int(self.masterTriggerDict.get(dev.id, ('60', ''))[0])
                            )

                            # Convert currentObservationEpoch to a localized datetime object
                            current_observation_epoch = float(dev.states['currentObservationEpoch'])
                            current_observation = time.strftime(
                                '%Y-%m-%d %H:%M', time.localtime(current_observation_epoch)
                            )
                            current_observation = parse(current_observation)

                            # Time elapsed since last observation
                            diff = dt.datetime.now() - current_observation

                            # If the observation is older than offline_delta
                            if diff >= offline_delta:
                                total_seconds = int(diff.total_seconds())
                                days, remainder = divmod(total_seconds, 60 * 60 * 24)
                                hours, remainder = divmod(remainder, 60 * 60)
                                minutes, seconds = divmod(remainder, 60)

                                # Note that we leave seconds off, but it could easily be added if
                                # needed.
                                diff_msg = f"{days} days, {hours} hrs, {minutes} mins"

                                dev.updateStateImageOnServer(
                                    indigo.kStateImageSel.TemperatureSensor
                                )
                                dev.updateStateOnServer('onOffState', value='offline')

                                if indigo.triggers[trigger_id].enabled:
                                    self.logger.warning(
                                        f"{dev.name} location appears to be offline for {diff_msg}"
                                    )
                                    indigo.trigger.execute(trigger_id)

                            # If the temperature observation is lower than -55
                            elif dev.states['temperature'] <= -55.0:
                                dev.updateStateImageOnServer(
                                    indigo.kStateImageSel.TemperatureSensor
                                )
                                dev.updateStateOnServer('onOffState', value='offline')

                                if indigo.triggers[trigger_id].enabled:
                                    self.logger.warning(
                                        f"{dev.name} location appears to be offline (ambient "
                                        f"temperature lower than -55)."
                                    )
                                    indigo.trigger.execute(trigger_id)

                # ============================ Severe Weather Alert ============================
                for trigger in indigo.triggers.iter('self.weatherAlert'):

                    if int(trigger.pluginProps['listOfDevices']) == dev.id \
                            and dev.states['alertStatus'] and trigger.enabled:

                        self.logger.warning(
                            f"{dev.name} location has at least one severe weather alert."
                        )
                        indigo.trigger.execute(trigger.id)

        except KeyError:
            pass

    # =============================================================================
    def ui_format_distance(self, dev=None, val=None):
        """
        Format distance data for Indigo UI

        Adds distance units to rain values for display in control pages, etc.

        :param indigo.Device dev:
        :param int or class Str val:
        :return str:
        """
        distance_units = dev.pluginProps['distanceUnits']

        try:
            return f"{float(val):0.{self.pluginPrefs['uiDistanceDecimal']}f}{distance_units}"

        except ValueError:
            return f"{val}{distance_units}"

    # =============================================================================
    def ui_format_index(self, dev=None, val=None):
        """
        Format index data for Indigo UI

        Adds index units to rain values for display in control pages, etc.

        :param indigo.Device dev:
        :param int or class Str val:
        :return str:
        """
        index_units = dev.pluginProps['indexUnits']

        try:
            return f"{float(val):0.{self.pluginPrefs['uiIndexDecimal']}f}{index_units}"

        except ValueError:
            return f"{val}{index_units}"

    # =============================================================================
    def ui_format_item_list_temperature(self, val=None):
        """
        Format temperature values for Indigo UI

        Adjusts the decimal precision of the temperature value for the Indigo Item List. Note: this
        method needs to return a string rather than a Unicode string (for now.)

        :param int or class Str val:
        :return str:
        """
        try:
            return f"{val:0.{int(self.pluginPrefs.get('itemListTempDecimal', '1'))}f}"
        except ValueError:
            return f"{val}"

    # =============================================================================
    def ui_format_pressure(self, dev=None, val=None):
        """
        Format index data for Indigo UI

        Adds index units to rain values for display in control pages, etc.

        :param indigo.Device dev:
        :param int or class Str val:
        :return str:
        """
        index_units = dev.pluginProps['pressureUnits']

        try:
            return f"{float(val):0.{self.pluginPrefs['uiIndexDecimal']}f}{index_units}"

        except ValueError:
            return f"{val}{index_units}"

    # =============================================================================
    def ui_format_percentage(self, dev=None, val=None):
        """
        Format percentage data for Indigo UI

        Adjusts the decimal precision of percentage values for display in control pages, etc.

        :param indigo.Device dev:
        :param int or class Str val:
        :return str:
        """
        percentage_decimal = int(self.pluginPrefs.get('uiPercentageDecimal', '1'))
        percentage_units = dev.pluginProps.get('percentageUnits', '')

        try:
            return f"{float(val):0.{percentage_decimal}f}{percentage_units}"

        except ValueError:
            return f"{val}{percentage_units}"

    # =============================================================================
    def ui_format_rain(self, dev=None, val=None):  # noqa
        """
        Format rain data for Indigo UI

        Adds rain units to rain values for display in control pages, etc.

        :param indigo.Device dev:
        :param int or class Str val:
        :return str:
        """
        # Some devices use the prop 'rainUnits' and some use the prop 'rainAmountUnits'.  So if we
        # fail on the first, try the second and--if still not successful, return and empty string.
        try:
            rain_units = dev.pluginProps['rainUnits']
        except KeyError:
            rain_units = dev.pluginProps.get('rainAmountUnits', '')

        if val in ("NA", "N/A", "--", ""):
            return val

        try:
            return f"{float(val):0.2f}{rain_units}"

        except ValueError:
            return f"{val}"

    # =============================================================================
    def ui_format_temperature(self, dev=None, val=None):
        """
        Format temperature data for Indigo UI

        Adjusts the decimal precision of certain temperature values and appends the desired units
        string for display in control pages, etc.

        :param indigo.Device dev:
        :param int or class Str val:
        :return str:
        """
        temp_decimal      = int(self.pluginPrefs.get('uiTempDecimal', '1'))
        temperature_units = dev.pluginProps.get('temperatureUnits', '')

        try:
            return f"{float(val):0.{temp_decimal}f}{temperature_units}"

        except ValueError:
            return "--"

    # =============================================================================
    def ui_format_wind(self, dev=None, val=None):
        """
        Format wind data for Indigo UI

        Adjusts the decimal precision of certain wind values for display in control pages, etc.

        :param indigo.Device dev:
        :param int or class Str val:
        :return str:
        """
        wind_decimal = int(self.pluginPrefs.get('uiWindDecimal', '1'))
        wind_units   = dev.pluginProps.get('windUnits', '')

        try:
            return f"{float(val):0.{wind_decimal}f}{wind_units}"

        except ValueError:
            return f"{val}"

    # =============================================================================
    def ui_format_wind_name(self, val=0):
        """
        Format wind data for Indigo UI

        Adjusts the decimal precision of certain wind values for display in control pages, etc.

        Credit to Indigo Forum user forestfield for conversion routine.

        :param float val:
        """
        long_short = self.pluginPrefs.get('uiWindName', 'Long')
        val        = round(val)

        if long_short == 'Long':
            index = int(((val + 22.5) % 360) / 45)
            value = ['North', 'Northeast', 'East', 'Southeast', 'South', 'Southwest', 'West',
                     'Northwest'][index]

        else:
            index = int(((val + 22.5) % 360) / 45)
            value = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'][index]

        return value
