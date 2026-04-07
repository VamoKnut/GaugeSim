import json

from gaugesim.mqtt_client import GaugeMqttPublisher, MqttSettings


class FakeClient:
    def __init__(self, *args, **kwargs):
        self.published = []
        self.on_connect = None
        self.on_disconnect = None
        self.kwargs = kwargs
        self.username_calls = []

    def username_pw_set(self, username, password):
        self.username_calls.append((username, password))

    def tls_set(self):
        pass

    def loop_start(self):
        pass

    def connect(self, host, port, keepalive=60):
        if self.on_connect:
            self.on_connect(self, None, None, 0)

    def publish(self, topic, payload, qos=0, retain=False):
        self.published.append((topic, payload, qos, retain))

    def loop_stop(self):
        pass

    def disconnect(self):
        pass


def test_publish_sample_and_status_anonymous_v5(monkeypatch):
    monkeypatch.setattr("gaugesim.mqtt_client.mqtt.Client", FakeClient)

    pub = GaugeMqttPublisher(MqttSettings(host="localhost", port=1883, username=""))
    pub.connect()
    pub.publish_sample({"stage": 1.0})
    pub.publish_status("SimulationStarted")

    sample = pub._client.published[0]
    status = pub._client.published[1]

    assert pub._client.kwargs["protocol"] == 5
    assert pub._client.username_calls == []
    assert sample[0] == "gaugsim/sample"
    assert json.loads(sample[1])["stage"] == 1.0
    assert status[0] == "gaugsim/status"
    assert json.loads(status[1])["status"] == "SimulationStarted"


def test_username_password_applied_when_set(monkeypatch):
    monkeypatch.setattr("gaugesim.mqtt_client.mqtt.Client", FakeClient)

    pub = GaugeMqttPublisher(MqttSettings(host="localhost", port=1883, username="user1", password="pw"))
    assert pub._client.username_calls == [("user1", "pw")]
