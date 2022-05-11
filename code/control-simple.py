from time import sleep
import subprocess

import readchar
import RPi.GPIO as GPIO

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


def set_dir_pin(power, dir_pin):
    if power < 0:
        GPIO.output(dir_pin, GPIO.HIGH)
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

    set_dir_pin(left_power, LEFT_DIR_PIN)
    set_dir_pin(right_power, RIGHT_DIR_PIN)

    RIGHT_PWM.ChangeDutyCycle(abs(right_power))
    LEFT_PWM.ChangeDutyCycle(abs(left_power))


try:
    print("Press control button <WSAD>")
    while True:
        key = readchar.readchar()
        if key == "w":
            set_motors(50, 50)
        elif key == "a":
            set_motors(-50, 50)
        elif key == "d":
            set_motors(50, -50)
        elif key == "s":
            set_motors(-50, -50)
        elif key == "W":
            set_motors(100, 100)
        elif key == "A":
            set_motors(-100, 100)
        elif key == "D":
            set_motors(100, -100)
        elif key == "S":
            set_motors(-100, -100)
        elif key == " ":
            set_motors(0, 0)
        elif key == "q":
            exit()
        else:
            print(f"invalid input: {key}")
finally:
    set_motors(0, 0)
    GPIO.cleanup()
