import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Info } from 'lucide-react';

interface Props {
  title?: string;
  text: string;
  align?: 'left' | 'center' | 'right';
  direction?: 'top' | 'bottom';
}

interface PopCoords {
  top: number;
  left: number;
  arrowLeft: number;
  placement: 'top' | 'bottom';
}

const VIEWPORT_PAD = 12;
const GAP = 10;

export function InfoTip({ title, text }: Props) {
  const [open, setOpen] = useState(false);
  const [pinned, setPinned] = useState(false);
  const [coords, setCoords] = useState<PopCoords | null>(null);
  const btnRef = useRef<HTMLButtonElement>(null);
  const popRef = useRef<HTMLDivElement>(null);
  const closeTimerRef = useRef<number | null>(null);

  const clearCloseTimer = useCallback(() => {
    if (closeTimerRef.current !== null) {
      window.clearTimeout(closeTimerRef.current);
      closeTimerRef.current = null;
    }
  }, []);

  const scheduleClose = useCallback(() => {
    if (pinned) return;
    clearCloseTimer();
    closeTimerRef.current = window.setTimeout(() => {
      setOpen(false);
    }, 120);
  }, [pinned, clearCloseTimer]);

  const computePosition = useCallback(() => {
    const btn = btnRef.current;
    const pop = popRef.current;
    if (!btn || !pop) return;

    const br = btn.getBoundingClientRect();
    const pr = pop.getBoundingClientRect();
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const popW = Math.min(pr.width || 310, vw - VIEWPORT_PAD * 2);
    const popH = pr.height || 100;

    const btnCenterX = br.left + br.width / 2;
    let left = btnCenterX - popW / 2;
    left = Math.max(VIEWPORT_PAD, Math.min(left, vw - popW - VIEWPORT_PAD));

    const spaceAbove = br.top - VIEWPORT_PAD;
    const spaceBelow = vh - br.bottom - VIEWPORT_PAD;

    let placement: 'top' | 'bottom' = 'top';
    let top: number;
    if (spaceAbove >= popH + GAP || spaceAbove >= spaceBelow) {
      placement = 'top';
      top = Math.max(VIEWPORT_PAD, br.top - popH - GAP);
    } else {
      placement = 'bottom';
      top = Math.min(vh - popH - VIEWPORT_PAD, br.bottom + GAP);
    }

    const arrowLeft = Math.max(14, Math.min(popW - 14, btnCenterX - left));
    setCoords({ top, left, arrowLeft, placement });
  }, []);

  useLayoutEffect(() => {
    if (!open) {
      setCoords(null);
      return;
    }
    computePosition();
    const raf = window.requestAnimationFrame(computePosition);
    window.addEventListener('scroll', computePosition, true);
    window.addEventListener('resize', computePosition);
    return () => {
      window.cancelAnimationFrame(raf);
      window.removeEventListener('scroll', computePosition, true);
      window.removeEventListener('resize', computePosition);
    };
  }, [open, computePosition]);

  useEffect(() => {
    if (!pinned && !open) return;
    function handleOutside(e: MouseEvent) {
      const target = e.target as Node;
      if (
        btnRef.current &&
        !btnRef.current.contains(target) &&
        popRef.current &&
        !popRef.current.contains(target)
      ) {
        setPinned(false);
        setOpen(false);
      }
    }
    function handleKey(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        setPinned(false);
        setOpen(false);
      }
    }
    document.addEventListener('mousedown', handleOutside);
    document.addEventListener('keydown', handleKey);
    return () => {
      document.removeEventListener('mousedown', handleOutside);
      document.removeEventListener('keydown', handleKey);
    };
  }, [pinned, open]);

  useEffect(() => () => clearCloseTimer(), [clearCloseTimer]);

  return (
    <span className="infotip-wrap">
      <button
        ref={btnRef}
        type="button"
        className={`infotip-btn ${open ? 'active' : ''}`}
        aria-label={title ? `Explain ${title}` : 'More information'}
        aria-expanded={open}
        onMouseEnter={() => {
          clearCloseTimer();
          setOpen(true);
        }}
        onMouseLeave={scheduleClose}
        onClick={(e) => {
          e.stopPropagation();
          clearCloseTimer();
          const next = !pinned;
          setPinned(next);
          setOpen(next);
        }}
        onFocus={() => {
          clearCloseTimer();
          setOpen(true);
        }}
        onBlur={scheduleClose}
      >
        <Info size={13.5} strokeWidth={2.1} />
      </button>

      {open &&
        createPortal(
          <div
            ref={popRef}
            role="tooltip"
            className={`infotip-portal ${coords ? 'ready' : ''} place-${coords?.placement ?? 'top'}`}
            style={
              coords
                ? { top: `${coords.top}px`, left: `${coords.left}px` }
                : { top: '-9999px', left: '-9999px' }
            }
            onMouseEnter={clearCloseTimer}
            onMouseLeave={scheduleClose}
            onClick={(e) => e.stopPropagation()}
          >
            {coords && (
              <span
                className={`infotip-arrow place-${coords.placement}`}
                style={{ left: `${coords.arrowLeft}px` }}
              />
            )}
            {title && <div className="infotip-title">{title}</div>}
            <div className="infotip-text">{text}</div>
          </div>,
          document.body,
        )}
    </span>
  );
}
