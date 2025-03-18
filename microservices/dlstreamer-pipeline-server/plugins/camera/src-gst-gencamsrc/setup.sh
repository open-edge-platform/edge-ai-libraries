echo "Copying GenICam runtime binaries to /usr/lib/x86_64-linux-gnu/"
cp plugins/genicam-core/genicam/bin/*.so /usr/lib/x86_64-linux-gnu/
echo "GenICam runtime copied to /usr/lib/x86_64-linux-gnu/"
./autogen.sh
echo "configure run"
make
echo "make successful"
make install
echo "install successful"
ldconfig
export GST_PLUGIN_PATH=/usr/local/lib/gstreamer-1.0
echo "GST_PLUGIN_PATH set to /usr/local/lib/gstreamer-1.0"
echo "Please set GENICAM_GENTL64_PATH to GenTL producer directory"
echo "exiting setup"
