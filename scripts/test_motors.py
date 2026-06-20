#!/usr/bin/env python3
"""Test each motor movement automatically (3s each)."""
import RPi.GPIO as GPIO
import time

IN1, IN2, IN3, IN4 = 8, 7, 16, 20

def setup():
    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)
    for p in (IN1, IN2, IN3, IN4):
        GPIO.setup(p, GPIO.OUT, initial=GPIO.LOW)

def run(desc, a, b, c, d, sec=3):
    print(f"\n{desc}  ({sec}s)")
    GPIO.output(IN1, a); GPIO.output(IN2, b)
    GPIO.output(IN3, c); GPIO.output(IN4, d)
    print(f"  IN1={a} IN2={b} IN3={c} IN4={d}")
    time.sleep(sec)
    for p in (IN1, IN2, IN3, IN4):
        GPIO.output(p, 0)

try:
    setup()
    print("=== Motor Test (wiring reversed) ===")
    run("Motor A forward",  0,1,0,0)
    run("Motor A backward", 1,0,0,0)
    run("Motor B forward",  0,0,0,1)
    run("Motor B backward", 0,0,1,0)
    run("Both forward",     0,1,0,1)
    run("Both backward",    1,0,1,0)
    run("Pivot right",      0,1,1,0)
    run("Pivot left",       1,0,0,1)
    print("\nDone")
finally:
    GPIO.cleanup()
