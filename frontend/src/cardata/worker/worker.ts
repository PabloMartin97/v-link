import { io } from "socket.io-client";

let settings;
// Connect to the canbus namespace to receive continuous data stream
const dataChannel = io("ws://localhost:4001/data");

const adcChannel = io("ws://localhost:4001/adc");
const canChannel = io("ws://localhost:4001/can");

// Function to handle incoming canbus settings
const handlesensorSettings = (data) => {
    settings = data.sensors;
    canChannel.connect();
};
// Function to post updated car data to the main thread
const postCarDataToMain = (data) => {
    const message = {
        type: 'message',
        message: data
      };
    postMessage(message);
};

// Listen for canbus settings
canChannel.on("settings", handlesensorSettings);

// Listen for adc settings
adcChannel.on("settings", handlesensorSettings);

// Listen for continuous data stream from data namespace
dataChannel.on("data", (data) => {
    // Check if the received data has the new structure with a timestamp
    if (data && typeof data.timestamp === 'number' && data.data) {
        const now_ms = Date.now();
        const request_timestamp_ms = data.timestamp * 1000;
        const round_trip_latency_ms = now_ms - request_timestamp_ms;

        //console.log(`Server latency: ${Math.round(round_trip_latency_ms)}ms`);

        // Post only the actual car data values to the main thread
        const message = { type: 'message', values: data.data, timestamp: now_ms}
        postCarDataToMain(message);
    }
});

// Send a request for data values
setInterval(() => {
    dataChannel.emit('request');
}, 100);

// Send a request for adc settings
//adcChannel.emit("load");
//canChannel.emit("load");

onmessage = async (event: MessageEvent<Command>) => {
    switch (event.data.type) {
        case 'hello':
            postMessage("Webworker says hi?")
            break
    }
}