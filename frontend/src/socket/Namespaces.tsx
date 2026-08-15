import { io, Socket } from "socket.io-client";

let sockets: {
  [key: string]: Socket
} | null = null;

export function useNamespaces() {
  if (!sockets) {
    sockets = {
      app: io("ws://localhost:4001/app"),
      can: io("ws://localhost:4001/can"),
      swc: io("ws://localhost:4001/swc"),
      adc: io("ws://localhost:4001/adc"),
      rti: io("ws://localhost:4001/rti"),
      sys: io("ws://localhost:4001/sys"),
      log: io("ws://localhost:4001/log"),
      // Keep the frontend key as `cam`, but connect to the namespace exposed
      // by the backend.
      cam: io("ws://localhost:4001/rearcam"),
      
      data: io("ws://localhost:4001/data"),
    };
  }
  return sockets;
}
