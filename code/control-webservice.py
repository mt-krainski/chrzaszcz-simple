import atexit
from datetime import datetime
from os import kill
import subprocess

from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask
from flask import request

LOCAL_TESTING = True  # do not use any of the RPi library functionality

if not LOCAL_TESTING:
    import RPi.GPIO as GPIO

sched = BackgroundScheduler()
sched.start()
atexit.register(sched.shutdown)


CONTROL_TIMEOUT = 5  # seconds
CONTROL_CHECK_INTERVAL = 1  # seconds

LEFT_PWM_PIN = 16
LEFT_DIR_PIN = 13
RIGHT_PWM_PIN = 12
RIGHT_DIR_PIN = 6

PWM_FREQUENCY = 5000

# Since the motors are connected in the same way to the drivers
#   they'll rotate in the same direction on the same state of DIR.
#   If motors on both sides would rotate CW or CCW, the rover would
#   be spinning in a circle instead of going forward. To mitigate
#   this, we simply use a -1 multiplier on one of the sides.
LEFT_DIRECTION_MULTIPLIER = -1
RIGHT_DIRECTION_MULTIPLIER = 1

if not LOCAL_TESTING:
    # Use BCM because this notation is on the HAT.
    GPIO.setmode(GPIO.BCM)

    # Start the video streaming service.
    subprocess.call(["sudo", "motion"])

    GPIO.setup(LEFT_PWM_PIN, GPIO.OUT)
    GPIO.setup(LEFT_DIR_PIN, GPIO.OUT)
    GPIO.setup(RIGHT_PWM_PIN, GPIO.OUT)
    GPIO.setup(RIGHT_DIR_PIN, GPIO.OUT)

    LEFT_PWM = GPIO.PWM(LEFT_PWM_PIN, PWM_FREQUENCY)
    RIGHT_PWM = GPIO.PWM(RIGHT_PWM_PIN, PWM_FREQUENCY)
    LEFT_PWM.start(0)
    RIGHT_PWM.start(0)


def _set_dir_pin(power, dir_pin):
    if power < 0:
        if LOCAL_TESTING:
            print(f"Would execute: GPIO.output({dir_pin}, GPIO.HIGH)")
        else:
            GPIO.output(dir_pin, GPIO.HIGH)
    else:
        if LOCAL_TESTING:
            print(f"Would execute: GPIO.output({dir_pin}, GPIO.LOW)")
        else:
            GPIO.output(dir_pin, GPIO.LOW)


def set_motors(left_power, right_power):
    """Set the power on the motors.

    Args:
        left_power (int): denotes the power and direction of the
            left motors, ranged -100 to 100, with -100 being full
            power backwards and 100 being full power forwards.
        right_power (int): denotes the power and direction of the
            right motors, ranged -100 to 100, with -100 being full
            power backwards and 100 being full power forwards.
    """
    left_power *= LEFT_DIRECTION_MULTIPLIER
    right_power *= RIGHT_DIRECTION_MULTIPLIER

    _set_dir_pin(left_power, LEFT_DIR_PIN)
    _set_dir_pin(right_power, RIGHT_DIR_PIN)

    if LOCAL_TESTING:
        print("Would execute: ")
        print(f"RIGHT_PWM.ChangeDutyCycle(abs({right_power}))")
        print(f"LEFT_PWM.ChangeDutyCycle(abs({left_power}))")
    else:
        RIGHT_PWM.ChangeDutyCycle(abs(right_power))
        LEFT_PWM.ChangeDutyCycle(abs(left_power))


# variables that are accessible from anywhere
last_control_set_time = datetime.timestamp(datetime.now())


def _kill_motors_if_inactive():
    global last_control_set_time
    print("Kill motors check.")
    now = datetime.timestamp(datetime.now())
    if last_control_set_time + CONTROL_TIMEOUT < now:
        print("Motors killed.")
        set_motors(0, 0)
        last_control_set_time = now


sched.add_job(_kill_motors_if_inactive, "interval", seconds=CONTROL_CHECK_INTERVAL)

app = Flask(__name__)


@app.route("/")
def hello_world():
    return "<p>Hello, World!</p>"


@app.route("/heartbeat")
def heartbeat():
    now = datetime.now().second
    return {"heartbeat": now % 2}


@app.route("/set_control")
def set_control():
    left = int(request.args.get("left", ""))
    right = int(request.args.get("right", ""))
    set_motors(left, right)
    last_control_set_time = datetime.timestamp(datetime.now())
    return ""
