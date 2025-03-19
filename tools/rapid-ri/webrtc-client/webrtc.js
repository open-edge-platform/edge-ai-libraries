/* 
/*
Copyright (C) 2022 Intel Corporation
SPDX-License-Identifier: MIT

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

  Adapted from code by: Nirbheek Chauhan <nirbheek@centricular.com>
  Updated by: Andrew Herrold <andrew.herrold@intel.com>, Tome Vang <andrew.herrold@intel.com>
*/
"use strict";
var g_pipeline_server_host=window.location.hostname;
var g_pipeline_server_port="8080";
var PIPELINE_SERVER = "http://" + g_pipeline_server_host + ':' + g_pipeline_server_port;
var ws_server;
var ws_port;
var g_pipeline_server_instance_id = null;
var g_default_server_peer_id = null;
// Set this to use a specific peer id instead of a random one; e.g., 256
var default_peer_id = null;

// Override with your own STUN servers if you want
var rtc_configuration = {

}
//var rtc_configuration = {iceServers: [{urls: "stun:stun.services.mozilla.com"},
//                                      {urls: "stun:stun.l.google.com:19302"}]};

// Launchable WebRTC pipelines
var auto_retry = true;
var DELAY_AUTOSTART_MSEC=2000

// The default constraints that will be attempted. Can be overriden by the user.
var default_constraints = {video: true, audio: false};

var connect_attempts = 0;
var loop = false;
var peer_connection;
var send_channel;
var ws_conn = null;
// Promise for local stream after constraints are approved by the user
var local_stream_promise;
var statsTimer;
var autoConnect

window.addEventListener('load', (event) => {
    /* istanbul ignore next */
    setPipelinePort();
});

function setPipelinePort(){
    console.log("Checking EVAM server status at", PIPELINE_SERVER)
    fetch(PIPELINE_SERVER + "/pipelines/status", {
        method: 'GET',
        })
    .then((response) => response.json())
    .then((data) => {
    console.log('Success, port set to 8443');
    ws_port = 8443;

    })
    .catch((error) => {
    console.error('Error:', error);
    ws_port = 30006;
    console.log("setting port to fallback 30006")
    });
}

function getOurId() {
    return Math.floor(Math.random() * (9000 - 10) + 10).toString();
}
/* istanbul ignore next */
function resetState() {
    // This will call onServerClose()
    if (ws_conn) {
        ws_conn.close();
    
    } else {
        console.log("INFO: resetState called with no active connection.")
    }
}

function handleIncomingError(error) {
    setError("ERROR: " + error);
    resetState();
    if (auto_retry) {
        window.setTimeout(websocketServerConnect, DELAY_AUTOSTART_MSEC);
    }
}

function getVideoElement() {
    return document.getElementById("stream");
}

function setStatus(text) {
    console.log(text);
    var span = document.getElementById("status")
    if (!span.classList.contains('error'))
        span.textContent = text;
}

function setError(text) {

    console.error(text);
    var span = document.getElementById("status")
    var newContent = text;
    if (!span.classList.contains('error'))
        span.classList.add('error');
    else {
        newContent = span.textContent + text;
    }
    span.style.visibility = "visible";
    span.textContent = newContent;
}

function resetVideo() {
    // Reset the video element and stop showing the last received frame
    var videoElement = getVideoElement();
    videoElement.pause();
    videoElement.src = "";
    videoElement.load();
}

// SDP offer received from peer, set remote description and create an answer
function onIncomingSDP(sdp) {
    /* istanbul ignore next */
    if (typeof peer_connection !== "undefined") {
        peer_connection.setRemoteDescription(sdp).then(() => {
            setStatus("Remote SDP set");
            if (sdp.type != "offer")
                return;
            setStatus("Got SDP offer");
            if (local_stream_promise) {
                local_stream_promise.then((stream) => {
                    setStatus("Got local stream, creating answer");
                    peer_connection.createAnswer()
                    .then(onLocalDescription).catch(setError);
                }).catch(setError);
            } else {
                peer_connection.createAnswer().then(onLocalDescription).catch(setError);
            }
        }).catch(setError);
    } else {
        console.log("ERROR: onIncomingSDP called with no active peer connection.")
    }
}
/* istanbul ignore next */
// Local description was set, send it to peer
function onLocalDescription(desc) {
    setStatus("Sending SDP answer");
    peer_connection.createAnswer()
    .then((answer) => peer_connection.setLocalDescription(answer))
    .then(() => {
        const msg = {sdp: peer_connection.localDescription};
        ws_conn.send(JSON.stringify(msg));
    })
    .catch(setError);
    
}
/* istanbul ignore next */
// ICE candidate received from peer, add it to the peer connection
function onIncomingICE(ice) {
    if (typeof RTCPeerConnection !== 'undefined') {
        var candidate = new RTCIceCandidate(ice);
        peer_connection.addIceCandidate(candidate).catch(setError);
    }
}

function onServerMessage(event) {
    console.log("Received " + event.data);
    switch (event.data) {
        case "HELLO":
            /* istanbul ignore next */
            if (ws_conn != undefined){
                ws_conn.send('SESSION ' + g_default_server_peer_id);
            }
            setStatus("Registered with server, waiting for call");
            return;
        case "SESSION_OK":
            setStatus("Initiating stream session");
            /* istanbul ignore next */
            if (ws_conn != undefined){
                ws_conn.send('START_WEBRTC_STREAM');
            }
            return;
        default:
            setStatus("Event received while registering with server: " + event.data);
            if (event.data.startsWith("ERROR")) {
                handleIncomingError(event.data);
                return;
            }
            // Handle incoming JSON SDP and ICE messages
            try {
                var msg = JSON.parse(event.data);
            } catch (e) {
                /* istanbul ignore next */
                if (e instanceof SyntaxError) {
                    handleIncomingError("Error parsing incoming JSON: " + event.data);
                } else {
                    handleIncomingError("Unknown error parsing response: " + event.data);
                }
                return;
            }

            // Incoming JSON signals the beginning of a call
            if (!peer_connection)
                createCall(msg);

            if (msg.sdp != null) {
                onIncomingSDP(msg.sdp);
            } else if (msg.ice != null) {
                onIncomingICE(msg.ice);
            } else {
                handleIncomingError("Unknown incoming JSON: " + msg);
            }
    }
}

function onServerClose(event) {
    setStatus('Stream ended. Disconnected from server');
    resetVideo();
    clearTimeout(statsTimer);
    /* istanbul ignore next */
    if (peer_connection) {
        peer_connection.close();
        peer_connection = null;
    }
    /* istanbul ignore next */
    // Reset after a second if we want to loop (connect and re-stream)
    if (loop) {
        window.setTimeout(websocketServerConnect, 1000);
    }
}

function onServerError(event) {
    setError("Unable to connect to server. Confirm it is running and accessible on network.")
    // Retry after 2 seconds
    window.setTimeout(websocketServerConnect, DELAY_AUTOSTART_MSEC);
}

function setStreamInstance() {
    const params = new Proxy(new URLSearchParams(window.location.search), {
        get: (searchParams, prop) => searchParams.get(prop),
    });
    g_pipeline_server_instance_id = params.instance_id;
    g_default_server_peer_id = params.destination_peer_id;
    /* istanbul ignore next */
    if (g_pipeline_server_instance_id) {
        console.log("Will attempt to automatically connect to instance_id: " + g_pipeline_server_instance_id);
    } else {
        console.error("Pipeline server instance id not provided in request - stream will not connect")
    }
    /* istanbul ignore next */
    if (g_default_server_peer_id) {
        console.log("Will attempt to automatically connect using frame destination peer_id: " + g_default_server_peer_id);
    } else {
        console.error("Default server peer id not provided - stream will nto connect")
    }
    setStatus("WebRTC auto-connecting to instance: '" + g_pipeline_server_instance_id + "' peer_id: '" + g_default_server_peer_id + "'");
    autoConnect = (g_default_server_peer_id && g_pipeline_server_instance_id);

    return autoConnect;
}

function websocketServerConnect() {
    connect_attempts++;
    /* istanbul ignore next */
    if (connect_attempts > 15) {
        setError("Too many connection attempts, aborting. Refresh page to try again");
        return;
    }
    /* istanbul ignore next */
    // initialize Pipeline Server API parameters
    if (typeof initPipelineValues !== "undefined") {
        initPipelineValues();
    }
    
    // if empty, populate pipeline server instance id to connect using value from query param
    if (typeof setStreamInstance !== "undefined") {
        var attempt_connect = setStreamInstance();
    }
    /* istanbul ignore next */
    if (attempt_connect) {
        console.log("Parameters provided - attempting to connect");
    } else {
        console.error("No stream parameters provided, not connecting to stream")
    }
    if (typeof g_default_server_peer_id == "undefined" || !g_default_server_peer_id) {
        console.log("Will not attempt connection until Pipeline Server WebRTC frame destination peerid is requested.");
    }

    // Clear errors in the status span for fresh run
    console.log("Clearing error state from WebRTC status field.")
    var span = document.getElementById("status");
    span.classList.remove('error');
    console.log("Clearing stats for fresh WebRTC run");
    window.document.getElementById("stats").innerHTML = "Preparing WebRTC Stats...";
    // Populate constraints
    var textarea = document.getElementById('constraints');
    if (textarea.value == '')
        textarea.value = JSON.stringify(default_constraints);
    // Fetch the peer id to use
    var peer_id = default_peer_id || getOurId();
    var ws_port = ws_port || '8443';
    /* istanbul ignore next */
    if (window.location.protocol.startsWith ("file")) {
        var ws_server = ws_server || "127.0.0.1";
    } else if (window.location.protocol.startsWith ("http")) {
        let searchParams = new URLSearchParams(window.location.search);
        if (searchParams.has("websocket") === true) {
            var ws_server = searchParams.get("websocket");
            ws_port = searchParams.get("wsport");
        } else {
            var ws_server = ws_server || window.location.hostname;
        }
    } else {
        throw new Error ("Don't know how to connect to the signaling server with uri" + window.location);
    }

    // Support AutoPlay in Chrome/Safari browsers
    var autoPlayVideo = document.getElementById("stream");
    /* istanbul ignore next */
    autoPlayVideo.oncanplaythrough = function() {
        autoPlayVideo.muted = true;
        autoPlayVideo.play();
        autoPlayVideo.pause();
        autoPlayVideo.play();
    }
    /* istanbul ignore next */
    if (typeof autoPlayVideo.scrollIntoView !== "undefined"){
        autoPlayVideo.scrollIntoView(false);
    }
    

    var ws_url = 'ws://' + ws_server + ':' + ws_port;
    setStatus("Connecting to server " + ws_url);
    ws_conn = new WebSocket(ws_url);
    /* When connected, immediately register with the server */
    ws_conn.addEventListener('open', (event) => {
        ws_conn.send('HELLO ' + peer_id);
        setStatus("Registering with server as client " + peer_id.toString());
    });
    ws_conn.addEventListener('error', onServerError);
    ws_conn.addEventListener('message', onServerMessage);
    ws_conn.addEventListener('close', onServerClose);
}

function onRemoteTrack(event) {
    console.log(event)
    if (getVideoElement().srcObject !== event.streams[0]) {
        console.log('Incoming stream');
        getVideoElement().srcObject = event.streams[0];
    }
}

function errorUserMediaHandler() {
    setError("Browser doesn't support getUserMedia!");
}

const handleDataChannelOpen = (event) =>{
    console.log("dataChannel.OnOpen", event);
};

const handleDataChannelMessageReceived = (event) =>{
    console.log("dataChannel.OnMessage:", event, event.data.type);

    setStatus("Received data channel message");
    if (typeof event.data === 'string' || event.data instanceof String) {
        console.log('Incoming string message: ' + event.data);
        var textarea = document.getElementById("text")
        if (textarea !== null){
            textarea.value = textarea.value + '\n' + event.data
        } else {
            textarea = {
                value: event.data
            }
        }
    } else {
        console.log('Incoming data message');
    }
    if (typeof send_channel !== "undefined"){
        send_channel.send("Hi! (from browser)");
    }
};
   

const handleDataChannelError = (error) =>{
    console.log("dataChannel.OnError:", error);
};

const handleDataChannelClose = (event) =>{
    console.log("dataChannel.OnClose", event);
};

function onDataChannel(event) {
    setStatus("Data channel created");
    let receiveChannel = event.channel;
    receiveChannel.onopen = handleDataChannelOpen;
    receiveChannel.onmessage = handleDataChannelMessageReceived;
    receiveChannel.onerror = handleDataChannelError;
    receiveChannel.onclose = handleDataChannelClose;
}

function printStats() {
    var statsEvery6Sec = window.setInterval(function() {
        /* istanbul ignore next */
        if (peer_connection == null) {
            setStatus("Stream completed. Check console output for detailed information.");
            clearInterval(statsEvery6Sec);
        } else {
            peer_connection.getStats(null).then(stats => {
            let statsOutput = "";
            if (g_pipeline_server_instance_id != "unknown") {
                statsOutput += `<h2>Pipeline Summary:</h2>\n<strong><a target="_blank" href=${PIPELINE_SERVER}/pipelines/${g_pipeline_server_instance_id}>${PIPELINE_SERVER}/pipelines/${g_pipeline_server_instance_id}</a></strong>`
                statsOutput += `<h2>Pipeline Status:</h2>\n<strong><a target="_blank" href=${PIPELINE_SERVER}/pipelines/status/${g_pipeline_server_instance_id}>${PIPELINE_SERVER}/pipelines/status/${g_pipeline_server_instance_id}</a></strong>`
            } else {
                statsOutput += `<h2>Pipeline Server Instance ID UNKNOWN</h2>`
            }
            stats.forEach(report => {
                statsOutput += `<h2>Report: ${report.type}</h2>\n<strong>ID:</strong> ${report.id}<br>\n` +
                            `<strong>Timestamp:</strong> ${report.timestamp}<br>\n`;
                // Now the statistics for this report; we intentionally drop the ones we
                // sorted to the top above
                Object.keys(report).forEach(statName => {
                if (statName !== "id" && statName !== "timestamp" && statName !== "type") {
                    statsOutput += `<strong>${statName}:</strong> ${report[statName]}<br>\n`;
                }
                });
            });
            window.document.getElementById("stats").innerHTML = statsOutput;
            });
        }
    }, 6000);
}

function createCall(msg) {
    // Reset connection attempts because we connected successfully
    connect_attempts = 0;

    console.log('Creating RTCPeerConnection');
    setStatus("Creating RTCPeerConnection");
    /* istanbul ignore next */
    if (typeof RTCPeerConnection !== 'undefined') {
        peer_connection = new RTCPeerConnection(rtc_configuration);
        send_channel = peer_connection.createDataChannel('label', null);
        send_channel.onopen = handleDataChannelOpen;
        send_channel.onmessage = handleDataChannelMessageReceived;
        send_channel.onerror = handleDataChannelError;
        send_channel.onclose = handleDataChannelClose;
        peer_connection.ondatachannel = onDataChannel;
        peer_connection.ontrack = onRemoteTrack;
        statsTimer = setTimeout(printStats, 4000);
    } else {
        setError("Browser doesn't support WebRTC!");
    }

    if (!msg.sdp) {
        console.log("WARNING: First message wasn't an SDP message!?");
    }
    /* istanbul ignore next */
    if (typeof peer_connection !== "undefined") {
        peer_connection.onicecandidate = (event) => {
            // We have a candidate, send it to the remote party with the same uuid
            if (event.candidate == null) {
                console.log("ICE Candidate was null, done");
                return;
            }
            ws_conn.send(JSON.stringify({'ice': event.candidate}));
        };
    }

    setStatus("Created peer connection for call, waiting for SDP");
}

module.exports = {
    setPipelinePort,
    createCall,
    onServerError,
    onServerMessage,
    onServerClose,
    onRemoteTrack,
    errorUserMediaHandler,
    handleDataChannelOpen,
    handleDataChannelMessageReceived,
    handleDataChannelError,
    handleDataChannelClose,
    setStreamInstance,
    onDataChannel,
    printStats,
    onIncomingICE,
    onIncomingSDP,
    resetState,
    resetVideo,
    setStatus,
    setError,
    getVideoElement,
    handleIncomingError,
    getOurId,
    websocketServerConnect,
    handleDataChannelClose,
    handleDataChannelError,
    handleDataChannelMessageReceived,
    handleDataChannelOpen
}