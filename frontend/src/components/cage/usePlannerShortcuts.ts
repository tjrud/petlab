import { useEffect, type Dispatch, type SetStateAction } from "react";

import { round1 } from "@/lib/cageLayout";
import type { HistAction } from "@/lib/cagePlannerDoc";
import type { LayoutItem } from "@/lib/types";

function isTyping(t: EventTarget | null): boolean {
  const el = t as HTMLElement | null;
  if (!el) return false;
  return el.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName);
}

/** 가상 케이지 단축키: Ctrl+Z / Ctrl+Shift+Z·Ctrl+Y 되돌리기·다시 하기, 선택한 구조물은 Ctrl+D 복제,
 *  방향키 1cm(Shift 1mm), Delete·Backspace 삭제, R 90°(Shift 반대로), Q/E 15°, Esc 선택 해제. 입력 칸에서는 쓰지 않아요 */
export function usePlannerShortcuts({
  selectedId,
  dispatch,
  setSelectedId,
  duplicateItem,
  removeItem,
  rotateItem,
  updateItem,
}: {
  selectedId: string | null;
  dispatch: Dispatch<HistAction>;
  setSelectedId: Dispatch<SetStateAction<string | null>>;
  duplicateItem: (id: string) => void;
  removeItem: (id: string) => void;
  rotateItem: (id: string, deg: number, absolute?: boolean) => void;
  updateItem: (id: string, fn: (it: LayoutItem) => LayoutItem) => void;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (isTyping(e.target)) return;
      const mod = e.ctrlKey || e.metaKey;
      if (mod && e.key.toLowerCase() === "z") {
        e.preventDefault();
        dispatch({ type: e.shiftKey ? "redo" : "undo" });
        return;
      }
      if (mod && e.key.toLowerCase() === "y") {
        e.preventDefault();
        dispatch({ type: "redo" });
        return;
      }
      if (!selectedId) return;
      if (mod && e.key.toLowerCase() === "d") {
        e.preventDefault();
        duplicateItem(selectedId);
        return;
      }
      if (mod || e.altKey) return;
      const step = e.shiftKey ? 1 : 10;
      const moves: Record<string, [number, number]> = {
        ArrowLeft: [-step, 0],
        ArrowRight: [step, 0],
        ArrowUp: [0, step], // 화면 위쪽 = 케이지 안쪽(뒤)
        ArrowDown: [0, -step],
      };
      if (e.key in moves) {
        e.preventDefault();
        const [dx, dy] = moves[e.key];
        updateItem(selectedId, (it) => ({ ...it, x_mm: round1(it.x_mm + dx), y_mm: round1(it.y_mm + dy) }));
      } else if (e.key === "Delete" || e.key === "Backspace") {
        e.preventDefault();
        removeItem(selectedId);
      } else if (e.key === "r" || e.key === "R") {
        rotateItem(selectedId, e.shiftKey ? -90 : 90);
      } else if (e.key === "q" || e.key === "Q") {
        rotateItem(selectedId, 15);
      } else if (e.key === "e" || e.key === "E") {
        rotateItem(selectedId, -15);
      } else if (e.key === "Escape") {
        setSelectedId(null);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [selectedId, dispatch, setSelectedId, duplicateItem, removeItem, rotateItem, updateItem]);
}
