#pragma once

namespace inference
{
    struct inferstat
    {
        int count;
        float avg;
        float max;
        float min;
    };

    class InferenceStat
    {
    public:
        InferenceStat() {
            stat.count = 0;
            stat.avg = 0;
            stat.max = -1;
            stat.min = 0x7fffffff;
        }
        virtual ~InferenceStat() = default;

        inferstat stat;
        void UpdateInferenceTime(double time_ms){
            if(time_ms < stat.min){
                stat.min = time_ms;
            }
            if(time_ms > stat.max){
                stat.max = time_ms;
            }
            stat.avg = (stat.avg*stat.count + time_ms)/(stat.count + 1);
            stat.count++;
        }

        void ResetInferenceStat(){
            stat.count = 0;
            stat.avg = 0;
            stat.max = -1;
            stat.min = 0x7fffffff;
        }

    protected:

    private:

    };

} // namespace inference
