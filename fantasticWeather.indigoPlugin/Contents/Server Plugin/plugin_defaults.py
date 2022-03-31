kDefaultPluginPrefs = {
    'alertLogging': False,           # Write severe weather alerts to the log?
    'apiKey': "apiKey",              # DS requires an api key.
    'callCounter': "999",            # DS call limit.
    'dailyCallCounter': "0",         # Number of API calls today.
    'dailyCallDay': "1970-01-01",    # API call counter date.
    'dailyCallLimitReached': False,  # Has the daily call limit been reached?
    'dailyIconNames': "",            # Hidden trap of icon names used by the API.
    'downloadInterval': "900",       # Frequency of weather updates.
    'hourlyIconNames': "",           # Hidden trap of icon names used by the API.
    'itemListTempDecimal': "1",      # Precision for Indigo Item List.
    'language': "en",                # Language for DS text.
    'lastSuccessfulPoll': "1970-01-01 00:00:00",    # Last successful plugin cycle
    'launchParameters': "https://darksky.net/dev",  # url for launch API button
    'nextPoll': "1970-01-01 00:00:00",              # Next plugin cycle
    'noAlertLogging': False,         # Suppresses "no active alerts" logging.
    'showDebugLevel': "30",          # Logger level.
    'uiDateFormat': "YYYY-MM-DD",    # Preferred date format string.
    'uiDistanceDecimal': "0",        # Precision for Indigo UI display (distance).
    'uiIndexDecimal': "0",           # Precision for Indigo UI display (index).
    'uiPercentageDecimal': "1",      # Precision for Indigo UI display (humidity, etc.)
    'uiTempDecimal': "1",            # Precision for Indigo UI display (temperature).
    'uiTimeFormat': "military",      # Preferred time format string.
    'uiWindDecimal': "1",            # Precision for Indigo UI display (wind).
    'uiWindName': "Long",            # Use long or short wind names (i.e., N vs. North)
    'units': "auto",                 # Standard, metric, Canadian, UK, etc.
    'updaterEmail': "",              # Email address for forecast email (legacy field name).
    'updaterEmailsEnabled': False,   # Enable/Disable forecast emails.
    'weatherIconNames': "",          # Hidden trap of icon names used by the API.
}
