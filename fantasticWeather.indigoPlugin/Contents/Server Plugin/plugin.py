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

# TODO: Refactor plugin config last success. This could key off the response headers and always be the most current (it now changes based on automatic updates only.)
# TODO: Consider temperature for item list UI for daily (day's high) and hourly (hour's high)
# TODO: Wind string (Southeast at 4 mph)

# TODO: Time format should adjust all times (i.e., hourly)
# TODO: more logging of bad conditions and less logging of good conditions.

# TODO: add feature to display dates and times as either server-local time or location-local time.

# ================================== IMPORTS ==================================

# Built-in modules
import datetime as dt
import logging
import pytz
import xml
import requests
import simplejson
import socket
import sys
import time
import urllib   # (satellite imagery fallback)
import urllib2  # (weather data fallback)

# Third-party modules
from DLFramework import indigoPluginUpdateChecker
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
__version__   = "0.1.07"

# =============================================================================

kDefaultPluginPrefs = {
    u'alertLogging': False,           # Write severe weather alerts to the log?
    u'apiKey': "",                    # DS requires an api key.
    u'callCounter': "999",            # DS call limit.
    u'dailyCallCounter': "0",         # Number of API calls today.
    u'dailyCallDay': "1970-01-01",    # API call counter date.
    u'dailyCallLimitReached': False,  # Has the daily call limit been reached?
    u'downloadInterval': "900",       # Frequency of weather updates.
    u'itemListTempDecimal': "1",      # Precision for Indigo Item List.
    u'language': "en",                # Language for DS text.
    u'lastSuccessfulPoll': "1970-01-01 00:00:00",  # Last successful plugin cycle
    u'launchParameters': "https://www.darksky.net",  # url for launch API button
    u'nextPoll': "",                  # Last successful plugin cycle
    u'noAlertLogging': False,         # Suppresses "no active alerts" logging.
    u'showDebugLevel': "30",          # Logger level.
    u'uiDateFormat': "YYYY-MM-DD",    # Preferred date format string.
    u'uiPercentageDecimal': "1",      # Precision for Indigo UI display (humidity).
    u'uiTempDecimal': "1",            # Precision for Indigo UI display (temperature).
    u'uiTimeFormat': "military",      # Preferred time format string.
    u'uiWindDecimal': "1",            # Precision for Indigo UI display (wind).
    u'updaterEmail': "",              # Email to notify of plugin updates.
    u'updaterEmailsEnabled': False    # Notification of plugin updates wanted.
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
        self.updater           = indigoPluginUpdateChecker.updateChecker(self, "https://raw.githubusercontent.com/DaveL17/Fantastic-Weather/master/fantastic_weather_version.html")
        self.ds_online         = True
        self.pluginPrefs['dailyCallLimitReached'] = False

        # ========================== API Poll Values ==========================
        last_poll = self.pluginPrefs.get('lastSuccessfulPoll', "1970-01-01 00:00:00")
        try:
            self.last_poll_attempt = dt.datetime.strptime(last_poll, '%Y-%m-%d %H:%M:%S')
        except ValueError:
            self.last_poll_attempt = dt.datetime.strptime(last_poll, '%Y-%m-%d %H:%M:%S.%f')

        next_poll = self.pluginPrefs.get('lastSuccessfulPoll', "1970-01-01 00:00:00")
        try:
            self.next_poll_attempt = dt.datetime.strptime(next_poll, '%Y-%m-%d %H:%M:%S')
        except ValueError:
            self.next_poll_attempt = dt.datetime.strptime(next_poll, '%Y-%m-%d %H:%M:%S.%f')

        # =========================== Version Check ===========================
        if int(indigo.server.version[0]) >= 7:
            pass
        else:
            raise Exception(u"The plugin requires Indigo 7 or later.")

        # ====================== Initialize DLFramework =======================

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
    def closedPrefsConfigUi(self, valuesDict, userCancelled):

        self.logger.debug(u"closedPrefsConfigUi called.")

        if userCancelled:
            self.logger.debug(u"User prefs dialog cancelled.")

        if not userCancelled:
            self.indigo_log_handler.setLevel(int(valuesDict['showDebugLevel']))

            # ============================= Update Poll Time ==============================
            self.download_interval = dt.timedelta(seconds=int(self.pluginPrefs.get('downloadInterval', '900')))
            last_poll              = self.pluginPrefs.get('lastSuccessfulPoll', "1970-01-01 00:00:00")

            try:
                next_poll = dt.datetime.strptime(last_poll, '%Y-%m-%d %H:%M:%S') + self.download_interval
            except ValueError:
                next_poll = dt.datetime.strptime(last_poll, '%Y-%m-%d %H:%M:%S.%f') + self.download_interval

            self.pluginPrefs['nextPoll'] = dt.datetime.strftime(next_poll, '%Y-%m-%d %H:%M:%S')

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
                    if current_on_off_state_ui not in ['Disabled', 'Enabled', '']:
                        try:
                            units_dict = {'auto': '', 'ca': 'C', 'uk2': 'C', 'us': 'F', 'si': 'C'}
                            units = units_dict[self.pluginPrefs.get('units', '')]
                            display_value = u"{0:.{1}f} {2}{3}".format(dev.states['temperature'], int(self.pluginPrefs['itemListTempDecimal']), dev.pluginProps['temperatureUnits'], units)

                        except KeyError:
                            display_value = u""

                        dev.updateStateOnServer('onOffState', value=current_on_off_state, uiValue=display_value)

            self.logger.debug(u"User prefs saved.")

    # =============================================================================
    def deviceStartComm(self, dev):

        self.logger.debug(u"Starting Device: {0}".format(dev.name))

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

        self.logger.debug(u"Stopping Device: {0}".format(dev.name))

        # =========================== Set Device Icon to Off ==========================
        if dev.deviceTypeId == 'Weather':
            dev.updateStateImageOnServer(indigo.kStateImageSel.TemperatureSensor)
        else:
            dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)

        dev.updateStateOnServer('onOffState', value=False, uiValue=u"Disabled")

    # =============================================================================
    def getDeviceConfigUiValues(self, valuesDict, typeId, devId):

        self.logger.debug(u"getDeviceConfigUiValues called.")

        if typeId == 'Daily':
            # weatherSummaryEmailTime is set by a generator. We need this bit to pre-
            # populate the control with the default value when a new device is created.
            if 'weatherSummaryEmailTime' not in valuesDict.keys():
                valuesDict['weatherSummaryEmailTime'] = "01:00"

        if typeId != 'satelliteImageDownloader':
            # If new device, lat/long will be zero. so let's start with the lat/long of
            # the Indigo server.
            if 'latitude' not in valuesDict.keys():
                lat_long = indigo.server.getLatitudeAndLongitude()
                valuesDict['latitude'] = lat_long[0]
                valuesDict['longitude'] = lat_long[1]

        return valuesDict

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

                # If the next poll attempt hasn't been changed to tomorrow, let's update it
                if self.next_poll_attempt == "1970-01-01 00:00:00" or not self.next_poll_attempt.day > dt.datetime.now().day:
                    self.next_poll_attempt = self.last_poll_attempt + self.download_interval
                    self.pluginPrefs['nextPoll'] = dt.datetime.strftime(self.next_poll_attempt, '%Y-%m-%d %H:%M:%S')

                # If we have reached the time for the next scheduled poll
                if dt.datetime.now() > self.next_poll_attempt:

                    self.last_poll_attempt = dt.datetime.now()
                    self.pluginPrefs['lastSuccessfulPoll'] = dt.datetime.strftime(self.last_poll_attempt, '%Y-%m-%d %H:%M:%S')

                    self.refresh_weather_data()
                    self.trigger_processing()

                    # Report results of download timer.
                    plugin_cycle_time = (dt.datetime.now() - self.last_poll_attempt)
                    plugin_cycle_time = (dt.datetime.min + plugin_cycle_time).time()

                    self.logger.debug(u"[  Plugin execution time: {0} seconds  ]".format(plugin_cycle_time.strftime('%S.%f')))
                    self.logger.debug(u"{0:{1}^40}".format(' Plugin Cycle Complete ', '='))

                # Wait 30 seconds before trying again.
                self.sleep(30)

        except self.StopThread as error:
            self.logger.debug(u"StopThread: (Line {0}) {1}".format(sys.exc_traceback.tb_lineno, error))
            self.logger.debug(u"Stopping Fantastically Useful Weather Utility thread.")

    # =============================================================================
    def shutdown(self):

        self.pluginIsShuttingDown = True

    # =============================================================================
    def startup(self):

        pass

    # =============================================================================
    def triggerStartProcessing(self, trigger):

        self.logger.debug(u"Starting Trigger: {0}".format(trigger.name))

        dev_id = trigger.pluginProps['listOfDevices']
        timer  = trigger.pluginProps.get('offlineTimer', '60')

        # ============================= masterTriggerDict =============================
        # masterTriggerDict contains information on Weather Location Offline triggers.
        # {dev.id: (timer, trigger.id)}
        if trigger.configured and trigger.pluginTypeId == 'weatherSiteOffline':
            self.masterTriggerDict[dev_id] = (timer, trigger.id)

    # =============================================================================
    def triggerStopProcessing(self, trigger):

        self.logger.debug(u"Stopping {0} trigger.".format(trigger.name))

    # =============================================================================
    def validateDeviceConfigUi(self, valuesDict, typeID, devId):

        error_msg_dict = indigo.Dict()

        if valuesDict['isWeatherDevice']:

            # ================================= Latitude ==================================
            if not -90 <= float(valuesDict['latitude']) <= 90:
                error_msg_dict['latitude'] = u"The latitude value must be between -90 and 90."
                error_msg_dict['showAlertText'] = u"Latitude Range Error\n\nThe latitude value must be between -90 and 90"
                return False, valuesDict, error_msg_dict

            # ================================= Longitude =================================
            if not -180 <= float(valuesDict['longitude']) <= 180:
                error_msg_dict['longitude'] = u"The longitude value must be between -90 and 90."
                error_msg_dict['showAlertText'] = u"Latitude Range Error\n\nThe latitude value must be between -180 and 180"
                return False, valuesDict, error_msg_dict

        return True

    # =============================================================================
    def validateEventConfigUi(self, valuesDict, typeId, eventId):

        self.logger.debug(u"validateEventConfigUi called.")

        dev_id         = valuesDict['list_of_devices']
        error_msg_dict = indigo.Dict()

        # Weather Site Offline trigger
        if typeId == 'weatherSiteOffline':

            self.masterTriggerDict = {trigger.pluginProps['listOfDevices']: (trigger.pluginProps['offlineTimer'], trigger.id) for trigger in indigo.triggers.iter(filter="self.weatherSiteOffline")}

            # ======================== Validate Trigger Unique ========================
            # Limit weather location offline triggers to one per device
            if dev_id in self.masterTriggerDict.keys() and eventId != self.masterTriggerDict[dev_id][1]:
                existing_trigger_id = int(self.masterTriggerDict[dev_id][1])
                error_msg_dict['listOfDevices'] = u"Please select a weather device without an existing offline trigger."
                error_msg_dict['showAlertText'] = u"There is an existing weather offline trigger for this location." \
                                                  u"\n\n[{0}]\n\n" \
                                                  u"You must select a location that does not have an existing trigger.".format(indigo.triggers[existing_trigger_id].name)
                valuesDict['listOfDevices'] = ''
                return False, valuesDict, error_msg_dict

            # ============================ Validate Timer =============================
            try:
                if int(valuesDict['offlineTimer']) <= 0:
                    raise ValueError

            except ValueError:
                error_msg_dict['offlineTimer'] = u"You must enter a valid time value in minutes (positive integer greater than zero)."
                error_msg_dict['showAlertText'] = u"Offline Time Error.\n\nYou must enter a valid offline time value. The value must be a positive integer that is greater than zero."
                valuesDict['offlineTimer'] = ''
                return False, valuesDict, error_msg_dict

        return True, valuesDict

    # =============================================================================
    def validatePrefsConfigUi(self, valuesDict):

        self.logger.debug(u"validatePrefsConfigUi called.")

        api_key_config      = valuesDict['apiKey']
        call_counter_config = valuesDict['callCounter']
        error_msg_dict      = indigo.Dict()
        update_email        = valuesDict['updaterEmail']
        update_wanted       = valuesDict['updaterEmailsEnabled']

        # Test api_keyconfig setting.
        try:
            if len(api_key_config) == 0:
                # Mouse over text error:
                error_msg_dict['apiKey'] = u"The plugin requires an API key to function. See help for details."
                # Screen error:
                error_msg_dict['showAlertText'] = (u"The API key that you have entered is invalid.\n\n"
                                                   u"Reason: You have not entered a key value. Valid API keys contain alpha-numeric characters only (no spaces.)")
                return False, valuesDict, error_msg_dict

            elif " " in api_key_config:
                error_msg_dict['apiKey'] = u"The API key can't contain a space."
                error_msg_dict['showAlertText'] = (u"The API key that you have entered is invalid.\n\n"
                                                   u"Reason: The key you entered contains a space. Valid API keys contain alpha-numeric characters only.")
                return False, valuesDict, error_msg_dict

            # Test call limit config setting.
            elif not int(call_counter_config):
                error_msg_dict['callCounter'] = u"The call counter can only contain integers."
                error_msg_dict['showAlertText'] = u"The call counter that you have entered is invalid.\n\nReason: Call counters can only contain integers."
                return False, valuesDict, error_msg_dict

            elif call_counter_config < 0:
                error_msg_dict['callCounter'] = u"The call counter value must be a positive integer."
                error_msg_dict['showAlertText'] = u"The call counter that you have entered is invalid.\n\nReason: Call counters must be positive integers."
                return False, valuesDict, error_msg_dict

            # Test plugin update notification settings.
            elif update_wanted and update_email == "":
                error_msg_dict['updaterEmail'] = u"If you want to be notified of updates, you must supply an email address."
                error_msg_dict['showAlertText'] = u"The notification settings that you have entered are invalid.\n\nReason: You must supply a valid notification email address."
                return False, valuesDict, error_msg_dict

            elif update_wanted and "@" not in update_email:
                error_msg_dict['updaterEmail'] = u"Valid email addresses have at least one @ symbol in them (foo@bar.com)."
                error_msg_dict['showAlertText'] = u"The notification settings that you have entered are invalid.\n\nReason: You must supply a valid notification email address."
                return False, valuesDict, error_msg_dict

        except Exception as error:
            self.logger.error(u"Exception in validatePrefsConfigUi API key test. (Line {0}) {1}".format(sys.exc_traceback.tb_lineno, error))

        return True, valuesDict

    # =============================================================================
    # ============================== Plugin Methods ===============================
    # =============================================================================
    def action_refresh_weather(self, valuesDict):
        """
        Refresh all weather as a result of an action call

        The action_refresh_weather() method calls the refresh_weather_data() method to
        request a complete refresh of all weather data (Actions.XML call.)

        -----

        :param indigo.Dict valuesDict:
        """

        self.logger.debug(u"Refresh all weather data.")

        self.refresh_weather_data()

    # =============================================================================
    def check_version_now(self):
        """
        Immediate call to determine if running latest version

        The check_version_now() method will call the Indigo Plugin Update Checker based
        on a user request.

        -----
        """

        try:
            self.updater.checkVersionNow()

        except Exception as error:
            self.logger.warning(u"Unable to check plugin update status. (Line {0}) {1}".format(sys.exc_traceback.tb_lineno, error))

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
    def dark_sky_site(self, valuesDict):
        """
        Launch a web browser to register for API

        Launch a web browser session with the valuesDict parm containing the target
        URL.

        -----

        :param indigo.Dict valuesDict:
        """

        self.browserOpen(valuesDict['launchParameters'])

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
            self.logger.info(u"Unable to write to Indigo Log folder.")

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

            # Get the desired summary email time and convert it for test.
            summary_time = dev.pluginProps.get('weatherSummaryEmailTime', '01:00')
            summary_time = dt.datetime.strptime(summary_time, '%H:%M')

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

                cloud_cover        = self.nested_lookup(forecast_day, keys=('cloudCover',))
                forecast_time      = self.nested_lookup(forecast_day, keys=('time',))
                forecast_day_name  = time.strftime('%A', time.localtime(float(forecast_time)))
                humidity           = self.nested_lookup(forecast_day, keys=('humidity',))
                ozone              = self.nested_lookup(forecast_day, keys=('ozone',))
                precip_probability = self.nested_lookup(forecast_day, keys=('precipProbability',))
                precip_type        = self.nested_lookup(forecast_day, keys=('precipType',))
                pressure           = self.nested_lookup(forecast_day, keys=('pressure',))
                summary            = self.nested_lookup(forecast_day, keys=('summary',))
                temperature_high   = self.nested_lookup(forecast_day, keys=('temperatureHigh',))
                temperature_low    = self.nested_lookup(forecast_day, keys=('temperatureLow',))
                uv_index           = self.nested_lookup(forecast_day, keys=('uvIndex',))
                visibility         = self.nested_lookup(forecast_day, keys=('visibility',))
                wind_bearing       = self.nested_lookup(forecast_day, keys=('windBearing',))
                wind_gust          = self.nested_lookup(forecast_day, keys=('windGust',))
                wind_name          = self.ui_format_wind_name(state_name='wind_bearing', val=wind_bearing)
                wind_speed         = self.nested_lookup(forecast_day, keys=('windSpeed',))

                email_body += u"Indigo Fantastic Weather Device: {0}\n".format(dev.name)
                email_body += u"{0:-<60}\n\n".format('')
                email_body += u"{0}:\n".format(forecast_day_name)
                email_body += u"{0:-<60}\n".format('')
                email_body += u"{0}\n\n".format(summary)
                email_body += u"High: {0}\n".format(temperature_high)
                email_body += u"Low: {0}\n".format(temperature_low)
                email_body += u"{0} chance of {1}\n".format(precip_probability, precip_type)
                email_body += u"Winds out of the {0} at {1} -- gusting to {2}\n".format(wind_name, wind_speed, wind_gust)
                email_body += u"Clouds: {0}\n".format(cloud_cover)
                email_body += u"Humidity: {0}\n".format(humidity)
                email_body += u"Ozone: {0}\n".format(ozone)
                email_body += u"Pressure: {0}\n".format(pressure)
                email_body += u"UV: {0}\n".format(uv_index)
                email_body += u"Visibility: {0}\n".format(visibility)

                indigo.server.sendEmailTo(self.pluginPrefs['updaterEmail'], subject=u"Daily Weather Summary", body=email_body)
                dev.updateStateOnServer('weatherSummaryEmailSent', value=True)
            else:
                pass

        except (KeyError, IndexError) as error:
            dev.updateStateOnServer('weatherSummaryEmailSent', value=True, uiValue=u"Err")
            self.logger.debug(u"Unable to compile forecast data for {0}. (Line {1}) {2}".format(dev.name, sys.exc_traceback.tb_lineno, error))

        except Exception as error:
            self.logger.warning(u"Unable to send forecast email message. Will keep trying. (Line {0}) {1}".format(sys.exc_traceback.tb_lineno, error))

    # =============================================================================
    def fix_corrupted_data(self, state_name, val):
        """
        Format corrupted and missing data

        Sometimes DS receives corrupted data from personal weather stations. Could be
        zero, positive value or "--" or "-999.0" or "-9999.0". This method tries to
        "fix" these values for proper display.

        -----

        :param str state_name:
        :param str or float val:
        """

        try:
            val = float(val)

            if val < -55.728:  # -99 F = -55.728 C
                self.logger.debug(u"Formatted {0} data. Got: {1} Returning: (-99.0, --)".format(state_name, val))
                return -99.0, u"--"

            else:
                return val, str(val)

        except (ValueError, TypeError):
            self.logger.debug(u"Imputing {0} data. Got: {1} Returning: (-99.0, --)".format(state_name, val))
            return -99.0, u"--"

    # =============================================================================
    def generator_time(self, filter="", valuesDict=None, typeId="", targetId=0):
        """
        List of hours generator

        Creates a list of times for use in setting the desired time for weather
        forecast emails to be sent.

        -----
        :param str filter:
        :param indigo.Dict valuesDict:
        :param str typeId:
        :param int targetId:
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
                    self.logger.debug(u"Source: {0}".format(source))
                    self.logger.debug(u"Destination: {0}".format(destination))
                    r = requests.get(source, stream=True, timeout=20)

                    with open(destination, 'wb') as img:
                        for chunk in r.iter_content(2000):
                            img.write(chunk)

                except requests.exceptions.ConnectionError:
                    if not self.comm_error:
                        self.logger.warning(u"Error downloading satellite image. (No comm.)".format(sys.exc_traceback.tb_lineno))
                        self.comm_error = True
                    dev.updateStateOnServer('onOffState', value=False, uiValue=u"No comm")
                    dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)
                    return

                # Requests not installed
                except NameError:
                    urllib.urlretrieve(source, destination)

                dev.updateStateOnServer('onOffState', value=True, uiValue=u" ")
                dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOn)

                # Report results of download timer.
                data_cycle_time = (dt.datetime.now() - get_data_time)
                data_cycle_time = (dt.datetime.min + data_cycle_time).time()

                self.logger.debug(u"[  {0} download: {1} seconds  ]".format(dev.name, data_cycle_time.strftime('%S.%f')))

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

        try:

            # Tuple of (lat, long) for tracking locations
            api_key   = self.pluginPrefs['apiKey']
            language  = self.pluginPrefs['language']
            latitude  = dev.pluginProps['latitude']
            longitude = dev.pluginProps['longitude']
            units     = self.pluginPrefs['units']
            location  = (latitude, longitude)

            if location in self.masterWeatherDict.keys():
                # We already have the data; no need to get it again.
                self.logger.debug(u"Location [{0}] already in master weather dictionary.".format(location))

            else:
                # Get the data and add it to the masterWeatherDict.
                url = u'https://api.darksky.net/forecast/{0}/{1},{2}?exclude="minutely"&extend=""&units={3}&lang={4}'.format(api_key, latitude, longitude, units, language)

                self.logger.debug(u"URL for {0}: {1}".format(location, url))

                # Start download timer.
                get_data_time = dt.datetime.now()

                try:
                    f = requests.get(url, timeout=20)
                    simplejson_string = f.text  # We convert the file to a json object below, so we don't use requests' built-in decoder.

                # If requests is not installed, try urllib2 instead.
                except NameError:
                    try:
                        # Connect to Dark Sky and retrieve data.
                        socket.setdefaulttimeout(20)
                        f = urllib2.urlopen(url)
                        simplejson_string = f.read()

                    except Exception as error:
                        if not self.comm_error:
                            self.logger.warning(u"Unable to reach Dark Sky. Sleeping until next scheduled poll.")
                            self.logger.debug(u"Unable to reach Dark Sky after 20 seconds. (Line {0}) {1}".format(sys.exc_traceback.tb_lineno, error))
                            self.comm_error = True

                        for dev in indigo.devices.itervalues("self"):
                            dev.updateStateOnServer("onOffState", value=False, uiValue=u" ")
                            dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)

                        return

                # Report results of download timer.
                data_cycle_time = (dt.datetime.now() - get_data_time)
                data_cycle_time = (dt.datetime.min + data_cycle_time).time()

                if simplejson_string != "":
                    self.logger.debug(u"[  {0} download: {1} seconds  ]".format(location, data_cycle_time.strftime('%S.%f')))

                # Load the JSON data from the file.
                try:
                    parsed_simplejson = simplejson.loads(simplejson_string, encoding="utf-8")

                except Exception as error:
                    self.logger.error(u"Unable to decode data. (Line {0}) {1}".format(sys.exc_traceback.tb_lineno, error))
                    parsed_simplejson = {}

                # Add location JSON to master weather dictionary.
                self.logger.debug(u"Adding weather data for {0} to Master Weather Dictionary.".format(location))
                self.masterWeatherDict[location] = parsed_simplejson

                # Increment the call counter
                self.pluginPrefs['dailyCallCounter'] = f.headers['X-Forecast-API-Calls']

                # We've been successful, mark device online
                self.comm_error = False
                dev.updateStateOnServer('onOffState', value=True)

        except Exception as error:
            if not self.comm_error:
                self.logger.warning(u"Unable to reach Dark Sky. Sleeping until next scheduled poll.")
                self.logger.debug(u"Unable to reach Dark Sky after 20 seconds. (Line {0}) {1}".format(sys.exc_traceback.tb_lineno, error))
                self.comm_error = True

            # Unable to fetch the JSON. Mark all devices as 'false'.
            for dev in indigo.devices.itervalues("self"):
                if dev.enabled:
                    # Mark device as off and dim the icon.
                    dev.updateStateOnServer('onOffState', value=False, uiValue=u"No comm")
                    self.comm_error = True
                    dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)

            self.ds_online = False
            return {}

        # We could have come here from several different places. Return to whence we came to further process the weather data.
        self.ds_online = True
        return self.masterWeatherDict

    # =============================================================================
    def list_of_devices(self, filter, valuesDict, targetId, triggerId):
        """
        Generate list of devices for offline trigger

        list_of_devices returns a list of plugin devices limited to weather
        devices only (not forecast devices, etc.) when the Weather Location Offline
        trigger is fired.

        -----

        :param str filter:
        :param indigo.Dict valuesDict:
        :param str targetId:
        :param int triggerId:
        """

        for key, value in valuesDict.iteritems():
            self.logger.debug(u"{0}: {1}".format(key, value))

        return [(dev.id, dev.name) for dev in indigo.devices.itervalues(filter='self')]

    # =============================================================================
    def list_of_weather_devices(self, filter, valuesDict, targetId, triggerId):
        """
        Generate list of devices for severe weather alert trigger

        list_of_weather_devices returns a list of plugin devices limited to weather
        devices only (not forecast devices, etc.) when severe weather alert trigger is
        fired.

        -----

        :param str filter:
        :param indigo.Dict valuesDict:
        :param str targetId:
        :param int triggerId:
        """

        for key, value in valuesDict.iteritems():
            self.logger.debug(u"{0}: {1}".format(key, value))

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

        alerts_states_list = []

        try:
            alert_array = []
            alerts_logging    = self.pluginPrefs.get('alertLogging', True)  # Whether to log alerts
            alerts_suppressed = dev.pluginProps.get('suppressWeatherAlerts', False)  # Suppress alert messages for device
            no_alerts_logging  = self.pluginPrefs.get('noAlertLogging', False)  # Suppress 'No Alert' messages

            location     = (dev.pluginProps['latitude'], dev.pluginProps['longitude'])
            weather_data = self.masterWeatherDict[location]
            alerts_data  = self.nested_lookup(weather_data, keys=('alerts',))

            # ============================= Delete Old Alerts =============================
            for alert_counter in range(1, 6):
                for state in ['alertDescription', 'alertExpires', 'alertRegions', 'alertSeverity', 'alertTime', 'alertTime', 'alertTitle', 'alertUri']:
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
                        alert_expires = time.strftime('%Y-%m-%d %H:%M', time.localtime(float(alert_array[alert][1])))
                        alert_time    = time.strftime('%Y-%m-%d %H:%M', time.localtime(float(alert_array[alert][4])))

                        alerts_states_list.append({'key': u"{0}{1}".format('alertDescription', alert_counter), 'value': u"{0}".format(alert_array[alert][0])})
                        alerts_states_list.append({'key': u"{0}{1}".format('alertExpires', alert_counter), 'value': u"{0}".format(alert_expires)})
                        alerts_states_list.append({'key': u"{0}{1}".format('alertRegions', alert_counter), 'value': u"{0}".format(alert_array[alert][2])})
                        alerts_states_list.append({'key': u"{0}{1}".format('alertSeverity', alert_counter), 'value': u"{0}".format(alert_array[alert][3])})
                        alerts_states_list.append({'key': u"{0}{1}".format('alertTime', alert_counter), 'value': u"{0}".format(alert_time)})
                        alerts_states_list.append({'key': u"{0}{1}".format('alertTitle', alert_counter), 'value': u"{0}".format(alert_array[alert][5])})
                        alerts_states_list.append({'key': u"{0}{1}".format('alertUri', alert_counter), 'value': u"{0}".format(alert_array[alert][6])})
                        alert_counter += 1

                    # Write alert to the log?
                    if alerts_logging and not alerts_suppressed:
                        self.logger.info(u"\n{0}".format(alert_array[alert][0]))

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

            # =============================== Sunrise Time ================================
            sunrise_time = int(sun_rise)
            sunrise_time = time.strftime("{0} {1}".format(self.date_format, self.time_format), time.localtime(sunrise_time))
            astronomy_states_list.append({'key': 'sunriseTime', 'value': sunrise_time})

            # ================================ Sunset Time ================================
            sunset_time = int(sun_set)
            sunset_time = time.strftime("{0} {1}".format(self.date_format, self.time_format), time.localtime(sunset_time))
            astronomy_states_list.append({'key': 'sunsetTime', 'value': sunset_time})

            # ================================ Moon Phase =================================
            moon_phase, moon_phase_ui = self.fix_corrupted_data(state_name='moonPhase', val=float(moon_phase * 100))
            moon_phase_ui = self.ui_format_percentage(dev=dev, state_name='moonPhase', val=moon_phase_ui)
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

            fore_counter = 1
            for observation in forecast_data:

                if fore_counter <= 24:

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
                    if fore_counter < 10:
                        fore_counter_text = u"0{0}".format(fore_counter)
                    else:
                        fore_counter_text = fore_counter

                    # =============================== Forecast Epoch ==============================
                    hourly_forecast_states_list.append({'key': u"h{0}_epoch".format(fore_counter_text), 'value': forecast_time})

                    # =========================== Forecast Hour and Day ===========================
                    if preferred_time == "time_here":
                        local_time       = time.localtime(float(forecast_time))

                        forecast_day     = time.strftime('%A', local_time)
                        forecast_hour    = time.strftime('%H:%M', local_time)
                        forecast_hour_ui = time.strftime(self.time_format, local_time)

                        hourly_forecast_states_list.append({'key': u"h{0}_day".format(fore_counter_text), 'value': forecast_day, 'uiValue': forecast_day})
                        hourly_forecast_states_list.append({'key': u"h{0}_hour".format(fore_counter_text), 'value': forecast_hour, 'uiValue': forecast_hour_ui})

                    elif preferred_time == "time_there":
                        aware_time       = dt.datetime.fromtimestamp(int(forecast_time), tz=pytz.utc)

                        forecast_day     = timezone.normalize(aware_time).strftime("%A")
                        forecast_hour    = timezone.normalize(aware_time).strftime("%H:%M")
                        forecast_hour_ui = time.strftime(self.time_format, timezone.normalize(aware_time).timetuple())

                        hourly_forecast_states_list.append({'key': u"h{0}_day".format(fore_counter_text), 'value': forecast_day, 'uiValue': forecast_day})
                        hourly_forecast_states_list.append({'key': u"h{0}_hour".format(fore_counter_text), 'value': forecast_hour, 'uiValue': forecast_hour_ui})

                    # ================================ Cloud Cover ================================
                    cloud_cover, cloud_cover_ui = self.fix_corrupted_data(state_name="h{0}_cloudCover".format(fore_counter_text), val=cloud_cover * 100)
                    cloud_cover_ui = self.ui_format_percentage(dev=dev, state_name="h{0}_cloudCover".format(fore_counter_text), val=cloud_cover_ui)
                    hourly_forecast_states_list.append({'key': u"h{0}_cloudCover".format(fore_counter_text), 'value': cloud_cover, 'uiValue': cloud_cover_ui})

                    # ================================= Humidity ==================================
                    humidity, humidity_ui = self.fix_corrupted_data(state_name="h{0}_humidity".format(fore_counter_text), val=humidity * 100)
                    humidity_ui = self.ui_format_percentage(dev=dev, state_name="h{0}_humidity".format(fore_counter_text), val=humidity_ui)
                    hourly_forecast_states_list.append({'key': u"h{0}_humidity".format(fore_counter_text), 'value': humidity, 'uiValue': humidity_ui})

                    # ============================= Precip Intensity ==============================
                    precip_intensity, precip_intensity_ui = self.fix_corrupted_data(state_name="h{0}_precipIntensity".format(fore_counter_text), val=precip_intensity)
                    precip_intensity_ui = self.ui_format_rain(dev=dev, state_name="h{0}_precipIntensity".format(fore_counter_text), val=precip_intensity_ui)
                    hourly_forecast_states_list.append({'key': u"h{0}_precipIntensity".format(fore_counter_text), 'value': precip_intensity, 'uiValue': precip_intensity_ui})

                    # ============================ Precip Probability =============================
                    precip_probability, precip_probability_ui = self.fix_corrupted_data(state_name="h{0}_precipChance".format(fore_counter_text), val=precip_probability * 100)
                    precip_probability_ui = self.ui_format_percentage(dev=dev, state_name="h{0}_precipChance".format(fore_counter_text), val=precip_probability_ui)
                    hourly_forecast_states_list.append({'key': u"h{0}_precipChance".format(fore_counter_text), 'value': precip_probability, 'uiValue': precip_probability_ui})

                    # =================================== Icon ====================================
                    hourly_forecast_states_list.append({'key': u"h{0}_icon".format(fore_counter_text), 'value': u"{0}".format(icon.replace('-', '_'))})

                    # TODO: This code is temporary and can be safely removed.
                    if icon not in self.pluginPrefs['hourlyIconNames']:
                        self.pluginPrefs['hourlyIconNames'] += u"{0}, ".format(icon)

                    # =================================== Ozone ===================================
                    ozone, ozone_ui = self.fix_corrupted_data(state_name="h{0}_ozone".format(fore_counter_text), val=ozone)
                    ozone_ui = self.ui_format_index(dev, state_name="h{0}_ozone".format(fore_counter_text), val=ozone_ui)
                    hourly_forecast_states_list.append({'key': u"h{0}_ozone".format(fore_counter_text), 'value': ozone, 'uiValue': ozone_ui})

                    # ================================ Precip Type ================================
                    hourly_forecast_states_list.append({'key': u"h{0}_precipType".format(fore_counter_text), 'value': precip_type})

                    # ================================= Pressure ==================================
                    pressure, pressure_ui = self.fix_corrupted_data(state_name="h{0}_pressure".format(fore_counter_text), val=pressure)
                    pressure_ui = self.ui_format_pressure(dev=dev, state_name="h{0}_pressure".format(fore_counter_text), val=pressure_ui)
                    hourly_forecast_states_list.append({'key': u"h{0}_pressure".format(fore_counter_text), 'value': pressure, 'uiValue': pressure_ui})

                    # ================================== Summary ==================================
                    hourly_forecast_states_list.append({'key': u"h{0}_summary".format(fore_counter_text), 'value': summary})

                    # ================================ Temperature ================================
                    temperature, temperature_ui = self.fix_corrupted_data(state_name="h{0}_temperature".format(fore_counter_text), val=temperature)
                    temperature_ui = self.ui_format_temperature(dev=dev, state_name="h{0}_temperature".format(fore_counter_text), val=temperature_ui)
                    hourly_forecast_states_list.append({'key': u"h{0}_temperature".format(fore_counter_text), 'value': temperature, 'uiValue': temperature_ui})

                    # ================================= UV Index ==================================
                    uv_index, uv_index_ui = self.fix_corrupted_data(state_name="h{0}_uvIndex".format(fore_counter_text), val=uv_index)
                    uv_index_ui = self.ui_format_index(dev, state_name="h{0}_uvIndex".format(fore_counter_text), val=uv_index_ui)
                    hourly_forecast_states_list.append({'key': u"h{0}_uvIndex".format(fore_counter_text), 'value': uv_index, 'uiValue': uv_index_ui})

                    # =============================== Wind Bearing ================================
                    wind_bearing, wind_bearing_ui = self.fix_corrupted_data(state_name="h{0}_windBearing".format(fore_counter_text), val=wind_bearing)
                    hourly_forecast_states_list.append({'key': u"h{0}_windBearing".format(fore_counter_text), 'value': wind_bearing, 'uiValue': int(float(wind_bearing_ui))})

                    # ============================= Wind Bearing Name =============================
                    wind_bearing_name = self.ui_format_wind_name(state_name="h{0}_windBearingName".format(fore_counter_text), val=wind_bearing)
                    hourly_forecast_states_list.append({'key': u"h{0}_windBearingName".format(fore_counter_text), 'value': wind_bearing_name})

                    # ================================= Wind Gust =================================
                    wind_gust, wind_gust_ui = self.fix_corrupted_data(state_name="h{0}_windGust".format(fore_counter_text), val=wind_gust)
                    wind_gust_ui = self.ui_format_wind(dev=dev, state_name="h{0}_windGust".format(fore_counter_text), val=wind_gust_ui)
                    hourly_forecast_states_list.append({'key': u"h{0}_windGust".format(fore_counter_text), 'value': wind_gust, 'uiValue': wind_gust_ui})

                    # ================================ Wind Speed =================================
                    wind_speed, wind_speed_ui = self.fix_corrupted_data(state_name="h{0}_windSpeed".format(fore_counter_text), val=wind_speed)
                    wind_speed_ui = self.ui_format_wind(dev=dev, state_name="h{0}_windSpeed".format(fore_counter_text), val=wind_speed_ui)
                    hourly_forecast_states_list.append({'key': u"h{0}_windSpeed".format(fore_counter_text), 'value': wind_speed, 'uiValue': wind_speed_ui})

                    # ================================ Visibility =================================
                    visibility, visibility_ui = self.fix_corrupted_data(state_name="h{0}_visibility".format(fore_counter_text), val=visibility)
                    visibility_ui = self.ui_format_distance(dev, state_name="h{0}_visibility".format(fore_counter_text), val=visibility_ui)
                    hourly_forecast_states_list.append({'key': u"h{0}_visibility".format(fore_counter_text), 'value': visibility, 'uiValue': visibility_ui})

                    fore_counter += 1

            new_props = dev.pluginProps
            new_props['address'] = u"{0:.5f}, {1:.5f}".format(float(dev.pluginProps.get('latitude', 'lat')), float(dev.pluginProps.get('longitude', 'long')))
            dev.replacePluginPropsOnServer(new_props)

            hourly_forecast_states_list.append({'key': 'onOffState', 'value': True, 'uiValue': u" "})
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
            location       = (dev.pluginProps['latitude'], dev.pluginProps['longitude'])
            weather_data   = self.masterWeatherDict[location]
            forecast_date   = self.masterWeatherDict[location]['daily']['data']
            preferred_time = dev.pluginProps.get('time_zone', 'time_here')
            timezone       = pytz.timezone(weather_data['timezone'])

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
                    cloud_cover, cloud_cover_ui = self.fix_corrupted_data(state_name="d{0}_cloudCover".format(fore_counter_text), val=cloud_cover * 100)
                    cloud_cover_ui = self.ui_format_percentage(dev=dev, state_name="d{0}_cloudCover".format(fore_counter_text), val=cloud_cover_ui)
                    daily_forecast_states_list.append({'key': u"d{0}_cloudCover".format(fore_counter_text), 'value': cloud_cover, 'uiValue': cloud_cover_ui})

                    # =========================== Forecast Date and Day ===========================
                    if preferred_time == "time_here":
                        local_time = time.localtime(float(forecast_time))

                        forecast_date = time.strftime('%Y-%m-%d', local_time)
                        forecast_day  = time.strftime('%A', local_time)

                        daily_forecast_states_list.append({'key': u"d{0}_date".format(fore_counter_text), 'value': forecast_date, 'uiValue': forecast_date})
                        daily_forecast_states_list.append({'key': u"d{0}_day".format(fore_counter_text), 'value': forecast_day, 'uiValue': forecast_day})

                    elif preferred_time == "time_there":
                        aware_time = dt.datetime.fromtimestamp(int(forecast_time), tz=pytz.utc)

                        forecast_date = timezone.normalize(aware_time).strftime('%Y-%m-%d')
                        forecast_day  = timezone.normalize(aware_time).strftime("%A")

                        daily_forecast_states_list.append({'key': u"d{0}_date".format(fore_counter_text), 'value': forecast_date, 'uiValue': forecast_date})
                        daily_forecast_states_list.append({'key': u"d{0}_day".format(fore_counter_text), 'value': forecast_day, 'uiValue': forecast_day})

                    # ================================= Humidity ==================================
                    humidity, humidity_ui = self.fix_corrupted_data(state_name="d{0}_humidity".format(fore_counter_text), val=humidity * 100)
                    humidity_ui = self.ui_format_percentage(dev=dev, state_name="d{0}_humidity".format(fore_counter_text), val=humidity_ui)
                    daily_forecast_states_list.append({'key': u"d{0}_humidity".format(fore_counter_text), 'value': humidity, 'uiValue': humidity_ui})

                    # =================================== Icon ====================================
                    daily_forecast_states_list.append({'key': u"d{0}_icon".format(fore_counter_text), 'value': u"{0}".format(icon.replace('-', '_'))})

                    # TODO: This code is temporary and can be safely removed.
                    if icon not in self.pluginPrefs['dailyIconNames']:
                        self.pluginPrefs['dailyIconNames'] += u"{0}, ".format(icon)

                    # =================================== Ozone ===================================
                    ozone, ozone_ui = self.fix_corrupted_data(state_name="d{0}_ozone".format(fore_counter_text), val=ozone)
                    ozone_ui = self.ui_format_index(dev, state_name="d{0}_ozone".format(fore_counter_text), val=ozone_ui)
                    daily_forecast_states_list.append({'key': u"d{0}_ozone".format(fore_counter_text), 'value': ozone, 'uiValue': ozone_ui})

                    # ============================= Precip Intensity ==============================
                    precip_intensity, precip_intensity_ui = self.fix_corrupted_data(state_name="d{0}_precipIntensity".format(fore_counter_text), val=precip_intensity)
                    precip_intensity_ui = self.ui_format_rain(dev=dev, state_name="d{0}_precipIntensity".format(fore_counter_text), val=precip_intensity_ui)
                    daily_forecast_states_list.append({'key': u"d{0}_precipIntensity".format(fore_counter_text), 'value': precip_intensity, 'uiValue': precip_intensity_ui})

                    # ============================ Precip Probability =============================
                    precip_probability, precip_probability_ui = self.fix_corrupted_data(state_name="d{0}_precipChance".format(fore_counter_text), val=precip_probability * 100)
                    precip_probability_ui = self.ui_format_percentage(dev=dev, state_name="d{0}_precipChance".format(fore_counter_text), val=precip_probability_ui)
                    daily_forecast_states_list.append({'key': u"d{0}_precipChance".format(fore_counter_text), 'value': precip_probability, 'uiValue': precip_probability_ui})

                    # ================================ Precip Total ===============================
                    precip_total = precip_intensity * 24
                    precip_total_ui = u"{0:.2f}".format(precip_total)
                    daily_forecast_states_list.append({'key': u"d{0}_precipTotal".format(fore_counter_text), 'value': precip_total, 'uiValue': precip_total_ui})

                    # ================================ Precip Type ================================
                    daily_forecast_states_list.append({'key': u"d{0}_precipType".format(fore_counter_text), 'value': precip_type})

                    # ================================= Pressure ==================================
                    pressure, pressure_ui = self.fix_corrupted_data(state_name="d{0}_pressure".format(fore_counter_text), val=pressure)
                    pressure_ui = self.ui_format_pressure(dev, state_name="d{0}_pressure".format(fore_counter_text), val=pressure_ui)
                    daily_forecast_states_list.append({'key': u"d{0}_pressure".format(fore_counter_text), 'value': pressure, 'uiValue': pressure_ui})

                    # ================================== Summary ==================================
                    daily_forecast_states_list.append({'key': u"d{0}_summary".format(fore_counter_text), 'value': summary})

                    # ============================= Temperature High ==============================
                    temperature_high, temperature_high_ui = self.fix_corrupted_data(state_name="d{0}_temperatureHigh".format(fore_counter_text), val=temperature_high)
                    temperature_high_ui = self.ui_format_temperature(dev, state_name="d{0}_temperatureHigh".format(fore_counter_text), val=temperature_high_ui)
                    daily_forecast_states_list.append({'key': u"d{0}_temperatureHigh".format(fore_counter_text), 'value': temperature_high, 'uiValue': temperature_high_ui})

                    # ============================== Temperature Low ==============================
                    temperature_low, temperature_low_ui = self.fix_corrupted_data(state_name="d{0}_temperatureLow".format(fore_counter_text), val=temperature_low)
                    temperature_low_ui = self.ui_format_temperature(dev, state_name="d{0}_temperatureLow".format(fore_counter_text), val=temperature_low_ui)
                    daily_forecast_states_list.append({'key': u"d{0}_temperatureLow".format(fore_counter_text), 'value': temperature_low, 'uiValue': temperature_low_ui})

                    # ================================= UV Index ==================================
                    uv_index, uv_index_ui = self.fix_corrupted_data(state_name="d{0}_uvIndex".format(fore_counter_text), val=uv_index)
                    uv_index_ui = self.ui_format_index(dev, state_name="d{0}_uvIndex".format(fore_counter_text), val=uv_index_ui)
                    daily_forecast_states_list.append({'key': u"d{0}_uvIndex".format(fore_counter_text), 'value': uv_index, 'uiValue': uv_index_ui})

                    # ================================ Visibility =================================
                    visibility, visibility_ui = self.fix_corrupted_data(state_name="d{0}_visibility".format(fore_counter_text), val=visibility)
                    visibility_ui = self.ui_format_distance(dev, state_name="d{0}_visibility".format(fore_counter_text), val=visibility_ui)
                    daily_forecast_states_list.append({'key': u"d{0}_visibility".format(fore_counter_text), 'value': visibility, 'uiValue': visibility_ui})

                    # =============================== Wind Bearing ================================
                    wind_bearing, wind_bearing_ui = self.fix_corrupted_data(state_name="d{0}_windBearing".format(fore_counter_text), val=wind_bearing)
                    daily_forecast_states_list.append({'key': u"d{0}_windBearing".format(fore_counter_text), 'value': wind_bearing, 'uiValue': int(float(wind_bearing_ui))})

                    # ============================= Wind Bearing Name =============================
                    wind_bearing_name = self.ui_format_wind_name(state_name="d{0}_windBearingName".format(fore_counter_text), val=wind_bearing)
                    daily_forecast_states_list.append({'key': u"d{0}_windBearingName".format(fore_counter_text), 'value': wind_bearing_name})

                    # ================================= Wind Gust =================================
                    wind_gust, wind_gust_ui = self.fix_corrupted_data(state_name="d{0}_windGust".format(fore_counter_text), val=wind_gust)
                    wind_gust_ui = self.ui_format_wind(dev, state_name="d{0}_windGust".format(fore_counter_text), val=wind_gust_ui)
                    daily_forecast_states_list.append({'key': u"d{0}_windGust".format(fore_counter_text), 'value': wind_gust, 'uiValue': wind_gust_ui})

                    # ================================ Wind Speed =================================
                    wind_speed, wind_speed_ui = self.fix_corrupted_data(state_name="d{0}_windSpeed".format(fore_counter_text), val=wind_speed)
                    wind_speed_ui = self.ui_format_wind(dev, state_name="d{0}_windSpeed".format(fore_counter_text), val=wind_speed_ui)
                    daily_forecast_states_list.append({'key': u"d{0}_windSpeed".format(fore_counter_text), 'value': wind_speed, 'uiValue': wind_speed_ui})

                    forecast_counter += 1

            new_props = dev.pluginProps
            new_props['address'] = u"{0:.5f}, {1:.5f}".format(float(dev.pluginProps.get('latitude', 'lat')), float(dev.pluginProps.get('longitude', 'long')))
            dev.replacePluginPropsOnServer(new_props)

            daily_forecast_states_list.append({'key': 'onOffState', 'value': True, 'uiValue': u" "})
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
            apparent_temperature, apparent_temperature_ui = self.fix_corrupted_data(state_name='apparentTemperature', val=apparent_temperature)
            apparent_temperature_ui = self.ui_format_temperature(dev, state_name='apparentTemperature', val=apparent_temperature_ui)
            weather_states_list.append({'key': 'apparentTemperature', 'value': apparent_temperature, 'uiValue': apparent_temperature_ui})
            weather_states_list.append({'key': 'apparentTemperatureIcon', 'value': round(apparent_temperature)})

            # ================================ Cloud Cover ================================
            cloud_cover, cloud_cover_ui = self.fix_corrupted_data(state_name='cloudCover', val=float(cloud_cover) * 100)
            cloud_cover_ui = self.ui_format_percentage(dev=dev, state_name="cloudCover", val=cloud_cover_ui)
            weather_states_list.append({'key': 'cloudCover', 'value': cloud_cover, 'uiValue': cloud_cover_ui})
            weather_states_list.append({'key': 'cloudCoverIcon', 'value': round(cloud_cover)})

            # ================================= Dew Point =================================
            dew_point, dew_point_ui = self.fix_corrupted_data(state_name='dewpoint', val=dew_point)
            dew_point_ui = self.ui_format_temperature(dev, state_name='dewpoint', val=dew_point_ui)
            weather_states_list.append({'key': 'dewpoint', 'value': dew_point, 'uiValue': dew_point_ui})
            weather_states_list.append({'key': 'dewpointIcon', 'value': round(dew_point)})

            # ================================= Humidity ==================================
            humidity, humidity_ui = self.fix_corrupted_data(state_name='humidity', val=float(humidity) * 100)
            humidity_ui = self.ui_format_percentage(dev=dev, state_name="humidity", val=humidity_ui)
            weather_states_list.append({'key': 'humidity', 'value': humidity, 'uiValue': humidity_ui})
            weather_states_list.append({'key': 'humidityIcon', 'value': round(humidity)})

            # =================================== Icon ====================================
            # (string: clear-day, clear-night, rain, snow, sleet, wind, fog, cloudy, partly-cloudy-day, or partly-cloudy-night...)
            weather_states_list.append({'key': 'icon', 'value': unicode(icon.replace('-', '_'))})

            # TODO: This code is temporary and can be safely removed.
            if icon not in self.pluginPrefs['weatherIconNames']:
                self.pluginPrefs['weatherIconNames'] += u"{0}, ".format(icon)

            # =========================== Nearest Storm Bearing ===========================
            storm_bearing, storm_bearing_ui = self.fix_corrupted_data(state_name='nearestStormBearing', val=storm_bearing)
            storm_bearing_ui = self.ui_format_index(dev, state_name='nearestStormBearing', val=storm_bearing_ui)
            weather_states_list.append({'key': 'nearestStormBearing', 'value': storm_bearing, 'uiValue': storm_bearing_ui})
            weather_states_list.append({'key': 'nearestStormBearingIcon', 'value': storm_bearing})

            # ========================== Nearest Storm Distance ===========================
            storm_distance, storm_distance_ui = self.fix_corrupted_data(state_name='nearestStormDistance', val=storm_distance)
            storm_distance_ui = self.ui_format_distance(dev, state_name='nearestStormDistance', val=storm_distance_ui)
            weather_states_list.append({'key': 'nearestStormDistance', 'value': storm_distance, 'uiValue': storm_distance_ui})
            weather_states_list.append({'key': 'nearestStormDistanceIcon', 'value': round(storm_distance)})

            # =================================== Ozone ===================================
            ozone, ozone_ui = self.fix_corrupted_data(state_name='ozone', val=ozone)
            ozone_ui = self.ui_format_index(dev, state_name='ozone', val=ozone_ui)
            weather_states_list.append({'key': 'ozone', 'value': ozone, 'uiValue': ozone_ui})
            weather_states_list.append({'key': 'ozoneIcon', 'value': round(ozone)})

            # ============================ Barometric Pressure ============================
            pressure, pressure_ui = self.fix_corrupted_data(state_name='pressure', val=pressure)
            pressure_ui = self.ui_format_pressure(dev, state_name='pressure', val=pressure_ui)
            weather_states_list.append({'key': 'pressure', 'value': pressure, 'uiValue': pressure_ui})
            weather_states_list.append({'key': 'pressureIcon', 'value': round(pressure)})

            # ============================= Precip Intensity ==============================
            precip_intensity, precip_intensity_ui = self.fix_corrupted_data(state_name='precipIntensity', val=precip_intensity)
            precip_intensity_ui = self.ui_format_rain(dev=dev, state_name="precipIntensity", val=precip_intensity_ui)
            weather_states_list.append({'key': 'precipIntensity', 'value': precip_intensity, 'uiValue': precip_intensity_ui})
            weather_states_list.append({'key': 'precipIntensityIcon', 'value': round(precip_intensity)})

            # ============================ Precip Probability =============================
            precip_probability, precip_probability_ui = self.fix_corrupted_data(state_name='precipProbability', val=float(precip_probability) * 100)
            precip_probability_ui = self.ui_format_percentage(dev=dev, state_name="precipProbability", val=precip_probability_ui)
            weather_states_list.append({'key': 'precipProbability', 'value': precip_probability, 'uiValue': precip_probability_ui})
            weather_states_list.append({'key': 'precipProbabilityIcon', 'value': round(precip_probability)})

            # ================================== Summary ==================================
            weather_states_list.append({'key': 'summary', 'value': unicode(summary)})

            # ================================ Temperature ================================
            temperature, temperature_ui = self.fix_corrupted_data(state_name='temperature', val=temperature)
            temperature_ui = self.ui_format_temperature(dev=dev, state_name="temperature", val=temperature_ui)
            weather_states_list.append({'key': 'temperature', 'value': temperature, 'uiValue': temperature_ui})
            weather_states_list.append({'key': 'temperatureIcon', 'value': round(temperature)})

            # ==================================== UV =====================================
            uv, uv_ui = self.fix_corrupted_data(state_name='uv', val=uv)
            uv_ui = self.ui_format_index(dev, state_name='uv', val=uv_ui)
            weather_states_list.append({'key': 'uv', 'value': uv, 'uiValue': uv_ui})
            weather_states_list.append({'key': 'uvIcon', 'value': round(uv)})

            # ================================ Visibility =================================
            visibility, visibility_ui = self.fix_corrupted_data(state_name='current_visibility', val=visibility)
            visibility_ui = self.ui_format_distance(dev, state_name='visibility', val=visibility_ui)
            weather_states_list.append({'key': 'visibility', 'value': visibility, 'uiValue': visibility_ui})
            weather_states_list.append({'key': 'visibilityIcon', 'value': round(visibility)})

            # =============================== Wind Bearing ================================
            current_wind_bearing, current_wind_bearing_ui = self.fix_corrupted_data(state_name='current_wind_bearing', val=wind_bearing)
            weather_states_list.append({'key': 'windBearing', 'value': current_wind_bearing, 'uiValue': int(float(current_wind_bearing_ui))})
            weather_states_list.append({'key': 'windBearingIcon', 'value': round(current_wind_bearing)})

            # ============================= Wind Bearing Name =============================
            wind_bearing_name = self.ui_format_wind_name(state_name='windBearingName', val=current_wind_bearing)
            weather_states_list.append({'key': 'windBearingName', 'value': wind_bearing_name})

            # ================================= Wind Gust =================================
            current_wind_gust, current_wind_gust_ui = self.fix_corrupted_data(state_name='current_wind_gust', val=wind_gust)
            current_wind_gust_ui = self.ui_format_wind(dev=dev, state_name="current_wind_gust", val=current_wind_gust_ui)
            weather_states_list.append({'key': 'windGust', 'value': current_wind_gust, 'uiValue': current_wind_gust_ui})
            weather_states_list.append({'key': 'windGustIcon', 'value': round(current_wind_gust)})

            # ================================ Wind Speed =================================
            current_wind_speed, current_wind_speed_ui = self.fix_corrupted_data(state_name='current_wind_speed', val=wind_speed)
            current_wind_speed_ui = self.ui_format_wind(dev=dev, state_name="current_wind_speed", val=current_wind_speed_ui)
            weather_states_list.append({'key': 'windSpeed', 'value': current_wind_speed, 'uiValue': current_wind_speed_ui})
            weather_states_list.append({'key': 'windSpeedIcon', 'value': round(current_wind_speed)})

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
        try:

            self.masterWeatherDict = {}

            for dev in indigo.devices.itervalues("self"):

                if not self.ds_online:
                    break

                if not dev:
                    # There are no FUWU devices, so go to sleep.
                    self.logger.info(u"There aren't any devices to poll yet. Sleeping.")

                elif not dev.configured:
                    # A device has been created, but hasn't been fully configured yet.
                    self.logger.info(u"A device has been created, but is not fully configured. Sleeping for a minute while you finish.")

                elif not dev.enabled:
                    self.logger.debug(u"{0}: device communication is disabled. Skipping.".format(dev.name))
                    dev.updateStateOnServer('onOffState', value=False, uiValue=u"{0}".format("Disabled"))
                    dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)

                elif dev.enabled:
                    self.logger.debug(u"Processing device: {0}".format(dev.name))

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
                                self.logger.info(u"Latest data are older than data we already have. Skipping {0} update.".format(dev.name))

                        except KeyError:
                            if not self.comm_error:
                                self.logger.info(u"{0} cannot determine age of data. Skipping until next scheduled poll.".format(dev.name))
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

            self.logger.debug(u"{0} locations polled: {1}".format(len(self.masterWeatherDict.keys()), self.masterWeatherDict.keys()))

        except Exception as error:
            self.logger.error(u"Problem parsing Weather data. Dev: {0} (Line: {1} Error: {2})".format(dev.name, sys.exc_traceback.tb_lineno, error))

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

        time_format = '%Y-%m-%d %H:%M:%S'

        # Reconstruct the masterTriggerDict in case it has changed.
        self.masterTriggerDict = {unicode(trigger.pluginProps['listOfDevices']): (trigger.pluginProps['offlineTimer'], trigger.id) for trigger in indigo.triggers.iter(filter="self.weatherSiteOffline")}
        self.logger.debug(u"Rebuild Master Trigger Dict: {0}".format(self.masterTriggerDict))

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
                            self.logger.debug(u"Offline weather location delta: {0}".format(offline_delta))

                            # Convert currentObservationEpoch to a localized datetime object
                            current_observation_epoch = float(dev.states['currentObservationEpoch'])

                            current_observation = time.strftime(time_format, time.localtime(current_observation_epoch))
                            current_observation = dt.datetime.strptime(current_observation, time_format)

                            # Time elapsed since last observation
                            diff = indigo.server.getTime() - current_observation

                            # If the observation is older than offline_delta
                            if diff >= offline_delta:
                                total_seconds = int(diff.total_seconds())
                                days, remainder = divmod(total_seconds, 60 * 60 * 24)
                                hours, remainder = divmod(remainder, 60 * 60)
                                minutes, seconds = divmod(remainder, 60)

                                # Note that we leave seconds off, but it could easily be added if needed.
                                diff_msg = u'{} days, {} hrs, {} mins'.format(days, hours, minutes)

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
    def ui_format_distance(self, dev, state_name, val):
        """
        Format distance data for Indigo UI

        Adds distance units to rain values for display in control pages, etc.

        -----

        :param indigo.Devices dev:
        :param str state_name:
        :param val:
        """

        distance_units = dev.pluginProps['distanceUnits']

        try:
            return u"{0:0.{1}f}{2}".format(float(val), self.pluginPrefs['uiDistanceDecimal'], distance_units)

        except ValueError:
            return u"{0}{1}".format(val, distance_units)

    # =============================================================================
    def ui_format_index(self, dev, state_name, val):
        """
        Format index data for Indigo UI

        Adds index units to rain values for display in control pages, etc.

        -----

        :param indigo.Devices dev:
        :param str state_name:
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
    def ui_format_pressure(self, dev, state_name, val):
        """
        Format index data for Indigo UI

        Adds index units to rain values for display in control pages, etc.

        -----

        :param indigo.Devices dev:
        :param str state_name:
        :param val:
        """

        index_units = dev.pluginProps['pressureUnits']

        try:
            return u"{0:0.{1}f}{2}".format(float(val), self.pluginPrefs['uiIndexDecimal'], index_units)

        except ValueError:
            return u"{0}{1}".format(val, index_units)

    # =============================================================================
    def ui_format_percentage(self, dev, state_name, val):
        """
        Format percentage data for Indigo UI

        Adjusts the decimal precision of percentage values for display in control
        pages, etc.

        -----

        :param indigo.Device dev:
        :param str state_name:
        :param str val:
        """

        percentage_decimal = int(self.pluginPrefs.get('uiPercentageDecimal', '1'))
        percentage_units = unicode(dev.pluginProps.get('percentageUnits', ''))

        try:
            return u"{0:0.{1}f}{2}".format(float(val), percentage_decimal, percentage_units)

        except ValueError:
            return u"{0}{1}".format(val, percentage_units)

    # =============================================================================
    def ui_format_rain(self, dev, state_name, val):
        """
        Format rain data for Indigo UI

        Adds rain units to rain values for display in control pages, etc.

        -----

        :param indigo.Devices dev:
        :param str state_name:
        :param val:
        """

        # Some devices use the prop 'rainUnits' and some use the prop
        # 'rainAmountUnits'.  So if we fail on the first, try the second and--if still
        # not successful, return and empty string.
        try:
            rain_units = dev.pluginProps['rainUnits']
        except KeyError:
            rain_units = dev.pluginProps.get('rainAmountUnits', '')

        if val in ["NA", "N/A", "--", ""]:
            return val

        try:
            return u"{0:0.2f}{1}".format(float(val), rain_units)

        except ValueError:
            return u"{0}".format(val)

    # =============================================================================
    def ui_format_temperature(self, dev, state_name, val):
        """
        Format temperature data for Indigo UI

        Adjusts the decimal precision of certain temperature values and appends the
        desired units string for display in control pages, etc.

        -----

        :param indigo.Device dev:
        :param str state_name:
        :param val:
        """

        temp_decimal      = int(self.pluginPrefs.get('uiTempDecimal', '1'))
        temperature_units = unicode(dev.pluginProps.get('temperatureUnits', ''))

        try:
            return u"{0:0.{precision}f}{1}".format(float(val), temperature_units, precision=temp_decimal)

        except ValueError:
            return u"--"

    # =============================================================================
    def ui_format_wind(self, dev, state_name, val):
        """
        Format wind data for Indigo UI

        Adjusts the decimal precision of certain wind values for display in control
        pages, etc.

        -----

        :param indigo.Device dev:
        :param str state_name:
        :param val:
        """

        wind_decimal = int(self.pluginPrefs.get('uiWindDecimal', '1'))
        wind_units   = unicode(dev.pluginProps.get('windUnits', ''))

        try:
            return u"{0:0.{precision}f}{1}".format(float(val), wind_units, precision=wind_decimal)

        except ValueError:
            return u"{0}".format(val)

    # =============================================================================
    def ui_format_wind_name(self, state_name, val):
        """
        Format wind data for Indigo UI

        Adjusts the decimal precision of certain wind values for display in control
        pages, etc.

        -----

        :param str state_name:
        :param val:
        """

        long_short = self.pluginPrefs.get('uiWindName', 'Long')

        val = round(val)

        if long_short == 'Long':
            if val in range(0, 22):
                return u"North"
            elif val in range(22, 68):
                return u"Northeast"
            elif val in range(68, 113):
                return u"East"
            elif val in range(113, 158):
                return u"Southeast"
            elif val in range(158, 203):
                return u"South"
            elif val in range(203, 248):
                return u"Southwest"
            elif val in range(248, 293):
                return u"West"
            elif val in range(293, 338):
                return u"Northwest"
            elif val in range(338, 361):
                return u"North"
        else:
            if val in range(0, 22):
                return u"N"
            elif val in range(22, 68):
                return u"NE"
            elif val in range(68, 113):
                return u"E"
            elif val in range(113, 158):
                return u"SE"
            elif val in range(158, 203):
                return u"S"
            elif val in range(203, 248):
                return u"SW"
            elif val in range(248, 293):
                return u"W"
            elif val in range(293, 338):
                return u"NW"
            elif val in range(338, 361):
                return u"N"
    # =============================================================================
