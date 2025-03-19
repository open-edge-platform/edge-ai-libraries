#!/bin/bash

npm install node-red-dashboard
npm install node-red-contrib-image-tools
npm install node-red-contrib-image-output
npm install node-red-node-annotate-image
npm install node-red-node-ui-iframe
apk update
apk add --no-cache ffmpeg

exit 0
