import { ReactNode, useEffect } from 'react';
import { motion } from 'motion/react';

interface ModalProps {
  title: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  width?: string;
}

export default function Modal({ title, onClose, children, footer, width = 'max-w-lg' }: ModalProps) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-100 flex items-center justify-center p-4">
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={onClose}
        className="absolute inset-0 bg-gray-900/30"
      />
      <motion.div
        initial={{ opacity: 0, scale: 0.97, y: 8 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.97, y: 8 }}
        transition={{ duration: 0.15 }}
        className={`relative z-10 w-full ${width} rounded-xl bg-white shadow-xl flex flex-col max-h-[88vh]`}
      >
        <div className="px-6 pt-5 pb-3">
          <h2 className="text-[15px] font-semibold text-ink">{title}</h2>
        </div>

        <div className="px-6 pb-4 overflow-y-auto">{children}</div>

        {footer && (
          <div className="px-6 py-4 flex items-center justify-end gap-3 border-t border-line-soft">
            {footer}
          </div>
        )}
      </motion.div>
    </div>
  );
}

export function ModalRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[110px_1fr] items-start gap-3 py-2">
      <span className="text-[13px] text-muted pt-1.5">{label}</span>
      <div className="text-[13px] text-body">{children}</div>
    </div>
  );
}
