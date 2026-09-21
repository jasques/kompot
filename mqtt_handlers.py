def on_connect(mosq, obj, rc, rc2=None):
    # for subscription in SUBSCRIPTIONS:
    # print("rc: " + str(rc))
    pass


def on_publish(mosq, obj, mid):
    # print("mid: " + str(mid))
    pass


def on_subscribe(mosq, obj, mid, granted_qos):
    # print("Subscribed: " + str(mid) + " " + str(granted_qos))
    pass


def on_log(mosq, obj, level, string):
    pass  # print(string)


def on_message(mosq, obj, msg):
    print(msg.payload.decode("utf-8"))
