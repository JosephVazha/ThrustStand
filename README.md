# Thrust Stand

A software and hardware platform for characterizing brushless DC (BLDC) motors, supporting the development and testing of advanced drone propulsion systems.

> **Demo:** TODO — Insert video

## Table of Contents

- [Project Overview](#project-overview)
- [Background and Motivation](#background-and-motivation)
  - [The Complexity of Existing Flight-Control Software](#the-complexity-of-existing-flight-control-software)
  - [The Lack of Affordable, Accessible Thrust Stands](#the-lack-of-affordable-accessible-thrust-stands)
  - [Bridging the Gap](#bridging-the-gap)
- [Features](#features)
- [Hardware Setup](#hardware-setup)
  - [Hardware Components](#hardware-components)
  - [Wiring Diagram](#wiring-diagram)
- [System Architecture](#system-architecture)
  - [ESC — FlyColor X-Cross HV3](#esc--flycolor-x-cross-hv3)
  - [Strain Gauge](#strain-gauge)
  - [LCD Screen](#lcd-screen)
- [Software Interface](#software-interface)
- [Setup and Usage](#setup-and-usage)
  - [Embedded Firmware](#embedded-firmware)
  - [Python Telemetry Interface](#python-telemetry-interface)
- [Reflection](#reflection)
- [Use of AI](#use-of-ai)

---

## Project Overview

## Background and Motivation

Modern drone electronics are largely designed around plug-and-play hobbyist ecosystems. While this makes building and operating drones relatively accessible, it creates an unexpected barrier when trying to develop, characterize, or independently test individual propulsion components.

Testing a motor and ESC (electronic speed controller) typically involves configuring a flight controller using software such as INAV, ArduPilot, Betaflight, PX4, or others. These platforms are powerful, but they expose an enormous number of parameters and configuration options intended for operating complete aircraft.

For someone already familiar with a particular flight-control ecosystem, configuring these systems may be relatively straightforward. However, for someone whose goal is simply to test a motor, the learning curve can be substantial. Even basic tasks, such as commanding a motor to spin independently of flight-controller sensor inputs, can require navigating configuration parameters, arming requirements, safety checks, and control modes.

Furthermore, these platforms are designed primarily for flight control, not propulsion characterization. While they may expose ESC telemetry, obtaining a useful experimental workflow often requires additional software and configuration to visualize measurements in real time and log them for later analysis.

This introduces a considerable amount of unnecessary complexity when the actual objective is much simpler: command a motor, measure its electrical behavior, measure its thrust, and record the results.

The alternative is to purchase a dedicated propulsion testing system. However, integrated thrust stands that combine motor control, force measurement, telemetry acquisition, visualization, and data logging are generally expensive, with professional systems such as Tyto Robotics costing well beyond what many students, hobbyists, and small engineering teams can reasonably justify.

In our experience, these also tend to suffer from limitations in their accompanying software. Proprietary interfaces can be buggy, difficult to extend, and closed source. Even when the underlying hardware is capable, users are often restricted to the functionality provided by the manufacturer's software. This makes it difficult to implement custom measurements, experiment with alternative hardware, or build new analysis tools on top of an existing platform.

There is a substantial gap between inexpensive hobby-grade propulsion electronics and professional characterization equipment. This gap makes little sense: the very components that make drone development accessible should also be independently testable and characterizable without requiring
Bridging the gap
The Thrust Stand was built to address this problem by providing an affordable, flexible, and extensible hardware-software platform for propulsion characterization.
Rather than configuring an entire flight controller or relying on proprietary testing equipment, the system communicates directly with the ESC, acquires force measurements from a strain gauge, and collects telemetry from the propulsion system.
The goal is to make it possible to command a motor, observe its behavior in real time, and log meaningful experimental data through a dedicated interface.
More broadly, the project aims to make hobby-grade propulsion electronics more transparent. By making it easier to characterize their performance and understand their limitations, engineers can make more informed decisions about when commercial off-the-shelf (COTS) components are sufficient and when custom electronics are justified.
This provides a more accessible middle ground between blindly relying on hobby-grade hardware and developing an entirely custom propulsion system.
Features
Live Telemetry: Real-time visualization of motor and system telemetry.
ESC Control: Directly controls a FlyColor X-Cross HV3 ESC and reads its KISS telemetry.
Thrust Measurement: Reads force measurements from a strain gauge through an ADC amplifier.
System Status: Displays system information and measurement data on an LCD.
Hardware-Level Access: Interfaces directly with propulsion hardware rather than relying on a flight controller abstraction.
Hardware Setup
The thrust stand integrates an electronic speed controller, a BLDC motor, a strain gauge, and an ADC amplifier. A microcontroller handles motor control and sensor acquisition, while a connected software interface provides telemetry visualization.
Hardware Components
Microcontroller: STM32F446RE (Nucleo development board).
ESC: FlyColor X-Cross HV3 80A.
Force Sensor: Strain gauge with an HX711 Module ADC
Display: I2C LCD.
Motor: BLDC motor under test.
Wiring Diagram

## System Architecture
The system is organized around three primary hardware interfaces: motor control and telemetry, force measurement, and system monitoring.
ESC — FlyColor X-Cross HV3
The ESC is controlled directly by the STM32 using an RC PWM control signal. This avoids the need for a flight controller to generate motor commands. More details on RC PWM can be found here.
The ESC also has a KISS one-wire telemetry interface, allowing the microcontroller to retrieve operating parameters, including:
Electrical RPM
Temperature
Voltage
Current
Current consumption
This provides direct insight into the electrical behavior of the propulsion system while the motor is operating. More details on the KISS telemetry protocol can be found here.
Strain Gauge
The strain gauge measures the force generated by the motor and propeller.
Its output is conditioned and amplified before being digitized by an ADC. The microcontroller reads this measurement alongside the ESC telemetry, allowing thrust and electrical performance to be monitored together.
LCD Screen
The LCD communicates with the microcontroller over I2C and provides local system status and measurement information.

## Software Interface
A Python-based interface provides live telemetry visualization and makes it easier to monitor the system during testing.
Setup and Usage
The project consists of embedded firmware running on the STM32 and a Python-based telemetry interface.
Embedded Firmware


Python Telemetry Interface



## Reflection
One of the biggest lessons from this project was the importance of maintaining consistency between hardware configuration tools and the actual firmware.
Initially, I did not consistently use STM32CubeMX to manage peripheral configuration. I made several configuration changes directly in the generated source code.
This created a mismatch between the firmware and the CubeM configuration file. Eventually, I encountered a bug where I had manually changed a timer prescaler in the source code without updating the corresponding CubeMX configuration.
When the project was regenerated, the manually modified value was overwritten. This caused unexpected timer behavior and took approximately two hours to identify and debug.
The experience reinforced the importance of having a single source of truth for hardware configuration. Going forward, I would make peripheral configuration changes in CubeMX and keep generated code separate from application logic wherever possible.
This project highlighted the relationship between embedded software and hardware design. A system can have logically correct firmware and still fail because of peripheral configuration, electrical connections, or timing assumptions.
I also learned the importance of developing incrementally and validating individual hardware interfaces before integrating them into a larger system.
In future projects, I would place greater emphasis on documenting peripheral configurations, testing interfaces independently, and maintaining a clear separation between generated configuration code and application logic.

## Use of AI
AI was used primarily as a design and development aid, particularly for UI design.
