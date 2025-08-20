import { io } from "socket.io-client";

let settings;
let latestData = null

// Create a single socket connection to the main server
const mainSocket = io('ws://localhost:4001');

// Create namespace connections using the main socket
const dataChannel = mainSocket.io.socket('/data');
const adcChannel = mainSocket.io.socket('/adc');
const canChannel = mainSocket.io.socket('/can');

// Function to handle incoming canbus settings
const handlesensorSettings = (data) => {
    settings = data.sensors;
    canChannel.connect();
};

// Listen for canbus settings
canChannel.on("settings", handlesensorSettings);

// Listen for adc settings
adcChannel.on("settings", handlesensorSettings);

dataChannel.on("data", (data) => {
  if (data && typeof data.timestamp === 'number' && data.data) {
    latestData = { values: data.data, timestamp: Date.now() }
  }
});

onmessage = (event) => {
  switch (event.data.type) {
    case 'request':
      dataChannel.emit('request');
      if (latestData) {
        postMessage({ type: 'message', ...latestData });
        latestData = null; // drop it so backlog can't build
      }
      break;
  }
}