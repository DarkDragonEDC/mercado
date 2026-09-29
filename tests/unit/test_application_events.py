import unittest

from albionmkt_app.application.events import (
    ApplicationEventDispatcher,
    BotErrorReceived,
)


class ApplicationEventDispatcherTests(unittest.TestCase):
    def test_publish_notifies_only_matching_listeners(self):
        dispatcher = ApplicationEventDispatcher()
        received = []
        dispatcher.subscribe(BotErrorReceived, received.append)
        dispatcher.publish(BotErrorReceived("failure", "E1"))
        dispatcher.publish("unrelated")
        self.assertEqual(received, [BotErrorReceived("failure", "E1")])

    def test_unsubscribe_stops_future_notifications(self):
        dispatcher = ApplicationEventDispatcher()
        received = []
        unsubscribe = dispatcher.subscribe(BotErrorReceived, received.append)
        unsubscribe()
        dispatcher.publish(BotErrorReceived("ignored"))
        self.assertEqual(received, [])

    def test_listener_can_unsubscribe_during_snapshot_dispatch(self):
        dispatcher = ApplicationEventDispatcher()
        received = []
        unsubscribe = None

        def listener(event):
            received.append(event)
            unsubscribe()

        unsubscribe = dispatcher.subscribe(BotErrorReceived, listener)
        dispatcher.publish(BotErrorReceived("first"))
        dispatcher.publish(BotErrorReceived("second"))
        self.assertEqual(received, [BotErrorReceived("first")])


if __name__ == "__main__":
    unittest.main()

