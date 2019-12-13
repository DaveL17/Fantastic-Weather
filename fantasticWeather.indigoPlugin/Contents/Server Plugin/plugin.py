#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-

"""
Fantastically Useful Weather Utility
plugin.py
Author: DaveL17
Credits:
Update Checker by: berkinet (with additional features by Travis Cook)
Regression Testing by: Monstergerm

The Fantastically Useful Weather Utility plugin downloads JSON data from Dark Sky and parses
it into custom device states. Theoretically, the user can create an unlimited
number of devices representing individual observation locations. The
Fantastically Useful Weather Utility plugin will update each custom device found in the device
dictionary incrementally.

The base Dark Sky developer plan allows for 1000 per day. See Dark Sky for
more information on API call limitations.

The plugin tries to leave DS data unchanged. But in order to be useful, some
changes need to be made. The plugin adjusts the raw JSON data in the following
ways:
- Takes numerics and converts them to strings for Indigo compatibility
  where necessary.
- Strips non-numeric values from numeric values for device states where
  appropriate (but retains them for ui.Value)
- Replaces anything that is not a rational value (i.e., "--" with "0"
    for precipitation since precipitation can only be zero or a
    positive value) and replaces "-999.0" with a value of -99.0 and a UI value
    of "--" since the actual value could be positive or negative.

Weather data copyright Dark Sky and its respective data providers. This plugin
and its author are in no way affiliated with Dark Sky. For more information
about data provided see Dark Sky Terms of Service located at:
http://www.darksky.net

For information regarding the use of this plugin, see the license located in
the plugin package or located on GitHub:
https://github.com/DaveL17/Fantastic-Weather/blob/master/LICENSE

"""

# =================================== TO DO ===================================

# TODO: None.

# ================================== IMPORTS ==================================

# Built-in modules
import datetime as dt
from dateutil.parser import parse
import logging
import pytz
import requests
import simplejson
import sys
import textwrap
import time

# Third-party modules
try:
    import indigo
except ImportError:
    pass
try:
    import pydevd
except ImportError:
    pass

# My modules
import DLFramework.DLFramework as Dave

# =================================== HEADER ==================================

__author__    = Dave.__author__
__copyright__ = Dave.__copyright__
__license__   = Dave.__license__
__build__     = Dave.__build__
__title__     = "Fantastically Useful Weather Utility"
__version__   = "0.5.01"

# =============================================================================

kDefaultPluginPrefs = {
    u'alertLogging': False,           # Write severe weather alerts to the log?
    u'apiKey': "apiKey",              # DS requires an api key.
    u'callCounter': "999",            # DS call limit.
    u'dailyCallCounter': "0",         # Number of API calls today.
    u'dailyCallDay': "1970-01-01",    # API call counter date.
    u'dailyCallLimitReached': False,  # Has the daily call limit been reached?
    u'dailyIconNames': "",            # Hidden trap of icon names used by the API.
    u'downloadInterval': "900",       # Frequency of weather updates.
    u'hourlyIconNames': "",           # Hidden trap of icon names used by the API.
    u'itemListTempDecimal': "1",      # Precision for Indigo Item List.
    u'language': "en",                # Language for DS text.
    u'lastSuccessfulPoll': "1970-01-01 00:00:00",    # Last successful plugin cycle
    u'launchParameters': "https://darksky.net/dev",  # url for launch API button
    u'nextPoll': "1970-01-01 00:00:00",              # Next plugin cycle
    u'noAlertLogging': False,         # Suppresses "no active alerts" logging.
    u'showDebugLevel': "30",          # Logger level.
    u'uiDateFormat': "YYYY-MM-DD",    # Preferred date format string.
    u'uiDistanceDecimal': "0",        # Precision for Indigo UI display (distance).
    u'uiIndexDecimal': "0",           # Precision for Indigo UI display (index).
    u'uiPercentageDecimal': "1",      # Precision for Indigo UI display (humidity, etc.)
    u'uiTempDecimal': "1",            # Precision for Indigo UI display (temperature).
    u'uiTimeFormat': "military",      # Preferred time format string.
    u'uiWindDecimal': "1",            # Precision for Indigo UI display (wind).
    u'uiWindName': "Long",            # Use long or short wind names (i.e., N vs. North)
    u'units': "auto",                 # Standard, metric, Canadian, UK, etc.
    u'updaterEmail': "",              # Email address for forecast email (legacy field name).
    u'updaterEmailsEnabled': False,   # Enable/Disable forecast emails.
    u'weatherIconNames': "",          # Hidden trap of icon names used by the API.
}


class Plugin(indigo.PluginBase):

    def __init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs):
        indigo.PluginBase.__init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs)

        self.pluginIsInitializing = True
        self.pluginIsShuttingDown = False

        self.comm_error        = False
        self.download_interval = dt.timedelta(seconds=int(self.pluginPrefs.get('downloadInterval', '900')))
        self.masterWeatherDict = {}
        self.masterTriggerDict = {}
        self.ds_online         = True
        self.pluginPrefs['dailyCallLimitReached'] = False

        # ========================== API Poll Values ==========================
        last_poll = self.pluginPrefs.get('lastSuccessfulPoll', "1970-01-01 00:00:00")
        try:
            self.last_successful_poll = parse(last_poll)

        except ValueError:
            self.last_successful_poll = parse("1970-01-01 00:00:00")

        next_poll = self.pluginPrefs.get('nextPoll', "1970-01-01 00:00:00")
        try:
            self.next_poll = parse(next_poll)

        except ValueError:
            self.next_poll = parse("1970-01-01 00:00:00")

        # =============================== Version Check ===============================
        if int(indigo.server.version[0]) >= 7:
            pass
        else:
            raise Exception(u"The plugin requires Indigo 7 or later.")

        # ========================== Initialize DLFramework ===========================

        self.Fogbert   = Dave.Fogbert(self)
        self.Formatter = Dave.Formatter(self)

        self.date_format = self.Formatter.dateFormat()
        self.time_format = self.Formatter.timeFormat()

        # Log pluginEnvironment information when plugin is first started
        self.Fogbert.pluginEnvironment()

        # Fantastically Useful Weather Utility Attribution and disclaimer.
        indigo.server.log(u"{0:*^130}".format(""))
        indigo.server.log(u"{0:*^130}".format(" Powered by Dark Sky. This plugin and its author are in no way affiliated with Dark Sky. "))
        indigo.server.log(u"{0:*^130}".format(""))

        # =============================== Debug Logging ===============================

        # Current debug level.
        debug_level = self.pluginPrefs.get('showDebugLevel', '30')

        # Set the format and level handlers for the logger
        self.plugin_file_handler.setFormatter(logging.Formatter('%(asctime)s.%(msecs)03d\t%(levelname)-10s\t%(name)s.%(funcName)-28s %(msg)s', datefmt='%Y-%m-%d %H:%M:%S'))
        self.indigo_log_handler.setLevel(int(debug_level))

        # ============================= Remote Debugging ==============================
        # try:
        #     pydevd.settrace('localhost', port=5678, stdoutToServer=True, stderrToServer=True, suspend=False)
        # except:
        #     pass

        self.pluginIsInitializing = False

    def __del__(self):
        indigo.PluginBase.__del__(self)

    # =============================================================================
    # ============================== Indigo Methods ===============================
    # =============================================================================
    def closedPrefsConfigUi(self, values_dict, user_cancelled):

        if not user_cancelled:
            self.indigo_log_handler.setLevel(int(values_dict['showDebugLevel']))

            # ============================= Update Poll Time ==============================
            self.download_interval = dt.timedelta(seconds=int(self.pluginPrefs.get('downloadInterval', '900')))
            last_poll              = self.pluginPrefs.get('lastSuccessfulPoll', "1970-01-01 00:00:00")

            try:
                next_poll = parse(last_poll) + self.download_interval

            except ValueError:
                next_poll = parse(last_poll) + self.download_interval

            self.pluginPrefs['nextPoll'] = u"{0}".format(next_poll)

            # =================== Update Item List Temperature Precision ==================
            # For devices that display the temperature as their main UI state, try to set
            # them to their (potentially changed) ui format.
            for dev in indigo.devices.itervalues('self'):

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
                            display_value = u"{0:.{1}f} {2}{3}".format(dev.states['temperature'],
                                                                       int(self.pluginPrefs['itemListTempDecimal']),
                                                                       dev.pluginProps['temperatureUnits'],
                                                                       units)

                        except KeyError:
                            display_value = u""

                        dev.updateStateOnServer('onOffState', value=current_on_off_state, uiValue=display_value)

            # Ensure that self.pluginPrefs includes any recent changes.
            for k in values_dict:
                self.pluginPrefs[k] = values_dict[k]

    # =============================================================================
    def deviceStartComm(self, dev):

        # Check to see if the device profile has changed.
        dev.stateListOrDisplayStateIdChanged()

        # ========================= Update Temperature Display ========================
        # For devices that display the temperature as their UI state, try to set them
        # to a value we already have.
        try:
            display_value = u"{0:.{1}f}{2}".format(dev.states['temperature'], int(self.pluginPrefs['itemListTempDecimal']), dev.pluginProps['temperatureUnits'])

        except KeyError:
            display_value = u"Enabled"

        # =========================== Set Device Icon to Off ==========================
        if dev.deviceTypeId == 'Weather':
            dev.updateStateImageOnServer(indigo.kStateImageSel.TemperatureSensor)
        else:
            dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)

        dev.updateStateOnServer('onOffState', value=True, uiValue=display_value)

    # =============================================================================
    def deviceStopComm(self, dev):

        # =========================== Set Device Icon to Off ==========================
        if dev.deviceTypeId == 'Weather':
            dev.updateStateImageOnServer(indigo.kStateImageSel.TemperatureSensor)
        else:
            dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)

        dev.updateStateOnServer('onOffState', value=False, uiValue=u"Disabled")

    # =============================================================================
    def getDeviceConfigUiValues(self, values_dict, type_id, dev_id):

        if type_id == 'Daily':
            # weatherSummaryEmailTime is set by a generator. We need this bit to pre-
            # populate the control with the default value when a new device is created.
            if 'weatherSummaryEmailTime' not in values_dict.keys():
                values_dict['weatherSummaryEmailTime'] = "01:00"

        if type_id != 'satelliteImageDownloader':
            # If new device, lat/long will be zero. so let's start with the lat/long of
            # the Indigo server.

            if values_dict.get('latitude', "0") == "0" or values_dict.get('longitude', "0") == "0":
                lat_long = indigo.server.getLatitudeAndLongitude()
                values_dict['latitude'] = str(lat_long[0])
                values_dict['longitude'] = str(lat_long[1])
                self.logger.debug(u"Populated lat/long.")

        return values_dict

    # =============================================================================
    def getPrefsConfigUiValues(self):

        return self.pluginPrefs

    # =============================================================================
    def runConcurrentThread(self):

        self.logger.debug(u"Starting main thread.")

        self.sleep(5)

        try:
            while True:

                # Load the download interval in case it's changed
                refresh_time           = self.pluginPrefs.get('downloadInterval', '900')
                self.download_interval = dt.timedelta(seconds=int(refresh_time))
                
                self.last_successful_poll = parse(self.pluginPrefs['lastSuccessfulPoll'])
                self.next_poll            = parse(self.pluginPrefs['nextPoll'])

                # If we have reached the time for the next scheduled poll
                if dt.datetime.now() > self.next_poll:

                    self.refresh_weather_data()
                    self.trigger_processing()

                # Wait 30 seconds before trying again.
                self.sleep(30)

        except self.StopThread as error:
            self.logger.debug(u"StopThread: (Line {0}) {1}".format(sys.exc_traceback.tb_lineno, error))
            self.logger.debug(u"Stopping Fantastically Useful Weather Utility thread.")

    # =============================================================================
    def sendDevicePing(self, dev_id=0, suppress_logging=False):

        indigo.server.log(u"Fantastic Weather Plugin devices do not support the ping function.")
        return {'result': 'Failure'}

    # =============================================================================
    def shutdown(self):

        self.pluginIsShuttingDown = True

    # =============================================================================
    def startup(self):

        # =========================== Audit Indigo Version ============================
        self.Fogbert.audit_server_version(min_ver=7)

    # =============================================================================
    def triggerStartProcessing(self, trigger):

        dev_id = trigger.pluginProps['list_of_devices']
        timer  = trigger.pluginProps.get('offlineTimer', '60')

        # ============================= masterTriggerDict =============================
        # masterTriggerDict contains information on Weather Location Offline triggers.
        # {dev.id: (timer, trigger.id)}
        if trigger.configured and trigger.pluginTypeId == 'weatherSiteOffline':
            self.masterTriggerDict[dev_id] = (timer, trigger.id)

    # =============================================================================
    def triggerStopProcessing(self, trigger):

        # self.logger.debug(u"Stopping {0} trigger.".format(trigger.name))
        pass

    # =============================================================================
    def validateDeviceConfigUi(self, values_dict, type_id, dev_id):

        error_msg_dict = indigo.Dict()

        if values_dict['isWeatherDevice']:

            # ================================= Latitude ==================================
            try:
                if not -90 <= float(values_dict['latitude']) <= 90:
                    error_msg_dict['latitude'] = u"The latitude value must be between -90 and 90."
            except ValueError:
                error_msg_dict['latitude'] = u"The latitude value must be between -90 and 90."

            # ================================= Longitude =================================
            try:
                if not -180 <= float(values_dict['longitude']) <= 180:
                    error_msg_dict['latitude'] = u"The longitude value must be between -180 and 180."
            except ValueError:
                error_msg_dict['latitude'] = u"The longitude value must be between -180 and 180."

            if len(error_msg_dict) > 0:
                return False, values_dict, error_msg_dict

            return True, values_dict

    # =============================================================================
    def validateEventConfigUi(self, values_dict, type_id, event_id):

        dev_id         = values_dict['list_of_devices']
        error_msg_dict = indigo.Dict()

        # Weather Site Offline trigger
        if type_id == 'weatherSiteOffline':

            self.masterTriggerDict = {trigger.pluginProps['listOfDevices']: (trigger.pluginProps['offlineTimer'], trigger.id) for trigger in indigo.triggers.iter(filter="self.weatherSiteOffline")}

            # ======================== Validate Trigger Unique ========================
            # Limit weather location offline triggers to one per device
            if dev_id in self.masterTriggerDict.keys() and event_id != self.masterTriggerDict[dev_id][1]:
                error_msg_dict['listOfDevices'] = u"Please select a weather device without an existing offline trigger."
                values_dict['listOfDevices'] = ''

            # ============================ Validate Timer =============================
            try:
                if int(values_dict['offlineTimer']) <= 0:
                    error_msg_dict['offlineTimer'] = u"You must enter a valid time value in minutes (positive integer greater than zero)."

            except ValueError:
                error_msg_dict['offlineTimer'] = u"You must enter a valid time value in minutes (positive integer greater than zero)."

            if len(error_msg_dict) > 0:
                return False, values_dict, error_msg_dict

            return True, values_dict

    # =============================================================================
    def validatePrefsConfigUi(self, values_dict):

        api_key_config      = values_dict['apiKey']
        call_counter_config = values_dict['callCounter']
        error_msg_dict      = indigo.Dict()

        # Test api_keyconfig setting.
        if len(api_key_config) == 0:
            error_msg_dict['apiKey'] = u"The plugin requires an API key to function. See help for details."

        elif " " in api_key_config:
            error_msg_dict['apiKey'] = u"The API key can't contain a space."

        elif not int(call_counter_config):
            error_msg_dict['callCounter'] = u"The call counter can only contain integers."

        elif call_counter_config < 0:
            error_msg_dict['callCounter'] = u"The call counter value must be a positive integer."

        if len(error_msg_dict) > 0:
            return False, values_dict, error_msg_dict

        return True, values_dict

    # =============================================================================
    # ============================== Plugin Methods ===============================
    # =============================================================================
    def action_refresh_weather(self, values_dict):
        """
        Refresh all weather as a result of an action call

        The action_refresh_weather() method calls the refresh_weather_data() method to
        request a complete refresh of all weather data (Actions.XML call.)

        -----

        :param indigo.Dict values_dict:
        """

        self.logger.debug(u"Refresh all weather data.")

        self.refresh_weather_data()

    # =============================================================================
    def comms_kill_all(self):
        """
        Disable all plugin devices

        comms_kill_all() sets the enabled status of all plugin devices to false.

        -----
        """

        for dev in indigo.devices.itervalues("self"):
            try:
                indigo.device.enable(dev, value=False)

            except Exception as error:
                self.logger.error(u"Exception when trying to kill all comms. (Line {0}) {1}".format(sys.exc_traceback.tb_lineno, error))

    # =============================================================================
    def comms_unkill_all(self):
        """
        Enable all plugin devices

        comms_unkill_all() sets the enabled status of all plugin devices to true.

        -----
        """

        for dev in indigo.devices.itervalues("self"):
            try:
                indigo.device.enable(dev, value=True)

            except Exception as error:
                self.logger.error(u"Exception when trying to unkill all comms. (Line {0}) {1}".format(sys.exc_traceback.tb_lineno, error))

    # =============================================================================
    def dark_sky_site(self, values_dict):
        """
        Launch a web browser to register for API

        Launch a web browser session with the values_dict parm containing the target
        URL.

        -----

        :param indigo.Dict values_dict:
        """

        self.browserOpen(values_dict['launchParameters'])

    # =============================================================================
    def dump_the_json(self):
        """
        Dump copy of weather JSON to file

        The dump_the_json() method reaches out to Dark Sky, grabs a copy of
        the configured JSON data and saves it out to a file placed in the Indigo Logs
        folder. If a weather data log exists for that day, it will be replaced. With a
        new day, a new log file will be created (file name contains the date.)

        -----
        """

        file_name = '{0}/{1} FUWU Plugin.txt'.format(indigo.server.getLogsFolderPath(), dt.datetime.today().date())

        try:

            with open(file_name, 'w') as logfile:

                logfile.write(u"Dark Sky JSON Data\n".encode('utf-8'))
                logfile.write(u"Written at: {0}\n".format(dt.datetime.today().strftime('%Y-%m-%d %H:%M')).encode('utf-8'))
                logfile.write(u"{0}{1}".format("=" * 72, '\n').encode('utf-8'))

                for key in self.masterWeatherDict.keys():
                    logfile.write(u"Location Specified: {0}\n".format(key).encode('utf-8'))
                    logfile.write(u"{0}\n\n".format(self.masterWeatherDict[key]).encode('utf-8'))

            indigo.server.log(u"Weather data written to: {0}".format(file_name))

        except IOError:
            self.logger.error(u"Unable to write to Indigo Log folder. Check folder permissions")

    # =============================================================================
    def email_forecast(self, dev):
        """
        Email forecast information

        The email_forecast() method will construct and send a summary of select weather
        information to the user based on the email address specified for plugin update
        notifications.

        -----

        :param indigo.Device dev:
        """

        email_body = u""

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
            if isinstance(summary_wanted, basestring):
                if summary_wanted.lower() == "false":
                    summary_wanted = False
                elif summary_wanted.lower() == "true":
                    summary_wanted = True

            if isinstance(summary_sent, basestring):
                if summary_sent.lower() == "false":
                    summary_sent = False
                elif summary_sent.lower() == "true":
                    summary_sent = True

            # If an email summary is wanted but not yet sent and we have reached the desired time of day.
            if summary_wanted and not summary_sent and dt.datetime.now().hour >= summary_time.hour:

                cloud_cover         = int(self.nested_lookup(forecast_day, keys=('cloudCover',)) * 100)
                forecast_time       = self.nested_lookup(forecast_day, keys=('time',))
                forecast_day_name   = time.strftime('%A', time.localtime(float(forecast_time)))
                humidity            = int(self.nested_lookup(forecast_day, keys=('humidity',)) * 100)
                long_range_forecast = self.masterWeatherDict[location]['daily'].get('summary', 'Not available.')
                ozone               = int(round(self.nested_lookup(forecast_day, keys=('ozone',))))
                precip_intensity    = self.nested_lookup(forecast_day, keys=('precipIntensity',))
                precip_probability  = int(self.nested_lookup(forecast_day, keys=('precipProbability',)) * 100)
                precip_total        = precip_intensity * 24
                precip_type         = self.nested_lookup(forecast_day, keys=('precipType',))
                pressure            = int(round(self.nested_lookup(forecast_day, keys=('pressure',))))
                summary             = self.nested_lookup(forecast_day, keys=('summary',))
                temperature_high    = int(round(self.nested_lookup(forecast_day, keys=('temperatureHigh',))))
                temperature_low     = int(round(self.nested_lookup(forecast_day, keys=('temperatureLow',))))
                uv_index            = self.nested_lookup(forecast_day, keys=('uvIndex',))
                visibility          = self.nested_lookup(forecast_day, keys=('visibility',))
                wind_bearing        = self.nested_lookup(forecast_day, keys=('windBearing',))
                wind_gust           = int(round(self.nested_lookup(forecast_day, keys=('windGust',))))
                wind_name           = self.ui_format_wind_name(val=wind_bearing)
                wind_speed          = int(round(self.nested_lookup(forecast_day, keys=('windSpeed',))))

                # Heading
                email_body += u"{0}\n".format(dev.name)
                email_body += u"{0:-<38}\n\n".format('')

                # Day
                email_body += u"{0} Forecast:\n".format(forecast_day_name)
                email_body += u"{0:-<38}\n".format('')
                email_body += u"{0}\n\n".format(summary)

                # Data
                email_body += u"High: {0}{1}\n".format(temperature_high, dev.pluginProps.get('temperatureUnits', ''))
                email_body += u"Low: {0}{1}\n".format(temperature_low, dev.pluginProps.get('temperatureUnits', ''))
                email_body += u"Chance of {1}: {0}{2} \n".format(precip_probability, precip_type, dev.pluginProps.get('percentageUnits', ''))
                email_body += u"Total Precipitation: {0:.2f}\n".format(precip_total, dev.pluginProps.get('rainAmountUnits', ''))
                email_body += u"Winds out of the {0} at {1}{3} -- gusting to {2}{3}\n".format(wind_name, wind_speed, wind_gust, dev.pluginProps.get('windUnits', ''))
                email_body += u"Clouds: {0}{1}\n".format(cloud_cover, dev.pluginProps.get('percentageUnits', ''))
                email_body += u"Humidity: {0}{1}\n".format(humidity, dev.pluginProps.get('percentageUnits', ''))
                email_body += u"Ozone: {0}{1}\n".format(ozone, dev.pluginProps.get('indexUnits', ''))
                email_body += u"Pressure: {0}{1}\n".format(pressure, dev.pluginProps.get('pressureUnits', ''))
                email_body += u"UV: {0}\n".format(uv_index, dev.pluginProps.get('pressureUnits', ''))
                email_body += u"Visibility: {0}{1}\n\n".format(visibility, dev.pluginProps.get('distanceUnits', ''))

                # Long Range Forecast
                email_body += u"Long Range Forecast:\n"
                email_body += u"{0:-<38}\n".format('')
                email_body += u"{0}\n\n".format(long_range_forecast)

                # Footer
                email_body += u"{0:-<38}\n".format('')
                email_body += u"{0}".format(u'This email sent at your request on behalf of the Fantastic Weather Plugin for Indigo.\n\n*** Powered by Dark Sky ***')

                indigo.server.sendEmailTo(self.pluginPrefs['updaterEmail'], subject=u"Daily Weather Summary", body=email_body)
                dev.updateStateOnServer('weatherSummaryEmailSent', value=True)

                # Set email sent date
                now = dt.datetime.now()
                timestamp = (u"{0:%Y-%m-%d}".format(now))
                dev.updateStateOnServer('weatherSummaryEmailTimestamp', timestamp)
            else:
                pass

        except (KeyError, IndexError) as error:
            dev.updateStateOnServer('weatherSummaryEmailSent', value=True, uiValue=u"Err")
            self.logger.debug(u"Unable to compile forecast data for {0}. (Line {1}) {2}".format(dev.name, sys.exc_traceback.tb_lineno, error))

        except Exception as error:
            self.logger.error(u"Unable to send forecast email message. Will keep trying. (Line {0}) {1}".format(sys.exc_traceback.tb_lineno, error))

    # =============================================================================
    def fix_corrupted_data(self, val):
        """
        Format corrupted and missing data

        Sometimes DS receives corrupted data from personal weather stations. Could be
        zero, positive value or "--" or "-999.0" or "-9999.0". This method tries to
        "fix" these values for proper display.

        -----

        :param str or float val:
        """

        try:
            val = float(val)

            if val < -55.728:  # -99 F = -55.728 C
                return -99.0, u"--"

            else:
                return val, str(val)

        except (ValueError, TypeError):
            return -99.0, u"--"

    # =============================================================================
    def generator_time(self, filter="", values_dict=None, type_id="", target_id=0):
        """
        List of hours generator

        Creates a list of times for use in setting the desired time for weather
        forecast emails to be sent.

        -----
        :param str filter:
        :param indigo.Dict values_dict:
        :param str type_id:
        :param int target_id:
        """

        return [(u"{0:02.0f}:00".format(hour), u"{0:02.0f}:00".format(hour)) for hour in range(0, 24)]

    # =============================================================================
    def get_satellite_image(self, dev):
        """
        Download satellite image and save to file

        The get_satellite_image() method will download a file from a user-specified
        location and save it to a user-specified folder on the local server. This
        method is used by the Satellite Image Downloader device type.

        -----

        :param indigo.Device dev:
        """

        destination = unicode(dev.pluginProps['imageDestinationLocation'])
        source      = unicode(dev.pluginProps['imageSourceLocation'])

        try:
            if destination.endswith((".gif", ".jpg", ".jpeg", ".png")):

                get_data_time = dt.datetime.now()

                # If requests doesn't work for some reason, revert to urllib.
                try:
                    r = requests.get(source, stream=True, timeout=20)

                    with open(destination, 'wb') as img:
                        for chunk in r.iter_content(2000):
                            img.write(chunk)

                except requests.exceptions.ConnectionError:
                    if not self.comm_error:
                        self.logger.error(u"Error downloading satellite image. (No comm.)".format(sys.exc_traceback.tb_lineno))
                        self.comm_error = True
                    dev.updateStateOnServer('onOffState', value=False, uiValue=u"No comm")
                    dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)
                    return

                dev.updateStateOnServer('onOffState', value=True, uiValue=u" ")
                dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOn)

                # Report results of download timer.
                data_cycle_time = (dt.datetime.now() - get_data_time)
                data_cycle_time = (dt.datetime.min + data_cycle_time).time()
                self.logger.debug(u"Satellite image download time: {0}".format(data_cycle_time))

                self.comm_error = False
                return

            else:
                self.logger.error(u"The image destination must include one of the approved types (.gif, .jpg, .jpeg, .png)")
                dev.updateStateOnServer('onOffState', value=False, uiValue=u"Bad Type")
                dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)
                return False

        except Exception as error:
            self.comm_error = True
            self.logger.error(u"[{0}] Error downloading satellite image. (Line {1}) {2}".format(dev.name, sys.exc_traceback.tb_lineno, error))
            dev.updateStateOnServer('onOffState', value=False, uiValue=u"No comm")
            dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)

    # =============================================================================
    def get_weather_data(self, dev):
        """
        Reach out to Dark Sky and download data for this location

        Grab the JSON return for the device. A separate call must be made for each
        weather device because the data are location specific.

        -----

        :param indigo.Device dev:
        """

        api_key   = self.pluginPrefs['apiKey']
        language  = self.pluginPrefs['language']
        latitude  = dev.pluginProps['latitude']
        longitude = dev.pluginProps['longitude']
        units     = self.pluginPrefs['units']
        location  = (latitude, longitude)
        comm_timeout = 10

        # Get the data and add it to the masterWeatherDict.
        if location not in self.masterWeatherDict.keys():
            url = u'https://api.darksky.net/forecast/{0}/{1},{2}?exclude="minutely"&extend=""&units={3}&lang={4}'.format(api_key, latitude, longitude, units, language)

            # Start download timer.

            get_data_time = dt.datetime.now()

            while True:
                try:
                    r = requests.get(url, timeout=20)
                    r.raise_for_status()

                    if r.status_code != 200:
                        if r.status_code == 400:
                            self.logger.warning(u"Problem communicating with Dark Sky. This problem can usually correct itself, but reloading the plugin can often force a repair.")
                            self.logger.debug(u"Bad URL - Status Code: {0}".format(r.status_code))
                            raise requests.exceptions.ConnectionError
                        else:
                            self.logger.debug(u"Status Code: {0}".format(r.status_code))

                    simplejson_string = r.text  # We convert the file to a json object below, so we don't use requests' built-in decoder.
                    self.comm_error = False
                    break

                # No connection to Internet, no response from Dark Sky. Let's keep trying.
                except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as sub_error:

                    self.logger.debug(u"Connection Error: {0}".format(sub_error))

                    if comm_timeout < 900:
                        self.logger.error(u"Unable to reach Dark Sky. Retrying in {0} seconds.".format(comm_timeout))

                    else:
                        self.logger.error(u"Unable to reach Dark Sky. Retrying in 15 minutes.")

                    time.sleep(comm_timeout)

                    # Keep adding 10 seconds to timeout until it reaches one minute.
                    # Then, jack it up to 15 minutes.
                    if comm_timeout < 60:
                        comm_timeout += 10
                    else:
                        comm_timeout = 900

                    self.comm_error = True
                    for dev in indigo.devices.itervalues("self"):
                        dev.updateStateOnServer("onOffState", value=False, uiValue=u"No Comm")
                        dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)

                # Report results of download timer.
                data_cycle_time = (dt.datetime.now() - get_data_time)
                data_cycle_time = (dt.datetime.min + data_cycle_time).time()
                self.logger.threaddebug(u"Satellite image download time: {0}".format(data_cycle_time))

            # Load the JSON data from the file.
            try:
                parsed_simplejson = simplejson.loads(simplejson_string, encoding="utf-8")

            except Exception as error:
                self.logger.error(u"Unable to decode data. (Line {0}) {1}".format(sys.exc_traceback.tb_lineno, error))
                parsed_simplejson = {}

            # Add location JSON to master weather dictionary.
            self.masterWeatherDict[location] = parsed_simplejson

            # Increment the call counter
            self.pluginPrefs['dailyCallCounter'] = r.headers['X-Forecast-API-Calls']

            # We've been successful, mark device online
            self.comm_error = False
            dev.updateStateOnServer('onOffState', value=True)

        # We could have come here from several different places. Return to whence we
        # came to further process the weather data.
        self.ds_online = True
        return self.masterWeatherDict

    # =============================================================================
    def list_of_devices(self, filter, values_dict, target_id, trigger_id):
        """
        Generate list of devices for offline trigger

        list_of_devices returns a list of plugin devices limited to weather
        devices only (not forecast devices, etc.) when the Weather Location Offline
        trigger is fired.

        -----

        :param str filter:
        :param indigo.Dict values_dict:
        :param str target_id:
        :param int trigger_id:
        """

        return [(dev.id, dev.name) for dev in indigo.devices.itervalues(filter='self')]

    # =============================================================================
    def list_of_weather_devices(self, filter, values_dict, target_id, trigger_id):
        """
        Generate list of devices for severe weather alert trigger

        list_of_weather_devices returns a list of plugin devices limited to weather
        devices only (not forecast devices, etc.) when severe weather alert trigger is
        fired.

        -----

        :param str filter:
        :param indigo.Dict values_dict:
        :param str target_id:
        :param int trigger_id:
        """

        return [(dev.id, dev.name) for dev in indigo.devices.itervalues(filter='self.Weather')]

    # =============================================================================
    def nested_lookup(self, obj, keys, default=u"Not available"):
        """
        Do a nested lookup of the DS JSON

        The nested_lookup() method is used to extract the relevant data from the JSON
        return. The JSON is known to be inconsistent in the form of sometimes missing
        keys. This method allows for a default value to be used in instances where a
        key is missing. The method call can rely on the default return, or send an
        optional 'default=some_value' parameter. Dark Sky say that there are times
        where they won't send a key (for example, if they don't have data) so this is
        to be expected.

        Credit: Jared Goguen at StackOverflow for initial implementation.

        -----

        :param obj:
        :param keys:
        :param default:
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
    def parse_alerts_data(self, dev):
        """
        Parse alerts data to devices

        The parse_alerts_data() method takes weather alert data and parses it to device
        states. This segment iterates through all available alert information. It
        retains only the first five alerts. We set all alerts to an empty string each
        time, and then repopulate (this clears out alerts that may have expired.) If
        there are no alerts, set alert status to false.

        -----

        :param indigo.Device dev:
        """

        alerts_states_list = []  # Alerts_states_list needs to be a list.

        try:
            alert_array = []
            alerts_logging    = self.pluginPrefs.get('alertLogging', True)  # Whether to log alerts
            alerts_suppressed = dev.pluginProps.get('suppressWeatherAlerts', False)  # Suppress alert messages for device
            no_alerts_logging  = self.pluginPrefs.get('noAlertLogging', False)  # Suppress 'No Alert' messages

            location     = (dev.pluginProps['latitude'], dev.pluginProps['longitude'])
            weather_data = self.masterWeatherDict[location]
            alerts_data  = self.nested_lookup(weather_data, keys=('alerts',))
            preferred_time = dev.pluginProps.get('time_zone', 'time_here')
            timezone = pytz.timezone(weather_data['timezone'])

            # ============================= Delete Old Alerts =============================
            for alert_counter in range(1, 6):
                for state in ('alertDescription', 'alertExpires', 'alertRegions', 'alertSeverity', 'alertTime', 'alertTime', 'alertTitle', 'alertUri'):
                    alerts_states_list.append({'key': '{0}{1}'.format(state, alert_counter), 'value': u" ", 'uiValue': u" "})

            # ================================= No Alerts =================================
            if alerts_data == u"Not available":
                alerts_states_list.append({'key': 'alertStatus', 'value': False, 'uiValue': u"False"})

                if alerts_logging and not no_alerts_logging and not alerts_suppressed:
                    self.logger.info(u"{0} There are no severe weather alerts.".format(dev.name))

            # ============================ At Least One Alert =============================
            else:
                alerts_states_list.append({'key': 'alertStatus', 'value': True, 'uiValue': u"True"})

                for alert in alerts_data:

                    alert_tuple = (u"{0}".format(alert.get('description', u"Not provided.").strip()),
                                   alert.get('expires', u"Not provided."),
                                   u"{0}".format(alert.get('regions', u"Not provided.")),
                                   u"{0}".format(alert.get('severity', u"Not provided.")),
                                   alert.get('time', u"Not provided."),
                                   u"{0}".format(alert.get('title', u"Not provided.").strip()),
                                   u"{0}".format(alert.get('uri', u"Not provided.")),
                                   )

                    alert_array.append(alert_tuple)

                if len(alert_array) == 1:
                    # If user has enabled alert logging, write alert message to the Indigo log.
                    if alerts_logging and not alerts_suppressed:
                        self.logger.info(u"{0}: There is 1 severe weather alert.".format(dev.name))
                else:
                    # If user has enabled alert logging, write alert message to the Indigo log.
                    if alerts_logging and not alerts_suppressed and 0 < len(alert_array) <= 5:
                        self.logger.info(u"{0}: There are {1} severe weather alerts.".format(dev.name, len(alert_array)))

                    # If user has enabled alert logging, write alert message to the Indigo log.
                    if alerts_logging and not alerts_suppressed and len(alert_array) > 5:
                        self.logger.info(u"{0}: The plugin only retains information for the first 5 alerts.".format(dev.name))

                alert_counter = 1
                for alert in range(len(alert_array)):
                    if alert_counter <= 5:

                        # Convert epoch times to human friendly values

                        # ============================ Effective / Expires ============================
                        # Local Time (server timezone)
                        if preferred_time == "time_here":

                            alert_effective_time = time.localtime(int(alert_array[alert][4]))
                            alert_time    = time.strftime('%Y-%m-%d %H:%M', alert_effective_time)
                            alerts_states_list.append({'key': u"{0}{1}".format('alertTime', alert_counter), 'value': u"{0}".format(alert_time)})

                            alert_expires_time = time.localtime(int(alert_array[alert][1]))
                            alert_expires = time.strftime('%Y-%m-%d %H:%M', alert_expires_time)
                            alerts_states_list.append({'key': u"{0}{1}".format('alertExpires', alert_counter), 'value': u"{0}".format(alert_expires)})

                        # Location Time (location timezone)
                        elif preferred_time == "time_there":

                            alert_effective_time = dt.datetime.fromtimestamp(int(alert_array[alert][4]), tz=pytz.utc)
                            alert_effective_time = timezone.normalize(alert_effective_time)
                            alert_time = time.strftime("{0} {1}".format(self.date_format, self.time_format), alert_effective_time.timetuple())
                            alerts_states_list.append({'key': u"{0}{1}".format('alertTime', alert_counter), 'value': u"{0}".format(alert_time)})

                            alert_expires_time = dt.datetime.fromtimestamp(int(alert_array[alert][1]), tz=pytz.utc)
                            alert_expires_time = timezone.normalize(alert_expires_time)
                            alert_expires = time.strftime("{0} {1}".format(self.date_format, self.time_format), alert_expires_time.timetuple())
                            alerts_states_list.append({'key': u"{0}{1}".format('alertExpires', alert_counter), 'value': u"{0}".format(alert_expires)})

                        # ================================ Alert Info =================================

                        alerts_states_list.append({'key': u"{0}{1}".format('alertDescription', alert_counter), 'value': u"{0}".format(alert_array[alert][0])})
                        alerts_states_list.append({'key': u"{0}{1}".format('alertRegions', alert_counter), 'value': u"{0}".format(alert_array[alert][2])})
                        alerts_states_list.append({'key': u"{0}{1}".format('alertSeverity', alert_counter), 'value': u"{0}".format(alert_array[alert][3])})
                        alerts_states_list.append({'key': u"{0}{1}".format('alertTitle', alert_counter), 'value': u"{0}".format(alert_array[alert][5])})
                        alerts_states_list.append({'key': u"{0}{1}".format('alertUri', alert_counter), 'value': u"{0}".format(alert_array[alert][6])})
                        alert_counter += 1

                    # Write alert to the log?
                    # Sample:
                    # Patchy freezing drizzle is expected this morning, possibly mixed with light snow showers or flurries. With temperatures
                    # in the lower 30s, any freezing drizzle could cause patchy icy conditions on untreated roadways. Motorists are advised to
                    # check for the latest forecasts and check road conditions before driving. Temperatures will rise above freezing in many
                    # areas by midday.
                    if alerts_logging and not alerts_suppressed:
                        alert_text = textwrap.wrap(alert_array[alert][0], 120)
                        alert_text_wrapped = u""
                        for _ in alert_text:
                            alert_text_wrapped += u"{0}\n".format(_)

                        self.logger.info(u"\n{0}".format(alert_text_wrapped))

            alerts_states_list.append({'key': 'alertCount', 'value': len(alert_array)})
            dev.updateStatesOnServer(alerts_states_list)

        except Exception as error:
            self.logger.error(u"Problem parsing weather alert data: (Line {0}) {1}".format(sys.exc_traceback.tb_lineno, error))
            alerts_states_list.append({'key': 'onOffState', 'value': False, 'uiValue': u" "})
            dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)

    # =============================================================================
    def parse_astronomy_data(self, dev):
        """
        Parse astronomy data to devices

        The parse_astronomy_data() method takes astronomy data and parses it to device
        states. See Dark Sky API for value meaning.

        -----

        :param indigo.Device dev:
        """

        astronomy_states_list = []

        try:
            location       = (dev.pluginProps['latitude'], dev.pluginProps['longitude'])
            weather_data   = self.masterWeatherDict[location]
            astronomy_data = weather_data['daily']['data']
            preferred_time = dev.pluginProps.get('time_zone', 'time_here')
            timezone = pytz.timezone(weather_data['timezone'])

            epoch      = self.nested_lookup(weather_data, keys=('currently', 'time'))
            sun_rise   = self.nested_lookup(astronomy_data, keys=('sunriseTime',))
            sun_set    = self.nested_lookup(astronomy_data, keys=('sunsetTime',))
            moon_phase = self.nested_lookup(astronomy_data, keys=('moonPhase',))

            # ============================= Observation Epoch =============================
            current_observation_epoch = int(epoch)
            astronomy_states_list.append({'key': 'currentObservationEpoch', 'value': current_observation_epoch})

            # ============================= Observation Time ==============================
            current_observation_time = u"Last updated on {0}".format(time.strftime('%b %d, %H:%M %p %z', time.localtime(current_observation_epoch)))
            astronomy_states_list.append({'key': 'currentObservation', 'value': current_observation_time})

            # ============================= Observation 24hr ==============================
            current_observation_24hr = time.strftime("{0} {1}".format(self.date_format, self.time_format), time.localtime(current_observation_epoch))
            astronomy_states_list.append({'key': 'currentObservation24hr', 'value': current_observation_24hr})

            # ============================= Sunrise / Sunset ==============================
            # Local Time (server timezone)
            if preferred_time == "time_here":

                sunrise_local = time.localtime(int(sun_rise))
                sunrise_local = time.strftime("{0} {1}".format(self.date_format, self.time_format), sunrise_local)
                astronomy_states_list.append({'key': 'sunriseTime', 'value': sunrise_local})

                sunset_local  = time.localtime(int(sun_set))
                sunset_local = time.strftime("{0} {1}".format(self.date_format, self.time_format), sunset_local)
                astronomy_states_list.append({'key': 'sunsetTime', 'value': sunset_local})

            # Location Time (location timezone)
            elif preferred_time == "time_there":
                sunrise_aware = dt.datetime.fromtimestamp(int(sun_rise), tz=pytz.utc)
                sunset_aware  = dt.datetime.fromtimestamp(int(sun_set), tz=pytz.utc)

                sunrise_normal = timezone.normalize(sunrise_aware)
                sunset_normal  = timezone.normalize(sunset_aware)

                sunrise_local = time.strftime("{0} {1}".format(self.date_format, self.time_format), sunrise_normal.timetuple())
                astronomy_states_list.append({'key': 'sunriseTime', 'value': sunrise_local})

                sunset_local = time.strftime("{0} {1}".format(self.date_format, self.time_format), sunset_normal.timetuple())
                astronomy_states_list.append({'key': 'sunsetTime', 'value': sunset_local})

            # ================================ Moon Phase =================================
            moon_phase, moon_phase_ui = self.fix_corrupted_data(val=float(moon_phase * 100))
            moon_phase_ui = self.ui_format_percentage(dev=dev, val=moon_phase_ui)
            astronomy_states_list.append({'key': 'moonPhase', 'value': moon_phase, 'uiValue': moon_phase_ui})

            new_props = dev.pluginProps
            new_props['address'] = u"{0:.5f}, {1:.5f}".format(float(dev.pluginProps.get('latitude', 'lat')), float(dev.pluginProps.get('longitude', 'long')))
            dev.replacePluginPropsOnServer(new_props)

            astronomy_states_list.append({'key': 'onOffState', 'value': True, 'uiValue': u" "})

            dev.updateStatesOnServer(astronomy_states_list)
            dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOn)

        except Exception as error:
            self.logger.error(u"Problem parsing astronomy data. (Line {0}) {1}".format(sys.exc_traceback.tb_lineno, error))
            dev.updateStateOnServer('onOffState', value=False, uiValue=u" ")
            dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)

    # =============================================================================
    def parse_hourly_forecast_data(self, dev):
        """
        Parse hourly forecast data to devices

        The parse_hourly_forecast_data() method takes hourly weather forecast data and parses
        it to device states. See Dark Sky API for value meaning.

        -----

        :param indigo.Device dev:
        """

        hourly_forecast_states_list = []

        try:
            hour_temp      = 0
            location       = (dev.pluginProps['latitude'], dev.pluginProps['longitude'])
            weather_data   = self.masterWeatherDict[location]
            forecast_data  = weather_data['hourly']['data']
            preferred_time = dev.pluginProps.get('time_zone', 'time_here')
            timezone       = pytz.timezone(weather_data['timezone'])

            # ============================== Hourly Summary ===============================
            hourly_forecast_states_list.append({'key': 'hourly_summary', 'value': self.masterWeatherDict[location]['hourly']['summary']})

            # ============================= Observation Epoch =============================
            current_observation_epoch = int(self.nested_lookup(weather_data, keys=('currently', 'time')))
            hourly_forecast_states_list.append({'key': 'currentObservationEpoch', 'value': current_observation_epoch})

            # ============================= Observation Time ==============================
            current_observation_time = u"Last updated on {0}".format(time.strftime('%b %d, %H:%M %p %z', time.localtime(current_observation_epoch)))
            hourly_forecast_states_list.append({'key': 'currentObservation', 'value': current_observation_time})

            # ============================= Observation 24hr ==============================
            current_observation_24hr = time.strftime("{0} {1}".format(self.date_format, self.time_format), time.localtime(current_observation_epoch))
            hourly_forecast_states_list.append({'key': 'currentObservation24hr', 'value': current_observation_24hr})

            forecast_counter = 1
            for observation in forecast_data:

                if forecast_counter <= 24:

                    cloud_cover        = self.nested_lookup(observation, keys=('cloudCover',))
                    forecast_time      = self.nested_lookup(observation, keys=('time',))
                    humidity           = self.nested_lookup(observation, keys=('humidity',))
                    icon               = self.nested_lookup(observation, keys=('icon',))
                    ozone              = self.nested_lookup(observation, keys=('ozone',))
                    precip_intensity   = self.nested_lookup(observation, keys=('precipIntensity',))
                    precip_probability = self.nested_lookup(observation, keys=('precipProbability',))
                    precip_type        = self.nested_lookup(observation, keys=('precipType',))
                    pressure           = self.nested_lookup(observation, keys=('pressure',))
                    summary            = self.nested_lookup(observation, keys=('summary',))
                    temperature        = self.nested_lookup(observation, keys=('temperature',))
                    uv_index           = self.nested_lookup(observation, keys=('uvIndex',))
                    visibility         = self.nested_lookup(observation, keys=('visibility',))
                    wind_bearing       = self.nested_lookup(observation, keys=('windBearing',))
                    wind_gust          = self.nested_lookup(observation, keys=('windGust',))
                    wind_speed         = self.nested_lookup(observation, keys=('windSpeed',))

                    # Add leading zero to counter value for device state names 1-9.
                    if forecast_counter < 10:
                        fore_counter_text = u"0{0}".format(forecast_counter)
                    else:
                        fore_counter_text = forecast_counter

                    # ========================= Forecast Day, Epoch, Hour =========================
                    # Local Time (server timezone)
                    if preferred_time == "time_here":
                        local_time       = time.localtime(float(forecast_time))

                        forecast_day_long  = time.strftime('%A', local_time)
                        forecast_day_short = time.strftime('%a', local_time)
                        forecast_hour      = time.strftime('%H:%M', local_time)
                        forecast_hour_ui   = time.strftime(self.time_format, local_time)

                        hourly_forecast_states_list.append({'key': u"h{0}_day".format(fore_counter_text), 'value': forecast_day_long, 'uiValue': forecast_day_long})
                        hourly_forecast_states_list.append({'key': u"h{0}_day_short".format(fore_counter_text), 'value': forecast_day_short, 'uiValue': forecast_day_short})
                        hourly_forecast_states_list.append({'key': u"h{0}_epoch".format(fore_counter_text), 'value': forecast_time})
                        hourly_forecast_states_list.append({'key': u"h{0}_hour".format(fore_counter_text), 'value': forecast_hour, 'uiValue': forecast_hour_ui})

                    # Location Time (location timezone)
                    elif preferred_time == "time_there":
                        aware_time       = dt.datetime.fromtimestamp(int(forecast_time), tz=pytz.utc)

                        forecast_day_long  = timezone.normalize(aware_time).strftime("%A")
                        forecast_day_short = timezone.normalize(aware_time).strftime("%a")
                        forecast_hour      = timezone.normalize(aware_time).strftime("%H:%M")
                        forecast_hour_ui   = time.strftime(self.time_format, timezone.normalize(aware_time).timetuple())

                        zone             = dt.datetime.fromtimestamp(forecast_time, timezone)
                        zone_tuple       = zone.timetuple()              # tuple
                        zone_posix       = int(time.mktime(zone_tuple))  # timezone timestamp

                        hourly_forecast_states_list.append({'key': u"h{0}_day".format(fore_counter_text), 'value': forecast_day_long, 'uiValue': forecast_day_long})
                        hourly_forecast_states_list.append({'key': u"h{0}_day_short".format(fore_counter_text), 'value': forecast_day_short, 'uiValue': forecast_day_short})
                        hourly_forecast_states_list.append({'key': u"h{0}_epoch".format(fore_counter_text), 'value': zone_posix})
                        hourly_forecast_states_list.append({'key': u"h{0}_hour".format(fore_counter_text), 'value': forecast_hour, 'uiValue': forecast_hour_ui})

                    # ================================ Cloud Cover ================================
                    cloud_cover, cloud_cover_ui = self.fix_corrupted_data(val=cloud_cover * 100)
                    cloud_cover_ui = self.ui_format_percentage(dev=dev, val=cloud_cover_ui)
                    hourly_forecast_states_list.append({'key': u"h{0}_cloudCover".format(fore_counter_text), 'value': cloud_cover, 'uiValue': cloud_cover_ui})

                    # ================================= Humidity ==================================
                    humidity, humidity_ui = self.fix_corrupted_data(val=humidity * 100)
                    humidity_ui = self.ui_format_percentage(dev=dev, val=humidity_ui)
                    hourly_forecast_states_list.append({'key': u"h{0}_humidity".format(fore_counter_text), 'value': humidity, 'uiValue': humidity_ui})

                    # ============================= Precip Intensity ==============================
                    precip_intensity, precip_intensity_ui = self.fix_corrupted_data(val=precip_intensity)
                    precip_intensity_ui = self.ui_format_rain(dev=dev, val=precip_intensity_ui)
                    hourly_forecast_states_list.append({'key': u"h{0}_precipIntensity".format(fore_counter_text), 'value': precip_intensity, 'uiValue': precip_intensity_ui})

                    # ============================ Precip Probability =============================
                    precip_probability, precip_probability_ui = self.fix_corrupted_data(val=precip_probability * 100)
                    precip_probability_ui = self.ui_format_percentage(dev=dev, val=precip_probability_ui)
                    hourly_forecast_states_list.append({'key': u"h{0}_precipChance".format(fore_counter_text), 'value': precip_probability, 'uiValue': precip_probability_ui})

                    # =================================== Icon ====================================
                    hourly_forecast_states_list.append({'key': u"h{0}_icon".format(fore_counter_text), 'value': u"{0}".format(icon.replace('-', '_'))})

                    # =================================== Ozone ===================================
                    ozone, ozone_ui = self.fix_corrupted_data(val=ozone)
                    ozone_ui = self.ui_format_index(dev, val=ozone_ui)
                    hourly_forecast_states_list.append({'key': u"h{0}_ozone".format(fore_counter_text), 'value': ozone, 'uiValue': ozone_ui})

                    # ================================ Precip Type ================================
                    hourly_forecast_states_list.append({'key': u"h{0}_precipType".format(fore_counter_text), 'value': precip_type})

                    # ================================= Pressure ==================================
                    pressure, pressure_ui = self.fix_corrupted_data(val=pressure)
                    pressure_ui = self.ui_format_pressure(dev=dev, val=pressure_ui)
                    hourly_forecast_states_list.append({'key': u"h{0}_pressure".format(fore_counter_text), 'value': pressure, 'uiValue': pressure_ui})

                    # ================================== Summary ==================================
                    hourly_forecast_states_list.append({'key': u"h{0}_summary".format(fore_counter_text), 'value': summary})

                    # ================================ Temperature ================================
                    temperature, temperature_ui = self.fix_corrupted_data(val=temperature)
                    temperature_ui = self.ui_format_temperature(dev=dev, val=temperature_ui)
                    hourly_forecast_states_list.append({'key': u"h{0}_temperature".format(fore_counter_text), 'value': temperature, 'uiValue': temperature_ui})

                    if forecast_counter == int(dev.pluginProps.get('ui_display', '1')):
                        hour_temp = round(temperature)

                    # ================================= UV Index ==================================
                    uv_index, uv_index_ui = self.fix_corrupted_data(val=uv_index)
                    uv_index_ui = self.ui_format_index(dev, val=uv_index_ui)
                    hourly_forecast_states_list.append({'key': u"h{0}_uvIndex".format(fore_counter_text), 'value': uv_index, 'uiValue': uv_index_ui})

                    # =============================== Wind Bearing ================================
                    wind_bearing, wind_bearing_ui = self.fix_corrupted_data(val=wind_bearing)
                    hourly_forecast_states_list.append({'key': u"h{0}_windBearing".format(fore_counter_text), 'value': wind_bearing, 'uiValue': int(float(wind_bearing_ui))})

                    # ============================= Wind Bearing Name =============================
                    wind_bearing_name = self.ui_format_wind_name(val=wind_bearing)
                    hourly_forecast_states_list.append({'key': u"h{0}_windBearingName".format(fore_counter_text), 'value': wind_bearing_name})

                    # ================================= Wind Gust =================================
                    wind_gust, wind_gust_ui = self.fix_corrupted_data(val=wind_gust)
                    wind_gust_ui = self.ui_format_wind(dev=dev, val=wind_gust_ui)
                    hourly_forecast_states_list.append({'key': u"h{0}_windGust".format(fore_counter_text), 'value': wind_gust, 'uiValue': wind_gust_ui})

                    # ================================ Wind Speed =================================
                    wind_speed, wind_speed_ui = self.fix_corrupted_data(val=wind_speed)
                    wind_speed_ui = self.ui_format_wind(dev=dev, val=wind_speed_ui)
                    hourly_forecast_states_list.append({'key': u"h{0}_windSpeed".format(fore_counter_text), 'value': wind_speed, 'uiValue': wind_speed_ui})

                    # ================================ Visibility =================================
                    visibility, visibility_ui = self.fix_corrupted_data(val=visibility)
                    visibility_ui = self.ui_format_distance(dev, val=visibility_ui)
                    hourly_forecast_states_list.append({'key': u"h{0}_visibility".format(fore_counter_text), 'value': visibility, 'uiValue': visibility_ui})

                    forecast_counter += 1

            new_props = dev.pluginProps
            new_props['address'] = u"{0:.5f}, {1:.5f}".format(float(dev.pluginProps.get('latitude', 'lat')), float(dev.pluginProps.get('longitude', 'long')))
            dev.replacePluginPropsOnServer(new_props)

            display_value = u"{0}{1}".format(int(hour_temp), dev.pluginProps['temperatureUnits'])
            hourly_forecast_states_list.append({'key': 'onOffState', 'value': True, 'uiValue': display_value})

            dev.updateStatesOnServer(hourly_forecast_states_list)
            dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOn)

        except Exception as error:
            self.logger.error(u"Problem parsing hourly forecast data. (Line {0}) {1}".format(sys.exc_traceback.tb_lineno, error))
            hourly_forecast_states_list.append({'key': 'onOffState', 'value': False, 'uiValue': u" "})
            dev.updateStatesOnServer(hourly_forecast_states_list)
            dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)

    # =============================================================================
    def parse_daily_forecast_data(self, dev):
        """
        Parse ten day forecast data to devices

        The parse_daily_forecast_data() method takes 10 day forecast data and parses it to
        device states. See Dark Sky API for value meaning.

        -----

        :param indigo.Device dev:
        """

        daily_forecast_states_list = []

        try:
            location      = (dev.pluginProps['latitude'], dev.pluginProps['longitude'])
            weather_data  = self.masterWeatherDict[location]
            forecast_date = self.masterWeatherDict[location]['daily']['data']
            timezone      = pytz.timezone(weather_data['timezone'])
            today_high    = 0
            today_low     = 0

            # =============================== Daily Summary ===============================
            current_summary = self.nested_lookup(weather_data, keys=('daily', 'summary'))
            daily_forecast_states_list.append({'key': 'daily_summary', 'value': current_summary})

            # ============================= Observation Epoch =============================
            current_observation_epoch = self.nested_lookup(weather_data, keys=('currently', 'time'))
            daily_forecast_states_list.append({'key': 'currentObservationEpoch', 'value': current_observation_epoch, 'uiValue': current_observation_epoch})

            # ============================= Observation Time ==============================
            current_observation_time = u"Last updated on {0}".format(time.strftime('%b %d, %H:%M %p %z', time.localtime(current_observation_epoch)))
            daily_forecast_states_list.append({'key': 'currentObservation', 'value': current_observation_time, 'uiValue': current_observation_time})

            # ============================= Observation 24hr ==============================
            current_observation_24hr = time.strftime("{0} {1}".format(self.date_format, self.time_format), time.localtime(float(current_observation_epoch)))
            daily_forecast_states_list.append({'key': 'currentObservation24hr', 'value': current_observation_24hr})

            forecast_counter = 1
            for observation in forecast_date:
                cloud_cover        = self.nested_lookup(observation, keys=('cloudCover',))
                forecast_time      = self.nested_lookup(observation, keys=('time',))
                humidity           = self.nested_lookup(observation, keys=('humidity',))
                icon               = self.nested_lookup(observation, keys=('icon',))
                ozone              = self.nested_lookup(observation, keys=('ozone',))
                precip_probability = self.nested_lookup(observation, keys=('precipProbability',))
                precip_intensity   = self.nested_lookup(observation, keys=('precipIntensity',))
                precip_type        = self.nested_lookup(observation, keys=('precipType',))
                pressure           = self.nested_lookup(observation, keys=('pressure',))
                summary            = self.nested_lookup(observation, keys=('summary',))
                temperature_high   = self.nested_lookup(observation, keys=('temperatureHigh',))
                temperature_low    = self.nested_lookup(observation, keys=('temperatureLow',))
                uv_index           = self.nested_lookup(observation, keys=('uvIndex',))
                visibility         = self.nested_lookup(observation, keys=('visibility',))
                wind_bearing       = self.nested_lookup(observation, keys=('windBearing',))
                wind_gust          = self.nested_lookup(observation, keys=('windGust',))
                wind_speed         = self.nested_lookup(observation, keys=('windSpeed',))

                if forecast_counter <= 8:

                    # Add leading zero to counter value for device state names 1-9. Although Dark
                    # Sky only provides 8 days of data at this time, if it should decide to
                    # increase that, this will provide for proper sorting of states.
                    if forecast_counter < 10:
                        fore_counter_text = "0{0}".format(forecast_counter)
                    else:
                        fore_counter_text = forecast_counter

                    # ================================ Cloud Cover ================================
                    cloud_cover, cloud_cover_ui = self.fix_corrupted_data(val=cloud_cover * 100)
                    cloud_cover_ui = self.ui_format_percentage(dev=dev, val=cloud_cover_ui)
                    daily_forecast_states_list.append({'key': u"d{0}_cloudCover".format(fore_counter_text), 'value': cloud_cover, 'uiValue': cloud_cover_ui})

                    # =========================== Forecast Date and Day ===========================
                    # We set the daily stuff to the location timezone regardless, because the
                    # timestamp from DS is always 00:00 localized. If we set it using the
                    # server timezone, it may display the wrong day if the location is ahead of
                    # where we are.
                    aware_time         = dt.datetime.fromtimestamp(int(forecast_time), tz=pytz.utc)
                    forecast_date      = timezone.normalize(aware_time).strftime('%Y-%m-%d')
                    forecast_day_long  = timezone.normalize(aware_time).strftime("%A")
                    forecast_day_short = timezone.normalize(aware_time).strftime("%a")

                    daily_forecast_states_list.append({'key': u"d{0}_date".format(fore_counter_text), 'value': forecast_date, 'uiValue': forecast_date})
                    daily_forecast_states_list.append({'key': u"d{0}_day".format(fore_counter_text), 'value': forecast_day_long, 'uiValue': forecast_day_long})
                    daily_forecast_states_list.append({'key': u"d{0}_day_short".format(fore_counter_text), 'value': forecast_day_short, 'uiValue': forecast_day_short})

                    # ================================= Humidity ==================================
                    humidity, humidity_ui = self.fix_corrupted_data(val=humidity * 100)
                    humidity_ui = self.ui_format_percentage(dev=dev, val=humidity_ui)
                    daily_forecast_states_list.append({'key': u"d{0}_humidity".format(fore_counter_text), 'value': humidity, 'uiValue': humidity_ui})

                    # =================================== Icon ====================================
                    daily_forecast_states_list.append({'key': u"d{0}_icon".format(fore_counter_text), 'value': u"{0}".format(icon.replace('-', '_'))})

                    # =================================== Ozone ===================================
                    ozone, ozone_ui = self.fix_corrupted_data(val=ozone)
                    ozone_ui = self.ui_format_index(dev, val=ozone_ui)
                    daily_forecast_states_list.append({'key': u"d{0}_ozone".format(fore_counter_text), 'value': ozone, 'uiValue': ozone_ui})

                    # ============================= Precip Intensity ==============================
                    precip_intensity, precip_intensity_ui = self.fix_corrupted_data(val=precip_intensity)
                    precip_intensity_ui = self.ui_format_rain(dev=dev, val=precip_intensity_ui)
                    daily_forecast_states_list.append({'key': u"d{0}_precipIntensity".format(fore_counter_text), 'value': precip_intensity, 'uiValue': precip_intensity_ui})

                    # ============================ Precip Probability =============================
                    precip_probability, precip_probability_ui = self.fix_corrupted_data(val=precip_probability * 100)
                    precip_probability_ui = self.ui_format_percentage(dev=dev, val=precip_probability_ui)
                    daily_forecast_states_list.append({'key': u"d{0}_precipChance".format(fore_counter_text), 'value': precip_probability, 'uiValue': precip_probability_ui})

                    # ================================ Precip Total ===============================
                    precip_total = precip_intensity * 24
                    precip_total_ui = self.ui_format_rain(dev, val=precip_total)
                    daily_forecast_states_list.append({'key': u"d{0}_precipTotal".format(fore_counter_text), 'value': precip_total, 'uiValue': precip_total_ui})

                    # ================================ Precip Type ================================
                    daily_forecast_states_list.append({'key': u"d{0}_precipType".format(fore_counter_text), 'value': precip_type})

                    # ================================= Pressure ==================================
                    pressure, pressure_ui = self.fix_corrupted_data(val=pressure)
                    pressure_ui = self.ui_format_pressure(dev, val=pressure_ui)
                    daily_forecast_states_list.append({'key': u"d{0}_pressure".format(fore_counter_text), 'value': pressure, 'uiValue': pressure_ui})

                    # ================================== Summary ==================================
                    daily_forecast_states_list.append({'key': u"d{0}_summary".format(fore_counter_text), 'value': summary})

                    # ============================= Temperature High ==============================
                    temperature_high, temperature_high_ui = self.fix_corrupted_data(val=temperature_high)
                    temperature_high_ui = self.ui_format_temperature(dev, val=temperature_high_ui)
                    daily_forecast_states_list.append({'key': u"d{0}_temperatureHigh".format(fore_counter_text), 'value': temperature_high, 'uiValue': temperature_high_ui})

                    if forecast_counter == 1:
                        today_high = round(temperature_high)

                    # ============================== Temperature Low ==============================
                    temperature_low, temperature_low_ui = self.fix_corrupted_data(val=temperature_low)
                    temperature_low_ui = self.ui_format_temperature(dev, val=temperature_low_ui)
                    daily_forecast_states_list.append({'key': u"d{0}_temperatureLow".format(fore_counter_text), 'value': temperature_low, 'uiValue': temperature_low_ui})

                    if forecast_counter == 1:
                        today_low = round(temperature_low)

                    # ================================= UV Index ==================================
                    uv_index, uv_index_ui = self.fix_corrupted_data(val=uv_index)
                    uv_index_ui = self.ui_format_index(dev, val=uv_index_ui)
                    daily_forecast_states_list.append({'key': u"d{0}_uvIndex".format(fore_counter_text), 'value': uv_index, 'uiValue': uv_index_ui})

                    # ================================ Visibility =================================
                    visibility, visibility_ui = self.fix_corrupted_data(val=visibility)
                    visibility_ui = self.ui_format_distance(dev, val=visibility_ui)
                    daily_forecast_states_list.append({'key': u"d{0}_visibility".format(fore_counter_text), 'value': visibility, 'uiValue': visibility_ui})

                    # =============================== Wind Bearing ================================
                    wind_bearing, wind_bearing_ui = self.fix_corrupted_data(val=wind_bearing)
                    daily_forecast_states_list.append({'key': u"d{0}_windBearing".format(fore_counter_text), 'value': wind_bearing, 'uiValue': int(float(wind_bearing_ui))})

                    # ============================= Wind Bearing Name =============================
                    wind_bearing_name = self.ui_format_wind_name(val=wind_bearing)
                    daily_forecast_states_list.append({'key': u"d{0}_windBearingName".format(fore_counter_text), 'value': wind_bearing_name})

                    # ================================= Wind Gust =================================
                    wind_gust, wind_gust_ui = self.fix_corrupted_data(val=wind_gust)
                    wind_gust_ui = self.ui_format_wind(dev, val=wind_gust_ui)
                    daily_forecast_states_list.append({'key': u"d{0}_windGust".format(fore_counter_text), 'value': wind_gust, 'uiValue': wind_gust_ui})

                    # ================================ Wind Speed =================================
                    wind_speed, wind_speed_ui = self.fix_corrupted_data(val=wind_speed)
                    wind_speed_ui = self.ui_format_wind(dev, val=wind_speed_ui)
                    daily_forecast_states_list.append({'key': u"d{0}_windSpeed".format(fore_counter_text), 'value': wind_speed, 'uiValue': wind_speed_ui})

                    forecast_counter += 1

            new_props = dev.pluginProps
            new_props['address'] = u"{0:.5f}, {1:.5f}".format(float(dev.pluginProps.get('latitude', 'lat')), float(dev.pluginProps.get('longitude', 'long')))
            dev.replacePluginPropsOnServer(new_props)

            display_value = u"{0}{2}/{1}{2}".format(int(today_high), int(today_low), dev.pluginProps['temperatureUnits'])
            daily_forecast_states_list.append({'key': 'onOffState', 'value': True, 'uiValue': display_value})

            dev.updateStatesOnServer(daily_forecast_states_list)
            dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOn)

        except Exception as error:
            self.logger.error(u"Problem parsing 10-day forecast data. (Line {0}) {1}".format(sys.exc_traceback.tb_lineno, error))
            daily_forecast_states_list.append({'key': 'onOffState', 'value': False, 'uiValue': u" "})
            dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)
            dev.updateStatesOnServer(daily_forecast_states_list)

    # =============================================================================
    def parse_current_weather_data(self, dev):
        """
        Parse weather data to devices

        The parse_current_weather_data() method takes weather data and parses it to Weather
        Device states. See Dark Sky API for value meaning.

        -----

        :param indigo.Device dev:
        """

        # Reload the date and time preferences in case they've changed.

        weather_states_list = []

        try:

            location     = (dev.pluginProps['latitude'], dev.pluginProps['longitude'])
            weather_data = self.masterWeatherDict[location]

            apparent_temperature = self.nested_lookup(weather_data, keys=('currently', 'apparentTemperature',))
            cloud_cover          = self.nested_lookup(weather_data, keys=('currently', 'cloudCover',))
            dew_point            = self.nested_lookup(weather_data, keys=('currently', 'dewPoint',))
            humidity             = self.nested_lookup(weather_data, keys=('currently', 'humidity',))
            icon                 = self.nested_lookup(weather_data, keys=('currently', 'icon',))
            storm_bearing        = self.nested_lookup(weather_data, keys=('currently', 'nearestStormBearing',))
            storm_distance       = self.nested_lookup(weather_data, keys=('currently', 'nearestStormDistance',))
            ozone                = self.nested_lookup(weather_data, keys=('currently', 'ozone',))
            pressure             = self.nested_lookup(weather_data, keys=('currently', 'pressure',))
            precip_intensity     = self.nested_lookup(weather_data, keys=('currently', 'precipIntensity',))
            precip_probability   = self.nested_lookup(weather_data, keys=('currently', 'precipProbability',))
            summary              = self.nested_lookup(weather_data, keys=('currently', 'summary',))
            temperature          = self.nested_lookup(weather_data, keys=('currently', 'temperature',))
            epoch                = self.nested_lookup(weather_data, keys=('currently', 'time'))
            uv                   = self.nested_lookup(weather_data, keys=('currently', 'uvIndex',))
            visibility           = self.nested_lookup(weather_data, keys=('currently', 'visibility',))
            wind_bearing         = self.nested_lookup(weather_data, keys=('currently', 'windBearing',))
            wind_gust            = self.nested_lookup(weather_data, keys=('currently', 'windGust',))
            wind_speed           = self.nested_lookup(weather_data, keys=('currently', 'windSpeed',))

            # ================================ Time Epoch =================================
            # (Int) Epoch time of the data.
            weather_states_list.append({'key': 'currentObservationEpoch', 'value': int(epoch)})

            # =================================== Time ====================================
            # (string: "Last Updated on MONTH DD, HH:MM AM/PM TZ")
            time_long = u"Last updated on {0}".format(time.strftime('%b %d, %H:%M %p %z', time.localtime(epoch)))
            weather_states_list.append({'key': 'currentObservation', 'value': time_long})

            # ================================ Time 24 Hour ===============================
            time_24 = time.strftime("{0} {1}".format(self.date_format, self.time_format), time.localtime(epoch))
            weather_states_list.append({'key': 'currentObservation24hr', 'value': time_24})

            # ============================= Apparent Temperature ==========================
            apparent_temperature, apparent_temperature_ui = self.fix_corrupted_data(val=apparent_temperature)
            apparent_temperature_ui = self.ui_format_temperature(dev, val=apparent_temperature_ui)
            weather_states_list.append({'key': 'apparentTemperature', 'value': apparent_temperature, 'uiValue': apparent_temperature_ui})
            weather_states_list.append({'key': 'apparentTemperatureIcon', 'value': round(apparent_temperature)})

            # ================================ Cloud Cover ================================
            cloud_cover, cloud_cover_ui = self.fix_corrupted_data(val=float(cloud_cover) * 100)
            cloud_cover_ui = self.ui_format_percentage(dev=dev, val=cloud_cover_ui)
            weather_states_list.append({'key': 'cloudCover', 'value': cloud_cover, 'uiValue': cloud_cover_ui})
            weather_states_list.append({'key': 'cloudCoverIcon', 'value': round(cloud_cover)})

            # ================================= Dew Point =================================
            dew_point, dew_point_ui = self.fix_corrupted_data(val=dew_point)
            dew_point_ui = self.ui_format_temperature(dev, val=dew_point_ui)
            weather_states_list.append({'key': 'dewpoint', 'value': dew_point, 'uiValue': dew_point_ui})
            weather_states_list.append({'key': 'dewpointIcon', 'value': round(dew_point)})

            # ================================= Humidity ==================================
            humidity, humidity_ui = self.fix_corrupted_data(val=float(humidity) * 100)
            humidity_ui = self.ui_format_percentage(dev=dev, val=humidity_ui)
            weather_states_list.append({'key': 'humidity', 'value': humidity, 'uiValue': humidity_ui})
            weather_states_list.append({'key': 'humidityIcon', 'value': round(humidity)})

            # =================================== Icon ====================================
            weather_states_list.append({'key': 'icon', 'value': unicode(icon.replace('-', '_'))})

            # =========================== Nearest Storm Bearing ===========================
            storm_bearing, storm_bearing_ui = self.fix_corrupted_data(val=storm_bearing)
            storm_bearing_ui = self.ui_format_index(dev, val=storm_bearing_ui)
            weather_states_list.append({'key': 'nearestStormBearing', 'value': storm_bearing, 'uiValue': storm_bearing_ui})
            weather_states_list.append({'key': 'nearestStormBearingIcon', 'value': storm_bearing})

            # ========================== Nearest Storm Distance ===========================
            storm_distance, storm_distance_ui = self.fix_corrupted_data(val=storm_distance)
            storm_distance_ui = self.ui_format_distance(dev, val=storm_distance_ui)
            weather_states_list.append({'key': 'nearestStormDistance', 'value': storm_distance, 'uiValue': storm_distance_ui})
            weather_states_list.append({'key': 'nearestStormDistanceIcon', 'value': round(storm_distance)})

            # =================================== Ozone ===================================
            ozone, ozone_ui = self.fix_corrupted_data(val=ozone)
            ozone_ui = self.ui_format_index(dev, val=ozone_ui)
            weather_states_list.append({'key': 'ozone', 'value': ozone, 'uiValue': ozone_ui})
            weather_states_list.append({'key': 'ozoneIcon', 'value': round(ozone)})

            # ============================ Barometric Pressure ============================
            pressure, pressure_ui = self.fix_corrupted_data(val=pressure)
            pressure_ui = self.ui_format_pressure(dev, val=pressure_ui)
            weather_states_list.append({'key': 'pressure', 'value': pressure, 'uiValue': pressure_ui})
            weather_states_list.append({'key': 'pressureIcon', 'value': round(pressure)})

            # ============================= Precip Intensity ==============================
            precip_intensity, precip_intensity_ui = self.fix_corrupted_data(val=precip_intensity)
            precip_intensity_ui = self.ui_format_rain(dev=dev, val=precip_intensity_ui)
            weather_states_list.append({'key': 'precipIntensity', 'value': precip_intensity, 'uiValue': precip_intensity_ui})
            weather_states_list.append({'key': 'precipIntensityIcon', 'value': round(precip_intensity)})

            # ============================ Precip Probability =============================
            precip_probability, precip_probability_ui = self.fix_corrupted_data(val=float(precip_probability) * 100)
            precip_probability_ui = self.ui_format_percentage(dev=dev, val=precip_probability_ui)
            weather_states_list.append({'key': 'precipProbability', 'value': precip_probability, 'uiValue': precip_probability_ui})
            weather_states_list.append({'key': 'precipProbabilityIcon', 'value': round(precip_probability)})

            # ================================== Summary ==================================
            weather_states_list.append({'key': 'summary', 'value': unicode(summary)})

            # ================================ Temperature ================================
            temperature, temperature_ui = self.fix_corrupted_data(val=temperature)
            temperature_ui = self.ui_format_temperature(dev=dev, val=temperature_ui)
            weather_states_list.append({'key': 'temperature', 'value': temperature, 'uiValue': temperature_ui})
            weather_states_list.append({'key': 'temperatureIcon', 'value': round(temperature)})

            # ==================================== UV =====================================
            uv, uv_ui = self.fix_corrupted_data(val=uv)
            uv_ui = self.ui_format_index(dev, val=uv_ui)
            weather_states_list.append({'key': 'uv', 'value': uv, 'uiValue': uv_ui})
            weather_states_list.append({'key': 'uvIcon', 'value': round(uv)})

            # ================================ Visibility =================================
            visibility, visibility_ui = self.fix_corrupted_data(val=visibility)
            visibility_ui = self.ui_format_distance(dev, val=visibility_ui)
            weather_states_list.append({'key': 'visibility', 'value': visibility, 'uiValue': visibility_ui})
            weather_states_list.append({'key': 'visibilityIcon', 'value': round(visibility)})

            # =============================== Wind Bearing ================================
            current_wind_bearing, current_wind_bearing_ui = self.fix_corrupted_data(val=wind_bearing)
            weather_states_list.append({'key': 'windBearing', 'value': current_wind_bearing, 'uiValue': int(float(current_wind_bearing_ui))})
            weather_states_list.append({'key': 'windBearingIcon', 'value': round(current_wind_bearing)})

            # ============================= Wind Bearing Name =============================
            wind_bearing_name = self.ui_format_wind_name(val=current_wind_bearing)
            weather_states_list.append({'key': 'windBearingName', 'value': wind_bearing_name})

            # ================================= Wind Gust =================================
            current_wind_gust, current_wind_gust_ui = self.fix_corrupted_data(val=wind_gust)
            current_wind_gust_ui = self.ui_format_wind(dev=dev, val=current_wind_gust_ui)
            weather_states_list.append({'key': 'windGust', 'value': current_wind_gust, 'uiValue': current_wind_gust_ui})
            weather_states_list.append({'key': 'windGustIcon', 'value': round(current_wind_gust)})

            # ================================ Wind Speed =================================
            current_wind_speed, current_wind_speed_ui = self.fix_corrupted_data(val=wind_speed)
            current_wind_speed_ui = self.ui_format_wind(dev=dev, val=current_wind_speed_ui)
            weather_states_list.append({'key': 'windSpeed', 'value': current_wind_speed, 'uiValue': current_wind_speed_ui})
            weather_states_list.append({'key': 'windSpeedIcon', 'value': round(current_wind_speed)})

            # ================================ Wind String ================================
            weather_states_list.append({'key': 'windString', 'value': u"{0} at {1}{2}".format(wind_bearing_name, round(current_wind_speed), dev.pluginProps['windUnits'])})

            new_props = dev.pluginProps
            new_props['address'] = u"{0:.5f}, {1:.5f}".format(float(dev.pluginProps.get('latitude', 'lat')), float(dev.pluginProps.get('longitude', 'long')))
            dev.replacePluginPropsOnServer(new_props)

            dev.updateStatesOnServer(weather_states_list)
            dev.updateStateImageOnServer(indigo.kStateImageSel.TemperatureSensorOn)
            display_value = self.ui_format_item_list_temperature(val=temperature)
            dev.updateStateOnServer('onOffState', value=True, uiValue=u"{0}{1}".format(display_value, dev.pluginProps['temperatureUnits']))

        except Exception as error:
            self.logger.error(u"Problem parsing weather device data. (Line {0}) {1}".format(sys.exc_traceback.tb_lineno, error))
            dev.updateStateOnServer('onOffState', value=False, uiValue=u" ")
            dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)

    # =============================================================================
    def refresh_weather_data(self):
        """
        Refresh data for plugin devices

        This method refreshes weather data for all devices based on a general
        cycle, Action Item or Plugin Menu call.

        -----
        """

        self.download_interval = dt.timedelta(seconds=int(self.pluginPrefs.get('downloadInterval', '900')))
        self.ds_online         = True

        self.date_format       = self.Formatter.dateFormat()
        self.time_format       = self.Formatter.timeFormat()

        # Check to see if the daily call limit has been reached.
        # try:
        #
        #     self.masterWeatherDict = {}
        #
        #     for dev in indigo.devices.itervalues("self"):

        self.masterWeatherDict = {}

        for dev in indigo.devices.itervalues("self"):

            try:

                if not self.ds_online:
                    break

                if not dev:
                    # There are no FUWU devices, so go to sleep.
                    self.logger.warning(u"There aren't any devices to poll yet. Sleeping.")

                elif not dev.configured:
                    # A device has been created, but hasn't been fully configured yet.
                    self.logger.warning(u"A device has been created, but is not fully configured. Sleeping for a minute while you finish.")

                elif not dev.enabled:
                    dev.updateStateOnServer('onOffState', value=False, uiValue=u"{0}".format("Disabled"))
                    dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)

                elif dev.enabled:
                    dev.updateStateOnServer('onOffState', value=True, uiValue=u" ")

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
                                weather_data_epoch = int(self.masterWeatherDict[location]['currently']['time'])

                            except ValueError:
                                weather_data_epoch = 0

                            good_time = device_epoch <= weather_data_epoch
                            if not good_time:
                                self.logger.warning(u"Latest data are older than data we already have. Skipping {0} update.".format(dev.name))

                        except KeyError:
                            if not self.comm_error:
                                self.logger.warning(u"{0} cannot determine age of data. Skipping until next scheduled poll.".format(dev.name))
                            good_time = False

                        # If the weather dict is not empty, the data are newer than the data we already have let's
                        # update the devices.
                        if self.masterWeatherDict != {} and good_time:

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
                self.last_successful_poll = (u"{0:%Y-%m-%d}".format(now))
                self.pluginPrefs['lastSuccessfulPoll'] = self.last_successful_poll

                # Update next poll time
                self.next_poll = (u"{0:%Y-%m-%d %H:%M:%S}".format(now + self.download_interval))
                self.pluginPrefs['nextPoll'] = self.next_poll

            except Exception as error:
                self.logger.error(u"Problem parsing Weather data. Dev: {0} (Line: {1} Error: {2})".format(dev.name, sys.exc_traceback.tb_lineno, error))

        self.logger.info(u"Weather data cycle complete.")

    # =============================================================================
    def trigger_processing(self):
        """
        Fire various triggers for plugin devices

        Weather Location Offline:
        The trigger_processing method will examine the time of the last weather location
        update and, if the update exceeds the time delta specified in a Fantastically
        Useful Weather Utility Plugin Weather Location Offline trigger, the trigger
        will be fired. The plugin examines the value of the latest
        "currentObservationEpoch" and *not* the Indigo Last Update value.

        An additional event that will cause a trigger to be fired is if the weather
        location temperature is less than -55 which indicates that a data value is
        invalid.

        Severe Weather Alerts:
        This trigger will fire if a weather location has at least one severe weather
        alert.

        Note that trigger processing will only occur during routine weather update
        cycles and will not be triggered when a data refresh is called from the Indigo
        Plugins menu.

        -----
        """

        # time_format = '%Y-%m-%d %H:%M:%S'

        # Reconstruct the masterTriggerDict in case it has changed.
        self.masterTriggerDict = {unicode(trigger.pluginProps['listOfDevices']): (trigger.pluginProps['offlineTimer'], trigger.id) for trigger in indigo.triggers.iter(filter="self.weatherSiteOffline")}

        try:

            # Iterate through all the plugin devices to see if a related trigger should be fired
            for dev in indigo.devices.itervalues(filter='self'):

                # ========================== Weather Location Offline ==========================
                # If the device is in the masterTriggerDict, it has an offline trigger
                if str(dev.id) in self.masterTriggerDict.keys():

                    # Process the trigger only if the device is enabled
                    if dev.enabled:

                        trigger_id = self.masterTriggerDict[str(dev.id)][1]  # Indigo trigger ID

                        if indigo.triggers[trigger_id].pluginTypeId == 'weatherSiteOffline':

                            offline_delta = dt.timedelta(minutes=int(self.masterTriggerDict.get(unicode(dev.id), ('60', ''))[0]))

                            # Convert currentObservationEpoch to a localized datetime object
                            current_observation_epoch = float(dev.states['currentObservationEpoch'])
                            current_observation = time.strftime('%Y-%m-%d %H:%M', time.localtime(current_observation_epoch))
                            current_observation = parse(current_observation)

                            # Time elapsed since last observation
                            diff = dt.datetime.now() - current_observation

                            # If the observation is older than offline_delta
                            if diff >= offline_delta:
                                total_seconds = int(diff.total_seconds())
                                days, remainder = divmod(total_seconds, 60 * 60 * 24)
                                hours, remainder = divmod(remainder, 60 * 60)
                                minutes, seconds = divmod(remainder, 60)

                                # Note that we leave seconds off, but it could easily be added if needed.
                                diff_msg = u'{0} days, {1} hrs, {2} mins'.format(days, hours, minutes)

                                dev.updateStateImageOnServer(indigo.kStateImageSel.TemperatureSensor)
                                dev.updateStateOnServer('onOffState', value='offline')

                                if indigo.triggers[trigger_id].enabled:
                                    self.logger.warning(u"{0} location appears to be offline for {1}".format(dev.name, diff_msg))
                                    indigo.trigger.execute(trigger_id)

                            # If the temperature observation is lower than -55
                            elif dev.states['temperature'] <= -55.0:
                                dev.updateStateImageOnServer(indigo.kStateImageSel.TemperatureSensor)
                                dev.updateStateOnServer('onOffState', value='offline')

                                if indigo.triggers[trigger_id].enabled:
                                    self.logger.warning(u"{0} location appears to be offline (ambient temperature lower than -55).".format(dev.name))
                                    indigo.trigger.execute(trigger_id)

                # ============================ Severe Weather Alert ============================
                for trigger in indigo.triggers.itervalues('self.weatherAlert'):

                    if int(trigger.pluginProps['listOfDevices']) == dev.id and dev.states['alertStatus'] and trigger.enabled:

                        self.logger.warning(u"{0} location has at least one severe weather alert.".format(dev.name))
                        indigo.trigger.execute(trigger.id)

        except KeyError:
            pass

    # =============================================================================
    def ui_format_distance(self, dev, val):
        """
        Format distance data for Indigo UI

        Adds distance units to rain values for display in control pages, etc.

        -----

        :param indigo.Devices dev:
        :param val:
        """

        distance_units = dev.pluginProps['distanceUnits']

        try:
            return u"{0:0.{1}f}{2}".format(float(val), self.pluginPrefs['uiDistanceDecimal'], distance_units)

        except ValueError:
            return u"{0}{1}".format(val, distance_units)

    # =============================================================================
    def ui_format_index(self, dev, val):
        """
        Format index data for Indigo UI

        Adds index units to rain values for display in control pages, etc.

        -----

        :param indigo.Devices dev:
        :param val:
        """

        index_units = dev.pluginProps['indexUnits']

        try:
            return u"{0:0.{1}f}{2}".format(float(val), self.pluginPrefs['uiIndexDecimal'], index_units)

        except ValueError:
            return u"{0}{1}".format(val, index_units)

    # =============================================================================
    def ui_format_item_list_temperature(self, val):
        """
        Format temperature values for Indigo UI

        Adjusts the decimal precision of the temperature value for the Indigo Item
        List. Note: this method needs to return a string rather than a Unicode string
        (for now.)

        -----

        :param val:
        """

        try:
            return u"{0:0.{1}f}".format(val, int(self.pluginPrefs.get('itemListTempDecimal', '1')))
        except ValueError:
            return u"{0}".format(val)

    # =============================================================================
    def ui_format_pressure(self, dev, val):
        """
        Format index data for Indigo UI

        Adds index units to rain values for display in control pages, etc.

        -----

        :param indigo.Devices dev:
        :param val:
        """

        index_units = dev.pluginProps['pressureUnits']

        try:
            return u"{0:0.{1}f}{2}".format(float(val), self.pluginPrefs['uiIndexDecimal'], index_units)

        except ValueError:
            return u"{0}{1}".format(val, index_units)

    # =============================================================================
    def ui_format_percentage(self, dev, val):
        """
        Format percentage data for Indigo UI

        Adjusts the decimal precision of percentage values for display in control
        pages, etc.

        -----

        :param indigo.Device dev:
        :param str val:
        """

        percentage_decimal = int(self.pluginPrefs.get('uiPercentageDecimal', '1'))
        percentage_units = unicode(dev.pluginProps.get('percentageUnits', ''))

        try:
            return u"{0:0.{1}f}{2}".format(float(val), percentage_decimal, percentage_units)

        except ValueError:
            return u"{0}{1}".format(val, percentage_units)

    # =============================================================================
    def ui_format_rain(self, dev, val):
        """
        Format rain data for Indigo UI

        Adds rain units to rain values for display in control pages, etc.

        -----

        :param indigo.Devices dev:
        :param val:
        """

        # Some devices use the prop 'rainUnits' and some use the prop
        # 'rainAmountUnits'.  So if we fail on the first, try the second and--if still
        # not successful, return and empty string.
        try:
            rain_units = dev.pluginProps['rainUnits']
        except KeyError:
            rain_units = dev.pluginProps.get('rainAmountUnits', '')

        if val in ("NA", "N/A", "--", ""):
            return val

        try:
            return u"{0:0.2f}{1}".format(float(val), rain_units)

        except ValueError:
            return u"{0}".format(val)

    # =============================================================================
    def ui_format_temperature(self, dev, val):
        """
        Format temperature data for Indigo UI

        Adjusts the decimal precision of certain temperature values and appends the
        desired units string for display in control pages, etc.

        -----

        :param indigo.Device dev:
        :param val:
        """

        temp_decimal      = int(self.pluginPrefs.get('uiTempDecimal', '1'))
        temperature_units = unicode(dev.pluginProps.get('temperatureUnits', ''))

        try:
            return u"{0:0.{precision}f}{1}".format(float(val), temperature_units, precision=temp_decimal)

        except ValueError:
            return u"--"

    # =============================================================================
    def ui_format_wind(self, dev, val):
        """
        Format wind data for Indigo UI

        Adjusts the decimal precision of certain wind values for display in control
        pages, etc.

        -----

        :param indigo.Device dev:
        :param val:
        """

        wind_decimal = int(self.pluginPrefs.get('uiWindDecimal', '1'))
        wind_units   = unicode(dev.pluginProps.get('windUnits', ''))

        try:
            return u"{0:0.{precision}f}{1}".format(float(val), wind_units, precision=wind_decimal)

        except ValueError:
            return u"{0}".format(val)

    # =============================================================================
    def ui_format_wind_name(self, val):
        """
        Format wind data for Indigo UI

        Adjusts the decimal precision of certain wind values for display in control
        pages, etc.

        Credit to Indigo Forum user forestfield for conversion routine.
        -----

        :param val:
        """

        long_short = self.pluginPrefs.get('uiWindName', 'Long')
        val        = round(val)

        if long_short == 'Long':
            return ['North', 'Northeast', 'East', 'Southeast', 'South', 'Southwest', 'West', 'Northwest'][int(((val + 22.5) % 360) / 45)]

        else:
            return ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'][int(((val + 22.5) % 360) / 45)]
