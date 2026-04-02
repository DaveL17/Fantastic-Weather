"""
Unit tests for the Fantastic Weather plugin.

Menu Items are tested by referencing hidden Actions which have the same callback method.
"""
import dotenv
import httpx
import os
import textwrap
from tests.shared import APIBase # noqa
from tests.shared.utils import run_host_script

dotenv.load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

GOOD_API_KEY  = os.getenv("GOOD_API_KEY")
PLUGIN_ID     = os.getenv("PLUGIN_ID")
URL_PREFIX    = os.getenv("URL_PREFIX")
LATITUDE      = os.getenv("LATITUDE")
LONGITUDE     = os.getenv("LONGITUDE")
IMAGE_URL     = os.getenv("IMAGE_URL")
DEVICE_FOLDER = int(os.getenv("DEVICE_FOLDER", 0))


def execute_action(action_id: str, msg: str = "test-plugin") -> bool | httpx.Response:
    """Post a plugin.executeAction command to the Indigo Web Server API.

    Args:
        action_id (str): The Indigo action ID to execute.
        msg (str): The message ID to include in the request.

    Returns:
        bool | httpx.Response: The HTTP response, or False if the request failed.
    """
    try:
        message = {
            "id": f"{msg}",
            "message": "plugin.executeAction",
            "pluginId": PLUGIN_ID,
            "actionId": action_id,
        }
        url = f"{URL_PREFIX}/v2/api/command/?api-key={GOOD_API_KEY}"
        return httpx.post(url, json=message, verify=False, timeout=30)
    except Exception as e:
        print(f"API Error {e}")
        return False


def execute_trigger(trigger_id: int, msg: str = "test-plugin") -> bool | httpx.Response:
    """Post an indigo.trigger.execute command to the Indigo Web Server API.

    Args:
        trigger_id (int): The Indigo trigger object ID to execute.
        msg (str): The message ID to include in the request.

    Returns:
        bool | httpx.Response: The HTTP response, or False if the request failed.
    """
    try:
        message = {
            "id": f"{msg}",
            "message": "indigo.trigger.execute",
            "objectId": trigger_id,
        }
        url = f"{URL_PREFIX}/v2/api/command/?api-key={GOOD_API_KEY}"
        return httpx.post(url, json=message, verify=False, timeout=30)
    except Exception as e:
        print(f"API Error {e}")
        return False


# ===================================== Menu Items =====================================
class TestMenuItems(APIBase):
    """Tests for plugin menu items.

    The API doesn't expose menu items directly, so hidden actions in Actions.xml are used
    to call the same callback methods. The result is equivalent.
    """

    @classmethod
    def setUpClass(cls):
        """Skip APIBase setup; tests use module-level env vars via execute_action."""
        pass

    def test_comms_unkill_all(self):
        """Enable all plugin devices via the Indigo Web Server API."""
        result = execute_action("comms_unkill_all", msg="test_comms_unkill_all")
        self.assertIsInstance(result, httpx.Response, "The enable plugin devices request failed with an exception.")
        self.assertEqual(result.status_code, 200,
                         f"The enable plugin devices menu item call was not successful: {result.text}")

    def test_comms_kill_all(self):
        """Disable all plugin devices via the Indigo Web Server API."""
        result = execute_action("comms_kill_all", msg="test_comms_kill_all")
        self.assertIsInstance(result, httpx.Response, "The disable plugin devices request failed with an exception.")
        self.assertEqual(result.status_code, 200,
                         f"The disable plugin devices menu item call was not successful: {result.text}")

    def test_log_plugin_environment(self):
        """Display plugin information via the Indigo Web Server API."""
        result = execute_action("log_plugin_environment", msg="test_log_plugin_environment")
        self.assertIsInstance(result, httpx.Response, "The display plugin information request failed with an exception.")
        self.assertEqual(result.status_code, 200,
                         f"The display plugin information menu item call was not successful: {result.text}")

    def test_refresh_weather_data(self):
        """Refresh weather data via the Indigo Web Server API."""
        result = execute_action("refresh_weather_data", msg="test_refresh_weather_data")
        self.assertIsInstance(result, httpx.Response, "The refresh weather data request failed with an exception.")
        self.assertEqual(result.status_code, 200,
                         f"The refresh weather data menu item call was not successful: {result.text}")

    def test_send_weather_emails(self):
        """Send weather emails via the Indigo Web Server API."""
        result = execute_action("send_weather_emails", msg="test_send_weather_emails")
        self.assertIsInstance(result, httpx.Response, "The send weather emails request failed with an exception.")
        self.assertEqual(result.status_code, 200,
                         f"The send weather emails menu item call was not successful: {result.text}")

    def test_dump_the_json(self):
        """Write weather data to file via the Indigo Web Server API."""
        result = execute_action("dump_the_json", msg="test_dump_the_json")
        self.assertIsInstance(result, httpx.Response, "The write weather data to file request failed with an exception.")
        self.assertEqual(result.status_code, 200,
                         f"The write weather data to file menu item call was not successful: {result.text}")


# ===================================== Events =====================================
class TestEvents(APIBase):
    """Tests for plugin events (triggers) defined in Events.xml."""

    @classmethod
    def setUpClass(cls):
        """Skip APIBase setup; tests use module-level env vars via execute_trigger."""
        pass

    def test_weather_alert(self):
        """Fire the Severe Weather Alert trigger via the Indigo Web Server API.

        Requires .env entry:
            TRIGGER_WEATHER_ALERT_ID=<trigger object id>
        """
        trigger_id = int(os.getenv("TRIGGER_WEATHER_ALERT_ID"))
        result = execute_trigger(trigger_id, msg="test_weather_alert")
        self.assertIsInstance(result, httpx.Response, "The weather alert trigger request failed with an exception.")
        self.assertEqual(result.status_code, 200,
                         f"The weather alert trigger execution was not successful: {result.text}")

    def test_weather_site_offline(self):
        """Fire the Weather Location Offline trigger via the Indigo Web Server API.

        Requires .env entry:
            TRIGGER_SITE_OFFLINE_ID=<trigger object id>
        """
        trigger_id = int(os.getenv("TRIGGER_SITE_OFFLINE_ID"))
        result = execute_trigger(trigger_id, msg="test_weather_site_offline")
        self.assertIsInstance(result, httpx.Response,
                              "The weather site offline trigger request failed with an exception.")
        self.assertEqual(result.status_code, 200,
                         f"The weather site offline trigger execution was not successful: {result.text}")


# ===================================== Actions =====================================
class TestActions(APIBase):
    """Tests for plugin actions defined in Actions.xml."""

    @classmethod
    def setUpClass(cls):
        """Skip APIBase setup; tests use module-level env vars via execute_action."""
        pass

    def test_refresh_weather_data(self):
        """Refresh weather data via the Indigo Web Server API."""
        result = execute_action("refresh_weather_data", msg="test_refresh_weather_data")
        self.assertIsInstance(result, httpx.Response,
                              "The refresh weather data action request failed with an exception.")
        self.assertEqual(result.status_code, 200,
                         f"The refresh weather data action call was not successful: {result.text}")


# ===================================== Devices =====================================
class TestDevices(APIBase):
    """Tests for plugin devices defined in Devices.xml."""

    @classmethod
    def setUpClass(cls):
        pass

    @staticmethod
    def payload(name: str = "", device_type_id: str = "", props: dict = None):
        """Generate a payload for creating devices via the Indigo Web Server API."""
        return textwrap.dedent(f"""\
            try:
                import time
                indigo.device.create(protocol=indigo.kProtocol.Plugin,
                    name={name},
                    description='Fantastic Weather unit test device',
                    pluginId={PLUGIN_ID},
                    deviceTypeId='{device_type_id}',
                    props={props},
                    folder={DEVICE_FOLDER}
                )
                time.sleep(1)
                return True
            except:
                return False
        """)

    @staticmethod
    def confirm_creation(name: str = ""):
        """Confirm the device was created"""
        return textwrap.dedent(f"""\
            if {name} in [dev.name for dev in indigo.devices.iter({PLUGIN_ID})]:
                return True
            else:
                return False
        """)

    @staticmethod
    def delete_device(name: str = ""):
        """Delete the device via the Indigo Web Server API."""
        return textwrap.dedent(f"""\
                    try:
                        indigo.device.delete({name})
                        return True
                    except:
                        return False
                """)

    def create_and_delete_device(self, name: str, device_type_id: str, props: dict):
        """Create a plugin device, confirm it exists, then delete it.

        Args:
            name (str): The quoted device name string passed to the host script.
            device_type_id (str): The Indigo device type ID from Devices.xml.
            props (dict): The device props dict passed to the host script.
        """
        host_script = self.payload(name, device_type_id, props)
        run_host_script(host_script)
        self.assertTrue(host_script, "Device creation successful.")

        host_script = self.confirm_creation(name)
        self.assertTrue(host_script, "Could not confirm the device was created.")

        host_script = self.delete_device(name)
        run_host_script(host_script)
        self.assertTrue(host_script, "Device deletion failed.")

    # ==================================== Astronomy Device ====================================
    def test_astronomy_device_creation(self):
        """Verify that an Astronomy device can be created and deleted via the Indigo API."""
        my_props  = {'latitude':        LATITUDE,
                     'longitude':       LONGITUDE,
                     'time_zone':       'time_here',
                     'percentageUnits': '%',
                     'isWeatherDevice': True}
        self.create_and_delete_device("'fw_unit_test_astronomy_device'", 'Astronomy', my_props)

    # ====================================== Daily Device ======================================
    def test_daily_device_creation(self):
        """Verify that a Daily Forecast device can be created and deleted via the Indigo API."""
        my_props  = {'latitude':         LATITUDE,
                     'longitude':        LONGITUDE,
                     'distanceUnits':    ' mi.',
                     'indexUnits':       ' ',
                     'percentageUnits':  '%',
                     'pressureUnits':    ' mb',
                     'rainAmountUnits':  ' in.',
                     'temperatureUnits': '°',
                     'windUnits':        ' mph',
                     'isWeatherDevice':  True}
        self.create_and_delete_device("'fw_unit_test_daily_device'", 'Daily', my_props)

    # ===================================== Hourly Device ======================================
    def test_hourly_device_creation(self):
        """Verify that an Hourly Forecast device can be created and deleted via the Indigo API."""
        my_props  = {'latitude':         LATITUDE,
                     'longitude':        LONGITUDE,
                     'time_zone':        'time_here',
                     'ui_display':       '001',
                     'distanceUnits':    ' mi.',
                     'indexUnits':       ' ',
                     'pressureUnits':    ' mb',
                     'percentageUnits':  '%',
                     'rainUnits':        ' in.',
                     'temperatureUnits': '°',
                     'windUnits':        ' mph',
                     'isWeatherDevice':  True}
        self.create_and_delete_device("'fw_unit_test_hourly_device'", 'Hourly', my_props)

    # ============================ Satellite Image Downloader Device ===========================
    def test_satellite_image_downloader_device_creation(self):
        """Verify that a Satellite Image Downloader device can be created and deleted via the Indigo API."""
        my_props  = {'imageSourceLocation':      IMAGE_URL,
                     'imageDestinationLocation': '/tmp/fw_unit_test_image.png',
                     'isWeatherDevice':          False}
        self.create_and_delete_device("'fw_unit_test_satellite_device'", 'satelliteImageDownloader', my_props)

    # ===================================== Weather Device =====================================
    def test_weather_device_creation(self):
        """Verify that a Weather device can be created and deleted via the Indigo API."""
        my_props  = {'latitude':              LATITUDE,
                     'longitude':             LONGITUDE,
                     'time_zone':             'time_here',
                     'distanceUnits':         ' mi.',
                     'indexUnits':            ' ',
                     'percentageUnits':       '%',
                     'pressureUnits':         ' mb',
                     'rainUnits':             ' in.',
                     'temperatureUnits':      '°',
                     'windUnits':             ' mph',
                     'suppressWeatherAlerts': False,
                     'isWeatherDevice':       True}
        self.create_and_delete_device("'fw_unit_test_weather_device'", 'Weather', my_props)
