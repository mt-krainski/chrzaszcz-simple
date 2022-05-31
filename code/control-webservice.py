import atexit
from datetime import datetime
import os
import subprocess

from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, render_template
from flask import request

import maestro

if os.environ.get("ENV", "development") == "rover":
    LOCAL_TESTING = False  # do not use any of the RPi library functionality
else:
    LOCAL_TESTING = True

if not LOCAL_TESTING:
    import RPi.GPIO as GPIO

LEFT_PWM_PIN = 16
LEFT_DIR_PIN = 13
RIGHT_PWM_PIN = 12
RIGHT_DIR_PIN = 6

PWM_FREQUENCY = 5000  # arbitrary choice

# Since the motors are connected in the same way to the drivers
#   they'll rotate in the same direction on the same state of DIR.
#   If motors on both sides would rotate CW or CCW, the rover would
#   be spinning in a circle instead of going forward. To mitigate
#   this, we simply use a -1 multiplier on one of the sides.
LEFT_DIRECTION_MULTIPLIER = -1
RIGHT_DIRECTION_MULTIPLIER = 1

app = Flask(__name__)

sched = BackgroundScheduler()
atexit.register(sched.shutdown)

# This variable notes when was the last movement command received.
#   Under normal circumstances, the webservice will receive a movement
#   command every ~100ms. If there's no command for CONTROL_TIMEOUT,
#   the rover will be put to a halt
last_control_set_timestamp = datetime.timestamp(datetime.now())
if LOCAL_TESTING:
    CONTROL_TIMEOUT = 10  # seconds
    CONTROL_CHECK_INTERVAL = 1  # seconds
    CONTROL_LOOP_INTERVAL = 5000  # milliseconds
else:
    CONTROL_TIMEOUT = 0.5  # seconds
    CONTROL_CHECK_INTERVAL = 0.1  # seconds
    CONTROL_LOOP_INTERVAL = 50  # milliseconds


ARM_BASE_POSITION = [5500, 9000, 9000, 3000, 9000, 3000]
ARM_CONTROL_MIN = 3000
ARM_CONTROL_MAX = 9000

arm_requested_position = ARM_BASE_POSITION.copy()
if not LOCAL_TESTING:
    arm_controller = maestro.Controller()


def _kill_motors_if_inactive():
    """Kill motors if there was no control signal for the timeout duration.

    This function is triggered periodically. It checks when was the last control
    signal sent to the rover. If a `CONTROL_TIMEOUT` duration passes, it will stop the
    rover. The intent here is to prevent the rover from driving away if communication is
    lost.
    """
    global last_control_set_timestamp
    now = datetime.timestamp(datetime.now())
    if last_control_set_timestamp + CONTROL_TIMEOUT < now:
        set_motors(0, 0)
        last_control_set_timestamp = now


sched.add_job(_kill_motors_if_inactive, "interval", seconds=CONTROL_CHECK_INTERVAL)

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

    def cleanup_pins():
        GPIO.cleanup()

    atexit.register(cleanup_pins)


def _set_dir_pin(power, dir_pin):
    """Correctly set the direction pin based on `power`.

    Args:
        power (int): -100 to 100 value. If the value is negative
          this will set the direction pin, otherwise it will clear it.
        dir_pin (int): ID of the direction pin to set or clear.
    """
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
        print(
            "Would execute: "
            f"RIGHT_PWM.ChangeDutyCycle(abs({right_power})), "
            f"LEFT_PWM.ChangeDutyCycle(abs({left_power}))"
        )
    else:
        RIGHT_PWM.ChangeDutyCycle(abs(right_power))
        LEFT_PWM.ChangeDutyCycle(abs(left_power))


def set_arm():
    """Set arm into position specified in global variable arm_requested_position.

    This is using a global variable arm_requested_position. It could be implemented
    equally well without using a global variable here, but I decided to go with this
    solution.
    """
    global arm_requested_position
    for joint, value in enumerate(arm_requested_position):
        if not LOCAL_TESTING:
            arm_controller.setTarget(joint, value)


# Start the scheduler for background tasks
sched.start()


@app.route("/")
def control():
    return render_template("control-application.html", interval=CONTROL_LOOP_INTERVAL)


@app.route("/heartbeat")
def heartbeat():
    now = datetime.now().second
    return {"heartbeat": now % 2}


@app.route("/control_rover_movement")
def control_rover_movement():
    """Endopoint used to control the rover movement.

    It requires `left` and `right` url query parameters.
    """
    global last_control_set_timestamp
    left = int(request.args.get("left", "0"))
    right = int(request.args.get("right", "0"))
    set_motors(left, right)
    last_control_set_timestamp = datetime.timestamp(datetime.now())
    return {"status": "ok"}


@app.route("/control_arm_movement")
def control_arm_movement():
    """Endpoint used to control the arm movement.

    It receives the movement command in `joint_{0..5}` url query parameters.
    The values are requested offsets compared to the current position expressed in
    the same unit that's used by the maestro package.

    It's using a global parameter to store the arm position as it's only incrementing
    or decrementing it. An alternative here would be to read the current position from
    the maestro before issuing the move command.
    """
    global arm_requested_position
    joint_movement_requests = [
        int(request.args.get(f"joint_{i}", "0")) for i in range(6)
    ]
    for i in range(len(arm_requested_position)):
        arm_requested_position[i] += joint_movement_requests[i]
        if arm_requested_position[i] < ARM_CONTROL_MIN:
            arm_requested_position[i] = ARM_CONTROL_MIN
        if arm_requested_position[i] > ARM_CONTROL_MAX:
            arm_requested_position[i] = ARM_CONTROL_MAX
    if LOCAL_TESTING:
        print(f"Moving arm to position {arm_requested_position}")
    set_arm()
    return {"status": "ok"}


@app.route("/reset_arm")
def reset_arm():
    """Reset the arm to the base position."""
    global arm_requested_position
    arm_requested_position = ARM_BASE_POSITION.copy()
    set_arm()


@app.route("/shutdown")
def shutdown():
    """Shutdown the rover."""
    if LOCAL_TESTING:
        print("Would shutdown.")
    else:
        subprocess.call(["sudo", "shutdown", "-h", "now"])
    return {"status": "ok"}
