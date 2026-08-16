import React, { useEffect, useRef, useState } from "react";
import styled, { useTheme } from 'styled-components';
import { useNamespaces } from "@/socket/Namespaces";
import { Typography } from "@/theme/styles/Typography";
import { APP } from "@/store/Store";

type ReverseCamSettings = {
  deviceSelectionMode?: { value: string };
  deviceId?: { value: string };
  deviceLabel?: { value: string };
  videoWidth?: { value: number };
  videoHeight?: { value: number };
  videoFps?: { value: number };
};

const VIDEO_START_TIMEOUT_MS = 10_000;

const getCameraErrorMessage = (error: unknown) => {
  const mediaError = error as DOMException & { constraint?: string };

  switch (mediaError?.name) {
    case "NotAllowedError":
      return "Camera access was denied. Allow camera access in Chromium permissions and try again.";
    case "NotFoundError":
      return "No video input device was found. Check that the camera or video grabber is connected and recognized by the system.";
    case "NotReadableError":
      return "The video device was found but could not be read. It may be disconnected, already in use, or unavailable to Chromium.";
    case "OverconstrainedError":
      return `The selected camera cannot satisfy the requested${mediaError.constraint ? ` ${mediaError.constraint}` : " video"} setting. Try another resolution, frame rate, or device.`;
    case "SecurityError":
      return "Camera access is blocked by the browser security policy for this page.";
    case "AbortError":
      return "The camera stopped while Chromium was opening it. Reconnect the device and try again.";
    case "PlaybackError":
    case "VideoTimeoutError":
      return mediaError.message;
    default:
      return mediaError?.message
        ? `Failed to open the video device: ${mediaError.message}`
        : "Failed to open the video device for an unknown reason.";
  }
};

const waitForVideoData = (video: HTMLVideoElement) => {
  if (video.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA) {
    return Promise.resolve();
  }

  return new Promise<void>((resolve, reject) => {
    const finish = (result: "ready" | "error" | "timeout") => {
      window.clearTimeout(timeoutId);
      video.removeEventListener("loadeddata", onLoadedData);
      video.removeEventListener("error", onVideoError);

      if (result === "ready") {
        resolve();
      } else {
        const error = new Error(
          result === "timeout"
            ? "The video device opened, but no video frames were received within 10 seconds. Check the selected channel, cable, and video signal."
            : "The camera stream opened, but Chromium reported a video decoding or playback error."
        );
        error.name = result === "timeout" ? "VideoTimeoutError" : "PlaybackError";
        reject(error);
      }
    };

    const onLoadedData = () => finish("ready");
    const onVideoError = () => finish("error");
    const timeoutId = window.setTimeout(() => finish("timeout"), VIDEO_START_TIMEOUT_MS);

    video.addEventListener("loadeddata", onLoadedData, { once: true });
    video.addEventListener("error", onVideoError, { once: true });
  });
};

const Container = styled.div`
  position: relative;
  width: 100%;
  height: 100%;
  background: #000;
  overflow: hidden;
`;
const Video = styled.video`
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: contain;
  background: #000;
`;
const OverlayImg = styled.img`
  position: absolute;
  top: 50%; left: 50%;
  transform: translate(-50%, -50%);
  width: 90%;
  object-fit: contain;
  pointer-events: none;
  z-index: 5;
`;
const BottomText = styled.div`
  position: absolute;
  left: 0; right: 0; bottom: 0;
  padding: 10px 14px;
  text-align: center;
  color: #fff;
  font-size: 25px;
  letter-spacing: .2px;
  background: linear-gradient(to top, rgba(0,0,0,.55), rgba(0,0,0,0));
  user-select: none;
  pointer-events: none;
  z-index: 5;
`;
const CenterMsg = styled.div`
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  color: #fff;
  z-index: 4;
`;

export default function Rearcam() {
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const openingRef = useRef(false);
  const requestIdRef = useRef(0);
  const socket = useNamespaces();

  const Caption = Typography.Subtitle;
  const theme = useTheme();
  const reverseCamSettings = APP((state) => state.settings.reverseCam as ReverseCamSettings | undefined);

  const [status, setStatus] =
    useState<"idle" | "opening" | "playing" | "error" | "denied">("idle");
  const [err, setErr] = useState("");

  // Turn GPIO on when entering and off when leaving
  useEffect(() => {
    socket.cam.emit('mount');
    return () => {
      socket.cam.emit('unmount');
    };
  }, []);

  // Configurable bottom text
  const overlayText = "CHECK SURROUNDINGS";

  const stopStream = () => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    if (videoRef.current) videoRef.current.srcObject = null;
  };

  const buildVideoConstraints = async () => {
    const constraints: MediaTrackConstraints = {};
    const selectionMode = reverseCamSettings?.deviceSelectionMode?.value ?? "auto";
    const deviceId = reverseCamSettings?.deviceId?.value ?? "";
    const deviceLabel = reverseCamSettings?.deviceLabel?.value ?? "";
    const width = Number(reverseCamSettings?.videoWidth?.value ?? 0);
    const height = Number(reverseCamSettings?.videoHeight?.value ?? 0);
    const fps = Number(reverseCamSettings?.videoFps?.value ?? 0);

    if (Number.isFinite(width) && width > 0) constraints.width = { ideal: width };
    if (Number.isFinite(height) && height > 0) constraints.height = { ideal: height };
    if (Number.isFinite(fps) && fps > 0) constraints.frameRate = { ideal: fps };

    if (selectionMode === "deviceId" && deviceId && deviceId !== "default") {
      const devices = navigator?.mediaDevices?.enumerateDevices
        ? await navigator.mediaDevices.enumerateDevices()
        : [];
      const deviceAvailable = devices.some(
        (device) => device.kind === "videoinput" && device.deviceId === deviceId
      );
      // A saved ID can change after moving the grabber to another USB port.
      // Fall back for this session without erasing the user's preference.
      if (deviceAvailable) constraints.deviceId = { exact: deviceId };
    } else if (selectionMode === "label" && deviceLabel && navigator?.mediaDevices?.enumerateDevices) {
      const devices = await navigator.mediaDevices.enumerateDevices();
      const match = devices.find(
        (device) =>
          device.kind === "videoinput" &&
          device.label.toLowerCase().includes(deviceLabel.toLowerCase())
      );
      if (match?.deviceId) {
        constraints.deviceId = { exact: match.deviceId };
      }
    }

    return constraints;
  };

  const openCamera = async () => {
    const requestId = ++requestIdRef.current;
    openingRef.current = true;
    setStatus("opening"); setErr("");
    try {
      stopStream();
      if (!navigator?.mediaDevices?.getUserMedia) {
        throw new Error("Media devices API not available");
      }

      const constraints = await buildVideoConstraints();
      const videoConstraint =
        Object.keys(constraints).length > 0 ? constraints : true;

      const stream = await navigator.mediaDevices.getUserMedia({
        video: videoConstraint,
        audio: false,
      });

      // The user may have left Rearcam or changed camera settings while the
      // browser was still opening this device. Never keep an outdated stream.
      if (requestId !== requestIdRef.current) {
        stream.getTracks().forEach((track) => track.stop());
        return;
      }

      streamRef.current = stream;
      if (videoRef.current) {
        const video = videoRef.current;
        video.srcObject = stream;
        try {
          await video.play();
        } catch (cause) {
          const detail = cause instanceof Error ? ` ${cause.message}` : "";
          const error = new Error(`The camera stream opened, but video playback could not start.${detail}`);
          error.name = "PlaybackError";
          throw error;
        }
        await waitForVideoData(video);
      }

      if (requestId !== requestIdRef.current) {
        stream.getTracks().forEach((track) => track.stop());
        return;
      }

      const videoTrack = stream.getVideoTracks()[0];
      videoTrack?.addEventListener("ended", () => {
        if (streamRef.current !== stream) return;
        stopStream();
        setStatus("error");
        setErr("The video device stopped sending data or was disconnected. Check the USB connection and selected camera.");
      }, { once: true });

      setStatus("playing");
    } catch (e: any) {
      if (requestId !== requestIdRef.current) return;
      setStatus(e?.name === "NotAllowedError" ? "denied" : "error");
      setErr(getCameraErrorMessage(e));
      stopStream();
    } finally {
      if (requestId === requestIdRef.current) openingRef.current = false;
    }
  };

  // Auto-start on enter
  useEffect(() => {
    openCamera();
    return () => {
      requestIdRef.current += 1;
      openingRef.current = false;
      stopStream();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    reverseCamSettings?.deviceSelectionMode?.value,
    reverseCamSettings?.deviceId?.value,
    reverseCamSettings?.deviceLabel?.value,
    reverseCamSettings?.videoWidth?.value,
    reverseCamSettings?.videoHeight?.value,
    reverseCamSettings?.videoFps?.value,
  ]);

  // Retry when the capture device connects/disconnects
  useEffect(() => {
    const h = async () => {
      if (status !== "opening" && status !== "denied") await openCamera();
    };
    if (!navigator?.mediaDevices?.addEventListener) return;
    navigator.mediaDevices.addEventListener("devicechange", h);
    return () => navigator.mediaDevices.removeEventListener("devicechange", h);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status]);

  return (
    <Container>
      <Video ref={videoRef} autoPlay playsInline muted />

      {/* Overlay PNG transparente */}
      <OverlayImg
        src="/assets/svg/graphics/guidelines.svg"
        alt="Rear camera guidelines"
      />

      {/* Bottom text */}
      <Caption style= {{position:'absolute', bottom:'0', left:'0', right:'0', textAlign:'center', zIndex: 5}}>{overlayText}</Caption>

      {/* Error messages */}
      {status === "error" && <CenterMsg>Error: {err}</CenterMsg>}
      {status === "denied" && (
        <CenterMsg>{err}</CenterMsg>
      )}
    </Container>
  );
}
