#!/bin/bash
#
# Apache v2 license
# Copyright (C) 2024 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#
apt update 
apt install -y curl 
cd /home/pipeline-server/gst-udf-loader/
wget  --quiet https://scan.coverity.com/download/linux64 --post-data "token=$DLSPS_COVERITY_TOKEN&project=$DLSPS_COVERITY_PROJECT" -O coverity_tool.tgz 
mkdir cov-analysis
tar xzf coverity_tool.tgz --strip-components=1 -C cov-analysis
/bin/bash -c "cd /home/pipeline-server/gst-udf-loader/ \
	          && if [ -d \"build\" ] ; then rm -rf build ; fi \
		            && mkdir build \
			              && cd gst_plugin && sed -i '/dlstreamer_gst_meta/c\\\t/opt/intel/dlstreamer/lib/libdlstreamer_gst_meta.so' CMakeLists.txt && cd .. \
				                && cd build \
						          && cmake -DCMAKE_BUILD_TYPE=${CMAKE_BUILD_TYPE} -DCMAKE_INSTALL_INCLUDEDIR=${CMAKE_INSTALL_PREFIX}/include -DCMAKE_INSTALL_PREFIX=${CMAKE_INSTALL_PREFIX} .. \
							            && /home/pipeline-server/gst-udf-loader/cov-analysis/bin/cov-build --dir cov-int make"

cd /home/pipeline-server/gst-udf-loader/build
echo "Create tarball for upload"
tar czf coverity-output.tgz cov-int
echo "Upload to Coverity Scan"         
curl --form token=$DLSPS_COVERITY_TOKEN --form email=$DLSPS_COVERITY_EMAIL  --form file=@coverity-output.tgz --form version="`date +%Y%m%d%H%M%S`" --form description="GitHub Action upload" https://scan.coverity.com/builds?project=$DLSPS_COVERITY_PROJECT
cp coverity-output.tgz /tmp/