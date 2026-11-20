import { useEffect, useRef, useState } from 'react';
import { Info } from 'lucide-react';

interface Props {
  title?: string;
  text: string;
  align?: 'left' | 'center' | 'right';
  direction?: 'top' | 'bottom';
}

export function InfoTip({ title, text, align = 'center', direction = 'top' }: Props) {
  const [open, setOpen] = useState(false);
  const [pinned, setPinned] = useState(false);
  const ref = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (!pinned) return;
    function handleOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setPinned(false);
        setOpen(false);
      }
    }
    document.addEventListener('mousedown', handleOutside);
    return () => document.removeEventListener('mousedown', handleOutside);
  }, [pinned]);

  return (
    <span
      ref={ref}
      className="infotip-wrap"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => {
        if (!pinned) setOpen(false);
      }}
    >
      <button
        type="button"
        className={`infotip-btn ${open ? 'active' : ''}`}
        aria-label={title ? `Explain ${title}` : 'More information'}
        aria-expanded={open}
        onClick={(e) => {
          e.stopPropagation();
          const next = !pinned;
          setPinned(next);
          setOpen(next);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => {
          if (!pinned) setOpen(false);
        }}
      >
        <Info size={13} strokeWidth={2.2} />
      </button>
      {open && (
        <span className={`infotip-pop align-${align} dir-${direction}`} role="tooltip">
          {title && <span className="infotip-title">{title}</span>}
          <span className="infotip-text">{text}</span>
        </span>
      )}
    </span>
  );
}
