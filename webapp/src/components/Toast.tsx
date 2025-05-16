import React, { useEffect } from 'react';
import './Toast.css';

interface ToastProps {
  message: string;
  duration?: number;
  onDismiss: () => void;
}

const Toast: React.FC<ToastProps> = ({ message, duration = 1000, onDismiss }) => {
  useEffect(() => {
    const timer = setTimeout(() => {
      onDismiss();
    }, duration);

    return () => clearTimeout(timer);
  }, [duration, onDismiss]);

  return (
    <div className="toast">
      {message}
    </div>
  );
};

export default Toast; 