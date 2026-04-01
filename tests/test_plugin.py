"""
Unit tests for the Fantastic Weather plugin.

Menu Items are tested by referencing hidden Actions which have the same callback method.
"""
import dotenv
import httpx
import os
from tests.shared import APIBase # noqa

dotenv.load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

GOOD_API_KEY = os.getenv("GOOD_API_KEY")
PLUGIN_ID    = os.getenv("PLUGIN_ID")
URL_PREFIX   = os.getenv("URL_PREFIX")


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


# ===================================== simpleeval.py =====================================
class TestMenuItems(APIBase):
    """ Note that the API doesn't expose menu items so we add hidden actions in `Actions.xml` that call the same
    method(s) that the menu item calls. The result is the same."""
    @classmethod
    def setUpClass(cls):
        pass

    # Enable all plugin devices
    def test_comms_unkill_all(self):
        """Post a dev.enabled() command to the Indigo Web Server."""
        result = execute_action("comms_unkill_all", msg="test_comms_unkill_all")
        self.assertEqual(result.status_code, 200, "The enable plugin devices menu item call was not successful.")

    # Disable all plugin devices.
    def test_comms_kill_all(self):
        """Post a dev.enabled() command to the Indigo Web Server."""
        result = execute_action("comms_kill_all", msg="test_comms_kill_all")
        self.assertEqual(result.status_code, 200, "The disable plugin devices menu item call was not successful.")

    # Display plugin information.
    def test_log_plugin_environment(self):
        """Post a log_plugin_environment command to the Indigo Web Server."""
        result = execute_action("log_plugin_environment", msg="test_log_plugin_environment")
        self.assertEqual(result.status_code, 200, "The display plugin information menu item call was not successful.")

    # Refresh weather data.
    def test_refresh_weather_data(self):
        """Post a refresh_weather_data command to the Indigo Web Server."""
        result = execute_action("refresh_weather_data", msg="test_refresh_weather_data")
        self.assertEqual(result.status_code, 200, "The refresh weather data menu item call was not successful.")

    # Send weather emails.
    def test_send_weather_emails(self):
        """Post a send_weather_emails command to the Indigo Web Server."""
        result = execute_action("send_weather_emails", msg="test_send_weather_emails")
        self.assertEqual(result.status_code, 200, "The send weather emails menu item call was not successful.")

    # Write weather data to file.
    def test_dump_the_json(self):
        """Post a dump_the_json command to the Indigo Web Server."""
        result = execute_action("dump_the_json", msg="test_dump_the_json")
        self.assertEqual(result.status_code, 200, "The write weather data to file menu item call was not successful.")


# ===================================== Actions =====================================
class TestActions(APIBase):
    """Tests for plugin actions defined in Actions.xml."""
    @classmethod
    def setUpClass(cls):
        pass

    # Refresh weather data.
    def test_refresh_weather_data(self):
        """Post a refresh_weather_data action command to the Indigo Web Server."""
        result = execute_action("refresh_weather_data", msg="test_refresh_weather_data")
        self.assertEqual(result.status_code, 200, "The refresh weather data action call was not successful.")
