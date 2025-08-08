# plcopen-benchmark
Motion control benchmark with PLCopen Function Blocks

## Depends
This repo depends on:
- plcopen-motion
- plcopen-servo
- ecat-enablekit

## Build
After setting up the dpendencies, follow below commands to build:
```shell
mkdir build && cd build

cmake ..

make
```

## Run
Run the benchmark program ``plcopen_benchmark``:
```shell
plcopen_benchmark --<options>

# Global options:
#     --eni          -n  Specify ENI/XML file.
#     --interval     -i  Specify RT cycle time(us).
#     --affinity     -a  Specify RT thread CPU affinity.
#     --break-trace  -b  Latency threshold (us) to break trace.
#     --cache        -c  Enable cache miss count.
#     --axis-num     -m  Specify axis number.
#     --time         -t  Specify running time(s).
#     --log          -l  Enable output to log file.
#     --verbose      -v  Be verbose.
#     --spike        -s  Specify spike value(us).
#     --output       -o  Enable output in 10ms cycle.
#     --real-servo   -r  User real servo instead of virtual servo.
#     --help         -h  Show this help.
```