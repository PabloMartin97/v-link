import React, { useEffect, useRef, useState } from "react";
import styled, { useTheme } from 'styled-components';
import { useNamespaces } from "../../../socket/Namespaces";
import { Typography } from "../../../theme/styles/Typography";

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
  const socket = useNamespaces();

  const Caption = Typography.Subtitle;
  const theme = useTheme();

  const [status, setStatus] =
    useState<"idle" | "opening" | "playing" | "error" | "denied">("idle");
  const [err, setErr] = useState("");

  // Encender GPIO al entrar y apagar al salir
  useEffect(() => {
    socket.cam.emit('mount');
    return () => {
      socket.cam.emit('unmount');
    };
  }, []);

  // Texto inferior configurable
  const overlayText = "CHECK SURROUNDINGS";

  const stopStream = () => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    if (videoRef.current) videoRef.current.srcObject = null;
  };

  const openDefaultCamera = async () => {
    setStatus("opening"); setErr("");
    try {
      stopStream();
      const stream = await navigator.mediaDevices.getUserMedia({
        video: true,
        audio: false,
      });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play().catch(() => {});
      }
      setStatus("playing");
    } catch (e: any) {
      setStatus(e?.name === "NotAllowedError" ? "denied" : "error");
      setErr(e?.message || "Failed to open camera");
    }
  };

  // Auto-inicio al entrar
  useEffect(() => {
    openDefaultCamera();
    return () => { stopStream(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Reintento si se conecta/desconecta el grabber
  useEffect(() => {
    const h = async () => {
      if (status === "playing") {
        await openDefaultCamera();
      }
    };
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

      {/* Texto inferior */}
      <Caption style= {{position:'absolute', bottom:'0', left:'0', right:'0', textAlign:'center', zIndex: 5}}>{overlayText}</Caption>

      {/* Mensajes de error */}
      {status === "error" && <CenterMsg>Error: {err}</CenterMsg>}
      {status === "denied" && (
        <CenterMsg>Camera access denied. Check browser permissions.</CenterMsg>
      )}
    </Container>
  );
}
