import React, { useEffect, useState } from 'react';
import ReactDOM from 'react-dom';
import styled from 'styled-components';
import { Typography } from '../../theme/styles/Typography';
import { Button } from '../../theme/styles/Inputs';

const Overlay = styled.div`
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background-color: rgba(0, 0, 0, 0.5);
  backdrop-filter: blur(10px);
  display: flex;
  justify-content: center;
  align-items: center;
  z-index: 4;

  opacity: ${({ $visible }) => ($visible ? 1 : 0)};
  transition: opacity 0.3s ease-in-out;
`;

const Content = styled.div`
  background: #151515;
  padding: 20px;
  border-radius: 10px;
  text-align: center;
  color: none;
  white-space: pre-line;

  min-width: 300px;

  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;

  opacity: ${({ $visible }) => ($visible ? 1 : 0)};
  transform: ${({ $visible }) => ($visible ? 'scale(1)' : 'scale(0.9)')};
  transition: opacity 0.3s ease-in-out, transform 0.3s ease-in-out;
`;

const Exit = styled.button`
  position: absolute;
  top: -30px;
  right: -30px;
  border: none;
  border-radius: 25px;
  width: 25px;
  height: 25px;
  background: #151515;
  font-size: 10px;
  font-weight: bold;
  cursor: pointer;
  color: #DBDBDB;
`;

const Modal = ({ isOpen, onClose, title, content, exit }) => {
  const Body1 = Typography.Body1;
  const Display2 = Typography.Display2;
  const [visible, setVisible] = useState(false);
  const [shouldRender, setShouldRender] = useState(isOpen);

  useEffect(() => {
    if (isOpen) {
      setShouldRender(true);
      setTimeout(() => setVisible(true), 100); // Ensure transition triggers
    } else {
      setVisible(false);
      setTimeout(() => setShouldRender(false), 300); // Delay unmounting until fade-out finishes
    }
  }, [isOpen, shouldRender]);

  if (!shouldRender) return null; // Prevent render when modal is fully closed

  return ReactDOM.createPortal(
    <Overlay $visible={visible}>
      <Content $visible={visible}>
        <Display2>{title}</Display2>
        {content}
        {exit ? 
        <Exit onClick={onClose}>X</Exit>
        : null }
      </Content>
    </Overlay>,
    document.getElementById('root')
  );
};

export default Modal;
