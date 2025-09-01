# plcopen-servo

PLCopen servo control interface that connects the EtherCAT EnableKit and RTmotion.

## Depends
- Igh EtherCAT
- EtherCAT EnableKit  
- PLCopen Motion Library (RTmotion)

## Run

```bash
cd <plcopen-servo root dir>/build/

# 1 axis control
# MC_MoveVelocity + 1 EtherCAT servo motor
./test/solo_rtmotion_demo -n ../test/inovance_solo_1ms.xml -i 1000

# 2 axis control
# MC_MoveVelocity + 1 EtherCAT servo motor
# MC_MoveRelative + 1 EtherCAT servo motor
./test/duo_rtmotion_demo -n ../test/inovance_duo_1ms.xml -i 1000

# 6 axis control
./test/six_rtmotion_demo -a 1 -n ../test/inovance_six_1ms.xml -i 1000
```
