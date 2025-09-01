# PLCopen Motion Control

For more information, please see the complete [documentation](https://docs.openedgeplatform.intel.com/edge-ai-libraries/plcopen-motion-control/main/index.html) 

## Description

The PLCopen motion standard provides a way to have standard and modular application libraries that are reusable for multiple industrial automation scenarios, such as PLC motion control, CNC and robotics. For more detailed information of the PLCopen motion specifications, please refer to [Motion Control](https://plcopen.org/technical-activities/motion-control).

## Collection

**Libraries**

| Library Name     | Description |
| ---------------- | ----------- |
| [RTmotion](https://docs.openedgeplatform.intel.com/edge-ai-libraries/plcopen-motion-control/main/rt-motion/rt-motion.html) | RTmotion is a library designed to match the interfaces and functions of the function blocks defined in PLCopen standard. It is not tied to any operating system, fieldbus, SoftPLC or applications. But it needs to run in a real-time thread to have steady cycle and gain maximum performance. So the real-time operating systems are the base foundation for RTmotion to run on.|
| [PLCopen Servo](plcopen-servo) | PLCopen servo control interface that connects the EtherCAT EnableKit and RTmotion. |

**Sample Applications**

| Application Name | Description |
| ---------------- | ----------- |
| [PLCopen Benchmark](plcopen-benchmark) | Motion control benchmark with PLCopen Function Blocks |
| [PLCopen Databus](plcopen-databus) | Communication layer which facilitates communication between real-time motion control applications and non-real-time applications. |

