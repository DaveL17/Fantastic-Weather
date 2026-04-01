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


# ===================================== simpleeval.py =====================================
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
