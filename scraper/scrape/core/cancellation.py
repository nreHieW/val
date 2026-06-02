import time


def raise_if_cancelled(cancel_event, message):
    if cancel_event is not None and cancel_event.is_set():
        raise TimeoutError(message)


def sleep_with_cancel(seconds, cancel_event, message):
    if cancel_event is None:
        time.sleep(seconds)
    elif cancel_event.wait(seconds):
        raise TimeoutError(message)
