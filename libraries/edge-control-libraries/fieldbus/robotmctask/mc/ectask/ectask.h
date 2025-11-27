#include <motionentry.h>
#include <shmringbuf.h>
#include "ecservo.h"

class EcTask
{
public:
    EcTask(unsigned long affinity);
    virtual ~EcTask();

    bool RequestMaster(servo_master* masters, char* eni_file, unsigned id);
    bool ActivateMaster();
    void RequestVirtualMaster(unsigned long slave_size, unsigned id);
    bool ExecCycle();
    void registerCallback(std::function<void(void*, void*, void*)> func, void* in, void* out);
    void RigisterShmHandler(char* name, unsigned long blks, unsigned long blk_size, unsigned char issend, std::function<void(void*, void*, void*)> cb, void* data);
    void setPositionBySlaveIdx(unsigned int index, mcLREAL position);
    bool is_trajalldone();
    void SlaveSetHomePosRadianByIdx(unsigned int index, mcLREAL radian);
    unsigned long GetCpuAffinity();
    unsigned long GetMasterid();
    void UpdateServoConfigByIdx(unsigned int index,  unsigned long encode_accuracy, float gear_ratio, unsigned long cycle_us);
    void SetSlaveEnableByIdx(unsigned int index, bool enable);
    bool SlaveGetActJointState(unsigned int index, mcLREAL* pos, mcLREAL* vel, mcLREAL* acc, mcLREAL* toq);
    uint32_t GetSlaveSize();

private:
    void Init_Rtmotion();
    void ProcessAllRxFrames();
    void ProcessAllTxFrames();
    bool CheckAllSlavePowerOn();
    void executeCallback();
    void ShmHandleUpdate();
    void ShmHandlePublish();
    void EnableAllSlavePowerMode();
    bool CheckAllSlaveModeSwitch();
    bool CheckAllSlavePositionSetDone();

    servo_master* master = nullptr;
    uint32_t sc_size;
    EcServo** servo;
    std::function<void(void*, void*, void*)> callback;
    void* inPtr;
    void* outPtr;
    std::function<void(void*, void*, void*)> shm_decode;
    std::function<void(void*, void*, void*)> shm_encode;
    void* shm_decode_data;
    void* shm_encode_data;

    shm_handle_t send_handler;
    shm_handle_t recv_handler;
    char* send_buf;
    char* recv_buf;
    unsigned long send_size;
    unsigned long recv_size;
    unsigned long cpuset;
    unsigned long master_id;
    bool use_virtual_servo;
};
