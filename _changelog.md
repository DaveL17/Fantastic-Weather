#### Reminder: Support for the Dark Sky Weather API has ended.

### v2022.0.3
- Switches the plugin API to Pirate Weather.
- Adds foundation for API `3.1`.

**There will be no more updates of the plugin after v2022.0.3.**

### v2022.0.2
- Updates documentation to latest API sunset date of 2023-03-31.
- Adds `_to_do_list.md` and changes changelog to markdown.
- Moves plugin environment logging to plugin menu item (log only on request).
- Fixes bug in construction of forecast email body text.

### v2022.0.1
- Updates plugin for Indigo 2022.1 and Python 3.
- Includes `pytz` module (to support Python 3).
- Standardizes Indigo method implementation.

### v1.0.18
- Fixes bug where email forecast can send "Not available" for the precipitation type.
- Addresses situation where Dark Sky does not provide the 'x-forecast-api-calls' payload key.

### v1.0.16, v1.0.17
- Bumps version number to force releases sync.

### v1.0.15
- Fixes bug in Write to File menu item.
- Logging refinements.

### v1.0.14
- Includes deprecation warning in startup logging.
- Improves macOS audit logic.
- Code refinements.

### v1.0.13
- Fixes bug in macOS audit logic.

### v1.0.12
- Implements Constants.py.
- Code refinements.

### v1.0.11
- Better trapping of errors raised by r.requests.raise_for_status().

### v1.0.10
- Removes traceback logging for requests timeout.

### v1.0.09
- Additional trap for satellite image retrieval timeout.

### v1.0.08
- Sync with server.

### v1.0.07
- Fixes critical bug in time formatting code.

### v1.0.06
- Code refinements.

### v1.0.05
- Further integrates DLFramework.

### v1.0.04
- Better integrates DLFramework.

### v1.0.03
- "Unable to reach..." error changed to warning.

### v1.0.02
- Changes level of "unable to reach" messages from errors to warnings until 15-minute interval reached.
- Adds states to display shortened Sunrise (sunRiseShort) and Sunset (sunSetShort).

### v1.0.01
- Takes plugin out of beta status.
- Rounds visibility in weather forecast email to the nearest quarter unit (i.e., 7.251 becomes 7.25, 7.38 becomes 7.50.)

### v0.5.04 (beta 13)
- Adds check to ensure minimum OS requirement is met.

### v0.5.03 (beta 13)
- Changes wind speed value in the wind string state to an integer.

### v0.5.02 (beta 13)
- Adds custom states to support moon phase image selection and text-based moon phase description.

### v0.5.01 (beta 13)
- Improvements to device configuration validation.
- Code refinements.

### v0.4.01 (beta 12)
- Removes all references to legacy version checking.

### v0.3.04 (beta 12)
- Adds new wind name conversion code. (Credit to forum user forestfield)

### v0.3.03 (beta 12)
- Adds new Short Day Name to Daily and Hourly Forecast devices.

### v0.3.02 (beta 12)
- Improved handling of bad url messages (Status Code 400).

### v0.3.01 (beta 12)
- Code refinements.

### v0.2.10 (beta 11)
- Ensures that the plugin is compatible with the Indigo server version.
- Standardizes SupportURL behavior across all plugin functions.

### v0.2.09 (beta 11)
- Synchronize self.pluginPrefs in closedPrefsConfigUi().

### v0.2.08 (beta 11)
- Audits kDefaultPluginPrefs

### v0.2.08 (beta 11)
- Changes "En/Disable all Fantastic Weather Devices" to "En/Disable all Plugin Devices".

### v0.2.07 (beta 11)
- Changes Python lists to tuples where possible to increase performance.

### v0.2.06 (beta 11)
- Increments version number.

### v0.2.05 (beta 11)
- Adds additional refresh frequencies of 2, 3, and 4 minutes.
- Deletes deprecated code.

### v0.2.04 (beta 11)
- Fixes bug in plugin initialization for new installs where a new device would not initialize properly.
- Migrates to the dateutil library from datetime for the majority of string to date operations.
- Code refinements.

### v0.2.03 (beta 11)
- Pretty prints severe weather alert text when written to the Indigo log.
- Improves robustness when connection problems occur.
- Removes plugin update notifications.
- Reduces plugin debug logging considerably.

### v0.2.02 (beta 10)
- Fixes KeyError bug when Fantastic Weather triggers are enabled.

### v0.2.01 (beta 10)
- Adds configuration option for hourly device UI display value. Options: Forecast high temperature `[current hour |
  next hour]`.
- Fixes a bug in getDeviceConfigUiValues: AttributeError: 'float' object has no attribute 'keys'.
- Fixes typo in trigger names for hourly devices.

### v0.1.08 (beta 8)
- Fixes bug for latitude/longitude where default values could not be overridden.
- Refinements to daily forecast email:
  - Adds long range forecast
  - Rounds total precipitation to 2 decimal places.
  - Refines data formatting.
  - Fixes bug for instances where email sent flag not reset on new day.
- Hides development fields for icon names in plugin configuration dialog.

### v0.1.07 (beta 7)
- Adds forecast precipitation total state to daily weather devices
- Adds timezone setting to astronomy, daily, hourly and weather forecast devices.
- Adds 'WindString' state to Weather devices 'East at 4.0 mph'.
- Adds temperatures to Indigo device state list for Daily and Hourly Weather devices (modified by temperature display
  units).
  - "Daily" reports daily High/Low (i.e., 72°/32°)
  - "Hourly" reports hourly High (i.e., 72°)

(Thanks for forum user Monstergerm for the suggestions and beta testing.)

### v0.1.06 (beta 6)
- Adds additional traps when Dark Sky API is offline.
- Fixes bug where alertCount state for weather devices was not resetting after severe weather alerts lifted.

### v0.1.05 (beta 5)
- Adds 'Epoch' state to Hourly forecast device.

### v0.1.04 (beta 4)
- Adds "Daily Summary" state to daily weather devices.
- Adds "Hourly Summary" state to hourly weather devices.
- Adds plugin configuration option for Long vs. Short wind names.
- Adds lat/long to Indigo UI Address field for most plugin devices.
- Fixes bug where global time setting didn't affect Hourly device state UI [h##_hour].

### v0.1.03 (beta 3)
- Renames menu items from "Dark Sky" to "Fantastic Weather".
- Updates support URLs to forum and wiki.
- Improves device config dialog UI.
- Fixed bug in setting of Weather Device dewpoint value.
- Fixes bug in icon naming convention.

### v0.1.02 (beta 2)
- Fixes missing precipitation type device state for hourly device

### v0.1.01 (beta 1)
- Initial release.
