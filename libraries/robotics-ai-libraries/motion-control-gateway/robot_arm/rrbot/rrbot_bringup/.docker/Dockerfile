From moveit/moveit2:foxy-source
MAINTAINER Yan Yu yu.yan@intel.com

COPY ./rrbot /root/ws_moveit/src/
COPY ./shmringbuf.h /usr/local/include/
COPY ./libshmringbuf.so.0.1.0 /usr/local/lib/

RUN ln -s /usr/local/lib/libshmringbuf.so.0.1.0 /usr/local/lib/libshmringbuf.so && \
    ldconfig && \
    cd /root/ws_moveit && \
    . /opt/ros/foxy/setup.sh && \
    colcon build
